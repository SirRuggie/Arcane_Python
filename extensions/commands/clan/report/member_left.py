# extensions/commands/clan/report/member_left.py
"""Handle refunds for members who left before completing 12 days"""

import hikari
import lightbulb
from datetime import datetime, timezone
from typing import List, Dict

from hikari.impl import (
    MessageActionRowBuilder as ActionRow,
    TextSelectMenuBuilder as TextSelectMenu,
    SelectOptionBuilder as SelectOption,
    ContainerComponentBuilder as Container,
    InteractiveButtonBuilder as Button,
    TextDisplayComponentBuilder as Text,
    SeparatorComponentBuilder as Separator,
    MediaGalleryComponentBuilder as Media,
    MediaGalleryItemBuilder as MediaItem,
)

from extensions.components import register_action
from utils.constants import DARK_MAGENTA_ACCENT, GREEN_ACCENT, GOLD_ACCENT
from utils.mongo import MongoClient
from utils.emoji import emojis
from extensions.commands.clan.report.helpers import get_clan_by_tag, get_clan_options, get_categorized_clan_components, create_progress_header

# Add the loader for proper integration
loader = lightbulb.Loader()

# Log channel for refund notifications
RECRUITMENT_LOG_CHANNEL = 1436169870273413169

# Session storage for multi-step flow
member_left_sessions = {}


async def get_refund_eligible_members(mongo: MongoClient, clan_tag: str) -> List[Dict]:
    """
    Get all members who left this clan within 12 days and haven't been refunded yet.
    This includes players who may have joined CWL clans temporarily.
    """

    # Use a simpler approach with find and manual filtering
    all_recruits = await mongo.new_recruits.find({
        "recruitment_history.clan_tag": clan_tag
    }).to_list(length=None)

    eligible_members = []

    for recruit in all_recruits:
        # Check each recruitment history entry
        for recruitment in recruit.get("recruitment_history", []):
            if (recruitment.get("clan_tag") == clan_tag and
                    recruitment.get("left_at") is not None and
                    recruitment.get("duration_days", 12) < 12 and
                    not recruitment.get("refund_processed", False) and
                    recruitment.get("bid_amount", 0) > 0):
                eligible_members.append({
                    "player_tag": recruit["player_tag"],
                    "player_name": recruit.get("player_name", "Unknown"),
                    "th_level": recruit.get("player_th_level", "??"),
                    "bid_points": recruitment["bid_amount"],
                    "joined_at": recruitment.get("recruited_at"),
                    "left_at": recruitment["left_at"],
                    "duration_days": recruitment.get("duration_days", 0),
                    "discord_user_id": recruit.get("discord_user_id", "Unknown"),
                    "current_clan": recruit.get("current_clan", "No Clan")
                })
                break  # Only add once per recruit

    return eligible_members


@register_action("report_type:member_left", no_return=True)
@lightbulb.di.with_di
async def show_member_left_flow(
        ctx: lightbulb.components.MenuContext,
        action_id: str,
        mongo: MongoClient = lightbulb.di.INJECTED,
        **kwargs
):
    """Initialize member left flow - Step 1: Select Clan"""

    # Extract user ID from action_id
    user_id = int(action_id.split("_")[-1])

    # Verify it's the correct user
    if ctx.user.id != user_id:
        await ctx.respond("❌ This menu is not for you!", ephemeral=True)
        return

    # Build component list
    component_list = [
        Text(content=create_progress_header(1, 2, ["Select Clan", "Select Member"])),
        Separator(divider=True),
        Text(content="## 🏰 Select Clan"),
        Text(content="Choose the clan to check for member refunds:"),
    ]

    # Add categorized clan dropdowns
    categorized_components = await get_categorized_clan_components("member_left_clan", str(user_id), mongo)

    if not categorized_components:
        components = [
            Container(
                accent_color=DARK_MAGENTA_ACCENT,
                components=[
                    Text(content="## ❌ No Clans Available"),
                    Text(content="No clans found in the database."),
                    ActionRow(
                        components=[
                            Button(
                                style=hikari.ButtonStyle.SECONDARY,
                                label="Back to Dashboard",
                                custom_id=f"report_home:{user_id}"
                            )
                        ]
                    ),
                    Media(items=[MediaItem(media="assets/Red_Footer.png")])
                ]
            )
        ]
        await ctx.respond(components=components, edit=True)
        return

    component_list.extend(categorized_components)

    # Add cancel button and footer
    component_list.extend([
        ActionRow(
            components=[
                Button(
                    style=hikari.ButtonStyle.SECONDARY,
                    label="Cancel",
                    custom_id=f"report_home:{user_id}"
                )
            ]
        ),
        Media(items=[MediaItem(media="assets/Gold_Footer.png")])
    ])

    # Create clan selection menu
    components = [
        Container(
            accent_color=GOLD_ACCENT,
            components=component_list
        )
    ]

    await ctx.respond(components=components, edit=True)


