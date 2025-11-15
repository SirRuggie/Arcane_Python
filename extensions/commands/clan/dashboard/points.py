# extensions/commands/clan/dashboard/clan_points.py
# Modern, streamlined clan points management system

import lightbulb
import hikari
from datetime import datetime
from typing import List, Optional
import asyncio
import math
import uuid

from extensions.components import register_action
from utils.mongo import MongoClient
from utils.classes import Clan
from utils.constants import DARK_MAGENTA_ACCENT, GREEN_ACCENT, BLUE_ACCENT, GOLD_ACCENT, MAGENTA_ACCENT
from utils.emoji import emojis

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
    ModalActionRowBuilder as ModalActionRow,
    ThumbnailComponentBuilder as Thumbnail,
    SectionComponentBuilder as Section
)

# Log channel for point changes
POINTS_LOG_CHANNEL = 1436169870273413169


async def log_points_change(
        bot: hikari.GatewayBot,
        clan: Clan,
        change_amount: float,
        new_total: float,
        changed_by: hikari.Member,
        note: Optional[str] = None
) -> None:
    """Log point changes to the designated channel"""

    # Determine color and action text based on change
    if change_amount > 0:
        color = GREEN_ACCENT
        action_text = f"Awarded +{change_amount} Point(s)"
        emoji = "✅"
    elif change_amount < 0:
        color = DARK_MAGENTA_ACCENT
        action_text = f"Points Reduced by {abs(change_amount)} Point"
        emoji = "❌"
    else:
        return  # No change, don't log

    # Get current timestamp
    timestamp = datetime.now()

    # Format time in a cross-platform way
    time_str = timestamp.strftime('%I:%M %p').lstrip('0')  # Removes leading zero manually

    # Build component list
    component_list = [
        Section(
            components=[
                Text(content=f"## {emoji} Manual Change: Clan Points - {clan.name}"),
                Text(content=(
                    f"**{clan.name}**: {action_text}\n"
                    f"• Clan now has **{new_total:.1f}** points."
                )),
            ],
            accessory=Thumbnail(
                media=clan.logo if clan.logo else "https://cdn-icons-png.flaticon.com/512/845/845665.png"
            )
        )
    ]

    # Add separator and note if note exists
    if note:
        component_list.append(Separator(divider=True))
        component_list.append(Text(content=f"📝 **Note:** {note}"))

    # Add footer
    component_list.append(Text(content=f"-# Ran by {changed_by.display_name} • Today at {time_str}"))

    # Build the log message
    components = [
        Container(
            accent_color=color,
            components=component_list
        )
    ]

    # Send the log message
    try:
        await bot.rest.create_message(
            channel=POINTS_LOG_CHANNEL,
            components=components
        )
    except Exception as e:
        print(f"Failed to log points change: {e}")


def format_points_leaderboard(clans: List[Clan], max_items: int = 10) -> str:
    """Format clans into a nice leaderboard display"""
    sorted_clans = sorted(clans, key=lambda c: c.points, reverse=True)

    lines = []
    for i, clan in enumerate(sorted_clans[:max_items], 1):
        # Medals for top 3
        if i == 1:
            rank = "🥇"
        elif i == 2:
            rank = "🥈"
        elif i == 3:
            rank = "🥉"
        else:
            rank = f"`{i:2d}`"

        # Format the line with emoji if available
        emoji = clan.emoji if clan.emoji else ""
        lines.append(f"{rank} {emoji} **{clan.name}** • {clan.points:.1f} pts")

    return "\n".join(lines) if lines else "*No clans with points yet*"


def format_recruit_summary(clans: List[Clan]) -> str:
    """Format recruitment summary"""
    total_recruits = sum(c.recruit_count for c in clans)
    active_clans = sum(1 for c in clans if c.recruit_count > 0)

    return (
        f"**Total Recruits This Month:** {total_recruits}\n"
        f"**Active Recruiting Clans:** {active_clans}/{len(clans)}"
    )


@register_action("clan_points", group="clan_database")
@lightbulb.di.with_di
async def clan_points_main(
        ctx: lightbulb.components.MenuContext,
        mongo: MongoClient = lightbulb.di.INJECTED,
        **kwargs
):
    """Main clan points dashboard - shows overview and quick stats"""

    # Get all clan data
    clan_data = await mongo.clans.find().to_list(length=None)
    clans = [Clan(data=data) for data in clan_data]

    # Calculate stats
    total_points = sum(c.points for c in clans)
    total_recruits = sum(c.recruit_count for c in clans)

    components = [
        # Header with stats
        Container(
            accent_color=MAGENTA_ACCENT,
            components=[
                Section(
                    components=[
                        Text(content="## 📊 **Clan Point System**"),
                        Text(content=(
                            f"Track clan performance and recruitment efforts\n\n"
                            f"**Total Points:** {total_points:.1f}\n"
                            f"**Total Recruits:** {total_recruits}"
                        )),
                    ],
                    accessory=Thumbnail(
                        media="https://cdn-icons-png.flaticon.com/512/3135/3135783.png"
                    )
                ),
                Separator(divider=True),
                Text(content="### 🏆 **Points Leaderboard**"),
                Text(content=format_points_leaderboard(clans, max_items=5)),

                ActionRow(
                    components=[
                        Button(
                            style=hikari.ButtonStyle.PRIMARY,
                            label="Manage Points",
                            emoji="✏️",
                            custom_id="points_quick_select:",
                        ),
                        Button(
                            style=hikari.ButtonStyle.SECONDARY,
                            label="Recruitment Stats",
                            emoji="📈",
                            custom_id="recruitment_overview:",
                        ),
                        Button(
                            style=hikari.ButtonStyle.DANGER,
                            label="Month Reset",
                            emoji="🔄",
                            custom_id="month_reset:",
                        ),
                    ]
                ),

                Media(items=[MediaItem(media="assets/Purple_Footer.png")]),
            ]
        )
    ]

    await ctx.respond(components=components, ephemeral=True)

    # Return to dashboard
    from extensions.commands.clan.dashboard import dashboard_page
    return await dashboard_page(ctx=ctx, mongo=mongo)


