import lightbulb
import hikari

from hikari.impl import (
    ContainerComponentBuilder as Container,
    SectionComponentBuilder as Section,
    ThumbnailComponentBuilder as Thumbnail,
    TextDisplayComponentBuilder as Text,
    SeparatorComponentBuilder as Separator,
    MediaGalleryComponentBuilder as Media,
    MediaGalleryItemBuilder as MediaItem,
)

from utils.constants import DARK_MAGENTA_ACCENT
from utils.emoji import emojis
from extensions.components import register_action
from utils.mongo import MongoClient
from utils.classes import Clan
from extensions.commands.clan.dashboard.dashboard import dashboard_page

@register_action("view_clan_list", group="clan_database")
@lightbulb.di.with_di
async def view_clan_list(
        ctx: lightbulb.components.MenuContext,
        bot: hikari.GatewayBot = lightbulb.di.INJECTED,
        mongo: MongoClient = lightbulb.di.INJECTED,
        **kwargs
):
    clan_data = await mongo.clans.find().to_list(length=None)
    clans = [Clan(data=data) for data in clan_data]

    # Build enhanced clan list with formatting
    clan_list = ""
    for clan in clans:
        # Get clan emoji if available
        clan_emoji = ""
        if clan.partial_emoji:
            clan_emoji = f"{clan.partial_emoji} "
        elif clan.emoji and not clan.emoji.startswith("<"):
            clan_emoji = f"{clan.emoji} "

        # Build clan info line
        clan_info = f"{emojis.red_arrow_right}{clan_emoji}**{clan.name}** `{clan.tag}`"

        # Add status badge if available
        if clan.status:
            clan_info += f" - {clan.status}"

        # Add TH requirement if available
        if clan.th_requirements:
            th_attr = clan.th_attribute or "min"
            clan_info += f" (TH{clan.th_requirements}+ {th_attr})"

        clan_list += f"{clan_info}\n"

    # Get guild icon for thumbnail
    guild_icon = bot.cache.get_guild(ctx.guild_id).make_icon_url()

    # View Clan List message with enhanced formatting
    components = [
        Container(
            accent_color=DARK_MAGENTA_ACCENT,
            components=[
                Section(
                    accessory=Thumbnail(media=guild_icon),
                    components=[
                        Text(content=(
                            "### Clan Management System\n"
                            f"Displaying all registered clans in the Kings Alliance\n\n"
                            f"{emojis.RedGem}**Total Clans:** `{len(clans)}`"
                        )),
                    ]
                ),
                Separator(divider=True, spacing=hikari.SpacingType.SMALL),
                Text(content=f"## Current Clan List\n\n{clan_list}"),
                Media(
                    items=[
                        MediaItem(media="assets/Red_Footer.png"),
                    ])
            ]
        )
    ]
    await ctx.respond(components=components, ephemeral=True)

    return (await dashboard_page(ctx=ctx))






