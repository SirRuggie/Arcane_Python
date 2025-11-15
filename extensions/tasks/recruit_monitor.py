# extensions/tasks/recruit_monitor.py
"""Background task to monitor recruit status and handle expirations/departures"""

import asyncio
import hikari
import lightbulb
import coc
from datetime import datetime, timezone, timedelta
from typing import List, Dict
from utils.mongo import MongoClient
from utils.constants import GREEN_ACCENT, DARK_MAGENTA_ACCENT, BLUE_ACCENT
from utils.emoji import emojis
from utils import bot_data

# Import Components V2
from hikari.impl import (
    ContainerComponentBuilder as Container,
    TextDisplayComponentBuilder as Text,
    SeparatorComponentBuilder as Separator,
    MediaGalleryComponentBuilder as Media,
    MediaGalleryItemBuilder as MediaItem,
)

loader = lightbulb.Loader()

# Configuration
CHECK_INTERVAL = 3600  # Check every hour (3600 seconds)
RECRUITMENT_LOG_CHANNEL = 1436169870273413169
MINIMUM_STAY_HOURS = 24  # No refund if they leave within 24 hours

# Global variables
monitor_task = None
bot_instance = None
mongo_client = None
coc_client = None


async def check_expired_recruits():
    """Check for recruits whose 12-day monitoring period has expired"""
    # Check if coc_client is initialized
    if not coc_client:
        print("[ERROR] CoC client not initialized in check_expired_recruits")
        return
    
    now = datetime.now(timezone.utc)

    # Find all expired recruits who are still being tracked
    expired_recruits = await mongo_client.new_recruits.find({
        "expires_at": {"$lte": now},
        "is_expired": False,
        "current_clan": {"$ne": None}
    }).to_list(length=None)

    print(f"[Recruit Monitor] Found {len(expired_recruits)} expired recruits to process")

    for recruit in expired_recruits:
        try:
            # Check if player is still in the clan
            player = await coc_client.get_player(recruit["player_tag"])

            if player.clan and player.clan.tag == recruit["current_clan"]:
                # Success! They stayed the full 12 days
                await process_successful_recruitment(recruit, player)
            else:
                # They left sometime during the 12 days (but we missed it)
                await process_expired_departure(recruit, player)

        except Exception as e:
            print(f"[ERROR] Failed to process expired recruit {recruit['player_tag']}: {e}")


async def check_early_departures():
    """Check for recruits who left their clan before 12 days - NO automatic refunds"""
    # Check if coc_client is initialized
    if not coc_client:
        print("[ERROR] CoC client not initialized in check_early_departures")
        return
    
    # Find all active recruits who are still being monitored
    # We need to check if they have an active recruitment (no left_at) for their current clan
    active_recruits = await mongo_client.new_recruits.find({
        "is_expired": False,
        "current_clan": {"$ne": None},
        "expires_at": {"$gt": datetime.now(timezone.utc)},
        "$or": [
            {"monitoring_active": True},
            {"monitoring_active": {"$exists": False}}  # Handle existing records without this field
        ]
    }).to_list(length=None)

    # Filter to only those who have matching recruitment history
    recruits_to_monitor = []
    for recruit in active_recruits:
        # Check if current_clan matches any recruitment history entry without left_at
        has_active_recruitment = False
        for hist in recruit.get("recruitment_history", []):
            if hist["clan_tag"] == recruit["current_clan"] and not hist.get("left_at"):
                has_active_recruitment = True
                break
        
        if has_active_recruitment:
            recruits_to_monitor.append(recruit)
        else:
            # Skip monitoring this recruit - they're in a clan they weren't recruited to
            print(f"[INFO] Skipping {recruit['player_tag']} - no active recruitment for {recruit['current_clan']}")

    print(f"[Recruit Monitor] Checking {len(recruits_to_monitor)} active recruits for departures (filtered from {len(active_recruits)})")

    for recruit in recruits_to_monitor:
        try:
            # Check current clan status
            player = await coc_client.get_player(recruit["player_tag"])

            # If they're no longer in the clan they joined
            if not player.clan or player.clan.tag != recruit["current_clan"]:
                # Just track the departure - clan leaders will handle refunds manually
                await track_early_departure(recruit, player)

        except Exception as e:
            print(f"[ERROR] Failed to check recruit {recruit['player_tag']}: {e}")