@register_action("points_quick_select")
@lightbulb.di.with_di
async def points_quick_select(
        ctx: lightbulb.components.MenuContext,
        mongo: MongoClient = lightbulb.di.INJECTED,
        **kwargs
):
    """Quick clan selector with inline point display - categorized by clan type"""

    # Check if user has permission to manage points
    POINTS_MANAGER_ROLE = 1344514130228285450
    if POINTS_MANAGER_ROLE not in ctx.interaction.member.role_ids:
        components = [
            Container(
                accent_color=DARK_MAGENTA_ACCENT,
                components=[
                    Text(content="## ❌ **Permission Denied**"),
                    Text(content="You do not have permission to edit clan points."),
                    Text(content="Only users with the Points Manager role can modify clan points."),
                    Media(items=[MediaItem(media="assets/Red_Footer.png")])
                ]
            )
        ]
        return components

    clan_data = await mongo.clans.find().to_list(length=None)
    clans = [Clan(data=data) for data in clan_data]

    # Categorize clans by type
    competitive_clans = [c for c in clans if c.type == "Competitive"]
    zen_casual_clans = [c for c in clans if c.type in ["Zen", "Casual"]]
    fwa_clans = [c for c in clans if c.type == "FWA"]

    # Sort each category by points descending
    competitive_clans = sorted(competitive_clans, key=lambda c: c.points or 0, reverse=True)
    zen_casual_clans = sorted(zen_casual_clans, key=lambda c: c.points or 0, reverse=True)
    fwa_clans = sorted(fwa_clans, key=lambda c: c.points or 0, reverse=True)

    action_id = str(uuid.uuid4())

    # Helper function to create dropdown options for a category
    def create_options(clan_list, max_clans=24):
        options = []
        seen_tags = {}
        clans_to_show = clan_list[:max_clans]

        for c in clans_to_show:
            description = f"💎 {c.points:.1f} pts • 👥 {c.recruit_count} recruits"

            # Handle duplicate clan tags by making values unique
            if c.tag in seen_tags:
                seen_tags[c.tag] += 1
                unique_value = f"{c.tag}_{seen_tags[c.tag]}"
            else:
                seen_tags[c.tag] = 0
                unique_value = c.tag

            opt_kwargs = {"label": c.name, "value": unique_value, "description": description}
            if getattr(c, "partial_emoji", None):
                opt_kwargs["emoji"] = c.partial_emoji
            options.append(SelectOption(**opt_kwargs))

        return options, len(clan_list) > max_clans

    # Build component list with categorized dropdowns
    component_list = [
        Text(content="## ✏️ **Quick Points Update**"),
        Text(content=(
            "Select a clan from any category below to manage their points and recruit count.\n"
            "Clans are organized by type and sorted by points."
        )),
    ]

    # Add Competitive dropdown if clans exist
    if competitive_clans:
        options, has_overflow = create_options(competitive_clans, max_clans=24)
        overflow_text = f" ({len(competitive_clans) - 24} more not shown)" if has_overflow else ""

        component_list.extend([
            Separator(divider=True, spacing=hikari.SpacingType.SMALL),
            Text(content=f"### <a:AngryGiant:1393193559921918002> **Main/Competitive Clans**{overflow_text}"),
            ActionRow(
                components=[
                    TextSelectMenu(
                        custom_id=f"quick_clan_select:competitive_{action_id}",
                        placeholder="Select a Main/Competitive clan",
                        max_values=1,
                        options=options,
                    )
                ]
            ),
        ])

    # Add Zen & Casual dropdown if clans exist
    if zen_casual_clans:
        options, has_overflow = create_options(zen_casual_clans, max_clans=24)
        overflow_text = f" ({len(zen_casual_clans) - 24} more not shown)" if has_overflow else ""

        component_list.extend([
            Separator(divider=True, spacing=hikari.SpacingType.SMALL),
            Text(content=f"### <:BabyYoda:1390465217997312234> **Zen** & <a:Chill:1393193145927340073> **Casual Clans**{overflow_text}"),
            ActionRow(
                components=[
                    TextSelectMenu(
                        custom_id=f"quick_clan_select:zen_{action_id}",
                        placeholder="Select a Zen/Casual clan",
                        max_values=1,
                        options=options,
                    )
                ]
            ),
        ])

    # Add FWA dropdown if clans exist
    if fwa_clans:
        options, has_overflow = create_options(fwa_clans, max_clans=24)
        overflow_text = f" ({len(fwa_clans) - 24} more not shown)" if has_overflow else ""

        component_list.extend([
            Separator(divider=True, spacing=hikari.SpacingType.SMALL),
            Text(content=f"### <a:FWA:1387882523358527608> **FWA Clans**{overflow_text}"),
            ActionRow(
                components=[
                    TextSelectMenu(
                        custom_id=f"quick_clan_select:fwa_{action_id}",
                        placeholder="Select an FWA clan",
                        max_values=1,
                        options=options,
                    )
                ]
            ),
        ])

    # Add navigation buttons
    component_list.extend([
        ActionRow(
            components=[
                Button(
                    style=hikari.ButtonStyle.SECONDARY,
                    label="Back",
                    emoji="◀️",
                    custom_id="back_to_points_main:",
                ),
            ]
        ),
        Media(items=[MediaItem(media="assets/Blue_Footer.png")]),
    ])

    components = [
        Container(
            accent_color=BLUE_ACCENT,
            components=component_list
        )
    ]

    return components


