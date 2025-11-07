# extensions/events/message/ticket_screenshot.py
"""
Ticket screenshot automation system.

Features:
- Monitors TEST ticket channels for screenshot uploads
- Sends reminders when users type without uploading screenshots
- Auto-deletes reminder messages after REMINDER_DELETE_TIMEOUT seconds
- Cooldown system to prevent spam (REMINDER_COOLDOWN_SECONDS)
- Triggers account collection flow after successful screenshot upload
"""

import asyncio
import aiohttp
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Set
import hikari
import lightbulb

from hikari.impl import (
    MessageActionRowBuilder as ActionRow,
    ContainerComponentBuilder as Container,
    InteractiveButtonBuilder as Button,
    TextDisplayComponentBuilder as Text,
    SeparatorComponentBuilder as Separator,
    MediaGalleryComponentBuilder as Media,
    MediaGalleryItemBuilder as MediaItem,
)

from utils.constants import RED_ACCENT, GREEN_ACCENT, BLUE_ACCENT
from utils.mongo import MongoClient
from utils.emoji import emojis
from extensions.events.message.ticket_account_collection import trigger_account_collection

# Configuration
PATTERNS = {
    "TEST": "𝕋𝔼𝕊𝕋",
    "CLAN": "ℂ𝕃𝔸ℕ",
    "FWA": "𝔽𝕎𝔸",
    "FWA_TEST": "𝕋-𝔽𝕎𝔸"
}
ACTIVE_PATTERNS = ["TEST", "FWA_TEST", "CLAN", "FWA"]
REMINDER_COOLDOWN_SECONDS = 10
SCREENSHOT_PROCESSING_DELAY = 1
REMINDER_DELETE_TIMEOUT = 15  # Seconds before reminder messages auto-delete
LOG_CHANNEL_ID = 1436169870273413169

# Global variables
mongo_client: Optional[MongoClient] = None
bot_instance: Optional[hikari.GatewayBot] = None
loader = lightbulb.Loader()

# Session storage
user_cooldowns: Dict[int, datetime] = {}
completed_screenshots: Set[str] = set()  # channel_id strings that have completed screenshots
deletion_tasks: Dict[int, asyncio.Task] = {}  # message_id -> deletion task mapping