async def process_successful_recruitment(recruit: Dict, player):
    """Process a recruit who stayed the full 12 days"""

    # Update database
    await mongo_client.new_recruits.update_one(
        {"_id": recruit["_id"]},
        {
            "$set": {
                "is_expired": True,
                "completion_status": "successful",
                "completed_at": datetime.now(timezone.utc),
                "monitoring_active": False  # Stop monitoring since they completed their 12 days
            }
        }
    )

    # Update clan statistics
    await mongo_client.clans.update_one(
        {"tag": recruit["current_clan"]},
        {
            "$inc": {
                "successful_recruits": 1
            }
        }
    )

    # Get clan info for the message
    clan = await mongo_client.clans.find_one({"tag": recruit["current_clan"]})

    # Send success notification
    components = [
        Container(
            accent_color=GREEN_ACCENT,
            components=[
                Text(content=(
                    f"## ✅ Recruitment Completed Successfully!"
                )),
                Separator(divider=True),
                Text(content=(
                    f"**{recruit['player_name']}** (TH{recruit['player_th_level']}) "
                    f"has completed their 12-day period in **{clan['name']}**!"
                )),
                Separator(divider=True),
                Text(content="### Final Status"),
                Text(content=(
                    f"• **Duration:** Full 12 days completed\n"
                    f"• **Points Status:** Finalized (no refunds)\n"
                    f"• **Recruited By:** <@{recruit.get('discord_user_id', 'Unknown')}>\n"
                    f"• **Player Tag:** {recruit['player_tag']}"
                )),
                Media(items=[MediaItem(media="assets/Green_Footer.png")])
            ]
        )
    ]

    await bot_instance.rest.create_message(
        channel=RECRUITMENT_LOG_CHANNEL,
        components=components
    )


async def track_early_departure(recruit: Dict, player):
    """Track when a recruit leaves before 12 days (NO automatic refund)"""

    # Calculate duration
    joined_at = recruit.get("joined_clan_at", recruit["created_at"])

    # Ensure joined_at is timezone-aware
    if joined_at.tzinfo is None:
        joined_at = joined_at.replace(tzinfo=timezone.utc)

    left_at = datetime.now(timezone.utc)
    duration = left_at - joined_at
    days_stayed = duration.days
    hours_stayed = duration.total_seconds() / 3600

    # Get recruitment history entry for this clan
    current_recruitment = None
    for hist in recruit.get("recruitment_history", []):
        if hist["clan_tag"] == recruit["current_clan"] and not hist.get("left_at"):
            current_recruitment = hist
            break

    if not current_recruitment:
        # This shouldn't happen with our new filtering, but handle it gracefully
        print(f"[WARN] No recruitment history found for {recruit['player_tag']} - setting monitoring_active to false")
        # Stop monitoring this recruit
        await mongo_client.new_recruits.update_one(
            {"_id": recruit["_id"]},
            {"$set": {"monitoring_active": False}}
        )
        return

    # Just track the departure - NO automatic refund
    # Refunds will be handled manually via the "Member Left" button
    await mongo_client.new_recruits.update_one(
        {
            "_id": recruit["_id"],
            "recruitment_history.clan_tag": recruit["current_clan"],
            "recruitment_history.left_at": None
        },
        {
            "$set": {
                "recruitment_history.$.left_at": left_at,
                "recruitment_history.$.duration_days": days_stayed,
                "recruitment_history.$.refund_eligible": days_stayed < 12,  # Full refund if < 12 days
                "recruitment_history.$.refund_processed": False,  # Not processed yet
                "current_clan": player.clan.tag if player.clan else None,  # They might have joined another clan
                "monitoring_active": False  # Stop monitoring since they left their recruited clan
            }
        }
    )

    # Just log the departure - clan leaders will handle refunds manually
    print(f"[INFO] Tracked departure: {recruit['player_name']} left {recruit['current_clan']} after {days_stayed} days")

    # Optional: Send a notification to clan leadership channel (if configured)
    # This would alert leaders that someone left and may need a refund


