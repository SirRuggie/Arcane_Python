# extensions/commands/clan/info_hub/handlers.py

import hikari
import lightbulb
import coc
from typing import List, Optional
from datetime import datetime

from hikari import Emoji
from hikari.impl import (
    MessageActionRowBuilder as ActionRow,
    ContainerComponentBuilder as Container,
    InteractiveButtonBuilder as Button,
    TextDisplayComponentBuilder as Text,
    SeparatorComponentBuilder as Separator,
    MediaGalleryComponentBuilder as Media,
    MediaGalleryItemBuilder as MediaItem,
    LinkButtonBuilder as LinkButton,
    SectionComponentBuilder as Section,
    ThumbnailComponentBuilder as Thumbnail,
)

from extensions.components import register_action
from utils.mongo import MongoClient
from utils.classes import Clan
from utils.constants import DARK_MAGENTA_ACCENT, GOLD_ACCENT, BLUE_ACCENT, GREEN_ACCENT, MAGENTA_ACCENT
from .helpers import get_clans_by_type, format_th_requirement, get_league_emoji
from utils.emoji import emojis

# League order for sorting
LEAGUE_ORDER = [
    "Champion League I", "Champion League II", "Champion League III",
    "Master League I", "Master League II", "Master League III",
    "Crystal League I", "Crystal League II", "Crystal League III",
    "Gold League I", "Gold League II", "Gold League III",
    "Silver League I", "Silver League II", "Silver League III",
    "Bronze League I", "Bronze League II", "Bronze League III",
    "Unranked"
]

BANNERS = {
    "Competitive": "https://res.cloudinary.com/dxmtzuomk/image/upload/v1763220421/server_banners/Competitive.png",
    "Casual": "https://res.cloudinary.com/dxmtzuomk/image/upload/v1763220417/server_banners/Casual.png",
    "Zen": "https://res.cloudinary.com/dxmtzuomk/image/upload/v1763220418/server_banners/Zen.png",
    "FWA": "https://res.cloudinary.com/dxmtzuomk/image/upload/v1763222405/server_banners/FWA.png",
    "Trial": "https://res.cloudinary.com/dxmtzuomk/image/upload/v1763222428/server_banners/TrialClans.png"
}