async def is_image_url(url: str) -> bool:
    """Check if a URL points to an image"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.head(url, timeout=5) as response:
                content_type = response.headers.get('content-type', '')
                return content_type.startswith('image/')
    except:
        return False


async def send_screenshot_reminder(channel_id: int, user_id: int) -> Optional[hikari.Message]:
    """Send a reminder to upload screenshot"""
    try:
        reminder_components = [
            Container(
                accent_color=RED_ACCENT,
                components=[
                    Text(content=(
                        f"{emojis.Alert_Strobing} **Screenshot Required** {emojis.Alert_Strobing}\n\n"
                        "Please upload a screenshot of your base to continue with your application.\n\n"
                    )),
                    Text(content=f"\n-# This reminder will delete in {REMINDER_DELETE_TIMEOUT} seconds"),
                    Media(items=[MediaItem(media="assets/Red_Footer.png")])
                ]
            )
        ]

        message = await bot_instance.rest.create_message(
            channel=channel_id,
            components=reminder_components,
            user_mentions=[user_id]
        )

        # Schedule auto-deletion
        async def delete_reminder():
            await asyncio.sleep(REMINDER_DELETE_TIMEOUT)
            try:
                await bot_instance.rest.delete_message(channel_id, message.id)
                print(f"[Screenshot] Auto-deleted reminder message {message.id} after {REMINDER_DELETE_TIMEOUT}s")
                # Clean up from tracking dict
                if message.id in deletion_tasks:
                    del deletion_tasks[message.id]
            except hikari.NotFoundError:
                # Message already deleted
                pass
            except Exception as e:
                print(f"[Screenshot] Error deleting reminder: {e}")
            finally:
                # Clean up from tracking dict
                if message.id in deletion_tasks:
                    del deletion_tasks[message.id]

        # Create and store deletion task
        deletion_task = asyncio.create_task(delete_reminder())
        deletion_tasks[message.id] = deletion_task

        # Update MongoDB with reminder message ID
        await mongo_client.ticket_automation_state.update_one(
            {"_id": str(channel_id)},
            {
                "$set": {
                    "messages.screenshot_reminder": message.id,
                    "step_data.screenshot.reminder_sent": True,
                    "step_data.screenshot.last_reminder": datetime.now(timezone.utc)
                },
                "$inc": {
                    "step_data.screenshot.reminder_count": 1
                }
            }
        )

        return message
    except Exception as e:
        print(f"Error sending screenshot reminder: {e}")
        return None


async def handle_screenshot_upload(
        channel_id: int,
        user_id: int,
        message: hikari.Message,
        ticket_state: Dict
):
    """Handle when a screenshot is uploaded"""

    # Mark as completed in memory
    completed_screenshots.add(str(channel_id))

    # Update MongoDB state
    await mongo_client.ticket_automation_state.update_one(
        {"_id": str(channel_id)},
        {
            "$set": {
                "automation_state.current_step": "account_collection",
                "automation_state.current_step_index": 2,
                "step_data.screenshot.uploaded": True,
                "step_data.screenshot.uploaded_at": datetime.now(timezone.utc),
                "step_data.screenshot.message_id": message.id
            },
            "$addToSet": {
                "automation_state.completed_steps": "screenshot"
            },
            "$push": {
                "interaction_history": {
                    "timestamp": datetime.now(timezone.utc),
                    "action": "screenshot_uploaded",
                    "details": {
                        "message_id": message.id,
                        "has_attachments": len(message.attachments) > 0,
                        "has_embeds": len(message.embeds) > 0
                    }
                }
            }
        }
    )

    # Get reminder message ID
    reminder_msg_id = ticket_state.get("messages", {}).get("screenshot_reminder")

    # Wait a moment to prevent race conditions
    await asyncio.sleep(SCREENSHOT_PROCESSING_DELAY)

    # Show success message as a NEW message
    success_components = [
        Container(
            accent_color=GREEN_ACCENT,
            components=[
                Text(content=(
                    "✅ **Screenshot Uploaded Successfully!**\n\n"
                    "Thank you for providing your base screenshot."
                )),
                Media(items=[MediaItem(media="assets/Green_Footer.png")])
            ]
        )
    ]

    # Send NEW success message
    await bot_instance.rest.create_message(
        channel=channel_id,
        components=success_components
    )
    print(f"[Screenshot] Sent success message for screenshot upload")

    # Cancel auto-deletion of reminder if it exists
    if reminder_msg_id and reminder_msg_id in deletion_tasks:
        deletion_tasks[reminder_msg_id].cancel()
        del deletion_tasks[reminder_msg_id]
        print(f"[Screenshot] Cancelled auto-deletion for reminder message {reminder_msg_id}")

    # Wait to ensure user sees the success message
    await asyncio.sleep(3)

    # Trigger the account collection step with error handling
    try:
        print(f"[Screenshot] Attempting to trigger account collection for channel {channel_id}")

        # Check if trigger_account_collection is available
        if trigger_account_collection is None:
            print("[Screenshot] ERROR: trigger_account_collection is None!")
            # Try to import it dynamically
            try:
                from extensions.events.message.ticket_account_collection import trigger_account_collection as tac
                await tac(
                    channel_id=channel_id,
                    user_id=user_id,
                    ticket_info=ticket_state["ticket_info"]
                )
            except Exception as import_error:
                print(f"[Screenshot] ERROR importing trigger_account_collection: {import_error}")
                return
        else:
            await trigger_account_collection(
                channel_id=channel_id,
                user_id=user_id,
                ticket_info=ticket_state["ticket_info"]
            )

        print(f"[Screenshot] Successfully triggered account collection")

        # Log the progression
        log_components = [
            Container(
                accent_color=BLUE_ACCENT,
                components=[
                    Text(content=(
                        f"**Ticket Automation Progress**\n"
                        f"Channel: <#{channel_id}>\n"
                        f"User: <@{user_id}>\n"
                        f"Step: Screenshot ✓ → Account Collection"
                    )),
                    Media(items=[MediaItem(media="assets/Blue_Footer.png")])
                ]
            )
        ]

        log_channel = bot_instance.cache.get_guild_channel(LOG_CHANNEL_ID)
        if log_channel:
            await bot_instance.rest.create_message(
                channel=log_channel.id,
                components=log_components
            )
    except Exception as e:
        print(f"[Screenshot] Error triggering account collection: {e}")
        import traceback
        traceback.print_exc()
        # Don't let this error prevent the success message from being shown
        # The success message was already sent above


@loader.listener(hikari.MessageCreateEvent)
async def on_message_create(event: hikari.MessageCreateEvent):
    """Listen for messages in ticket channels"""

    if not mongo_client or not bot_instance:
        return

    # Ignore bot messages
    if event.is_bot:
        return

    # Check if this is a ticket channel
    if not event.channel_id:
        return

    channel_id = event.channel_id

    # Skip if screenshot already completed for this channel
    if str(channel_id) in completed_screenshots:
        return

    # Get ticket state from MongoDB
    ticket_state = await mongo_client.ticket_automation_state.find_one({"_id": str(channel_id)})
    if not ticket_state:
        # Not a ticket channel
        return

    # Check if we're in the screenshot awaiting state
    if ticket_state["automation_state"]["current_step"] != "awaiting_screenshot":
        return

    # Check if screenshot already uploaded
    if ticket_state["step_data"]["screenshot"]["uploaded"]:
        completed_screenshots.add(str(channel_id))
        return

    # Verify the message is from the ticket creator
    if event.author_id != int(ticket_state["ticket_info"]["user_id"]):
        return

    # Get ticket type - FIRST check stored type, THEN check channel name
    ticket_pattern = None

    # Method 1: Use stored ticket type from MongoDB (most reliable)
    stored_type = ticket_state["ticket_info"].get("ticket_type")
    if stored_type in ACTIVE_PATTERNS:
        ticket_pattern = stored_type
    else:
        # Method 2: Check channel name for patterns
        channel = bot_instance.cache.get_guild_channel(channel_id)
        if channel and hasattr(channel, 'name'):
            channel_name = channel.name

            # Check for Unicode patterns
            for pattern in ACTIVE_PATTERNS:
                if pattern in PATTERNS and PATTERNS[pattern] in channel_name:
                    ticket_pattern = pattern
                    break

            # Check for regular text patterns if no Unicode found
            if not ticket_pattern:
                for pattern in ACTIVE_PATTERNS:
                    if pattern.lower() in channel_name.lower():
                        ticket_pattern = pattern
                        break

    if not ticket_pattern:
        print(f"[Screenshot] Warning: No valid pattern for ticket {channel_id}, type: {stored_type}")
        # Since we have a valid ticket state, continue anyway
        ticket_pattern = "TEST"  # Default fallback

    # Check for image upload
    has_image = False

    # Check attachments
    if event.message.attachments:
        for attachment in event.message.attachments:
            if attachment.media_type and attachment.media_type.startswith('image/'):
                has_image = True
                break

    # Check embeds (for linked images)
    if not has_image and event.message.embeds:
        for embed in event.message.embeds:
            if embed.image or (embed.url and await is_image_url(embed.url)):
                has_image = True
                break

    if has_image:
        # Handle screenshot upload
        await handle_screenshot_upload(channel_id, event.author_id, event.message, ticket_state)
    else:
        # Check cooldown
        user_id = event.author_id
        now = datetime.now(timezone.utc)

        if user_id in user_cooldowns:
            time_since_last = (now - user_cooldowns[user_id]).total_seconds()
            if time_since_last < REMINDER_COOLDOWN_SECONDS:
                return

        # Update cooldown
        user_cooldowns[user_id] = now

        # Send reminder if not already sent recently
        last_reminder = ticket_state["step_data"]["screenshot"].get("last_reminder")
        if last_reminder:
            if isinstance(last_reminder, str):
                # Handle string format from MongoDB
                last_reminder_time = datetime.fromisoformat(last_reminder.replace('Z', '+00:00'))
                # Ensure it's timezone-aware
                if last_reminder_time.tzinfo is None:
                    last_reminder_time = last_reminder_time.replace(tzinfo=timezone.utc)
            else:
                last_reminder_time = last_reminder
                # Ensure it's timezone-aware
                if last_reminder_time.tzinfo is None:
                    last_reminder_time = last_reminder_time.replace(tzinfo=timezone.utc)

            if (now - last_reminder_time).total_seconds() < REMINDER_COOLDOWN_SECONDS:
                return

        await send_screenshot_reminder(channel_id, user_id)


async def check_pending_screenshot_tickets():
    """Check for tickets still awaiting screenshots on startup"""
    if not mongo_client:
        return

    try:
        # Find all active tickets awaiting screenshots
        pending_tickets = await mongo_client.ticket_automation_state.find({
            "automation_state.current_step": "awaiting_screenshot",
            "automation_state.status": "active",
            "step_data.screenshot.uploaded": False
        }).to_list(length=None)

        active_count = 0
        closed_count = 0

        for ticket in pending_tickets:
            channel_id = ticket["ticket_info"]["channel_id"]

            # Check if channel still exists and is not closed
            try:
                channel = await bot_instance.rest.fetch_channel(int(channel_id))

                # Check if channel is archived or otherwise closed
                if hasattr(channel, 'is_archived') and channel.is_archived:
                    # Clean up archived ticket
                    await mongo_client.ticket_automation_state.update_one(
                        {"_id": str(channel_id)},
                        {"$set": {"automation_state.status": "closed"}}
                    )
                    closed_count += 1
                    continue

                # Add to completed if already uploaded (shouldn't happen, but safety check)
                if ticket["step_data"]["screenshot"]["uploaded"]:
                    completed_screenshots.add(str(channel_id))

                active_count += 1

            except hikari.NotFoundError:
                # Channel doesn't exist - mark ticket as closed
                await mongo_client.ticket_automation_state.update_one(
                    {"_id": str(channel_id)},
                    {"$set": {"automation_state.status": "closed"}}
                )
                closed_count += 1
            except Exception as e:
                print(f"[Screenshot] Error checking channel {channel_id}: {e}")

        if closed_count > 0:
            print(f"[Screenshot] Cleaned up {closed_count} closed/archived tickets")
        print(f"[Screenshot] Loaded {active_count} pending screenshot tickets")

    except Exception as e:
        print(f"Error checking pending tickets: {e}")


# Debug commands
@loader.command
class TicketDiagnostics(
    lightbulb.SlashCommand,
    name="ticket-debug",
    description="Debug ticket screenshot automation"
):
    @lightbulb.invoke
    @lightbulb.di.with_di
    async def invoke(
            self,
            ctx: lightbulb.Context,
            mongo: MongoClient = lightbulb.di.INJECTED,
    ) -> None:
        channel_id = ctx.channel_id

        # Check if ticket state exists
        ticket_state = await mongo.ticket_automation_state.find_one({"_id": str(channel_id)})

        if not ticket_state:
            await ctx.respond(
                "❌ **No ticket state found for this channel!**\n"
                "This channel is not registered as a ticket channel.",
                ephemeral=True
            )
            return

        # Get channel info
        channel = ctx.app.cache.get_guild_channel(channel_id)
        channel_name = channel.name if channel else "Unknown"

        # Check patterns
        found_patterns = []
        for pattern, unicode_pattern in PATTERNS.items():
            if unicode_pattern in channel_name:
                found_patterns.append(f"{pattern} ({unicode_pattern})")

        # Build diagnostic info
        diagnostic_info = f"""**Ticket Screenshot Diagnostics**