async def process_expired_departure(recruit: Dict, player):
    """Process a recruit who left but we only discovered after expiration"""
    # Similar to early departure but marked differently
    # This catches cases where the hourly check missed them leaving
    # Implementation would be similar to track_early_departure

    # Ensure timezone-aware datetime handling
    joined_at = recruit.get("joined_clan_at", recruit["created_at"])
    if joined_at.tzinfo is None:
        joined_at = joined_at.replace(tzinfo=timezone.utc)

    # Track the departure with appropriate handling
    pass


async def monitor_loop():
    """Main monitoring loop"""
    print("[Recruit Monitor] Starting recruitment monitoring task...")
    
    # Wait for coc_client to be initialized
    retry_count = 0
    while not coc_client and retry_count < 10:
        print(f"[Recruit Monitor] Waiting for CoC client initialization... (attempt {retry_count + 1}/10)")
        await asyncio.sleep(5)
        retry_count += 1
    
    if not coc_client:
        print("[ERROR] CoC client failed to initialize after 50 seconds. Stopping recruit monitor.")
        return

    while True:
        try:
            print(f"[Recruit Monitor] Running checks at {datetime.now(timezone.utc)}")

            # Check for expired 12-day periods
            await check_expired_recruits()

            # Check for early departures
            await check_early_departures()

            # Wait for next check
            await asyncio.sleep(CHECK_INTERVAL)

        except asyncio.CancelledError:
            print("[Recruit Monitor] Task cancelled")
            break
        except Exception as e:
            print(f"[Recruit Monitor] Error in monitor loop: {e}")
            await asyncio.sleep(60)  # Wait a minute before retrying


@loader.listener(hikari.StartedEvent)
@lightbulb.di.with_di
async def on_bot_started(
        event: hikari.StartedEvent,
        mongo: MongoClient = lightbulb.di.INJECTED,
        coc_api: coc.Client = lightbulb.di.INJECTED
) -> None:
    """Start the monitoring task when bot starts"""
    global monitor_task, bot_instance, mongo_client, coc_client

    bot_instance = event.app
    mongo_client = mongo
    coc_client = coc_api
    
    # Fallback to bot_data if dependency injection didn't work
    if not coc_client:
        coc_client = bot_data.data.get("coc_client")
        if coc_client:
            print("[Recruit Monitor] Using CoC client from bot_data")

    # Start the background task
    monitor_task = asyncio.create_task(monitor_loop())
    print("[Recruit Monitor] Background monitoring task started!")


@loader.listener(hikari.StoppingEvent)
async def on_bot_stopping(event: hikari.StoppingEvent) -> None:
    """Cancel the task when bot stops"""
    global monitor_task

    if monitor_task and not monitor_task.done():
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass
        print("[Recruit Monitor] Background task cancelled!")


# Manual commands for testing/admin use
@loader.command
class CheckRecruits(
    lightbulb.SlashCommand,
    name="check-recruits",
    description="Manually trigger recruit status check",
    default_member_permissions=hikari.Permissions.ADMINISTRATOR
):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        await ctx.respond("🔍 Checking recruit status...", ephemeral=True)

        try:
            await check_expired_recruits()
            await check_early_departures()
            await ctx.edit_last_response("✅ Recruit check completed!")
        except Exception as e:
            await ctx.edit_last_response(f"❌ Check failed: {str(e)}")