@register_action("quick_clan_select")
@lightbulb.di.with_di
async def quick_clan_select(
        ctx: lightbulb.components.MenuContext,
        action_id: str = "",
        mongo: MongoClient = lightbulb.di.INJECTED,
        **kwargs
):
    """Streamlined points management for selected clan"""

    # Parse category prefix from action_id (e.g., "competitive_uuid")
    # The category prefix is optional for backwards compatibility
    if "_" in action_id and action_id.split("_")[0] in ["competitive", "zen", "fwa"]:
        category, action_id = action_id.split("_", 1)

    # Check if user has permission to manage points
    POINTS_MANAGER_ROLE = 1344514130228285450
    if POINTS_MANAGER_ROLE not in ctx.interaction.member.role_ids:
        components = [
            Container(
                accent_color=DARK_MAGENTA_ACCENT,
                components=[
                    Text(content="## ❌ **Permission Denied**"),
                    Text(content="You do not have permission to edit clan points."),
                    Text(content="Only users with the Points Manager role can modify clan points."),
                    Media(items=[MediaItem(media="assets/Red_Footer.png")])
                ]
            )
        ]
        return components

    selected_value = ctx.interaction.values[0]

    # Extract original tag from potentially modified value (remove _1, _2 etc.)
    tag = selected_value.split("_")[0] if "_" in selected_value else selected_value

    raw = await mongo.clans.find_one({"tag": tag})
    if not raw:
        return

    clan = Clan(data=raw)

    # Create a visual points bar (optional but nice)
    points_bar = "█" * int(clan.points / 5) + "░" * (20 - int(clan.points / 5))

    components = [
        Container(
            accent_color=GOLD_ACCENT,
            components=[
                Section(
                    components=[
                        Text(content=f"## {clan.emoji if clan.emoji else '🏆'} **{clan.name}**"),
                        Text(content=(
                            f"**Points:** {clan.points:.1f}\n"
                            f"**Recruits:** {clan.recruit_count}\n"
                            f"`[{points_bar}]`"
                        )),
                    ],
                    accessory=Thumbnail(
                        media=clan.logo if clan.logo else "https://cdn-icons-png.flaticon.com/512/845/845665.png"
                    )
                ),

                Separator(divider=True),

                # Quick action buttons in a grid
                Text(content="**Quick Actions**"),
                ActionRow(
                    components=[
                        Button(
                            style=hikari.ButtonStyle.SUCCESS,
                            label="+1",
                            custom_id=f"quick_add:1_{tag}",
                        ),
                        Button(
                            style=hikari.ButtonStyle.SUCCESS,
                            label="+0.5",
                            custom_id=f"quick_add:0.5_{tag}",
                        ),
                        Button(
                            style=hikari.ButtonStyle.DANGER,
                            label="-0.5",
                            custom_id=f"quick_sub:0.5_{tag}",
                        ),
                        Button(
                            style=hikari.ButtonStyle.DANGER,
                            label="-1",
                            custom_id=f"quick_sub:1_{tag}",
                        ),
                    ]
                ),

                # Advanced options
                ActionRow(
                    components=[
                        Button(
                            style=hikari.ButtonStyle.PRIMARY,
                            label="Custom Amount",
                            emoji="🔢",
                            custom_id=f"custom_points:{tag}",
                        ),
                        Button(
                            style=hikari.ButtonStyle.PRIMARY,
                            label="Recruit +1",
                            emoji="👥",
                            custom_id=f"add_recruit_quick:{tag}",
                        ),
                        Button(
                            style=hikari.ButtonStyle.SECONDARY,
                            label="Done",
                            emoji="✅",
                            custom_id="points_quick_select:",
                        ),
                    ]
                ),

                Media(items=[MediaItem(media="assets/Gold_Footer.png")]),
            ]
        )
    ]

    return components


@register_action("quick_add", no_return=True, is_modal=True)
async def quick_add(
        ctx: lightbulb.components.MenuContext,
        action_id: str,
        **kwargs
):
    """Quick add points - opens modal for note"""

    # Check if user has permission to manage points
    POINTS_MANAGER_ROLE = 1344514130228285450
    if POINTS_MANAGER_ROLE not in ctx.interaction.member.role_ids:
        # For modal handlers, we need to respond with a modal anyway
        error_input = ModalActionRow().add_text_input(
            "error",
            "Permission Denied",
            value="You do not have permission to edit clan points.",
            required=False,
            max_length=100
        )
        await ctx.respond_with_modal(
            title="Access Denied",
            custom_id="permission_denied:",
            components=[error_input]
        )
        return

    amount, tag = action_id.split("_", 1)

    note_input = ModalActionRow().add_text_input(
        "note",
        "Note (required)",
        placeholder=f"Reason for adding {amount} points",
        required=True,
        max_length=100
    )

    await ctx.respond_with_modal(
        title=f"Add {amount} Points",
        custom_id=f"quick_add_submit:{amount}_{tag}",
        components=[note_input]
    )


