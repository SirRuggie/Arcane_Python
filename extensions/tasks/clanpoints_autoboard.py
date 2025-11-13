import asyncio
import lightbulb
import hikari
from datetime import datetime

from hikari.impl import (
    ContainerComponentBuilder as Container,
    TextDisplayComponentBuilder as Text,
    SeparatorComponentBuilder as Separator,
    MediaGalleryComponentBuilder as Media,
    MediaGalleryItemBuilder as MediaItem,
)

from utils.mongo import MongoClient
from utils.constants import MAGENTA_ACCENT
from utils.classes import Clan
from utils.emoji import emojis

loader = lightbulb.Loader()

# Configuration
AUTOBOARD_CHANNEL_ID = 1435996160950009917
UPDATE_INTERVAL = 30

# Global variables
autoboard_task = None
bot_instance = None
mongo_client = None


async def create_autoboard_embed(clans: list[Clan]) -> list[Container]:
    """Create the autoboard embed using Components V2"""
    # Sort clans by points (highest first) for display order
    sorted_clans = sorted(clans, key=lambda c: c.points, reverse=True)
    # Filter out clans with 0 points
    sorted_clans = [c for c in sorted_clans if c.points > 0]

    # Build components list
    component_list = [
        Text(content="# 📊 Clan Points and Recruitment Tally"),
        Separator(divider=True),
    ]

    # Calculate totals
    total_points = sum(c.points for c in clans)
    total_recruits = sum(c.recruit_count for c in clans)
    active_clans = sum(1 for c in clans if c.points > 0 or c.recruit_count > 0)

    # Add summary stats
    component_list.extend([
        Text(content=(
            f"**Overall Statistics**\n"
            f"• Total Points Earned: **{total_points:.1f}**\n"
            f"• Total Recruits: **{total_recruits}**\n"
            f"• Active Clans: **{active_clans}/{len(clans)}**"
        )),
        Separator(divider=True),
    ])

    # Group clans to avoid component limit
    clan_text_blocks = []
    current_block = []

    for i, clan in enumerate(sorted_clans):
        # Get clan emoji or default
        emoji = clan.emoji if clan.emoji else "🔹"

        # Format points (show .0 if whole number, .1 if decimal)
        points_display = f"{clan.points:.0f}" if clan.points % 1 == 0 else f"{clan.points:.1f}"

        # Format clan info - more compact with points and recruits on same line
        clan_info = (
            f"## {emoji} {clan.name}\n"
            f"{emojis.blank}{emojis.RedGem} Clan Points: `{points_display}` • 👥 Recruit Count: `{clan.recruit_count}`"
        )

        current_block.append(clan_info)

        # Create a new text component every 20 clans to stay under Discord's 4000 character limit
        if len(current_block) >= 20 or i == len(sorted_clans) - 1:
            component_list.append(Text(content="\n".join(current_block)))
            current_block = []

    # Get current timestamp for Discord formatting
    current_timestamp = int(datetime.now().timestamp())

    # Add informational note about filtered clans
    component_list.extend([
        Separator(divider=True),
        Text(content="-# ℹ️ Clans with 0 points are not displayed"),
    ])

    # Add footer
    component_list.extend([
        Separator(divider=True),
        Text(content=f"-# 🔄 This board updates every 5 minutes • Last refresh: <t:{current_timestamp}:f>"),
        Media(items=[MediaItem(media="assets/Purple_Footer.png")]),
    ])

    # Build the embed
    components = [
        Container(
            accent_color=MAGENTA_ACCENT,
            components=component_list
        )
    ]

    return components