async def build_clan_list_components(
        ctx: lightbulb.components.MenuContext,
        clan_type: str,
        accent_color: hikari.Color,
        mongo: MongoClient,
        coc_client: coc.Client,
        bot: hikari.GatewayBot
) -> List:
    """Build components for displaying clans of a specific type"""

    # Get clans by type
    clans = await get_clans_by_type(mongo, clan_type)

    # Fetch API data for all clans
    clan_api_data = {}
    for clan in clans:
        try:
            api_clan = await coc_client.get_clan(tag=clan.tag)
            clan_api_data[clan.tag] = api_clan
        except:
            clan_api_data[clan.tag] = None

    # Sort clans by league
    def get_league_rank(clan: Clan) -> int:
        api_clan = clan_api_data.get(clan.tag)
        if not api_clan or not hasattr(api_clan, 'war_league'):
            return len(LEAGUE_ORDER) - 1  # Put unranked at the end

        league_name = api_clan.war_league.name
        try:
            return LEAGUE_ORDER.index(league_name)
        except ValueError:
            return len(LEAGUE_ORDER) - 1

    sorted_clans = sorted(clans, key=get_league_rank)

    # Build components
    components = []

    # Get the banner URL for this clan type
    banner_url = BANNERS.get(clan_type, BANNERS["Competitive"])

    components.append(
        Container(
            accent_color=accent_color,
            components=[
                Media(items=[MediaItem(media=banner_url)]),
                Separator(divider=True, spacing=hikari.SpacingType.LARGE),
            ]
        )
    )

    # Clan list
    clan_components = []

    for clan in sorted_clans:
        api_clan = clan_api_data.get(clan.tag)

        # Get league info
        if api_clan and hasattr(api_clan, 'war_league'):
            league_name = api_clan.war_league.name
            league_emoji = get_league_emoji(league_name)
        else:
            league_name = "Unranked"
            league_emoji = "📊"

        # Build the clan entry
        clan_text = (
            f"## {clan.emoji if clan.emoji else ''} **{clan.name}**\n"
            f" {emojis.BulletPoint} {league_emoji} {league_name} {emojis.BulletPoint} "
            f"{format_th_requirement(clan.th_requirements, clan.th_attribute)}"
        )

        # Add thread link if available
        if clan.thread_id:
            clan_text += f" {emojis.BulletPoint} [More Info](https://discord.com/channels/{ctx.guild_id}/{clan.thread_id})"

        clan_components.append(Text(content=clan_text))

        if clan != sorted_clans[-1]:
            clan_components.append(Separator(divider=False, spacing=hikari.SpacingType.SMALL))

    # Add all clan entries to a container
    final_components = clan_components.copy()

    # Add "What is?" button for Zen and FWA types
    if clan_type == "Zen":
        final_components.append(Separator(divider=True, spacing=hikari.SpacingType.SMALL))
        final_components.append(ActionRow( # type: ignore
            components=[
                Button(
                    style=hikari.ButtonStyle.SUCCESS,
                    custom_id="what_is_zen_info:",
                    label="What is Zen?",
                    emoji="❓"
                )
            ]
        ))
    elif clan_type == "FWA":
        final_components.append(Separator(divider=True, spacing=hikari.SpacingType.SMALL))
        final_components.append(ActionRow( # type: ignore
            components=[
                Button(
                    style=hikari.ButtonStyle.PRIMARY,
                    custom_id="what_is_fwa_info:",
                    label="What is FWA?",
                    emoji="❓"
                )
            ]
        ))

    # Add footer
    final_components.extend([ # type: ignore
        Media(items=[MediaItem(media="assets/Red_Footer.png")])
    ])

    components.append(
        Container(
            accent_color=accent_color,
            components=final_components
        )
    )

    return components


# Handler for Competitive/Main clans
@register_action("show_competitive", ephemeral=True, no_return=True)
@lightbulb.di.with_di
async def show_competitive_clans(
        ctx: lightbulb.components.MenuContext,
        action_id: str,
        mongo: MongoClient = lightbulb.di.INJECTED,
        coc_client: coc.Client = lightbulb.di.INJECTED,
        bot: hikari.GatewayBot = lightbulb.di.INJECTED,
        **kwargs
):
    """Show competitive/main clans"""
    components = await build_clan_list_components(
        ctx, "Competitive", DARK_MAGENTA_ACCENT, mongo, coc_client, bot
    )
    await ctx.respond(components=components, ephemeral=True)


# Handler for Casual clans
@register_action("show_casual", ephemeral=True, no_return=True)
@lightbulb.di.with_di
async def show_casual_clans(
        ctx: lightbulb.components.MenuContext,
        action_id: str,
        mongo: MongoClient = lightbulb.di.INJECTED,
        coc_client: coc.Client = lightbulb.di.INJECTED,
        bot: hikari.GatewayBot = lightbulb.di.INJECTED,
        **kwargs
):
    """Show casual/feeder clans"""
    components = await build_clan_list_components(
        ctx, "Casual", GOLD_ACCENT, mongo, coc_client, bot
    )
    await ctx.respond(components=components, ephemeral=True)


# Handler for Zen clans
@register_action("show_zen", ephemeral=True, no_return=True)
@lightbulb.di.with_di
async def show_zen_clans(
        ctx: lightbulb.components.MenuContext,
        action_id: str,
        mongo: MongoClient = lightbulb.di.INJECTED,
        coc_client: coc.Client = lightbulb.di.INJECTED,
        bot: hikari.GatewayBot = lightbulb.di.INJECTED,
        **kwargs
):
    """Show Zen clans"""
    components = await build_clan_list_components(
        ctx, "Zen", GREEN_ACCENT, mongo, coc_client, bot
    )
    await ctx.respond(components=components, ephemeral=True)


