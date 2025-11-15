# extensions/commands/clan/info_hub/info.py

import hikari
import lightbulb
from hikari.impl import (
    MessageActionRowBuilder as ActionRow,
    ContainerComponentBuilder as Container,
    InteractiveButtonBuilder as Button,
    TextDisplayComponentBuilder as Text,
    SeparatorComponentBuilder as Separator,
    MediaGalleryComponentBuilder as Media,
    MediaGalleryItemBuilder as MediaItem,
)

from extensions.commands.clan import loader, clan
from extensions.components import register_action
from utils.constants import DARK_MAGENTA_ACCENT, GOLD_ACCENT, BLUE_ACCENT, GREEN_ACCENT, MAGENTA_ACCENT


@clan.register()
class Info(
    lightbulb.SlashCommand,
    name="info",
    description="View information about all clans in the family"
):
    @lightbulb.invoke
    @lightbulb.di.with_di
    async def invoke(
            self,
            ctx: lightbulb.Context,
            bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    ) -> None:
        # Defer the response as ephemeral (this creates the "thinking" message)
        await ctx.defer(ephemeral=True)

        # Cloudinary URL for the Our_Clans banner
        banner_url = "https://res.cloudinary.com/dxmtzuomk/image/upload/v1763222607/server_banners/OurClans.png"

        components = [
            Container(
                accent_color=DARK_MAGENTA_ACCENT,
                components=[
                    Media(items=[MediaItem(media=banner_url)]),
                    Separator(divider=True, spacing=hikari.SpacingType.LARGE),
                    Text(content=(
                        "Arcane Alliance aims to provide a top tier and personalized clashing "
                        "experience. We offer a variety of clans to suit your needs, whether "
                        "you're a top-tier eSports player looking to prove your skills and "
                        "climb the leaderboards or just want to relax, farm and have fun. "
                        "Look no further than Arcane and join one of our clans below."
                    )),
                    Separator(divider=True, spacing=hikari.SpacingType.SMALL),

                    # Main Clans Button
                    Text(content=(
                        f"## __<a:AngryGiant:1393193559921918002> **Main**__\n"
                        "Our Main Clans host Arcane's most competitive players. A "
                        "combination of trophy pushing giveaways and B2B wars provide for "
                        "a competitive experience.\n\n"
                    )),
                    Separator(divider=False, spacing=hikari.SpacingType.SMALL),
                    # Casual Clans Button
                    Text(content=(
                        f"## __<a:Chill:1393193145927340073> **Casual**__\n"
                        "Main Clans full? Try one of our Casual Clans. Arcane's casual clans "
                        "encapsulate the same attitude of our Main Clan system whilst you "
                        "wait."
                    )),
                    Separator(divider=False, spacing=hikari.SpacingType.SMALL),
                    # Zen Button
                    Text(content=(
                        f"## __<:BabyYoda:1390465217997312234> **Zen**__\n"
                        "Originally created by Arcane, Zen War Clans offer a laid-back, "
                        "stress-free environment where players can learn competitive attack "
                        "strategies without criticism: members participate in B2B wars "
                        "while farming, staying active without pressure from hero upgrades. "
                        "Active participation is required with at least one war attack; "
                        "second attacks are encouraged but not mandatory."
                    )),
                    Separator(divider=False, spacing=hikari.SpacingType.SMALL),
                    # FWA Button
                    Text(content=(
                        f"## __<a:FWA:1387882523358527608> **FWA**__\n"
                        "Arcane's FWA Clans, part of the Farm War Alliance, offer a unique "
                        "clashing experience. Focused on strategic farming and no-hero "
                        "wars, these clans help you grow your base. Once you're upgraded "
                        "here, join one of our main clans to unleash your competitive side."
                    )),
                    Separator(divider=False, spacing=hikari.SpacingType.SMALL),
                    # Clans on Trial Button
                    Text(content=(
                        f"## __<:PepeJail:1393193768454459463> **Clans on Trial**__\n"
                        "As part of Arcane's goal to provide a top tier clashing experience, new "
                        "clans are trialed before entering our ranks permanently. If one of "
                        "these clans catches your attention, join!"
                    )),

                    Separator(divider=True, spacing=hikari.SpacingType.SMALL),
                    Text(content=(
                        "To check out the details of our clans, please press the buttons attached to "
                        "this embed. More info on Zen and FWA is available below in the buttons."
                    )),
                    Separator(divider=False, spacing=hikari.SpacingType.SMALL),
                    # Action buttons
                    ActionRow(components=[
                        Button(
                            style=hikari.ButtonStyle.SECONDARY,
                            custom_id="show_competitive:",
                            label="Main",
                            emoji=1393193559921918002
                        ),
                        Button(
                            style=hikari.ButtonStyle.SECONDARY,
                            custom_id="show_casual:",
                            label="Casual",
                            emoji=1393193145927340073
                        ),
                        Button(
                            style=hikari.ButtonStyle.SECONDARY,
                            custom_id="show_zen:",
                            label="Zen",
                            emoji=1390465217997312234
                        ),
                        Button(
                            style=hikari.ButtonStyle.SECONDARY,
                            custom_id="show_fwa:",
                            label="FWA",
                            emoji=1387882523358527608
                        ),
                        Button(
                            style=hikari.ButtonStyle.SECONDARY,
                            custom_id="show_trial:",
                            label="Clans on Trial",
                            emoji=1393193768454459463
                        ),
                    ]),
                    Media(items=[MediaItem(media="assets/Red_Footer.png")]),
                ],
            )
        ]

        # Send the message to the channel
        await bot.rest.create_message(
            channel=ctx.channel_id,
            components=components
        )

        # Delete the ephemeral "thinking" message
        await ctx.interaction.delete_initial_response()


# Import handlers to register their actions
from . import handlers