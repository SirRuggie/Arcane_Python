# events/message/disboard_review_upload.py

"""Event listener for Disboard review screenshot uploads"""

import hikari
import lightbulb
from datetime import datetime
from typing import Optional

from hikari.impl import (
    ContainerComponentBuilder as Container,
    TextDisplayComponentBuilder as Text,
    MediaGalleryComponentBuilder as Media,
    MediaGalleryItemBuilder as MediaItem,
    SeparatorComponentBuilder as Separator
)
from utils.constants import BLUE_ACCENT, DARK_MAGENTA_ACCENT

loader = lightbulb.Loader()

# Global variables
mongo_client = None
bot_instance = None


@loader.listener(hikari.StartingEvent)
async def on_starting(event: hikari.StartingEvent):
    """Initialize global variables on bot startup"""
    global bot_instance
    bot_instance = event.app
    print("[Disboard Review Upload] Event listener initialized")


@loader.listener(hikari.GuildMessageCreateEvent)
@lightbulb.di.with_di
async def on_disboard_review_upload(
        event: hikari.GuildMessageCreateEvent,
        mongo = lightbulb.di.INJECTED,
        bot: hikari.GatewayBot = lightbulb.di.INJECTED
):
    """Listen for Disboard review screenshot uploads"""
    global mongo_client, bot_instance

    # Initialize if needed
    if not mongo_client:
        mongo_client = mongo
    if not bot_instance:
        bot_instance = bot

    # Ignore bot messages
    if event.is_bot or not event.message.attachments:
        return

    # Check if this user has an active image collection session
    user_id = event.author_id

    # Import here to avoid circular imports
    from extensions.commands.clan.report.disboard_review import (
        image_collection_sessions,
        disboard_review_data,
        show_disboard_review_in_channel
    )

    # Early exit if no active sessions - prevents log spam
    if not image_collection_sessions:
        return

    # Find session by user ID and channel
    session_key = None
    session_data = None

    print(f"[Disboard Review Upload] Looking for session with user_id={user_id} and channel_id={event.channel_id}")
    print(f"[Disboard Review Upload] Active sessions: {list(image_collection_sessions.keys())}")

    for key, session in image_collection_sessions.items():
        print(f"[Disboard Review Upload] Checking session {key}: user_id={session.get('user_id')}, channel_id={session.get('channel_id')}")

        # Convert both to int for comparison
        if int(session["user_id"]) == int(user_id) and session["channel_id"] == event.channel_id:
            session_key = key
            session_data = session
            print(f"[Disboard Review Upload] Found session for user {user_id}: key={key}")
            break

    if not session_data:
        return

    # Check for image attachments
    image_attachment = None
    for attachment in event.message.attachments:
        if attachment.media_type and attachment.media_type.startswith("image/"):
            image_attachment = attachment
            print(f"[Disboard Review Upload] Found image attachment: {attachment.filename}")
            break

    if not image_attachment:
        return

    # Process the screenshot
    await process_screenshot_upload(
        bot_instance,
        session_key,
        session_data,
        image_attachment,
        event.message
    )


async def process_screenshot_upload(
        bot: hikari.GatewayBot,
        session_key: str,
        session_data: dict,
        attachment: hikari.Attachment,
        message: hikari.Message
) -> None:
    """Process the uploaded Disboard review screenshot"""
    print(f"[Disboard Review Upload] Processing screenshot for session_key={session_key}")

    # Import here to avoid circular imports
    from extensions.commands.clan.report.disboard_review import (
        image_collection_sessions,
        disboard_review_data,
        show_disboard_review_in_channel
    )
    from utils.cloudinary_client import CloudinaryClient
    from utils.mongo import MongoClient

    # Get injected dependencies from bot_data module
    from utils import bot_data

    cloudinary_client = bot_data.data.get("cloudinary_client")
    mongo = bot_data.data.get("mongo")

    if not cloudinary_client or not mongo:
        print("[Disboard Review Upload] Error: Missing dependencies for screenshot processing")
        return

    try:
        # Download the image BEFORE deleting the message
        image_data = None
        try:
            image_data = await attachment.read()
            print(f"[Disboard Review Upload] Successfully downloaded image using direct read method")
        except Exception as e:
            print(f"[Disboard Review Upload] Direct read failed: {e}")

            # Fallback: Using REST client
            try:
                async with bot.rest.http_session.get(attachment.url) as response:
                    if response.status == 200:
                        image_data = await response.read()
                        print(f"[Disboard Review Upload] Successfully downloaded image using REST client")
                    else:
                        print(f"[Disboard Review Upload] REST client failed with status: {response.status}")
            except Exception as e2:
                print(f"[Disboard Review Upload] REST client method failed: {e2}")

        if not image_data:
            raise Exception("Failed to download image data")

        print(f"[Disboard Review Upload] Image data size: {len(image_data)} bytes")

        # Delete the user's message after we have the image data
        await message.delete()

        # Upload to Cloudinary
        timestamp = int(datetime.now().timestamp())
        clean_clan_tag = session_data['clan'].tag.replace('#', '')
        public_id = f"disboard_review_{clean_clan_tag}_{session_data['user_id']}_{timestamp}"

        result = await cloudinary_client.upload_image_from_bytes(
            image_data,
            folder="clan_recruitment/disboard_reviews",
            public_id=public_id
        )

        screenshot_url = result["secure_url"]

        # Store in disboard_review_data
        disboard_review_data[session_key] = {
            "screenshot_url": screenshot_url
        }

        # Clean up image collection session
        del image_collection_sessions[session_key]

        # Show review screen
        print(f"[Disboard Review Upload] Calling show_disboard_review_in_channel")
        await show_disboard_review_in_channel(
            bot,
            session_key,
            str(session_data['user_id']),
            message.channel_id,
            mongo
        )

    except Exception as e:
        print(f"[Disboard Review Upload] Error processing screenshot: {e}")

        # Create error message
        error_components = [
            Container(
                accent_color=DARK_MAGENTA_ACCENT,
                components=[
                    Text(content=f"❌ <@{session_data['user_id']}> Failed to process screenshot."),
                    Text(content=f"**Error:** {str(e)[:200]}"),
                    Text(content="Please try again or contact an administrator."),
                    Media(items=[MediaItem(media="assets/Red_Footer.png")])
                ]
            )
        ]

        await bot.rest.create_message(
            channel=message.channel_id,
            components=error_components
        )

        # Clean up session on error
        if session_key in image_collection_sessions:
            del image_collection_sessions[session_key]