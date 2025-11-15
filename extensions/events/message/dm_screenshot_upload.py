# events/message/dm_screenshot_upload.py

"""Event listener for DM recruitment screenshot uploads"""

import hikari
import lightbulb
from datetime import datetime
from typing import Optional

# Import components for processing message
from hikari.impl import (
    ContainerComponentBuilder as Container,
    TextDisplayComponentBuilder as Text,
    MediaGalleryComponentBuilder as Media,
    MediaGalleryItemBuilder as MediaItem,
    SeparatorComponentBuilder as Separator
)
from utils.constants import BLUE_ACCENT, DARK_MAGENTA_ACCENT


# Register this event with the bot
def load(bot: hikari.GatewayBot) -> None:
    bot.subscribe(hikari.GuildMessageCreateEvent, on_message_create)


def unload(bot: hikari.GatewayBot) -> None:
    bot.unsubscribe(hikari.GuildMessageCreateEvent, on_message_create)


async def on_message_create(event: hikari.GuildMessageCreateEvent) -> None:
    """Handle message creation events for screenshot uploads"""
    # Import here to avoid circular imports
    from extensions.commands.clan.report.dm_recruitment import (
        image_collection_sessions,
        dm_recruitment_data,
        show_dm_review_in_channel
    )
    from utils.cloudinary_client import CloudinaryClient
    from utils.mongo import MongoClient

    # Ignore bot messages
    if event.is_bot or not event.message.attachments:
        return

    # Check if this user has an active image collection session
    user_id = event.author_id

    # Find session by user ID
    session_key = None
    session_data = None

    for key, session in image_collection_sessions.items():
        # Convert both to int for comparison to handle type mismatches
        if int(session["user_id"]) == int(user_id) and session["channel_id"] == event.channel_id:
            session_key = key
            session_data = session
            break

    if not session_data:
        return

    # Check for image attachments
    image_attachment = None
    for attachment in event.message.attachments:
        if attachment.media_type and attachment.media_type.startswith("image/"):
            image_attachment = attachment
            break

    if not image_attachment:
        return

    # Process the screenshot - use event.app instead of event.app
    await process_screenshot_upload(
        event.app,  # This is the bot instance
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
    """Process the uploaded screenshot"""
    # Import here to avoid circular imports
    from extensions.commands.clan.report.dm_recruitment import (
        image_collection_sessions,
        dm_recruitment_data,
        show_dm_review_in_channel
    )
    from utils.cloudinary_client import CloudinaryClient
    from utils.mongo import MongoClient

    # Get injected dependencies from bot_data module
    from utils import bot_data

    cloudinary_client = bot_data.data.get("cloudinary_client")
    mongo = bot_data.data.get("mongo")

    if not cloudinary_client or not mongo:
        print("Error: Missing dependencies for screenshot processing")
        return

    try:
        # Download the image BEFORE deleting the message!
        # Method 1: Direct read
        image_data = None
        try:
            image_data = await attachment.read()
            print(f"Successfully downloaded image using direct read method")
        except Exception as e:
            print(f"Direct read failed: {e}")

            # Method 2: Using REST client
            try:
                async with bot.rest.http_session.get(attachment.url) as response:
                    if response.status == 200:
                        image_data = await response.read()
                        print(f"Successfully downloaded image using REST client")
                    else:
                        print(f"REST client failed with status: {response.status}")
            except Exception as e2:
                print(f"REST client method failed: {e2}")

        if not image_data:
            raise Exception("Failed to download image data")

        print(f"Image data size: {len(image_data)} bytes")

        # NOW delete the user's message after we have the image data
        await message.delete()

        # No need to update any existing message - we'll create a new one for the review

        # Upload to Cloudinary
        timestamp = int(datetime.now().timestamp())
        # Remove the # from clan tag for Cloudinary public_id
        clean_clan_tag = session_data['clan'].tag.replace('#', '')
        public_id = f"dm_recruitment_{clean_clan_tag}_{session_data['user_id']}_{timestamp}"

        result = await cloudinary_client.upload_image_from_bytes(
            image_data,
            folder="clan_recruitment/dm_screenshots",
            public_id=public_id
        )

        screenshot_url = result["secure_url"]

        # Store in dm_recruitment_data
        dm_recruitment_data[session_key] = {
            "discord_id": session_data["discord_id"],
            "context": session_data["context"],
            "screenshot_url": screenshot_url
        }

        # Clean up image collection session
        del image_collection_sessions[session_key]

        # Show review screen (this will edit the existing message)
        await show_dm_review_in_channel(
            bot,
            session_key,
            str(session_data['user_id']),
            message.channel_id,
            mongo
        )

    except Exception as e:
        print(f"Error processing screenshot: {e}")

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