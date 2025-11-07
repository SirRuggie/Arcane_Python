# extensions/commands/clan/report/helpers.py
"""Helper functions for clan report system"""

import re
from typing import Optional, List, Dict
from datetime import datetime

import hikari
from hikari.impl import (
    SelectOptionBuilder as SelectOption,
    MessageActionRowBuilder as ActionRow,
    TextSelectMenuBuilder as TextSelectMenu,
    SeparatorComponentBuilder as Separator,
    TextDisplayComponentBuilder as Text,
)

from utils.mongo import MongoClient
from utils.classes import Clan

# Channel IDs
APPROVAL_CHANNEL = 1436169940120899704
LOG_CHANNEL = 1436169870273413169
RECRUITMENT_PING = 1039311270614142977
# Regex for Discord message links
DISCORD_LINK_REGEX = re.compile(r"https://discord\.com/channels/(\d+)/(\d+)/(\d+)")

# ╔══════════════════════════════════════════════════════════════╗
# ║                Progress Header Creation Utility              ║
# ╚══════════════════════════════════════════════════════════════╝

def create_progress_header(current_step: int, total_steps: int, steps: List[str]) -> str:
    """Create a progress indicator header"""
    parts = []
    for i, step in enumerate(steps):
        if i < current_step - 1:
            parts.append(f"{step} ✓")
        elif i == current_step - 1:
            parts.append(f"**{step}**")
        else:
            parts.append(step)

    return f"**Step {current_step} of {total_steps}** • " + " → ".join(parts)

# ╔══════════════════════════════════════════════════════════════╗
# ║                Parse Discord Link Utility                    ║
# ╚══════════════════════════════════════════════════════════════╝

def parse_discord_link(link: str) -> Optional[dict]:
    """Parse a Discord message link"""
    match = DISCORD_LINK_REGEX.match(link.strip())
    if match:
        return {
            "guild_id": int(match.group(1)),
            "channel_id": int(match.group(2)),
            "message_id": int(match.group(3))
        }
    return None

# ╔══════════════════════════════════════════════════════════════╗
# ║                Validate Discord ID Utility                   ║
# ╚══════════════════════════════════════════════════════════════╝

def validate_discord_id(discord_id: str) -> bool:
    """Validate a Discord user ID"""
    try:
        # Discord IDs are 17-19 digit numbers
        id_int = int(discord_id)
        return 10 ** 16 <= id_int < 10 ** 19
    except ValueError:
        return False

# ╔══════════════════════════════════════════════════════════════╗
# ║                   Get Clan By Tag Utility                    ║
# ╚══════════════════════════════════════════════════════════════╝

async def get_clan_by_tag(mongo: MongoClient, tag: str) -> Optional[Clan]:
    """Get clan data by tag"""
    clan_data = await mongo.clans.find_one({"tag": tag})
    if clan_data:
        return Clan(data=clan_data)
    return None

# ╔══════════════════════════════════════════════════════════════╗
# ║                  Get Clan Options Utility                    ║
# ╚══════════════════════════════════════════════════════════════╝

async def get_clan_options(mongo: MongoClient) -> List[SelectOption]:
    """Get clan options for select menu"""
    clan_data = await mongo.clans.find().to_list(length=None)
    clans = [Clan(data=data) for data in clan_data]

    # Use clans directly without sorting
    options = []
    seen_tags = {}
    for clan in clans[:25]:  # Discord limit
        # Handle duplicate clan tags by making values unique
        if clan.tag in seen_tags:
            seen_tags[clan.tag] += 1
            unique_value = f"{clan.tag}_{seen_tags[clan.tag]}"
        else:
            seen_tags[clan.tag] = 0
            unique_value = clan.tag

        kwargs = {
            "label": clan.name,
            "value": unique_value,
            "description": f"Points: {clan.points:.1f}"
        }
        if clan.partial_emoji:
            kwargs["emoji"] = clan.partial_emoji

        options.append(SelectOption(**kwargs))

    return options

