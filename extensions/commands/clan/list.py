import uuid
import hikari
import lightbulb
import coc

from extensions.commands.clan   import loader, clan
from extensions.components      import register_action
from utils.mongo                import MongoClient
from utils.classes              import Clan
from utils.constants            import DARK_MAGENTA_ACCENT
from utils.emoji                import emojis

from hikari.impl import (
    MessageActionRowBuilder         as ActionRow,
    TextSelectMenuBuilder           as TextSelectMenu,
    SelectOptionBuilder             as SelectOption,
    ContainerComponentBuilder       as Container,
    SectionComponentBuilder         as Section,
    TextDisplayComponentBuilder     as Text,
    SeparatorComponentBuilder       as Separator,
    MediaGalleryComponentBuilder    as Media,
    MediaGalleryItemBuilder         as MediaItem,
    ThumbnailComponentBuilder       as Thumbnail,
    LinkButtonBuilder               as LinkButton,
    InteractiveButtonBuilder        as Button,
)


@clan.register()
class ListCommand(
    lightbulb.SlashCommand,
    name="list",
    description="Pick a clan to view or manage",
):
    # 1) define a user‐select option here:
    user = lightbulb.user(
        "discord-user",
        "Which user to show this for",
    )

    @lightbulb.invoke
    async def invoke(
        self,
        ctx: lightbulb.Context,
        mongo: MongoClient = lightbulb.di.INJECTED,
    ) -> None:
        await ctx.defer(ephemeral=True)
        clan_data = await mongo.clans.find().to_list(length=None)
        clans     = [Clan(data=d) for d in clan_data]

        # Categorize clans by type (trial clans show in their type category)
        competitive_clans = [c for c in clans if c.type == "Competitive"]
        zen_casual_clans = [c for c in clans if c.type in ["Zen", "Casual"]]
        fwa_clans = [c for c in clans if c.type == "FWA"]

        # Sort each category by points (activity)
        competitive_clans = sorted(competitive_clans, key=lambda c: c.points or 0, reverse=True)
        zen_casual_clans = sorted(zen_casual_clans, key=lambda c: c.points or 0, reverse=True)
        fwa_clans = sorted(fwa_clans, key=lambda c: c.points or 0, reverse=True)

        action_id = str(uuid.uuid4())

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

                kwargs = {"label": c.name, "value": unique_value, "description": c.tag}
                if getattr(c, "partial_emoji", None):
                    kwargs["emoji"] = c.partial_emoji
                options.append(SelectOption(**kwargs))

            return options, len(clan_list) > max_clans

        # Build component list with categorized dropdowns
        component_list = [
            Text(content=(
                "## **Pick Your Clan**\n"
                "Clans are organized by category below.\n"
                "Select a clan from any dropdown to view details."
            )),
        ]

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
                            custom_id=f"clan_select_menu:competitive_{action_id}_{self.user.id}",
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
                            custom_id=f"clan_select_menu:zen_{action_id}_{self.user.id}",
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
                            custom_id=f"clan_select_menu:fwa_{action_id}_{self.user.id}",
                            placeholder="Select an FWA clan",
                            max_values=1,
                            options=options,
                        )
                    ]
                ),
            ])

        # Add footer
        component_list.append(Media(items=[MediaItem(media="assets/Red_Footer.png")]))

        # Check if we have any clans to display
        if not any([competitive_clans, zen_casual_clans, fwa_clans]):
            component_list = [
                Text(content="## **No Clans Found**\n⚠️ No clans are currently registered in the system."),
                Media(items=[MediaItem(media="assets/Red_Footer.png")])
            ]

        components = [
            Container(
                accent_color=DARK_MAGENTA_ACCENT,
                components=component_list,
            )
        ]
        await ctx.respond(components=components, ephemeral=True)