@register_action("quick_add_submit", no_return=True, is_modal=True)
@lightbulb.di.with_di
async def quick_add_submit(
        ctx: lightbulb.components.ModalContext,
        action_id: str,
        mongo: MongoClient = lightbulb.di.INJECTED,
        bot: hikari.GatewayBot = lightbulb.di.INJECTED,
        **kwargs
):
    """Process quick add with note"""
    amount, tag = action_id.split("_", 1)
    amount = float(amount)

    def get_value(custom_id: str) -> str:
        for row in ctx.interaction.components:
            for comp in row:
                if comp.custom_id == custom_id:
                    return comp.value
        return ""

    note = get_value("note").strip()

    if not note:
        await ctx.respond("❌ Note is required!", ephemeral=True)
        return

    # Get clan data for logging
    clan_data = await mongo.clans.find_one({"tag": tag})
    if not clan_data:
        return

    clan = Clan(data=clan_data)
    old_points = clan.points

    # Update points
    await mongo.clans.update_one(
        {"tag": tag},
        {"$inc": {"points": amount}}
    )

    new_points = old_points + amount

    # Log the change
    await log_points_change(
        bot=bot,
        clan=clan,
        change_amount=amount,
        new_total=new_points,
        changed_by=ctx.member,
        note=note
    )

    # Create initial response to defer
    await ctx.interaction.create_initial_response(
        hikari.ResponseType.MESSAGE_UPDATE,
        components=[
            Container(
                accent_color=GREEN_ACCENT,
                components=[
                    Text(content=f"✅ **Added {amount} points!**"),
                    Text(content="*Updating...*"),
                ]
            )
        ]
    )

    # After short delay, refresh the view
    await asyncio.sleep(0.5)

    # Get updated clan data
    raw = await mongo.clans.find_one({"tag": tag})
    if raw:
        clan = Clan(data=raw)

        # Create a visual points bar
        points_bar = "█" * int(clan.points / 5) + "░" * (20 - int(clan.points / 5))

        components = [
            Container(
                accent_color=GOLD_ACCENT,
                components=[
                    Section(
                        components=[
                            Text(content=f"## {clan.emoji if clan.emoji else '🏆'} **{clan.name}**"),
                            Text(content=(
                                f"**Points:** {clan.points:.1f}\n"
                                f"**Recruits:** {clan.recruit_count}\n"
                                f"`[{points_bar}]`"
                            )),
                        ],
                        accessory=Thumbnail(
                            media=clan.logo if clan.logo else "https://cdn-icons-png.flaticon.com/512/845/845665.png"
                        )
                    ),

                    Separator(divider=True),

                    # Quick action buttons in a grid
                    Text(content="**Quick Actions**"),
                    ActionRow(
                        components=[
                            Button(
                                style=hikari.ButtonStyle.SUCCESS,
                                label="+1",
                                custom_id=f"quick_add:1_{tag}",
                            ),
                            Button(
                                style=hikari.ButtonStyle.SUCCESS,
                                label="+0.5",
                                custom_id=f"quick_add:0.5_{tag}",
                            ),
                            Button(
                                style=hikari.ButtonStyle.DANGER,
                                label="-0.5",
                                custom_id=f"quick_sub:0.5_{tag}",
                            ),
                            Button(
                                style=hikari.ButtonStyle.DANGER,
                                label="-1",
                                custom_id=f"quick_sub:1_{tag}",
                            ),
                        ]
                    ),

                    # Advanced options
                    ActionRow(
                        components=[
                            Button(
                                style=hikari.ButtonStyle.PRIMARY,
                                label="Custom Amount",
                                emoji="🔢",
                                custom_id=f"custom_points:{tag}",
                            ),
                            Button(
                                style=hikari.ButtonStyle.PRIMARY,
                                label="Recruit +1",
                                emoji="👥",
                                custom_id=f"add_recruit_quick:{tag}",
                            ),
                            Button(
                                style=hikari.ButtonStyle.SECONDARY,
                                label="Done",
                                emoji="✅",
                                custom_id="points_quick_select:",
                            ),
                        ]
                    ),

                    Media(items=[MediaItem(media="assets/Gold_Footer.png")]),
                ]
            )
        ]

        await ctx.interaction.edit_initial_response(components=components)


@register_action("quick_sub", no_return=True, is_modal=True)
async def quick_sub(
        ctx: lightbulb.components.MenuContext,
        action_id: str,
        **kwargs
):
    """Quick subtract points - opens modal for note"""

    # Check if user has permission to manage points
    POINTS_MANAGER_ROLE = 1344514130228285450
    if POINTS_MANAGER_ROLE not in ctx.interaction.member.role_ids:
        # For modal handlers, we need to respond with a modal anyway
        error_input = ModalActionRow().add_text_input(
            "error",
            "Permission Denied",
            value="You do not have permission to edit clan points.",
            required=False,
            max_length=100
        )
        await ctx.respond_with_modal(
            title="Access Denied",
            custom_id="permission_denied:",
            components=[error_input]
        )
        return

    amount, tag = action_id.split("_", 1)

    note_input = ModalActionRow().add_text_input(
        "note",
        "Note (required)",
        placeholder=f"Reason for removing {amount} points",
        required=True,
        max_length=100
    )

    await ctx.respond_with_modal(
        title=f"Remove {amount} Points",
        custom_id=f"quick_sub_submit:{amount}_{tag}",
        components=[note_input]
    )