# Handler for FWA clans
@register_action("show_fwa", ephemeral=True, no_return=True)
@lightbulb.di.with_di
async def show_fwa_clans(
        ctx: lightbulb.components.MenuContext,
        action_id: str,
        mongo: MongoClient = lightbulb.di.INJECTED,
        coc_client: coc.Client = lightbulb.di.INJECTED,
        bot: hikari.GatewayBot = lightbulb.di.INJECTED,
        **kwargs
):
    """Show FWA clans"""
    components = await build_clan_list_components(
        ctx, "FWA", BLUE_ACCENT, mongo, coc_client, bot
    )
    await ctx.respond(components=components, ephemeral=True)


# Handler for Trial clans
@register_action("show_trial", ephemeral=True, no_return=True)
@lightbulb.di.with_di
async def show_trial_clans(
        ctx: lightbulb.components.MenuContext,
        action_id: str,
        mongo: MongoClient = lightbulb.di.INJECTED,
        coc_client: coc.Client = lightbulb.di.INJECTED,
        bot: hikari.GatewayBot = lightbulb.di.INJECTED,
        **kwargs
):
    """Show trial clans"""
    # Get clans with status "Trial"
    clans = await mongo.clans.find({"status": "Trial"}).to_list(length=None)
    clans = [Clan(data=data) for data in clans]

    # Fetch API data
    clan_api_data = {}
    for clan in clans:
        try:
            api_clan = await coc_client.get_clan(tag=clan.tag)
            clan_api_data[clan.tag] = api_clan
        except:
            clan_api_data[clan.tag] = None

    # Sort by league
    def get_league_rank(clan: Clan) -> int:
        api_clan = clan_api_data.get(clan.tag)
        if not api_clan or not hasattr(api_clan, 'war_league'):
            return len(LEAGUE_ORDER) - 1

        league_name = api_clan.war_league.name
        try:
            return LEAGUE_ORDER.index(league_name)
        except ValueError:
            return len(LEAGUE_ORDER) - 1

    sorted_clans = sorted(clans, key=get_league_rank)

    # Build components
    components = []

    # Get the banner URL for this clan type
    banner_url = BANNERS.get("Trial", BANNERS["Competitive"])

    components.append(
        Container(
            accent_color=MAGENTA_ACCENT,
            components=[
                Media(items=[MediaItem(media=banner_url)]),
                Separator(divider=True, spacing=hikari.SpacingType.LARGE),
            ]
        )
    )

    # Clan list
    clan_components = []

    for clan in sorted_clans:
        api_clan = clan_api_data.get(clan.tag)

        # Get league info
        if api_clan and hasattr(api_clan, 'war_league'):
            league_name = api_clan.war_league.name
            league_emoji = get_league_emoji(league_name)
        else:
            league_name = "Unranked"
            league_emoji = "📊"

        # Build the clan entry
        clan_text = (
            f"{clan.emoji if clan.emoji else ''} **{clan.name}** "
            f"`{clan.tag}`\n"
            f"{league_emoji} {league_name} | "
            f"{format_th_requirement(clan.th_requirements, clan.th_attribute)}"
        )

        # Add thread link if available
        if clan.thread_id:
            clan_text += f" | [More Info](https://discord.com/channels/{ctx.guild_id}/{clan.thread_id})"

        clan_components.append(Text(content=clan_text))

    if not clan_components:
        clan_components.append(Text(content=(
            "*No clans are currently on trial.*\n\n"
            "Check back later for new clans being evaluated!"
        )))

    # Add all clan entries to a container
    components.append(
        Container(
            accent_color=MAGENTA_ACCENT,
            components=[
                *clan_components,
                Separator(divider=True, spacing=hikari.SpacingType.LARGE),
                Media(items=[MediaItem(media="assets/Red_Footer.png")]),
            ]
        )
    )

    await ctx.respond(components=components, ephemeral=True)