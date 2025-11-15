# extensions/commands/poll/view.py
"""
View detailed poll results including who voted for what.
"""

import hikari
import lightbulb
from typing import Optional

from utils.mongo import MongoClient
from utils.constants import BLUE_ACCENT, GREEN_ACCENT, DARK_MAGENTA_ACCENT
from extensions.components import register_action
from . import loader, poll

from hikari.impl import (
    ContainerComponentBuilder as Container,
    TextDisplayComponentBuilder as Text,
    SeparatorComponentBuilder as Separator,
    InteractiveButtonBuilder as Button,
    MessageActionRowBuilder as ActionRow,
    TextSelectMenuBuilder as TextSelectMenu,
    SelectOptionBuilder as SelectOption,
)

@poll.register()
class View(
    lightbulb.SlashCommand,
    name="view",
    description="View detailed poll results",
):
    poll_id = lightbulb.string(
        "poll_id",
        "The poll ID to view",
        default=None
    )
    
    channel = lightbulb.channel(
        "channel",
        "Channel with an active poll",
        default=None,
        channel_types=[hikari.ChannelType.GUILD_TEXT]
    )
    
    @lightbulb.invoke
    @lightbulb.di.with_di
    async def invoke(
        self,
        ctx: lightbulb.Context,
        mongo: MongoClient = lightbulb.di.INJECTED,
        bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    ) -> None:
        await ctx.defer(ephemeral=True)
        
        # If poll_id provided, show that poll directly
        if self.poll_id:
            poll_data = await mongo.discord_polls.find_one({"_id": self.poll_id})
            if not poll_data:
                await ctx.respond("❌ Poll not found with that ID", ephemeral=True)
                return
            
            # Show poll results
            await show_poll_results(ctx, poll_data, bot)
            return
        
        # If channel provided, find active poll in that channel
        if self.channel:
            poll_data = await mongo.discord_polls.find_one({
                "channel_id": str(self.channel.id),
                "active": True
            })
            
            if not poll_data:
                await ctx.respond(
                    f"❌ No active poll found in <#{self.channel.id}>",
                    ephemeral=True
                )
                return
            
            await show_poll_results(ctx, poll_data, bot)
            return
        
        # Otherwise, show select menu with recent polls
        recent_polls = await mongo.discord_polls.find({
            "guild_id": str(ctx.guild_id)
        }).sort("created_at", -1).limit(25).to_list(length=25)
        
        if not recent_polls:
            await ctx.respond("❌ No polls found in this server", ephemeral=True)
            return
        
        # Create select menu
        options = []
        for poll_data in recent_polls[:25]:  # Discord limit
            status = "🟢 Active" if poll_data["active"] else "⚪ Ended"
            option_text = poll_data["description"][:50]
            if len(poll_data["description"]) > 50:
                option_text += "..."
            
            options.append(
                SelectOption(
                    label=f"{status} {option_text}",
                    value=poll_data["_id"],
                    description=f"Created by {poll_data.get('creator_id', 'Unknown')} • {len(poll_data['votes'])} votes"
                )
            )
        
        components = [
            Container(
                accent_color=BLUE_ACCENT,
                components=[
                    Text(content="## 📊 Select a Poll to View"),
                    Text(content="Choose a poll from the dropdown to see detailed results"),
                    Separator(),
                    ActionRow(
                        components=[
                            TextSelectMenu(
                                custom_id="poll_view_select:menu",
                                placeholder="Select a poll...",
                                options=options
                            )
                        ]
                    )
                ]
            )
        ]
        
        await ctx.respond(components=components, ephemeral=True)

async def show_poll_results(
    ctx: lightbulb.Context, 
    poll_data: dict,
    bot: hikari.GatewayBot
) -> None:
    """Display detailed poll results"""
    
    # Build vote breakdown
    vote_breakdown = {}
    for option in poll_data["options"]:
        vote_breakdown[option["id"]] = []
    
    # Group votes by option
    for user_id, option_id in poll_data["votes"].items():
        if option_id in vote_breakdown:
            vote_breakdown[option_id].append(user_id)
    
    # Create embed
    color = GREEN_ACCENT if poll_data["active"] else DARK_MAGENTA_ACCENT
    embed = hikari.Embed(
        title=f"📊 Poll Results: {poll_data['description'][:100]}",
        color=color,
        timestamp=poll_data["created_at"]
    )
    
    # Add info field
    status = "Active" if poll_data["active"] else f"Ended ({poll_data.get('ended_reason', 'unknown')})"
    embed.add_field(
        name="Poll Information",
        value=(
            f"**ID:** `{poll_data['_id']}`\n"
            f"**Status:** {status}\n"
            f"**Created by:** <@{poll_data['creator_id']}>\n"
            f"**Channel:** <#{poll_data['channel_id']}>\n"
            f"**Total votes:** {len(poll_data['votes'])}"
        ),
        inline=False
    )
    
    # Add vote breakdown for each option
    for option in poll_data["options"]:
        voters = vote_breakdown[option["id"]]
        vote_count = len(voters)
        
        if poll_data["votes"]:
            percentage = (vote_count / len(poll_data["votes"])) * 100
        else:
            percentage = 0
        
        # Format voter list
        if voters:
            # Show first 10 voters
            voter_list = "\n".join([f"• <@{uid}>" for uid in voters[:10]])
            if len(voters) > 10:
                voter_list += f"\n• *...and {len(voters) - 10} more*"
        else:
            voter_list = "*No votes*"
        
        embed.add_field(
            name=f"{option['emoji']} {option['text']} - {vote_count} votes ({percentage:.1f}%)",
            value=voter_list,
            inline=False
        )
    
    # Add link to poll message
    if poll_data.get("message_id"):
        embed.add_field(
            name="Jump to Poll",
            value=f"[Click here](https://discord.com/channels/{poll_data['guild_id']}/{poll_data['channel_id']}/{poll_data['message_id']})",
            inline=False
        )
    
    await ctx.respond(embed=embed, ephemeral=True)

@register_action("poll_view_select", no_return=True)
@lightbulb.di.with_di
async def handle_poll_select(
    ctx: lightbulb.components.MenuContext,
    action_id: str,
    mongo: MongoClient = lightbulb.di.INJECTED,
    bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    **kwargs
) -> None:
    """Handle poll selection from dropdown"""
    
    poll_id = ctx.interaction.values[0]
    
    # Get poll data
    poll_data = await mongo.discord_polls.find_one({"_id": poll_id})
    if not poll_data:
        await ctx.respond("❌ Poll not found", ephemeral=True)
        return
    
    # Show results
    await show_poll_results(ctx, poll_data, bot)

loader.command(View)