async def update_autoboard_message(bot: hikari.GatewayBot, mongo: MongoClient):
    """Update or create the autoboard message"""
    try:
        # Get all clans from database
        clan_data = await mongo.clans.find().to_list(length=None)
        clans = [Clan(data=data) for data in clan_data]

        # Create the embed
        components = await create_autoboard_embed(clans)

        # Check if we have a stored message ID using bot_config collection
        try:
            autoboard_data = await mongo.bot_config.find_one({"_id": "clanpoints_autoboard"})
            message_id = autoboard_data.get("message_id") if autoboard_data else None
        except Exception as e:
            print(f"[ClanPoints Autoboard] Error getting stored message ID: {e}")
            message_id = None

        # Try to update existing message
        if message_id:
            try:
                await bot.rest.edit_message(
                    channel=AUTOBOARD_CHANNEL_ID,
                    message=message_id,
                    components=components
                )
                return
            except (hikari.NotFoundError, hikari.ForbiddenError):
                # Message doesn't exist or we can't edit it
                pass

        # Create new message
        message = await bot.rest.create_message(
            channel=AUTOBOARD_CHANNEL_ID,
            components=components
        )

        # Store the message ID in bot_config collection
        await mongo.bot_config.update_one(
            {"_id": "clanpoints_autoboard"},
            {"$set": {
                "message_id": message.id,
                "channel_id": AUTOBOARD_CHANNEL_ID,
                "last_updated": datetime.utcnow().isoformat()
            }},
            upsert=True
        )

    except Exception as e:
        print(f"[ClanPoints Autoboard] Error updating autoboard: {type(e).__name__}: {e}")


async def autoboard_update_loop(mongo: MongoClient):
    """Main loop that updates the autoboard every 5 minutes"""
    print("[ClanPoints Autoboard] Starting autoboard update task...")

    while True:
        try:
            # Update the autoboard
            await update_autoboard_message(bot_instance, mongo)

            # Wait for the next update
            await asyncio.sleep(UPDATE_INTERVAL)

        except asyncio.CancelledError:
            # Task is being cancelled, exit gracefully
            print("[ClanPoints Autoboard] Update task cancelled")
            break
        except Exception as e:
            print(f"[ClanPoints Autoboard] Error in update loop: {type(e).__name__}: {e}")
            # Wait before retrying
            await asyncio.sleep(60)


@loader.listener(hikari.StartedEvent)
@lightbulb.di.with_di
async def on_bot_started(
        event: hikari.StartedEvent,
        mongo: MongoClient = lightbulb.di.INJECTED
) -> None:
    """Start the autoboard update task when bot starts"""
    global autoboard_task, bot_instance, mongo_client

    # Store bot instance for sending messages
    bot_instance = event.app
    mongo_client = mongo

    # Create the task
    autoboard_task = asyncio.create_task(autoboard_update_loop(mongo))
    print("[ClanPoints Autoboard] Background task started!")


@loader.listener(hikari.StoppingEvent)
async def on_bot_stopping(event: hikari.StoppingEvent) -> None:
    """Cancel the task when bot is stopping"""
    global autoboard_task

    if autoboard_task and not autoboard_task.done():
        autoboard_task.cancel()
        try:
            await autoboard_task
        except asyncio.CancelledError:
            pass
        print("[ClanPoints Autoboard] Background task cancelled!")


@loader.command
class UpdateAutoboard(
    lightbulb.SlashCommand,
    name="update-autoboard",
    description="Manually update the clan points autoboard",
    default_member_permissions=hikari.Permissions.ADMINISTRATOR
):
    @lightbulb.invoke
    @lightbulb.di.with_di
    async def invoke(
            self,
            ctx: lightbulb.Context,
            mongo: MongoClient = lightbulb.di.INJECTED
    ) -> None:
        """Manually trigger an autoboard update"""
        await ctx.respond("🔄 Updating clan points autoboard...", ephemeral=True)

        try:
            await update_autoboard_message(ctx.app, mongo)
            await ctx.edit_last_response("✅ Clan points autoboard updated successfully!")
        except Exception as e:
            await ctx.edit_last_response(f"❌ Failed to update autoboard: {str(e)}")