@register_action("quick_sub_submit", no_return=True, is_modal=True)
@lightbulb.di.with_di
async def quick_sub_submit(
        ctx: lightbulb.components.ModalContext,
        action_id: str,
        mongo: MongoClient = lightbulb.di.INJECTED,
        bot: hikari.GatewayBot = lightbulb.di.INJECTED,
        **kwargs
):
    """Process quick subtract with note"""
    amount, tag = action_id.split("_", 1)
    amount = float(amount)

    def get_value(custom_id: str) -> str:
        for row in ctx.interaction.components:
            for comp in row:
                if comp.custom_id == custom_id:
                    return comp.value
        return ""

    note = get_value("note").strip()

    if not note:
        await ctx.respond("❌ Note is required!", ephemeral=True)
        return

    # Get clan data
    clan_data = await mongo.clans.find_one({"tag": tag})
    if not clan_data:
        return

    clan = Clan(data=clan_data)
    old_points = clan.points

    # Check if we're trying to subtract more than available
    if amount > old_points:
        await ctx.respond(
            f"❌ Cannot subtract {amount} points! Clan only has {old_points} points.",
            ephemeral=True
        )
        return

    # Make sure we don't go negative
    new_points = max(0, old_points - amount)
    actual_change = old_points - new_points  # Actual amount reduced

    await mongo.clans.update_one(
        {"tag": tag},
        {"$set": {"points": new_points}}
    )

    # Log the change (negative value for reduction)
    if actual_change > 0:
        await log_points_change(
            bot=bot,
            clan=clan,
            change_amount=-actual_change,
            new_total=new_points,
            changed_by=ctx.member,
            note=note
        )

    # Create initial response
    await ctx.interaction.create_initial_response(
        hikari.ResponseType.MESSAGE_UPDATE,
        components=[
            Container(
                accent_color=GREEN_ACCENT,
                components=[
                    Text(content=f"✅ **Removed {actual_change} points!**"),
                    Text(content="*Updating...*"),
                ]
            )
        ]
    )

    # After short delay, refresh the view
    await asyncio.sleep(0.5)

    # Get updated clan data
    raw = await mongo.clans.find_one({"tag": tag})
    if raw:
        clan = Clan(data=raw)

        # Create a visual points bar
        points_bar = "█" * int(clan.points / 5) + "░" * (20 - int(clan.points / 5))

        components = [
            Container(
                accent_color=GOLD_ACCENT,
                components=[
                    Section(
                        components=[
                            Text(content=f"## {clan.emoji if clan.emoji else '🏆'} **{clan.name}**"),
                            Text(content=(
                                f"**Points:** {clan.points:.1f}\n"
                                f"**Recruits:** {clan.recruit_count}\n"
                                f"`[{points_bar}]`"
                            )),
                        ],
                        accessory=Thumbnail(
                            media=clan.logo if clan.logo else "https://cdn-icons-png.flaticon.com/512/845/845665.png"
                        )
                    ),

                    Separator(divider=True),

                    # Quick action buttons in a grid
                    Text(content="**Quick Actions**"),
                    ActionRow(
                        components=[
                            Button(
                                style=hikari.ButtonStyle.SUCCESS,
                                label="+1",
                                custom_id=f"quick_add:1_{tag}",
                            ),
                            Button(
                                style=hikari.ButtonStyle.SUCCESS,
                                label="+0.5",
                                custom_id=f"quick_add:0.5_{tag}",
                            ),
                            Button(
                                style=hikari.ButtonStyle.DANGER,
                                label="-0.5",
                                custom_id=f"quick_sub:0.5_{tag}",
                            ),
                            Button(
                                style=hikari.ButtonStyle.DANGER,
                                label="-1",
                                custom_id=f"quick_sub:1_{tag}",
                            ),
                        ]
                    ),

                    # Advanced options
                    ActionRow(
                        components=[
                            Button(
                                style=hikari.ButtonStyle.PRIMARY,
                                label="Custom Amount",
                                emoji="🔢",
                                custom_id=f"custom_points:{tag}",
                            ),
                            Button(
                                style=hikari.ButtonStyle.PRIMARY,
                                label="Recruit +1",
                                emoji="👥",
                                custom_id=f"add_recruit_quick:{tag}",
                            ),
                            Button(
                                style=hikari.ButtonStyle.SECONDARY,
                                label="Done",
                                emoji="✅",
                                custom_id="points_quick_select:",
                            ),
                        ]
                    ),

                    Media(items=[MediaItem(media="assets/Gold_Footer.png")]),
                ]
            )
        ]

        await ctx.interaction.edit_initial_response(components=components)


@register_action("custom_points", no_return=True, is_modal=True)
async def custom_points_modal(
        ctx: lightbulb.components.MenuContext,
        action_id: str,
        **kwargs
):
    """Modern modal for custom points"""

    # Check if user has permission to manage points
    POINTS_MANAGER_ROLE = 1344514130228285450
    if POINTS_MANAGER_ROLE not in ctx.interaction.member.role_ids:
        # For modal handlers, we need to respond with a modal anyway
        error_input = ModalActionRow().add_text_input(
            "error",
            "Permission Denied",
            value="You do not have permission to edit clan points.",
            required=False,
            max_length=100
        )
        await ctx.respond_with_modal(
            title="Access Denied",
            custom_id="permission_denied:",
            components=[error_input]
        )
        return

    tag = action_id

    amount_input = ModalActionRow().add_text_input(
        "amount",
        "Points to add/subtract (optional)",
        placeholder="Use + or - (e.g., +5.5 or -2) Max: ±50",
        required=False,
        max_length=10
    )

    recruit_input = ModalActionRow().add_text_input(
        "recruits",
        "Recruits to add/subtract (optional)",
        placeholder="Use + or - (e.g., +1 or -1)",
        required=False,
        max_length=10
    )

    note_input = ModalActionRow().add_text_input(
        "note",
        "Note (required)",
        placeholder="Reason for change (required)",
        required=True,
        max_length=100
    )

    await ctx.respond_with_modal(
        title="Adjust Clan Points & Recruits",
        custom_id=f"custom_points_submit:{tag}",
        components=[amount_input, recruit_input, note_input]
    )