# ╔══════════════════════════════════════════════════════════════╗
# ║           Get Categorized Clan Components Utility            ║
# ╚══════════════════════════════════════════════════════════════╝

async def get_categorized_clan_components(
    custom_id_prefix: str,
    action_id_suffix: str,
    mongo: MongoClient
) -> List:
    """
    Get categorized clan dropdown components

    Args:
        custom_id_prefix: The action name (e.g., "dr_select_clan")
        action_id_suffix: The suffix for action_id (e.g., user_id)
        mongo: MongoDB client

    Returns:
        List of components (Separator, Text, ActionRow) for categorized dropdowns
    """
    # Fetch all clans
    clan_data = await mongo.clans.find().to_list(length=None)
    clans = [Clan(data=d) for d in clan_data]

    # Categorize clans by type (trial clans show in their type category)
    competitive_clans = [c for c in clans if c.type == "Competitive"]
    zen_casual_clans = [c for c in clans if c.type in ["Zen", "Casual"]]
    fwa_clans = [c for c in clans if c.type == "FWA"]

    # Sort each category by points (activity)
    competitive_clans = sorted(competitive_clans, key=lambda c: c.points or 0, reverse=True)
    zen_casual_clans = sorted(zen_casual_clans, key=lambda c: c.points or 0, reverse=True)
    fwa_clans = sorted(fwa_clans, key=lambda c: c.points or 0, reverse=True)

    # Helper function to create dropdown options for a category
    def create_options(clan_list, max_clans=25):
        options = []
        seen_tags = {}
        clans_to_show = clan_list[:max_clans]

        for c in clans_to_show:
            # Handle duplicate clan tags by making values unique
            if c.tag in seen_tags:
                seen_tags[c.tag] += 1
                unique_value = f"{c.tag}_{seen_tags[c.tag]}"
            else:
                seen_tags[c.tag] = 0
                unique_value = c.tag

            kwargs = {
                "label": c.name,
                "value": unique_value,
                "description": f"Points: {c.points:.1f}"
            }
            if getattr(c, "partial_emoji", None):
                kwargs["emoji"] = c.partial_emoji
            options.append(SelectOption(**kwargs))

        return options, len(clan_list) > max_clans

    # Build component list
    component_list = []

    # Add Main/Competitive dropdown if clans exist
    if competitive_clans:
        options, has_overflow = create_options(competitive_clans, max_clans=24)
        overflow_text = f" ({len(competitive_clans) - 24} more not shown)" if has_overflow else ""

        component_list.extend([
            Separator(divider=True, spacing=hikari.SpacingType.SMALL),
            Text(content=f"### <a:AngryGiant:1393193559921918002> **Main/Competitive Clans**{overflow_text}"),
            ActionRow(
                components=[
                    TextSelectMenu(
                        custom_id=f"{custom_id_prefix}:competitive_{action_id_suffix}",
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
                        custom_id=f"{custom_id_prefix}:zen_{action_id_suffix}",
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
                        custom_id=f"{custom_id_prefix}:fwa_{action_id_suffix}",
                        placeholder="Select an FWA clan",
                        max_values=1,
                        options=options,
                    )
                ]
            ),
        ])

    return component_list

# ╔══════════════════════════════════════════════════════════════╗
# ║               Create Submission Data Utility                 ║
# ╚══════════════════════════════════════════════════════════════╝

async def create_submission_data(
        submission_type: str,
        clan: Clan,
        user: hikari.User,
        **kwargs
) -> Dict:
    """Create standardized submission data for approval"""
    return {
        "submission_id": f"{clan.tag}_{user.id}_{int(datetime.now().timestamp())}",
        "type": submission_type,
        "clan_tag": clan.tag,
        "clan_name": clan.name,
        "clan_logo": clan.logo or "https://cdn-icons-png.flaticon.com/512/845/845665.png",
        "user_id": str(user.id),
        "user_mention": f"<@{user.id}>",
        "timestamp": int(datetime.now().timestamp()),
        **kwargs
    }