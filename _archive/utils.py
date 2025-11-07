# extensions/commands/clan/report/utils.py
"""Utility functions for clan points reporting"""

import re
import hikari
from typing import Optional, Dict, List
from datetime import datetime

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

from utils.constants import GOLD_ACCENT, BLUE_ACCENT, GREEN_ACCENT, RED_ACCENT, MAGENTA_ACCENT
from utils.mongo import MongoClient
from utils.classes import Clan

# Channel IDs
APPROVAL_CHANNEL = 1436169940120899704
LOG_CHANNEL = 1436169870273413169

# Regex for Discord message links
DISCORD_LINK_REGEX = re.compile(r"https://discord\.com/channels/(\d+)/(\d+)/(\d+)")


async def create_home_dashboard(member: hikari.Member) -> List[Container]:
    """Create the home dashboard for reporting"""
    return [
        Container(
            accent_color=GOLD_ACCENT,
            components=[
                # Clear title and instructions
                Text(content="## 📊 Report Clan Points"),
                Text(content="*Choose how you recruited a new member:*"),

                # Visual card-style buttons
                ActionRow(
                    components=[
                        Button(
                            style=hikari.ButtonStyle.PRIMARY,
                            label="Discord Post",
                            emoji="💬",
                            custom_id=f"report_type:discord_post_{member.id}"
                        ),
                        Button(
                            style=hikari.ButtonStyle.PRIMARY,
                            label="DM Recruitment",
                            emoji="📩",
                            custom_id=f"report_type:dm_recruit_{member.id}"
                        )
                    ]
                ),

                # Status for "Member Left" button
                ActionRow(
                    components=[
                        Button(
                            style=hikari.ButtonStyle.SECONDARY,
                            label="Member Left",
                            emoji="👋",
                            custom_id=f"report_type:member_left_{member.id}",
                            is_disabled=True
                        )
                    ]
                ),

                # Help section
                Separator(divider=True),
                Text(content=(
                    "**📌 Quick Guide:**\n"
                    "• **Discord Post** - You recruited via a public Discord message\n"
                    "• **DM Recruitment** - You recruited via DMs (requires screenshot)\n"
                    "• **Member Left** - *(Coming soon)*\n\n"
                    "-# Points are awarded after leadership approval"
                )),

                Media(items=[MediaItem(media="assets/Gold_Footer.png")])
            ]
        )
    ]


def parse_discord_link(link: str) -> Optional[Dict[str, int]]:
    """Parse a Discord message link into its components"""
    match = DISCORD_LINK_REGEX.match(link.strip())
    if match:
        return {
            "guild_id": int(match.group(1)),
            "channel_id": int(match.group(2)),
            "message_id": int(match.group(3))
        }
    return None


async def get_clan_options(mongo: MongoClient) -> List[SelectOption]:
    """Get clan options for select menu"""
    clan_data = await mongo.clans.find().to_list(length=None)
    clans = [Clan(data=data) for data in clan_data]

    # Sort alphabetically
    sorted_clans = sorted(clans, key=lambda c: c.name)

    options = []
    for clan in sorted_clans[:25]:  # Discord limit
        kwargs = {
            "label": clan.name,
            "value": clan.tag,
            "description": f"Points: {clan.points:.1f}"
        }
        if clan.partial_emoji:
            kwargs["emoji"] = clan.partial_emoji

        options.append(SelectOption(**kwargs))

    return options


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