@register_action("custom_points_submit", no_return=True, is_modal=True)
@lightbulb.di.with_di
async def custom_points_submit(
        ctx: lightbulb.components.ModalContext,
        action_id: str,
        mongo: MongoClient = lightbulb.di.INJECTED,
        bot: hikari.GatewayBot = lightbulb.di.INJECTED,
        **kwargs
):
    """Process custom points modal"""
    tag = action_id

    def get_value(custom_id: str) -> str:
        for row in ctx.interaction.components:
            for comp in row:
                if comp.custom_id == custom_id:
                    return comp.value
        return ""

    amount_str = get_value("amount").strip()
    recruit_str = get_value("recruits").strip()
    note = get_value("note").strip()

    # Validate note is provided
    if not note:
        await ctx.respond(
            "❌ Note is required! Please provide a reason for the change.",
            ephemeral=True
        )
        return

    # Check if at least one change is being made
    if not amount_str and not recruit_str:
        await ctx.respond(
            "❌ Please enter either points or recruits to change (or both).",
            ephemeral=True
        )
        return

    try:
        # Parse amount if provided
        amount = 0
        if amount_str:
            if amount_str.startswith('+'):
                amount = float(amount_str[1:])
            elif amount_str.startswith('-'):
                amount = -float(amount_str[1:])
            else:
                amount = float(amount_str)

            # Validate amount is within limits
            if abs(amount) > 50:
                await ctx.respond(
                    "❌ Point changes are limited to ±50 points maximum!",
                    ephemeral=True
                )
                return

        # Parse recruits if provided
        recruit_change = 0
        if recruit_str:
            if recruit_str.startswith('+'):
                recruit_change = int(recruit_str[1:])
            elif recruit_str.startswith('-'):
                recruit_change = -int(recruit_str[1:])
            else:
                recruit_change = int(recruit_str)

        # Get clan data
        clan_data = await mongo.clans.find_one({"tag": tag})
        if not clan_data:
            return

        clan = Clan(data=clan_data)
        old_points = clan.points
        old_recruits = clan.recruit_count

        # Check if we're trying to subtract more points than available
        if amount < 0 and abs(amount) > old_points:
            await ctx.respond(
                f"❌ Cannot subtract {abs(amount)} points! Clan only has {old_points} points.",
                ephemeral=True
            )
            return

        # Check if we're trying to subtract more recruits than available
        if recruit_change < 0 and abs(recruit_change) > old_recruits:
            await ctx.respond(
                f"❌ Cannot subtract {abs(recruit_change)} recruits! Clan only has {old_recruits} recruits.",
                ephemeral=True
            )
            return

        new_points = max(0, old_points + amount)
        new_recruits = max(0, old_recruits + recruit_change)
        actual_points_change = new_points - old_points  # Account for 0 floor
        actual_recruit_change = new_recruits - old_recruits

        # Update database
        update_data = {}
        if actual_points_change != 0:
            update_data["points"] = new_points
        if actual_recruit_change != 0:
            update_data["recruit_count"] = new_recruits

        if update_data:
            await mongo.clans.update_one(
                {"tag": tag},
                {"$set": update_data}
            )

        # Log the points change if any
        if actual_points_change != 0:
            await log_points_change(
                bot=bot,
                clan=clan,
                change_amount=actual_points_change,
                new_total=new_points,
                changed_by=ctx.member,
                note=note
            )

        # Build success message
        success_lines = ["✅ **Updates Applied!**"]
        if actual_points_change != 0:
            success_lines.append(f"Points: {actual_points_change:+.1f} (New total: {new_points:.1f})")
        if actual_recruit_change != 0:
            success_lines.append(f"Recruits: {actual_recruit_change:+d} (New total: {new_recruits})")
        success_lines.append(f"\n*Note: {note}*")

        # Success feedback
        await ctx.interaction.create_initial_response(
            hikari.ResponseType.MESSAGE_UPDATE,
            components=[
                Container(
                    accent_color=GREEN_ACCENT,
                    components=[
                        Text(content="\n".join(success_lines))
                    ]
                )
            ]
        )

        # Refresh after delay
        await asyncio.sleep(1.5)

        # Get the updated clan data to show refreshed view
        raw = await mongo.clans.find_one({"tag": tag})
        if raw:
            clan = Clan(data=raw)

            # Create a visual points bar
            points_bar = "█" * int(clan.points / 5) + "░" * (20 - int(clan.points / 5))

            components = [
                Container(
                    accent_color=GOLD_ACCENT,
                    components=[
                        Section(
                            components=[
                                Text(content=f"## {clan.emoji if clan.emoji else '🏆'} **{clan.name}**"),
                                Text(content=(
                                    f"**Points:** {clan.points:.1f}\n"
                                    f"**Recruits:** {clan.recruit_count}\n"
                                    f"`[{points_bar}]`"
                                )),
                            ],
                            accessory=Thumbnail(
                                media=clan.logo if clan.logo else "https://cdn-icons-png.flaticon.com/512/845/845665.png"
                            )
                        ),

                        Separator(divider=True),

                        # Quick action buttons in a grid
                        Text(content="**Quick Actions**"),
                        ActionRow(
                            components=[
                                Button(
                                    style=hikari.ButtonStyle.SUCCESS,
                                    label="+1",
                                    custom_id=f"quick_add:1_{tag}",
                                ),
                                Button(
                                    style=hikari.ButtonStyle.SUCCESS,
                                    label="+0.5",
                                    custom_id=f"quick_add:0.5_{tag}",
                                ),
                                Button(
                                    style=hikari.ButtonStyle.DANGER,
                                    label="-0.5",
                                    custom_id=f"quick_sub:0.5_{tag}",
                                ),
                                Button(
                                    style=hikari.ButtonStyle.DANGER,
                                    label="-1",
                                    custom_id=f"quick_sub:1_{tag}",
                                ),
                            ]
                        ),

                        # Advanced options
                        ActionRow(
                            components=[
                                Button(
                                    style=hikari.ButtonStyle.PRIMARY,
                                    label="Custom Amount",
                                    emoji="🔢",
                                    custom_id=f"custom_points:{tag}",
                                ),
                                Button(
                                    style=hikari.ButtonStyle.PRIMARY,
                                    label="Recruit +1",
                                    emoji="👥",
                                    custom_id=f"add_recruit_quick:{tag}",
                                ),
                                Button(
                                    style=hikari.ButtonStyle.SECONDARY,
                                    label="Done",
                                    emoji="✅",
                                    custom_id="points_quick_select:",
                                ),
                            ]
                        ),

                        Media(items=[MediaItem(media="assets/Gold_Footer.png")]),
                    ]
                )
            ]

            await ctx.interaction.edit_initial_response(components=components)

    except ValueError:
        await ctx.respond(
            "❌ Invalid input! Points format: +5, -2.5, or 10 (max ±50)\nRecruits must be whole numbers.",
            ephemeral=True
        )


