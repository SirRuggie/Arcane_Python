import aiohttp
import asyncio
import lightbulb
import hikari
from datetime import datetime
import json
import os

from hikari.impl import (
    MessageActionRowBuilder as ActionRow,
    InteractiveButtonBuilder as Button,
    LinkButtonBuilder as LinkButton,
    ContainerComponentBuilder as Container,
    SectionComponentBuilder as Section,
    TextDisplayComponentBuilder as Text,
    SeparatorComponentBuilder as Separator,
    MediaGalleryComponentBuilder as Media,
    MediaGalleryItemBuilder as MediaItem,
)

from extensions.components import register_action
from utils.mongo import MongoClient
from utils.constants import DARK_MAGENTA_ACCENT, GREEN_ACCENT
from utils.emoji import emojis

loader = lightbulb.Loader()

# DEBUG CONFIGURATION - Change this to False for production
DEBUG_MODE = os.getenv("BAND_DEBUG", "True").lower() == "true"  # Default to True for debugging


def debug_print(*args, **kwargs):
    """Only print if DEBUG_MODE is enabled"""
    if DEBUG_MODE:
        print(*args, **kwargs)


# BAND API Configuration
BAND_API_BASE = "https://openapi.band.us/v2/band/posts"
BAND_ACCESS_TOKEN = "ZQAAAR-9LGjvTxYmwok2WaTSYvcrA8M84ZK3s5BQSxxmggdJkyIFUUT4KCFvH1QNz2I3syNF_2aKaPLtownMSAVAC7pprIKu1TD_600hDD8GjhvX"
BAND_KEY = "AADMPvOeSi6era-iwqaVkEtP"

# Discord channel to send notifications
NOTIFICATION_CHANNEL_ID = 1078702146180104233
ALLOWED_ROLE_ID = 1088914884999249940

# Global variables
band_check_task = None
bot_instance = None  # Store bot reference for sending messages
mongo_client = None  # Store mongo reference


async def fetch_band_posts():
    """Fetch posts from BAND API with enhanced error handling"""
    params = {
        "access_token": BAND_ACCESS_TOKEN,
        "band_key": BAND_KEY,
        "locale": "en_US"
    }

    async with aiohttp.ClientSession() as session:
        try:
            debug_print(f"[BAND API] Making request to: {BAND_API_BASE}")
            debug_print(f"[BAND API] With params: band_key={BAND_KEY[:10]}..., locale=en_US")

            async with session.get(BAND_API_BASE, params=params) as response:
                debug_print(f"[BAND API] Response Status: {response.status}")
                debug_print(f"[BAND API] Response Headers: {dict(response.headers)}")

                # Get response text first
                text = await response.text()
                debug_print(f"[BAND API] Raw Response (first 500 chars): {text[:500]}")

                if response.status == 200:
                    try:
                        data = json.loads(text)

                        # Log the entire response structure
                        debug_print(f"[BAND API] Full Response Structure:")
                        debug_print(json.dumps(data, indent=2)[:1000])  # First 1000 chars

                        # Check for result_code
                        if "result_code" in data:
                            debug_print(f"[BAND API] result_code: {data['result_code']}")
                            if "result_msg" in data:
                                debug_print(f"[BAND API] result_msg: {data['result_msg']}")

                        return data
                    except json.JSONDecodeError as e:
                        debug_print(f"[BAND API] JSON Decode Error: {e}")
                        debug_print(f"[BAND API] Response was not valid JSON: {text[:200]}")
                        return None
                else:
                    debug_print(f"[BAND API] Non-200 Status: {response.status}")
                    debug_print(f"[BAND API] Error Response: {text}")
                    return None

        except aiohttp.ClientError as e:
            debug_print(f"[BAND API] Client Error: {type(e).__name__}: {e}")
            return None
        except Exception as e:
            debug_print(f"[BAND API] Unexpected Exception: {type(e).__name__}: {e}")
            import traceback
            debug_print(f"[BAND API] Traceback: {traceback.format_exc()}")
            return None