**Channel Info:**
- Name: `{channel_name}`
- ID: `{channel_id}`
- Found Patterns: {', '.join(found_patterns) if found_patterns else 'None'}
- Active Patterns: {', '.join(ACTIVE_PATTERNS)}
- Stored Type: `{ticket_state['ticket_info'].get('ticket_type', 'None')}`

**Ticket State:**
- Current Step: `{ticket_state['automation_state']['current_step']}`
- Status: `{ticket_state['automation_state']['status']}`
- Ticket Creator: <@{ticket_state['ticket_info']['user_id']}> (ID: `{ticket_state['ticket_info']['user_id']}`)

**Screenshot Status:**
- Uploaded: `{ticket_state['step_data']['screenshot']['uploaded']}`
- Reminder Sent: `{ticket_state['step_data']['screenshot']['reminder_sent']}`
- Reminder Count: `{ticket_state['step_data']['screenshot']['reminder_count']}`
- In Completed Set: `{str(channel_id) in completed_screenshots}`

**Expected Pattern:** One of {[PATTERNS[p] for p in ACTIVE_PATTERNS]}
"""

        await ctx.respond(diagnostic_info, ephemeral=True)


@loader.command
class TriggerReminder(
    lightbulb.SlashCommand,
    name="trigger-reminder",
    description="Manually trigger screenshot reminder (admin only)"
):
    @lightbulb.invoke
    @lightbulb.di.with_di
    async def invoke(
            self,
            ctx: lightbulb.Context,
            mongo: MongoClient = lightbulb.di.INJECTED,
    ) -> None:
        channel_id = ctx.channel_id

        # Check ticket state
        ticket_state = await mongo.ticket_automation_state.find_one({"_id": str(channel_id)})
        if not ticket_state:
            await ctx.respond("❌ This is not a ticket channel!", ephemeral=True)
            return

        user_id = int(ticket_state['ticket_info']['user_id'])

        # Force send reminder
        await send_screenshot_reminder(channel_id, user_id)
        await ctx.respond("✅ Screenshot reminder sent!", ephemeral=True)


# Initialize when bot starts
@loader.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent):
    global mongo_client, bot_instance

    # Get instances from bot_data
    from utils import bot_data
    mongo_client = bot_data.data.get("mongo")
    bot_instance = bot_data.data.get("bot")

    if mongo_client and bot_instance:
        await check_pending_screenshot_tickets()
        print("Screenshot automation system initialized")


# Cleanup on stop
@loader.listener(hikari.StoppingEvent)
async def on_stopping(event: hikari.StoppingEvent):
    # Cancel all pending deletion tasks
    for task in deletion_tasks.values():
        task.cancel()

    user_cooldowns.clear()
    completed_screenshots.clear()
    deletion_tasks.clear()
    print("Screenshot automation system stopped")