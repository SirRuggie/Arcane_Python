import uuid
import hikari
import lightbulb

from extensions.commands.recruit import recruit
from extensions.components import register_action
from utils.mongo import MongoClient
from utils.classes import Clan
from utils.constants import RED_ACCENT

from hikari.impl import (
    MessageActionRowBuilder as ActionRow,
    TextSelectMenuBuilder as TextSelectMenu,
    SelectOptionBuilder as SelectOption,
    ContainerComponentBuilder as Container,
    TextDisplayComponentBuilder as Text,
    SeparatorComponentBuilder as Separator,
    MediaGalleryComponentBuilder as Media,
    MediaGalleryItemBuilder as MediaItem,
)


@recruit.register()
class Welcome(
    lightbulb.SlashCommand,
    name="welcome",
    description="Send a clan's welcome message to a user",
):
    user = lightbulb.user(
        "user",
        "Which user to send the welcome message to",
    )

    @lightbulb.invoke
    async def invoke(
        self,
        ctx: lightbulb.Context,
        mongo: MongoClient = lightbulb.di.INJECTED,
    ) -> None:
        await ctx.defer(ephemeral=True)

        # Get user's clans where they have leader role
        user_roles = ctx.interaction.member.role_ids
        clan_data = await mongo.clans.find({
            "leader_role_id": {"$in": user_roles}
        }).to_list(length=None)

        if not clan_data:
            await ctx.respond("You must have a clan leader role to send welcome messages.", ephemeral=True)
            return

        clans = [Clan(data=d) for d in clan_data]

        # Categorize clans by type (trial clans show in their type category)
        competitive_clans = [c for c in clans if c.type == "Competitive"]
        zen_casual_clans = [c for c in clans if c.type in ["Zen", "Casual"]]
        fwa_clans = [c for c in clans if c.type == "FWA"]

        # Sort each category by points (activity)
        competitive_clans = sorted(competitive_clans, key=lambda c: c.points or 0, reverse=True)
        zen_casual_clans = sorted(zen_casual_clans, key=lambda c: c.points or 0, reverse=True)
        fwa_clans = sorted(fwa_clans, key=lambda c: c.points or 0, reverse=True)

        action_id = str(uuid.uuid4())

        # Store user selection in button store for the handler
        await mongo.button_store.insert_one({
            "_id": action_id,
            "selected_user_id": self.user.id,
            "invoker_id": ctx.user.id
        })

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
                "## **Pick Your Clan to Welcome From**\n"
                "Clans are organized by category below.\n"
                f"This will be sent to {self.user.mention}."
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
                            custom_id=f"clan_welcome_select:competitive_{action_id}",
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
                            custom_id=f"clan_welcome_select:zen_{action_id}",
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
                            custom_id=f"clan_welcome_select:fwa_{action_id}",
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
                Text(content="## **No Clans Found**\n⚠️ You don't have a leader role in any clans."),
                Media(items=[MediaItem(media="assets/Red_Footer.png")])
            ]

        components = [
            Container(
                accent_color=RED_ACCENT,
                components=component_list,
            )
        ]
        await ctx.respond(components=components, ephemeral=True)


@register_action("clan_welcome_select", no_return=True)
@lightbulb.di.with_di
async def on_clan_welcome_chosen(
    action_id: str,
    bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    ctx: lightbulb.components.MenuContext = kwargs["ctx"]

    # Parse category prefix from action_id (e.g., "competitive_uuid")
    # The category prefix is optional for backwards compatibility
    if "_" in action_id and action_id.split("_")[0] in ["competitive", "zen", "fwa"]:
        category, action_id = action_id.split("_", 1)

    # Get stored data
    store_data = await mongo.button_store.find_one({"_id": action_id})
    if not store_data:
        await ctx.respond("Session expired. Please try again.", ephemeral=True)
        return
    
    selected_user_id = store_data["selected_user_id"]
    user = await bot.rest.fetch_member(ctx.guild_id, selected_user_id)

    selected_value = ctx.interaction.values[0]

    # Extract original tag from potentially modified value (remove _1, _2 etc.)
    tag = selected_value.split("_")[0] if "_" in selected_value else selected_value

    raw = await mongo.clans.find_one({"tag": tag})
    if not raw:
        components = [
            Container(
                accent_color=RED_ACCENT,
                components=[Text(content="⚠️ I couldn't find that clan in our database.")]
            )
        ]
        await ctx.interaction.edit_initial_response(components=components)
        return

    db_clan = Clan(data=raw)

    # Check if clan has recruit_welcome message
    if not db_clan.recruit_welcome:
        components = [
            Container(
                accent_color=RED_ACCENT,
                components=[
                    Text(content=(
                        f"⚠️ {db_clan.name} doesn't have a welcome message set up.\n\n"
                        "Please message Ruggie what welcome you would like displayed."
                    )),
                    Media(items=[MediaItem(media="assets/Red_Footer.png")]),
                ]
            )
        ]
        await ctx.interaction.edit_initial_response(components=components)
        return

    # Check if clan has chat_channel_id
    if not db_clan.chat_channel_id:
        components = [
            Container(
                accent_color=RED_ACCENT,
                components=[
                    Text(content=(
                        f"⚠️ {db_clan.name} doesn't have a chat channel configured.\n\n"
                        "Cannot send welcome message."
                    )),
                    Media(items=[MediaItem(media="assets/Red_Footer.png")]),
                ]
            )
        ]
        await ctx.interaction.edit_initial_response(components=components)
        return

    # Send the welcome message to the clan's chat channel
    try:
        await bot.rest.create_message(
            channel=db_clan.chat_channel_id,
            content=f"{user.mention}\n{db_clan.recruit_welcome}",
            user_mentions=[user.id],
        )

        # Update the original message to show success
        components = [
            Container(
                accent_color=RED_ACCENT,
                components=[
                    Text(content=(
                        f"✅ Welcome message sent to {user.mention} in <#{db_clan.chat_channel_id}>!\n\n"
                        f"**Clan:** {db_clan.name}"
                    )),
                    Media(items=[MediaItem(media="assets/Red_Footer.png")]),
                ]
            )
        ]
        await ctx.interaction.edit_initial_response(components=components)

    except Exception as e:
        components = [
            Container(
                accent_color=RED_ACCENT,
                components=[
                    Text(content=(
                        f"❌ Failed to send welcome message.\n\n"
                        f"Error: {str(e)[:100]}"
                    )),
                    Media(items=[MediaItem(media="assets/Red_Footer.png")]),
                ]
            )
        ]
        await ctx.interaction.edit_initial_response(components=components)
    finally:
        # Clean up button store
        await mongo.button_store.delete_one({"_id": action_id})