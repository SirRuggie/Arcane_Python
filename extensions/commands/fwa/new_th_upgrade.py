import uuid
import hikari
import lightbulb

from extensions.components import register_action
from utils.mongo import MongoClient
from extensions.commands.fwa import fwa
from .helpers import get_fwa_base_object
from utils.emoji import emojis

from utils.constants import DARK_MAGENTA_ACCENT, GOLD_ACCENT, BLUE_ACCENT, GREEN_ACCENT, FWA_WAR_BASE, FWA_ACTIVE_WAR_BASE

from hikari.impl import (
    MessageActionRowBuilder as ActionRow,
    TextSelectMenuBuilder as TextSelectMenu,
    SelectOptionBuilder as SelectOption,
    ContainerComponentBuilder as Container,
    SectionComponentBuilder as Section,
    InteractiveButtonBuilder as Button,
    TextDisplayComponentBuilder as Text,
    SeparatorComponentBuilder as Separator,
    ThumbnailComponentBuilder as Thumbnail,
    MediaGalleryComponentBuilder as Media,
    MediaGalleryItemBuilder as MediaItem,
    LinkButtonBuilder as LinkButton
)


@fwa.register()
class NewThUpgrade(
    lightbulb.SlashCommand,
    name="new-th-upgrade",
    description="Display Town Hall upgrade notes for FWA bases",
):
    user = lightbulb.user(
        "discord-user",
        "Which user to show this for",
    )

    @lightbulb.invoke
    @lightbulb.di.with_di
    async def invoke(
            self,
            ctx: lightbulb.Context,
            mongo: MongoClient = lightbulb.di.INJECTED,
    ) -> None:
        await ctx.defer(ephemeral=True)

        action_id = str(uuid.uuid4())

        # Store the user_id in MongoDB like other commands do
        data = {
            "_id": action_id,
            "user_id": self.user.id  # Store as integer
        }
        await mongo.button_store.insert_one(data)

        components = [
            Container(
                accent_color=BLUE_ACCENT,
                components=[
                    Text(content="## Select FWA Base Town Hall Level"),
                    Text(
                        content=(
                            "Use the dropdown menu below to assign the appropriate "
                            "Town Hall level for the recruit."
                        )
                    ),
                    ActionRow(
                        components=[
                            TextSelectMenu(
                                max_values=1,
                                custom_id=f"fwa_new_th_upgrade_th_select:{action_id}",
                                placeholder="Select a Base...",
                                options=[
                                    SelectOption(
                                        emoji=emojis.TH17.partial_emoji,
                                        label="TH17",
                                        value="th17"
                                    ),
                                    SelectOption(
                                        emoji=emojis.TH17.partial_emoji,
                                        label="TH17 New",
                                        value="th17_new"
                                    ),
                                    SelectOption(
                                        emoji=emojis.TH16.partial_emoji,
                                        label="TH16",
                                        value="th16"
                                    ),
                                    SelectOption(
                                        emoji=emojis.TH16.partial_emoji,
                                        label="TH16 New",
                                        value="th16_new"
                                    ),
                                    SelectOption(
                                        emoji=emojis.TH15.partial_emoji,
                                        label="TH15",
                                        value="th15"
                                    ),
                                    SelectOption(
                                        emoji=emojis.TH14.partial_emoji,
                                        label="TH14",
                                        value="th14"
                                    ),
                                    SelectOption(
                                        emoji=emojis.TH13.partial_emoji,
                                        label="TH13",
                                        value="th13"
                                    ),
                                    SelectOption(
                                        emoji=emojis.TH12.partial_emoji,
                                        label="TH12",
                                        value="th12"
                                    ),
                                    SelectOption(
                                        emoji=emojis.TH11.partial_emoji,
                                        label="TH11",
                                        value="th11"
                                    ),
                                    SelectOption(
                                        emoji=emojis.TH10.partial_emoji,
                                        label="TH10",
                                        value="th10"
                                    ),
                                    SelectOption(
                                        emoji=emojis.TH9.partial_emoji,
                                        label="TH9",
                                        value="th9"
                                    ),
                                ],
                            ),
                        ]
                    ),
                    Media(items=[MediaItem(media="assets/Blue_Footer.png")]),
                ],
            )
        ]

        await ctx.respond(components=components, ephemeral=True)