async def send_war_sync_to_discord(post):
    """Send a War Sync reminder to Discord channel using Components V2"""
    global bot_instance

    if not bot_instance:
        debug_print("[BAND Monitor] Bot instance not available!")
        return

    # Extract post details
    author = post.get('author', {})
    author_name = author.get('name', 'FWA Clan Rep')
    content = post.get('content', '')

    # Create message ID for tracking responses
    message_id = str(datetime.now().timestamp())

    # Create components using V2 style
    components = [
        Container(
            accent_color=DARK_MAGENTA_ACCENT,
            components=[
                Text(content="## ⚔️ War Sync Event has been posted."),
                Text(content=f"<@&{ALLOWED_ROLE_ID}> - A new FWA War Sync has been scheduled!"),
                Separator(divider=True),
                ActionRow(
                    components=[
                        LinkButton(
                            url="https://www.band.us/band/57375315",
                            label="Check FWA Sync Time",
                            emoji="🕐"
                        )
                    ]
                ),
                Text(content=(
                    "Please review the **FWA Sync Time** and confirm your availability by selecting the "
                    "corresponding button below:"
                )),
                Separator(divider=True),
                Text(content=f"{str(emojis.confirm)} - If you are available to start."),
                Text(content=f"{str(emojis.maybe)} - If you may be available to start."),
                Text(content=f"{str(emojis.cancel)} - If you are unavailable to start."),
                Separator(divider=True),
                Text(content=(
                    "*Please note that if your availability changes, you can update your response by "
                    "selecting the appropriate button.*"
                )),
                Separator(divider=True),
                Text(content="## Rep Availability"),
                Text(content="*No responses yet...*"),
                ActionRow(
                    components=[
                        Button(
                            style=hikari.ButtonStyle.SUCCESS,
                            label="Yes",
                            emoji=emojis.confirm.partial_emoji,
                            custom_id=f"war_response:yes_{message_id}"
                        ),
                        Button(
                            style=hikari.ButtonStyle.SECONDARY,
                            label="Maybe",
                            emoji=emojis.maybe.partial_emoji,
                            custom_id=f"war_response:maybe_{message_id}"
                        ),
                        Button(
                            style=hikari.ButtonStyle.DANGER,
                            label="No",
                            emoji=emojis.cancel.partial_emoji,
                            custom_id=f"war_response:no_{message_id}"
                        ),
                    ]
                ),
            ]
        )
    ]

    try:
        # Send the message
        message = await bot_instance.rest.create_message(
            channel=NOTIFICATION_CHANNEL_ID,
            components=components,
            user_mentions=True,
            role_mentions=[ALLOWED_ROLE_ID]
        )

        debug_print(f"[BAND Monitor] Sent War Sync reminder to Discord")
    except Exception as e:
        debug_print(f"[BAND Monitor] Failed to send Discord message: {e}")


@register_action("war_response", no_return=True)
@lightbulb.di.with_di
async def on_war_response(
        action_id: str,
        bot: hikari.GatewayBot = lightbulb.di.INJECTED,
        mongo: MongoClient = lightbulb.di.INJECTED,
        **kwargs
):
    """Handle war sync response buttons"""
    ctx: lightbulb.components.MenuContext = kwargs["ctx"]
    response_type, message_id = action_id.split("_", 1)

    # Check if user has the required role
    member = ctx.member
    if not any(role == ALLOWED_ROLE_ID for role in member.role_ids):
        await ctx.respond(
            "❌ You don't have permission to respond to War Sync events.",
            ephemeral=True
        )
        return

    # Get stored data from fwa_band_data collection
    stored_data = await mongo.fwa_band_data.find_one({"_id": message_id})
    if not stored_data:
        stored_data = {"_id": message_id, "responses": {}}
        await mongo.fwa_band_data.insert_one(stored_data)

    # Update user's response
    user_id = str(ctx.user.id)
    old_response = stored_data["responses"].get(user_id)
    stored_data["responses"][user_id] = response_type

    # Save to mongo
    await mongo.fwa_band_data.update_one(
        {"_id": message_id},
        {"$set": {"responses": stored_data["responses"]}}
    )

    # Build response lists
    yes_users = []
    maybe_users = []
    no_users = []

    for uid, resp in stored_data["responses"].items():
        mention = f"<@{uid}>"
        if resp == "yes":
            yes_users.append(mention)
        elif resp == "maybe":
            maybe_users.append(mention)
        elif resp == "no":
            no_users.append(mention)

    # Build response text
    response_lines = []
    if yes_users:
        for user in yes_users:
            response_lines.append(f"{str(emojis.confirm)} **Available** - {user}")
    if maybe_users:
        for user in maybe_users:
            response_lines.append(f"{str(emojis.maybe)} **Maybe** - {user}")
    if no_users:
        for user in no_users:
            response_lines.append(f"{str(emojis.cancel)} **Unavailable** - {user}")

    if not response_lines:
        response_lines.append("*No responses yet...*")

    # Update the message with new responses
    components = [
        Container(
            accent_color=DARK_MAGENTA_ACCENT,
            components=[
                Text(content="## ⚔️ War Sync Event has been posted."),
                Text(content=f"<@&{ALLOWED_ROLE_ID}> - A new FWA War Sync has been scheduled!"),
                Separator(divider=True),
                ActionRow(
                    components=[
                        LinkButton(
                            url="https://www.band.us/band/57375315",
                            label="Check FWA Sync Time",
                            emoji="🕐"
                        )
                    ]
                ),
                Text(content=(
                    "Please review the **FWA Sync Time** and confirm your availability by selecting the "
                    "corresponding button below:"
                )),
                Separator(divider=True),
                Text(content=f"{str(emojis.confirm)} - If you are available to start."),
                Text(content=f"{str(emojis.maybe)} - If you may be available to start."),
                Text(content=f"{str(emojis.cancel)} - If you are unavailable to start."),
                Separator(divider=True),
                Text(content=(
                    "*Please note that if your availability changes, you can update your response by "
                    "selecting the appropriate button.*"
                )),
                Separator(divider=True),
                Text(content="## Rep Availability"),
                Text(content="\n".join(response_lines)),
                ActionRow(
                    components=[
                        Button(
                            style=hikari.ButtonStyle.SUCCESS,
                            label="Yes",
                            emoji=emojis.confirm.partial_emoji,
                            custom_id=f"war_response:yes_{message_id}"
                        ),
                        Button(
                            style=hikari.ButtonStyle.SECONDARY,
                            label="Maybe",
                            emoji=emojis.maybe.partial_emoji,
                            custom_id=f"war_response:maybe_{message_id}"
                        ),
                        Button(
                            style=hikari.ButtonStyle.DANGER,
                            label="No",
                            emoji=emojis.cancel.partial_emoji,
                            custom_id=f"war_response:no_{message_id}"
                        ),
                    ]
                ),
            ]
        )
    ]

    # Update the message
    await ctx.interaction.edit_initial_response(components=components)