@register_action("add_recruit_quick", no_return=True, is_modal=True)
async def add_recruit_quick(
        ctx: lightbulb.components.MenuContext,
        action_id: str,
        **kwargs
):
    """Quick add recruit - opens modal for note"""

    # Check if user has permission to manage points
    POINTS_MANAGER_ROLE = 1344514130228285450
    if POINTS_MANAGER_ROLE not in ctx.interaction.member.role_ids:
        # For modal handlers, we need to respond with a modal anyway
        error_input = ModalActionRow().add_text_input(
            "error",
            "Permission Denied",
            value="You do not have permission to edit clan points.",
            required=False,
            max_length=100
        )
        await ctx.respond_with_modal(
            title="Access Denied",
            custom_id="permission_denied:",
            components=[error_input]
        )
        return

    tag = action_id

    note_input = ModalActionRow().add_text_input(
        "note",
        "Note (required)",
        placeholder="Who did they recruit? (required)",
        required=True,
        max_length=100
    )

    await ctx.respond_with_modal(
        title="Add Recruit",
        custom_id=f"add_recruit_submit:{tag}",
        components=[note_input]
    )


@register_action("add_recruit_submit", no_return=True, is_modal=True)
@lightbulb.di.with_di
async def add_recruit_submit(
        ctx: lightbulb.components.ModalContext,
        action_id: str,
        mongo: MongoClient = lightbulb.di.INJECTED,
        bot: hikari.GatewayBot = lightbulb.di.INJECTED,
        **kwargs
):
    """Process recruit add with note"""
    tag = action_id

    def get_value(custom_id: str) -> str:
        for row in ctx.interaction.components:
            for comp in row:
                if comp.custom_id == custom_id:
                    return comp.value
        return ""

    note = get_value("note").strip()

    if not note:
        await ctx.respond("❌ Note is required!", ephemeral=True)
        return

    # Update recruit count
    await mongo.clans.update_one(
        {"tag": tag},
        {"$inc": {"recruit_count": 1}}
    )

    # Get updated clan data
    clan_data = await mongo.clans.find_one({"tag": tag})
    if not clan_data:
        return

    clan = Clan(data=clan_data)

    # Create initial response
    await ctx.interaction.create_initial_response(
        hikari.ResponseType.MESSAGE_UPDATE,
        components=[
            Container(
                accent_color=GREEN_ACCENT,
                components=[
                    Text(content=f"✅ **Recruit added!**"),
                    Text(content=f"*Note: {note}*"),
                    Text(content="*Updating...*"),
                ]
            )
        ]
    )

    # After short delay, refresh the view
    await asyncio.sleep(0.5)

    # Create a visual points bar
    points_bar = "█" * int(clan.points / 5) + "░" * (20 - int(clan.points / 5))

    components = [
        Container(
            accent_color=GOLD_ACCENT,
            components=[
                Section(
                    components=[
                        Text(content=f"## {clan.emoji if clan.emoji else '🏆'} **{clan.name}**"),
                        Text(content=(
                            f"**Points:** {clan.points:.1f}\n"
                            f"**Recruits:** {clan.recruit_count}\n"
                            f"`[{points_bar}]`"
                        )),
                    ],
                    accessory=Thumbnail(
                        media=clan.logo if clan.logo else "https://cdn-icons-png.flaticon.com/512/845/845665.png"
                    )
                ),

                Separator(divider=True),

                # Quick action buttons in a grid
                Text(content="**Quick Actions**"),
                ActionRow(
                    components=[
                        Button(
                            style=hikari.ButtonStyle.SUCCESS,
                            label="+1",
                            custom_id=f"quick_add:1_{tag}",
                        ),
                        Button(
                            style=hikari.ButtonStyle.SUCCESS,
                            label="+0.5",
                            custom_id=f"quick_add:0.5_{tag}",
                        ),
                        Button(
                            style=hikari.ButtonStyle.DANGER,
                            label="-0.5",
                            custom_id=f"quick_sub:0.5_{tag}",
                        ),
                        Button(
                            style=hikari.ButtonStyle.DANGER,
                            label="-1",
                            custom_id=f"quick_sub:1_{tag}",
                        ),
                    ]
                ),

                # Advanced options
                ActionRow(
                    components=[
                        Button(
                            style=hikari.ButtonStyle.PRIMARY,
                            label="Custom Amount",
                            emoji="🔢",
                            custom_id=f"custom_points:{tag}",
                        ),
                        Button(
                            style=hikari.ButtonStyle.PRIMARY,
                            label="Recruit +1",
                            emoji="👥",
                            custom_id=f"add_recruit_quick:{tag}",
                        ),
                        Button(
                            style=hikari.ButtonStyle.SECONDARY,
                            label="Done",
                            emoji="✅",
                            custom_id="points_quick_select:",
                        ),
                    ]
                ),

                Media(items=[MediaItem(media="assets/Gold_Footer.png")]),
            ]
        )
    ]

    await ctx.interaction.edit_initial_response(components=components)