@register_action("fwa_new_th_upgrade_th_select", no_return=True)
@lightbulb.di.with_di
async def fwa_new_th_upgrade_th_select(
        user_id: int,
        bot: hikari.GatewayBot = lightbulb.di.INJECTED,
        mongo: MongoClient = lightbulb.di.INJECTED,
        **kwargs
):
    print(f"[FWA New TH Upgrade] ========== fwa_new_th_upgrade_th_select CALLED ==========")
    print(f"[FWA New TH Upgrade] user_id: {user_id}")
    print(f"[FWA New TH Upgrade] kwargs keys: {list(kwargs.keys())}")

    try:
        ctx: lightbulb.components.MenuContext = kwargs["ctx"]
        print(f"[FWA New TH Upgrade] Got ctx successfully")

        # Get the user from the user_id that was stored in MongoDB
        print(f"[FWA New TH Upgrade] Fetching member...")
        user = await bot.rest.fetch_member(ctx.guild_id, user_id)
        print(f"[FWA New TH Upgrade] Got user: {user.username}")

        # Get the selected TH level
        choice = ctx.interaction.values[0]
        print(f"[FWA New TH Upgrade] Choice from dropdown: {choice}")

        # Get FWA data
        print(f"[FWA New TH Upgrade] Getting FWA data...")
        fwa_data = await get_fwa_base_object(mongo)
        if not fwa_data:
            print(f"[FWA New TH Upgrade] ERROR: FWA data not found!")
            await ctx.respond("FWA data not found in database!", ephemeral=True)
            return
        print(f"[FWA New TH Upgrade] Got FWA data successfully")

        # Format display name properly for _new variants
        if choice.endswith('_new'):
            base_th = choice.replace('_new', '')
            th_number = base_th.lstrip('th')
            display_name = f"TH{th_number} New"
            friendly_name = f"Town Hall {th_number} New"
        else:
            th_number = choice.lstrip('th')
            display_name = f"TH{th_number}"
            friendly_name = f"Town Hall {th_number}"

        base_link = getattr(fwa_data.fwa_base_links, choice, "")
        print(f"[FWA New TH Upgrade] Base link: {base_link[:50] if base_link else 'NONE'}")

        if not base_link:
            print(f"[FWA New TH Upgrade] ERROR: No base link found for {choice}")
            await ctx.respond(f"No base link found for {choice}!", ephemeral=True)
            return

        # Get base upgrade notes for this TH level
        print(f"[FWA New TH Upgrade] Getting base_upgrade_notes...")
        print(f"[FWA New TH Upgrade] base_upgrade_notes type: {type(fwa_data.base_upgrade_notes)}")
        print(f"[FWA New TH Upgrade] base_upgrade_notes keys: {list(fwa_data.base_upgrade_notes.keys())}")
        upgrade_notes = fwa_data.base_upgrade_notes.get(choice, "")
        print(f"[FWA New TH Upgrade] Retrieved upgrade_notes for '{choice}': {upgrade_notes[:50] if upgrade_notes else 'EMPTY'}")
    except Exception as e:
        print(f"[FWA New TH Upgrade] EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        return
    if not upgrade_notes:
        upgrade_notes = (
            "No upgrade notes available for this Town Hall level at this time.\n\n"
            "Please check back later or contact leadership for more information."
        )

    # Build the response
    components = [
        Text(content=f"{user.mention}"),
        Container(
            accent_color=BLUE_ACCENT,
            components=[
                Text(content=f"## {friendly_name}"),
                Media(
                    items=[
                        MediaItem(media=FWA_WAR_BASE.get(choice, ""))
                    ]
                ),
                ActionRow(
                    components=[
                        LinkButton(
                            url=base_link,
                            label="Click Me!",
                        )
                    ]
                ),
            ]
        ),
        Container(
            accent_color=BLUE_ACCENT,
            components=[
                Text(content=f"### TH{th_number} Upgrade Notes"),
                Text(content=upgrade_notes),
                Media(
                    items=[
                        MediaItem(media=FWA_ACTIVE_WAR_BASE.get(choice, ""))
                    ]
                ),
                Text(content=f"-# Requested by {ctx.member.mention}")
            ]
        )
    ]

    await bot.rest.create_message(
        components=components,
        channel=ctx.channel_id,
        user_mentions=[user.id],
        role_mentions=True,
    )
