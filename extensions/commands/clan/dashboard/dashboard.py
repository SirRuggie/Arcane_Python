
import lightbulb
import hikari

from extensions.commands.clan import loader, clan

from hikari.impl import (
    MessageActionRowBuilder as ActionRow,
    TextSelectMenuBuilder as TextSelectMenu,
    SelectMenuBuilder as SelectMenu,
    SelectOptionBuilder as SelectOption,
    ContainerComponentBuilder as Container,
    SectionComponentBuilder as Section,
    InteractiveButtonBuilder as Button,
    TextDisplayComponentBuilder as Text,
    SeparatorComponentBuilder as Separator,
    ThumbnailComponentBuilder as Thumbnail,
    MediaGalleryComponentBuilder as Media,
    MediaGalleryItemBuilder as MediaItem,
    ModalActionRowBuilder as ModalActionRow
)

from utils.constants import DARK_MAGENTA_ACCENT
from utils.emoji import emojis
from utils.mongo import MongoClient
from utils.classes import Clan

# Main Clan Dashboard Management
@lightbulb.di.with_di
async def dashboard_page(
        bot: hikari.GatewayBot = lightbulb.di.INJECTED,
        ctx: lightbulb.Context = lightbulb.di.INJECTED,
        mongo: MongoClient = lightbulb.di.INJECTED,
        **kwargs
):
    clan_data = await mongo.clans.find().to_list(length=None)
    clans = [Clan(data=data) for data in clan_data]
    components = [
        Container(
            accent_color=DARK_MAGENTA_ACCENT,
            components=[
                Section(
                    accessory=Thumbnail(
                        media=bot.cache.get_guild(ctx.guild_id).make_icon_url()
                    ),
                    components=[
                        Text(content=(
                            "### Clan Management Dashboard\n"
                            "welcome to the Kings Alliance Clan Management Dashboard\n\n"
                            f"{emojis.white_arrow_right}**Clans in System:** `{len(clans)}`\n\n"
                        )),
                    ]
                ),
                Separator(divider=True, spacing=hikari.SpacingType.SMALL),
                Text(content=(
                    "Use the dropdown menu below to:\n"
                    f"{emojis.white_arrow_right}View clan details\n"
                    f"{emojis.white_arrow_right}Track & Update Clan Points\n"
                    f"{emojis.white_arrow_right}Update Clan Information\n"
                    f"{emojis.white_arrow_right}Update FWA Data\n"
                )),
                ActionRow(
                    components=[
                        TextSelectMenu(
                            max_values=1,
                            custom_id=f"clan_database:",
                            placeholder="Make a Selection...",
                            options=[
                                SelectOption(
                                    emoji=emojis.view.partial_emoji,
                                    label="View Clan List",
                                    description="View all clans & their IDs",
                                    value="view_clan_list"),
                                SelectOption(
                                    emoji=emojis.edit.partial_emoji,
                                    label="Update Clan Information",
                                    description="Edit or Manage Clan Details",
                                    value="update_clan_information"),
                                SelectOption(
                                    emoji=1387884570501710015,
                                    label="Clan Points",
                                    description="Track & Update Clan Points",
                                    value="clan_points"),
                                SelectOption(
                                    emoji=1387882523358527608,
                                    label="Manage FWA Data",
                                    description="Update FWA Links & Images",
                                    value="manage_fwa_data"),
                            ]),
                    ]),
                Media(
                    items=[
                        MediaItem(media="assets/Red_Footer.png")
                    ]),
            ]
        )
    ]
    return components


@clan.register()
class DashboardCommand(
    lightbulb.SlashCommand,
    name="dashboard",
    description="Open the Clan Management Dashboard",
):
    @lightbulb.invoke
    @lightbulb.di.with_di
    async def invoke(
            self,
            ctx: lightbulb.Context,
            bot: hikari.GatewayBot = lightbulb.di.INJECTED,
            mongo: MongoClient = lightbulb.di.INJECTED,
    ) -> None:
        await ctx.defer(ephemeral=True)  # Keep this ephemeral for the "thinking" message

        # Get the components
        comps = await dashboard_page(bot=bot, ctx=ctx, mongo=mongo)

        # Send to channel without replying
        await bot.rest.create_message(
            channel=ctx.channel_id,
            components=comps
        )

        # Delete the ephemeral "thinking" message
        await ctx.interaction.delete_initial_response()