@register_action("recruitment_overview")
@lightbulb.di.with_di
async def recruitment_overview(
        ctx: lightbulb.components.MenuContext,
        mongo: MongoClient = lightbulb.di.INJECTED,
        **kwargs
):
    """Show recruitment statistics overview"""

    clan_data = await mongo.clans.find().to_list(length=None)
    clans = [Clan(data=data) for data in clan_data]

    # Sort by recruit count
    sorted_by_recruits = sorted(clans, key=lambda c: c.recruit_count, reverse=True)

    # Build recruit leaderboard
    recruit_lines = []
    for i, clan in enumerate(sorted_by_recruits[:10], 1):
        if clan.recruit_count > 0:
            emoji = clan.emoji if clan.emoji else ""
            recruit_lines.append(
                f"`{i:2d}` {emoji} **{clan.name}** • {clan.recruit_count} recruits"
            )

    components = [
        Container(
            accent_color=BLUE_ACCENT,
            components=[
                Text(content="## 📈 **Recruitment Statistics**"),
                Separator(divider=True),
                Text(content=format_recruit_summary(clans)),
                Separator(divider=True),
                Text(content="### 👥 **Top Recruiting Clans**"),
                Text(content="\n".join(recruit_lines) if recruit_lines else "*No recruits this month*"),

                ActionRow(
                    components=[
                        Button(
                            style=hikari.ButtonStyle.SECONDARY,
                            label="Back",
                            emoji="◀️",
                            custom_id="back_to_points_main:",
                        ),
                    ]
                ),

                Media(items=[MediaItem(media="assets/Blue_Footer.png")]),
            ]
        )
    ]

    return components


@register_action("month_reset", ephemeral=True)
@lightbulb.di.with_di
async def month_reset_confirm(
        ctx: lightbulb.components.MenuContext,
        mongo: MongoClient = lightbulb.di.INJECTED,
        **kwargs
):
    """Confirm monthly reset"""

    clans = await mongo.clans.find().to_list(length=None)
    total_points = sum(c.get("points", 0) for c in clans)
    clans_affected = sum(1 for c in clans if c.get("points", 0) > 0)

    components = [
        Container(
            accent_color=DARK_MAGENTA_ACCENT,
            components=[
                Text(content="## 🔄 **Monthly Reset**"),
                Separator(divider=True),
                Text(content=(
                    "**This will:**\n"
                    "• 25% of current points (rounded up), or 10, whichever is less.\n"
                    "• Reset all recruit counts to 0\n\n"
                    f"**Clans affected:** {clans_affected}\n"
                    f"**Total points before reset:** {total_points:.1f}"
                )),

                ActionRow(
                    components=[
                        Button(
                            style=hikari.ButtonStyle.DANGER,
                            label="Confirm Reset",
                            emoji="⚠️",
                            custom_id="confirm_month_reset:",
                        ),
                        Button(
                            style=hikari.ButtonStyle.SECONDARY,
                            label="Cancel",
                            custom_id="back_to_points_main:",
                        ),
                    ]
                ),

                Media(items=[MediaItem(media="assets/Red_Footer.png")]),
            ]
        )
    ]

    return components


@register_action("confirm_month_reset", ephemeral=True)
@lightbulb.di.with_di
async def confirm_month_reset(
        ctx: lightbulb.components.MenuContext,
        mongo: MongoClient = lightbulb.di.INJECTED,
        **kwargs
):
    """Execute monthly reset"""

    clans = await mongo.clans.find().to_list(length=None)

    changes = []
    for clan in clans:
        old_points = clan.get("points", 0)
        if old_points > 0:
            twenty_five_percent = math.ceil(old_points * 0.25)
            new_points = min(twenty_five_percent, 10)
            await mongo.clans.update_one(
                {"tag": clan["tag"]},
                {"$set": {"points": new_points}}
            )

            changes.append(f"{clan['name']}: {old_points:.1f} → {new_points:.1f}")

    # Reset all recruit counts
    await mongo.clans.update_many({}, {"$set": {"recruit_count": 0}})

    components = [
        Container(
            accent_color=GREEN_ACCENT,
            components=[
                Text(content="## ✅ **Monthly Reset Complete**"),
                Separator(divider=True),
                Text(content=(
                    f"**Reset {len(changes)} clans**\n"
                    "• Points reduced to 25% of previous value (rounded up), or 10, whichever is less.\n"
                    "• All recruit counts reset to 0\n\n"
                    f"Reset performed by: {ctx.member.mention}"
                )),

                ActionRow(
                    components=[
                        Button(
                            style=hikari.ButtonStyle.SUCCESS,
                            label="View Updated Stats",
                            custom_id="back_to_points_main:",
                        ),
                    ]
                ),

                Media(items=[MediaItem(media="assets/Green_Footer.png")]),
            ]
        )
    ]

    return components


@register_action("back_to_points_main")
@lightbulb.di.with_di
async def back_to_points_main(
        ctx: lightbulb.components.MenuContext,
        mongo: MongoClient = lightbulb.di.INJECTED,
        **kwargs
):
    """Return to main points view"""
    return await clan_points_main(ctx=ctx, mongo=mongo)