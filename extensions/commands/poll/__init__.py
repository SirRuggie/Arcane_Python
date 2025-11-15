# extensions/commands/poll/__init__.py
import lightbulb
import hikari
import asyncio
from datetime import datetime, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from utils.mongo import MongoClient
from utils import bot_data
from extensions.components import register_action

loader = lightbulb.Loader()
poll = lightbulb.Group("poll", "Create and manage polls")

# Initialize scheduler
scheduler = AsyncIOScheduler(timezone="UTC")
scheduler.start()

# Flag to track if recovery has already run
_recovery_completed = False

# Import submodules to register commands
from . import create
from . import handlers  # Import handlers for button actions
from . import view
from . import active

# Register the poll group
loader.command(poll)

# Poll end handler
async def end_poll(poll_id: str, guild_id: str, channel_id: str, message_id: str):
    """End a poll and update its status"""
    try:
        # Get bot and mongo from bot_data
        bot = bot_data.data.get("bot")
        mongo = bot_data.data.get("mongo")
        
        if not bot or not mongo:
            print(f"[Poll] Failed to end poll {poll_id}: Bot or MongoDB not available")
            return
        
        # Update poll status in database
        await mongo.discord_polls.update_one(
            {"_id": poll_id},
            {"$set": {"active": False, "ended_reason": "expired"}}
        )
        
        # Get the poll data
        poll_data = await mongo.discord_polls.find_one({"_id": poll_id})
        if not poll_data:
            return
        
        # Try to update the message
        try:
            from .handlers import calculate_percentages, create_progress_bar
            from hikari.impl import (
                ContainerComponentBuilder as Container,
                TextDisplayComponentBuilder as Text,
                SeparatorComponentBuilder as Separator,
                SectionComponentBuilder as Section,
                MediaGalleryComponentBuilder as Media,
                MediaGalleryItemBuilder as MediaItem,
            )
            from utils.constants import DARK_MAGENTA_ACCENT
            
            # Calculate final results
            results = calculate_percentages(poll_data["votes"], poll_data["options"])
            total_votes = len(poll_data["votes"])
            
            # Find the winner(s)
            max_votes = 0
            winners = []
            for option_id, (count, percentage) in results.items():
                if count > max_votes:
                    max_votes = count
                    winners = [option_id]
                elif count == max_votes and count > 0:
                    winners.append(option_id)
            
            # Create ended poll components
            poll_components = []
            
            # Header with ended status
            header_components = []
            
            # Add role ping at the top if specified (to show who was pinged)
            if poll_data.get('ping_role_id'):
                header_components.append(Text(content=f"📢 <@&{poll_data['ping_role_id']}> **Poll has ended!**"))
                header_components.append(Separator(divider=True))
            
            header_components.extend([
                Text(content=f"## 📊 {poll_data.get('title', 'Poll')} - **ENDED**"),
                Text(content=f"*{poll_data['description']}*"),
                Separator(divider=False),
                Text(content=(
                    f"👤 **Created by:** <@{poll_data['creator_id']}> • "
                    f"⏰ **Ended:** <t:{int(datetime.now(timezone.utc).timestamp())}:R>"
                )),
                Separator(divider=True)
            ])
            
            # Show results with winner highlight
            for option in poll_data["options"]:
                count, percentage = results[option["id"]]
                progress_bar = create_progress_bar(percentage)
                
                # Get all voters for this option
                voters = [f"<@{uid}>" for uid, vote_id in poll_data["votes"].items() if vote_id == option["id"]]
                voter_text = "👤 " + " ".join(voters[:5]) if voters else "*No votes*"
                if len(voters) > 5:
                    voter_text += f" *+{len(voters) - 5} more*"
                
                # Add winner badge
                is_winner = option["id"] in winners and count > 0
                title = f"{option['emoji']} **{option['text']}**"
                if is_winner:
                    title += " 👑 **WINNER!**"
                
                poll_components.append(Text(content=title))
                poll_components.append(Text(content=f"`[{progress_bar}]` **{percentage:.0f}%** ({count} vote{'s' if count != 1 else ''})"))
                poll_components.append(Text(content=voter_text))
                poll_components.append(Separator(divider=False))
            
            # Add final stats
            poll_components.append(Separator(divider=True))
            poll_components.append(
                Text(content=f"🎉 **Poll Results** 🎉")
            )
            
            if winners and max_votes > 0:
                winner_names = [opt["text"] for opt in poll_data["options"] if opt["id"] in winners]
                if len(winners) == 1:
                    poll_components.append(
                        Text(content=f"**Winner:** {winner_names[0]} with {max_votes} votes!")
                    )
                else:
                    poll_components.append(
                        Text(content=f"**Tie between:** {', '.join(winner_names)} with {max_votes} votes each!")
                    )
            else:
                poll_components.append(
                    Text(content="**No votes were cast**")
                )
            
            poll_components.append(
                Text(content=f"**Total votes:** {total_votes}")
            )
            
            # Add footer
            poll_components.append(
                Media(items=[MediaItem(media="assets/Red_Footer.png")])
            )
            
            # Create the Container with gray accent for ended polls
            container = Container(
                accent_color=DARK_MAGENTA_ACCENT,
                components=header_components + poll_components
            )
            
            await bot.rest.edit_message(
                channel=int(channel_id),
                message=int(message_id),
                components=[container]
            )
        except Exception as e:
            print(f"[Poll] Failed to update message for poll {poll_id}: {e}")
            
    except Exception as e:
        print(f"[Poll] Error ending poll {poll_id}: {e}")

# Startup recovery function
@loader.listener(hikari.StartedEvent)
async def recover_active_polls(event: hikari.StartedEvent):
    """Recover active polls after bot restart"""
    global _recovery_completed
    
    # Prevent multiple recovery runs
    if _recovery_completed:
        return
    _recovery_completed = True
    
    await asyncio.sleep(5)  # Wait for bot to fully initialize
    
    mongo = bot_data.data.get("mongo")
    if not mongo:
        print("[Poll] MongoDB not available for poll recovery")
        return
    
    print("[Poll] Starting poll recovery...")
    
    # Find all active polls
    active_polls = await mongo.discord_polls.find({
        "active": True
    }).to_list(length=None)
    
    now = datetime.now(timezone.utc)
    recovered = 0
    expired = 0
    
    for poll_data in active_polls:
        poll_id = poll_data["_id"]
        ends_at = poll_data["ends_at"]
        
        # Ensure ends_at is timezone-aware
        if ends_at.tzinfo is None:
            ends_at = ends_at.replace(tzinfo=timezone.utc)
        
        if ends_at <= now:
            # Poll expired while bot was down
            await end_poll(
                poll_id,
                poll_data["guild_id"],
                poll_data["channel_id"],
                poll_data["message_id"]
            )
            expired += 1
        else:
            # Reschedule poll end
            scheduler.add_job(
                end_poll,
                trigger=DateTrigger(run_date=ends_at),
                args=[poll_id, poll_data["guild_id"], poll_data["channel_id"], poll_data["message_id"]],
                id=f"poll_end_{poll_id}",
                replace_existing=True
            )
            recovered += 1
    
    print(f"[Poll] Recovery complete: {recovered} polls rescheduled, {expired} polls marked as expired")

__all__ = ["loader", "poll", "scheduler", "end_poll"]