@register_action("clan_select_menu", no_return=True)
@lightbulb.di.with_di
async def on_clan_chosen(
    action_id: str,
    bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    coc_client: coc.Client  = lightbulb.di.INJECTED,
    mongo: MongoClient      = lightbulb.di.INJECTED,
    **kwargs
):
    ctx: lightbulb.components.MenuContext = kwargs["ctx"]
    # Parse category prefix from action_id (e.g., "competitive_uuid_userid")
    # The category prefix is optional for backwards compatibility
    if "_" in action_id and action_id.split("_")[0] in ["competitive", "zen", "fwa"]:
        category, action_id = action_id.split("_", 1)
    _, user_id = action_id.rsplit("_", 1)
    user = await bot.rest.fetch_member(ctx.guild_id, int(user_id))

    selected_value = ctx.interaction.values[0]

    # Extract original tag from potentially modified value (remove _1, _2 etc.)
    tag = selected_value.split("_")[0] if "_" in selected_value else selected_value

    raw = await mongo.clans.find_one({"tag": tag})
    if not raw:
        return [
            Container(
                accent_color=DARK_MAGENTA_ACCENT,
                components=[Text(content="⚠️ I couldn’t find that clan in our database.")]
            )
        ]
    db_clan = Clan(data=raw)

    api_clan = None
    try:
        api_clan = await coc_client.get_clan(tag=tag)
    except coc.NotFound:
        pass

    if api_clan and api_clan.capital_districts:
        peak = max(d.hall_level for d in api_clan.capital_districts)
    else:
        peak = 0

    lines = [
        f"{emojis.red_arrow_right}**Name:** {db_clan.name} (`{db_clan.tag}`)",
        f"{emojis.red_arrow_right}**Level:** {api_clan.level}" if api_clan else "• **Level:** —",
        f"{emojis.red_arrow_right}**CWL Rank:** {api_clan.war_league.name if api_clan else '—'}",
        f"{emojis.red_arrow_right}**Type:** {db_clan.type or '—'}",
        f"{emojis.red_arrow_right}**Capital Peak:** Level {peak}",
    ]
    content = (
        f"Hey {user.mention},\n"
        f"I’d like to introduce you to **{db_clan.name}**, led by "
        f"<@{db_clan.leader_id}> and <@&{db_clan.leader_role_id}>."
    )
    components = [
        Container(
            accent_color=DARK_MAGENTA_ACCENT,
            components=[
                Text(content=f"Hey {user.mention},"),
                Text(content=(
                    f"I’d like to introduce you to **{db_clan.name}**, led by "
                    f"<@{db_clan.leader_id}> and <@&{db_clan.leader_role_id}>."
                )),
                Separator(divider=True),
                Text(content="## **Important Information Below**"),
                Text(content=(
                    "You’re free to move temporarily within our Family. "
                    "If you want to switch clans permanently, please discuss it with leadership to ensure a good fit.\n\n"
                    "If you’re unhappy with the clan given, let us know—we can explore other options."
                )),
                Separator(divider=True),
                Text(content=(
                    f"From now on, **{db_clan.name}** is your new home. "
                    "Use the code `Arcane` to access any clan within our Family. "
                    "It will become your friend during CWL... *make sense?*"
                )),
            ],
        ),
        Container(
            accent_color=DARK_MAGENTA_ACCENT,
            components=[
                Section(
                    components=[Text(content="\n".join(lines))],
                    accessory=Thumbnail(media=api_clan.badge.large if api_clan else db_clan.logo),
                ),
                Media(items=[MediaItem(media=db_clan.banner if db_clan.banner and db_clan.banner != '.' else "assets/Red_Footer.png")]),
                ActionRow(
                    components=[
                        LinkButton(
                            label="Open In-Game",
                            url=api_clan.share_link if api_clan else ""
                        )
                    ]
                ),
                Separator(divider=True),
                Text(content=f"-# Requested by {ctx.member.mention}"),
            ],
        ),
    ]

    await ctx.interaction.delete_initial_response()

    await bot.rest.create_message(
        channel=ctx.channel_id,
        components=components,
        user_mentions = [user.id, db_clan.leader_id],
        role_mentions = True,
    )