@register_action("member_left_clan", no_return=True)
@lightbulb.di.with_di
async def handle_clan_selection(
        ctx: lightbulb.components.MenuContext,
        action_id: str,
        mongo: MongoClient = lightbulb.di.INJECTED,
        **kwargs
):
    """Handle clan selection - Step 2: Show eligible members"""
    # Parse category prefix from action_id (e.g., "competitive_user123")
    if "_" in action_id and action_id.split("_")[0] in ["competitive", "zen", "fwa"]:
        category, action_id = action_id.split("_", 1)

    user_id = int(action_id)

    # Verify user
    if ctx.user.id != user_id:
        await ctx.respond("❌ This menu is not for you!", ephemeral=True)
        return

    # Get selected clan tag
    clan_tag = ctx.interaction.values[0]

    # Get clan details
    clan = await get_clan_by_tag(mongo, clan_tag)
    if not clan:
        await ctx.respond("❌ Clan not found in database.", ephemeral=True)
        return

    # Check if user has permission (must have clan's leadership role)
    member = ctx.member
    has_permission = False

    if clan.leader_role_id and clan.leader_role_id in member.role_ids:
        has_permission = True

    if not has_permission:
        components = [
            Container(
                accent_color=DARK_MAGENTA_ACCENT,
                components=[
                    Text(content="## ❌ Permission Denied"),
                    Text(content=f"Only leadership of **{clan.name}** can process refunds."),

                    ActionRow(
                        components=[
                            Button(
                                style=hikari.ButtonStyle.SECONDARY,
                                label="Back to Dashboard",
                                custom_id=f"report_home:{user_id}"
                            )
                        ]
                    ),

                    Media(items=[MediaItem(media="assets/Red_Footer.png")])
                ]
            )
        ]
        await ctx.respond(components=components, edit=True)
        return

    # Get eligible members for refund
    eligible_members = await get_refund_eligible_members(mongo, clan_tag)

    if not eligible_members:
        components = [
            Container(
                accent_color=GOLD_ACCENT,
                components=[
                    Text(content=create_progress_header(2, 2, ["Select Clan", "Select Member"])),
                    Separator(divider=True),
                    Text(content=f"## 📊 No Refunds Available - {clan.name}"),
                    Text(content=(
                        f"There are no members who left **{clan.name}** within 12 days "
                        "that are eligible for point refunds.\n\n"
                        "**Possible reasons:**\n"
                        "• All recent departures stayed 12+ days\n"
                        "• Refunds have already been processed\n"
                        "• No bids were placed on departed members"
                    )),

                    ActionRow(
                        components=[
                            Button(
                                style=hikari.ButtonStyle.PRIMARY,
                                label="Select Different Clan",
                                custom_id=f"report_type:member_left_{user_id}"
                            ),
                            Button(
                                style=hikari.ButtonStyle.SECONDARY,
                                label="Back to Dashboard",
                                custom_id=f"report_home:{user_id}"
                            )
                        ]
                    ),

                    Media(items=[MediaItem(media="assets/Gold_Footer.png")])
                ]
            )
        ]

        await ctx.respond(components=components, edit=True)
        return

    # Build select menu options
    options = []
    for member in eligible_members[:25]:  # Discord limit
        # Format the description
        desc = f"Left after {member['duration_days']} days • {member['bid_points']} points"
        if member['current_clan'] and member['current_clan'] != "No Clan":
            desc += f" • Now in: {member['current_clan'][:20]}"  # Truncate clan name if needed

        options.append(
            SelectOption(
                label=f"{member['player_name']} (TH{member['th_level']})",
                value=member['player_tag'],
                description=desc,
                emoji="💰"
            )
        )

    # Store session data
    session_key = f"member_left_{user_id}"
    member_left_sessions[session_key] = {
        "clan_tag": clan_tag,
        "clan_name": clan.name
    }

    # Create the selection menu
    components = [
        Container(
            accent_color=DARK_MAGENTA_ACCENT,
            components=[
                Text(content=create_progress_header(2, 2, ["Select Clan", "Select Member"])),
                Separator(divider=True),
                Text(content=f"## 💰 Process Member Refund - {clan.name}"),
                Text(content=(
                    "Select a member who left before completing 12 days to process their refund.\n"
                    "**Note:** Full bid amount will be refunded to your clan."
                )),

                ActionRow(
                    components=[
                        TextSelectMenu(
                            placeholder="Select a member to refund...",
                            custom_id=f"process_refund:{user_id}",
                            options=options
                        )
                    ]
                ),

                Separator(divider=True),
                Text(content=(
                    f"**Total refunds available:** {len(eligible_members)}\n"
                    f"-# Members who joined CWL clans are still eligible for refunds"
                )),

                ActionRow(
                    components=[
                        Button(
                            style=hikari.ButtonStyle.SECONDARY,
                            label="Back",
                            custom_id=f"report_type:member_left_{user_id}"
                        ),
                        Button(
                            style=hikari.ButtonStyle.SECONDARY,
                            label="Cancel",
                            custom_id=f"report_home:{user_id}"
                        )
                    ]
                ),

                Media(items=[MediaItem(media="assets/Red_Footer.png")])
            ]
        )
    ]

    await ctx.respond(components=components, edit=True)