async def band_checker_loop(mongo: MongoClient):
    """Main loop that checks BAND API every 30 seconds"""
    debug_print("[BAND Monitor] Starting BAND API monitoring task...")

    # Log initial configuration
    debug_print(f"[BAND Monitor] Configuration:")
    debug_print(f"  - API Base: {BAND_API_BASE}")
    debug_print(f"  - Band Key: {BAND_KEY[:10]}... (truncated)")
    debug_print(f"  - Access Token: {BAND_ACCESS_TOKEN[:20]}... (truncated)")
    debug_print(f"  - Notification Channel: {NOTIFICATION_CHANNEL_ID}")
    debug_print(f"  - Allowed Role: {ALLOWED_ROLE_ID}")

    while True:
        try:
            debug_print(f"\n{'=' * 60}")
            debug_print(f"[BAND Monitor] Checking at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

            # Fetch posts from BAND API
            data = await fetch_band_posts()

            if data is None:
                debug_print("[BAND Monitor] fetch_band_posts returned None")
            elif "result_code" in data:
                result_code = data.get("result_code")
                result_msg = data.get("result_msg", "No message provided")

                debug_print(f"[BAND Monitor] API Response - Code: {result_code}, Message: {result_msg}")

                if result_code == 1:
                    posts = data.get("result_data", {}).get("items", [])

                    debug_print(f"[BAND Monitor] Found {len(posts)} posts")

                    if posts:
                        # Get the most recent post (assuming first post is newest)
                        latest_post = posts[0]
                        latest_post_key = latest_post.get('post_key')
                        latest_content = latest_post.get('content', '')

                        debug_print(f"[BAND Monitor] Latest post key: {latest_post_key}")
                        debug_print(f"[BAND Monitor] Latest post content preview: {latest_content[:100]}...")

                        if latest_post_key:
                            # Get the last processed post from MongoDB
                            last_processed_doc = await mongo.fwa_band_data.find_one({"_id": "last_processed_post"})
                            last_processed_key = last_processed_doc.get("post_key") if last_processed_doc else None

                            debug_print(f"[BAND Monitor] Last processed post key: {last_processed_key}")

                            # Only process if this is a NEW most recent post
                            if latest_post_key != last_processed_key:
                                debug_print(f"[BAND Monitor] New latest post detected!")

                                # Check if this new post contains war sync text
                                if "PLEASE stop searching when the window closes after 1.5 hours" in latest_content:
                                    debug_print("[BAND Monitor] New post contains War Sync reminder!")
                                    await send_war_sync_to_discord(latest_post)
                                else:
                                    debug_print("[BAND Monitor] New post doesn't contain War Sync text.")

                                # Update the last processed post in MongoDB
                                await mongo.fwa_band_data.update_one(
                                    {"_id": "last_processed_post"},
                                    {"$set": {
                                        "post_key": latest_post_key,
                                        "content": latest_content,
                                        "processed_at": datetime.now().isoformat()
                                    }},
                                    upsert=True
                                )
                                debug_print(f"[BAND Monitor] Updated last processed post to: {latest_post_key}")
                            else:
                                debug_print("[BAND Monitor] No new posts since last check.")
                        else:
                            debug_print("[BAND Monitor] Latest post has no post_key")
                    else:
                        debug_print("[BAND Monitor] No posts found in API response")
                else:
                    debug_print(f"[BAND Monitor] API returned error code {result_code}: {result_msg}")

                    # Common BAND API error codes
                    if result_code == -101:
                        debug_print("[BAND Monitor] ERROR: Invalid access token! Token may be expired.")
                    elif result_code == -102:
                        debug_print("[BAND Monitor] ERROR: Invalid band key!")
                    elif result_code == -103:
                        debug_print("[BAND Monitor] ERROR: No permission to access this band!")
            else:
                debug_print("[BAND Monitor] Unexpected API response format - no result_code field")
                debug_print(f"[BAND Monitor] Response keys: {list(data.keys())}")

        except Exception as e:
            debug_print(f"[BAND Monitor] Error in loop: {type(e).__name__}: {e}")
            import traceback
            debug_print(f"[BAND Monitor] Traceback: {traceback.format_exc()}")

        # Wait 300 seconds before next check
        debug_print(f"\n[BAND Monitor] Waiting 300 seconds until next check...")
        debug_print(f"{'=' * 60}")
        await asyncio.sleep(300)


@loader.listener(hikari.StartedEvent)
@lightbulb.di.with_di
async def on_bot_started(
        event: hikari.StartedEvent,
        mongo: MongoClient = lightbulb.di.INJECTED
) -> None:
    """Start the BAND monitor task when bot starts"""
    global band_check_task, bot_instance, mongo_client

    # Store bot instance for sending messages
    bot_instance = event.app
    mongo_client = mongo

    # Create the task with mongo passed in
    band_check_task = asyncio.create_task(band_checker_loop(mongo))
    debug_print("[BAND Monitor] Background task started!")


@loader.listener(hikari.StoppingEvent)
async def on_bot_stopping(event: hikari.StoppingEvent) -> None:
    """Cancel the task when bot is stopping"""
    global band_check_task

    if band_check_task and not band_check_task.done():
        band_check_task.cancel()
        try:
            await band_check_task
        except asyncio.CancelledError:
            pass
        debug_print("[BAND Monitor] Background task cancelled!")


@loader.command
class ToggleDebug(
    lightbulb.SlashCommand,
    name="toggle-debug",
    description="Toggle debug mode for BAND monitor",
    default_member_permissions=hikari.Permissions.ADMINISTRATOR
):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        global DEBUG_MODE
        DEBUG_MODE = not DEBUG_MODE
        status = "ON" if DEBUG_MODE else "OFF"
        await ctx.respond(f"🔧 BAND Monitor debug mode: **{status}**", ephemeral=True)
        debug_print(f"[DEBUG] Debug mode toggled to: {status} by {ctx.user.username}")


# Check if test commands are enabled
ENABLE_TEST_COMMANDS = os.getenv("ENABLE_TEST_COMMANDS", "false").lower() == "true"

if ENABLE_TEST_COMMANDS:
    @loader.command
    class TestWarSync(
        lightbulb.SlashCommand,
        name="test-war-sync",
        description="Test the war sync notification with custom emojis",
        default_member_permissions=hikari.Permissions.ADMINISTRATOR
    ):
        @lightbulb.invoke
        async def invoke(self, ctx: lightbulb.Context) -> None:
            await ctx.respond("🚀 Sending test war sync notification...", ephemeral=True)
            
            # Create a dummy post for testing
            test_post = {
                'author': {
                    'name': 'Test FWA Rep'
                },
                'content': 'TEST WAR SYNC - This is a test notification to verify custom emojis are working correctly.',
                'post_key': 'test_' + str(datetime.now().timestamp())
            }
            
            try:
                # Call the send function directly
                await send_war_sync_to_discord(test_post)
                await ctx.edit_last_response(
                    f"✅ **Test war sync sent!**\n"
                    f"Check <#{NOTIFICATION_CHANNEL_ID}> to see the notification and test the buttons."
                )
            except Exception as e:
                await ctx.edit_last_response(
                    f"❌ **Failed to send test notification!**\n"
                    f"Error: {str(e)}"
                )