@register_action("process_refund", no_return=True)
@lightbulb.di.with_di
async def process_refund(
        ctx: lightbulb.components.MenuContext,
        action_id: str,
        mongo: MongoClient = lightbulb.di.INJECTED,
        bot: hikari.GatewayBot = lightbulb.di.INJECTED,
        **kwargs
):
    """Process the selected refund"""

    user_id = int(action_id)

    # Verify user
    if ctx.user.id != user_id:
        await ctx.respond("❌ This menu is not for you!", ephemeral=True)
        return

    # Get session data
    session_key = f"member_left_{user_id}"
    session_data = member_left_sessions.get(session_key)
    if not session_data:
        await ctx.respond("❌ Session expired. Please start over.", ephemeral=True)
        return

    clan_tag = session_data["clan_tag"]
    clan_name = session_data["clan_name"]

    # Get selected player tag
    player_tag = ctx.interaction.values[0]

    # Get the recruitment details
    recruit = await mongo.new_recruits.find_one({"player_tag": player_tag})
    if not recruit:
        await ctx.respond("❌ Could not find recruitment data.", ephemeral=True)
        return

    # Find the specific recruitment history entry
    recruitment_entry = None
    for hist in recruit.get("recruitment_history", []):
        if hist["clan_tag"] == clan_tag and hist.get("left_at") and not hist.get("refund_processed"):
            recruitment_entry = hist
            break

    if not recruitment_entry:
        await ctx.respond("❌ Could not find eligible recruitment entry.", ephemeral=True)
        return

    refund_amount = recruitment_entry["bid_amount"]

    # Process the refund
    # 1. Update clan points
    clan_update = await mongo.clans.update_one(
        {"tag": clan_tag},
        {
            "$inc": {
                "points": refund_amount,
                "points_refunded": refund_amount
            }
        }
    )

    # 2. Mark refund as processed
    recruit_update = await mongo.new_recruits.update_one(
        {
            "player_tag": player_tag,
            "recruitment_history.clan_tag": clan_tag,
            "recruitment_history.left_at": {"$ne": None}
        },
        {
            "$set": {
                "recruitment_history.$.refund_processed": True,
                "recruitment_history.$.refund_processed_at": datetime.now(timezone.utc),
                "recruitment_history.$.refund_processed_by": str(user_id)
            }
        }
    )

    # Get clan details for the message
    clan = await mongo.clans.find_one({"tag": clan_tag})

    # Clean up session
    del member_left_sessions[session_key]

    # Send success message
    success_components = [
        Container(
            accent_color=GREEN_ACCENT,
            components=[
                Text(content="## ✅ Refund Processed Successfully"),
                Separator(divider=True),
                Text(content=(
                    f"**Player:** {recruit['player_name']} (TH{recruit['player_th_level']})\n"
                    f"**Refund Amount:** {refund_amount} points\n"
                    f"**Duration in Clan:** {recruitment_entry['duration_days']} days\n\n"
                    f"The points have been returned to **{clan['name']}**'s balance."
                )),

                ActionRow(
                    components=[
                        Button(
                            style=hikari.ButtonStyle.PRIMARY,
                            label="Process Another Refund",
                            custom_id=f"report_type:member_left_{user_id}"
                        ),
                        Button(
                            style=hikari.ButtonStyle.SECONDARY,
                            label="Back to Dashboard",
                            custom_id=f"report_home:{user_id}"
                        )
                    ]
                ),

                Media(items=[MediaItem(media="assets/Green_Footer.png")])
            ]
        )
    ]

    await ctx.respond(components=success_components, edit=True)

    # Log the refund to the recruitment log channel
    log_components = [
        Container(
            accent_color=GOLD_ACCENT,
            components=[
                Text(content=(
                    f"## 💰 Manual Refund Processed"
                )),
                Separator(divider=True),
                Text(content="### Refund Details"),
                Text(content=(
                    f"<@&{clan.get('leader_role_id', 0)}> "
                    f"• **Player:** {recruit['player_name']} ({recruit['player_tag']})\n"
                    f"• **TH Level:** {recruit['player_th_level']}\n"
                    f"• **Clan:** {clan['name']}\n"
                    f"• **Refund Amount:** {refund_amount} points\n"
                    f"• **Days in Clan:** {recruitment_entry['duration_days']}/12\n"
                    f"• **Processed By:** <@{user_id}>"
                )),
                Separator(divider=True),
                Text(content=(
                    f"-# Player may have temporarily joined a CWL clan\n"
                    f"-# Full refund processed as per policy (< 12 days)"
                )),
                Media(items=[MediaItem(media="assets/Gold_Footer.png")])
            ]
        )
    ]

    try:
        await bot.rest.create_message(
            channel=RECRUITMENT_LOG_CHANNEL,
            components=log_components,
            role_mentions=True
        )
    except Exception as e:
        print(f"[ERROR] Failed to send refund log: {e}")


@register_action("report_home", no_return=True)
async def back_to_dashboard(
        ctx: lightbulb.components.MenuContext,
        action_id: str,
        **kwargs
):
    """Return to the main report dashboard"""
    from extensions.commands.clan.report.router import create_home_dashboard

    user_id = int(action_id)
    if ctx.user.id != user_id:
        await ctx.respond("❌ This menu is not for you!", ephemeral=True)
        return

    # Clean up any session data
    session_key = f"member_left_{user_id}"
    if session_key in member_left_sessions:
        del member_left_sessions[session_key]

    components = await create_home_dashboard(ctx.member)
    await ctx.respond(components=components, edit=True)