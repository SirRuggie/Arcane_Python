# commands/clan/report/discord_post.py

"""Discord post reporting functionality"""

import hikari
import lightbulb
from datetime import datetime

loader = lightbulb.Loader()

from hikari.impl import (
    MessageActionRowBuilder as ActionRow,
    TextSelectMenuBuilder as TextSelectMenu,
    ContainerComponentBuilder as Container,
    InteractiveButtonBuilder as Button,
    TextDisplayComponentBuilder as Text,
    SeparatorComponentBuilder as Separator,
    MediaGalleryComponentBuilder as Media,
    MediaGalleryItemBuilder as MediaItem,
    ModalActionRowBuilder as ModalActionRow,
    ThumbnailComponentBuilder as Thumbnail,
    SectionComponentBuilder as Section,
    LinkButtonBuilder as LinkButton
)

from extensions.components import register_action
from utils.mongo import MongoClient
from utils.classes import Clan
from utils.constants import BLUE_ACCENT, GREEN_ACCENT, MAGENTA_ACCENT, RED_ACCENT

from .helpers import (
    get_clan_options,
    get_categorized_clan_components,
    create_progress_header,
    parse_discord_link,
    create_submission_data,
    get_clan_by_tag,
    APPROVAL_CHANNEL,
    RECRUITMENT_PING
)

# ╔══════════════════════════════════════════════════════════╗
# ║            Show Discord Post Flow (Step 1)               ║
# ╚══════════════════════════════════════════════════════════╝

@lightbulb.di.with_di
async def show_discord_post_flow(
        ctx: lightbulb.components.MenuContext,
        user_id: str,
        mongo: MongoClient = lightbulb.di.INJECTED
):
    # Build component list
    component_list = [
        Text(content=create_progress_header(1, 3, ["Select Clan", "Add Link", "Review"])),
        Separator(),
        Text(content="## 🏰 Select Your Clan"),
        Text(content="Which clan recruited the new member?"),
    ]

    # Add categorized clan dropdowns
    component_list.extend(await get_categorized_clan_components("dp_select_clan", user_id, mongo))

    # Add cancel button and footer
    component_list.extend([
        ActionRow(
            components=[
                Button(
                    style=hikari.ButtonStyle.SECONDARY,
                    label="Cancel",
                    emoji="❌",
                    custom_id=f"cancel_report:{user_id}"
                )
            ]
        ),
        Media(items=[MediaItem(media="assets/Blue_Footer.png")])
    ])

    components = [
        Container(
            accent_color=BLUE_ACCENT,
            components=component_list
        )
    ]

    await ctx.respond(components=components, edit=True)

# ╔══════════════════════════════════════════════════════════╗
# ║            Clan Selection Handler (Step 2)               ║
# ╚══════════════════════════════════════════════════════════╝

@register_action("dp_select_clan", no_return=True, opens_modal=True)
async def dp_handle_clan_selection(
        ctx: lightbulb.components.MenuContext,
        action_id: str,
        **kwargs
):
    # Parse category prefix from action_id (e.g., "competitive_user123")
    if "_" in action_id and action_id.split("_")[0] in ["competitive", "zen", "fwa"]:
        category, action_id = action_id.split("_", 1)

    user_id = action_id
    selected_value = ctx.interaction.values[0]

    # Extract original tag from potentially modified value (remove _1, _2 etc.)
    selected_clan = selected_value.split("_")[0] if "_" in selected_value else selected_value

    link_input = ModalActionRow().add_text_input(
        "discord_link",
        "Discord Message Link",
        placeholder="https://discord.com/channels/.../.../.../",
        required=True,
        min_length=20
    )

    notes_input = ModalActionRow().add_text_input(
        "notes",
        "Additional Notes (Optional)",
        placeholder="Any additional context for the reviewers?",
        required=False,
        style=hikari.TextInputStyle.PARAGRAPH,
        max_length=200
    )

    await ctx.respond_with_modal(
        title="Add Discord Message Link",
        custom_id=f"dp_submit_link:{selected_clan}_{user_id}",
        components=[link_input, notes_input]
    )

# ╔══════════════════════════════════════════════════════════╗
# ║         Discord Link Submission Handler (Step 3)         ║
# ╚══════════════════════════════════════════════════════════╝

@register_action("dp_submit_link", no_return=True, is_modal=True)
@lightbulb.di.with_di
async def dp_submit_discord_link(
        ctx: lightbulb.components.ModalContext,
        action_id: str,
        mongo: MongoClient = lightbulb.di.INJECTED,
        bot: hikari.GatewayBot = lightbulb.di.INJECTED,
        **kwargs
):
    parts = action_id.split("_")
    clan_tag = parts[0]
    user_id = parts[1]

    discord_link = ""
    notes = ""
    for row in ctx.interaction.components:
        for comp in row:
            if comp.custom_id == "discord_link":
                discord_link = comp.value.strip()
            elif comp.custom_id == "notes":
                notes = comp.value.strip()

    link_data = parse_discord_link(discord_link)
    if not link_data:
        await ctx.respond(
            "❌ Invalid Discord message link! Please use a valid link format:\n"
            "`https://discord.com/channels/guild_id/channel_id/message_id`",
            ephemeral=True
        )
        return

    clan = await get_clan_by_tag(mongo, clan_tag)
    if not clan:
        await ctx.respond("❌ Clan not found!", ephemeral=True)
        return

    submission_id = f"{clan_tag}_{user_id}_{int(datetime.now().timestamp())}"
    submission_data = {
        "_id": submission_id,
        "data": {
            "discord_link": discord_link,
            "notes": notes,
            "link_data": link_data
        }
    }
    await mongo.button_store.insert_one(submission_data)

    await ctx.interaction.create_initial_response(hikari.ResponseType.DEFERRED_MESSAGE_UPDATE)

    review_components = [
        Text(content=create_progress_header(3, 3, ["Select Clan", "Add Link", "Review"])),
        Separator(),

        Text(content="## 📋 Review Your Submission"),

        Section(
            components=[
                Text(content=(
                    f"**Clan:** {clan.emoji if clan.emoji else ''} {clan.name}\n"
                    f"**Type:** Discord Post\n"
                    f"**Points to Award:** 1"
                ))
            ],
            accessory=Thumbnail(
                media=clan.logo if clan.logo else "https://cdn-icons-png.flaticon.com/512/845/845665.png"
            )
        ),

        Text(content="**📌 Discord Post Link:**"),
        Text(content=f"`{discord_link}`"),
    ]

    if link_data:
        review_components.append(
            ActionRow(
                components=[
                    LinkButton(
                        label="Preview Message",
                        url=discord_link,
                        emoji="🔗"
                    )
                ]
            )
        )

    if notes:
        review_components.append(Text(content=f"**📝 Notes:** {notes}"))

    review_components.extend([
        ActionRow(
            components=[
                Button(
                    style=hikari.ButtonStyle.SUCCESS,
                    label="Submit for Approval",
                    emoji="✅",
                    custom_id=f"dp_confirm_submit:{submission_id}"
                ),
                Button(
                    style=hikari.ButtonStyle.SECONDARY,
                    label="Start Over",
                    emoji="🔄",
                    custom_id=f"cancel_report:{user_id}"
                )
            ]
        ),

        Text(content="-# Your submission will be reviewed by leadership"),

        Media(items=[MediaItem(media="assets/Green_Footer.png")])
    ])

    components = [
        Container(
            accent_color=GREEN_ACCENT,
            components=review_components
        )
    ]

    await ctx.interaction.edit_initial_response(components=components)

# ╔══════════════════════════════════════════════════════════╗
# ║             Confirm Submission Handler                   ║
# ╚══════════════════════════════════════════════════════════╝

@register_action("dp_confirm_submit", no_return=True)
@lightbulb.di.with_di
async def dp_confirm_submission(
        ctx: lightbulb.components.MenuContext,
        action_id: str,
        mongo: MongoClient = lightbulb.di.INJECTED,
        bot: hikari.GatewayBot = lightbulb.di.INJECTED,
        **kwargs
):
    submission_id = action_id

    stored_data = await mongo.button_store.find_one({"_id": submission_id})
    if not stored_data or "data" not in stored_data:
        await ctx.respond("❌ Error: Submission data not found!", ephemeral=True)
        return

    submission_data = stored_data["data"]
    discord_link = submission_data.get("discord_link", "")
    notes = submission_data.get("notes", "")

    parts = submission_id.split("_")
    clan_tag = parts[0]
    user_id = parts[1]

    await mongo.button_store.delete_one({"_id": submission_id})

    clan = await get_clan_by_tag(mongo, clan_tag)
    if not clan:
        await ctx.respond("❌ Error: Clan not found!", ephemeral=True)
        return

    approval_data = await create_submission_data(
        submission_type="Discord Post",
        clan=clan,
        user=ctx.user,
        discord_link=discord_link,
        notes=notes
    )

    approval_components_list = [
        Text(content=f"<@&{RECRUITMENT_PING}>"),
        Separator(divider=True, spacing=hikari.SpacingType.SMALL),
        Text(content="## 🔔 Clan Points Submission"),

        Section(
            components=[
                Text(content=(
                    f"**Submitted by:** {approval_data['user_mention']}\n"
                    f"**Clan:** {approval_data['clan_name']}\n"
                    f"**Type:** Discord Post\n"
                    f"**Time:** <t:{approval_data['timestamp']}:R>"
                ))
            ],
            accessory=Thumbnail(media=approval_data['clan_logo'])
        ),

        Separator(),

        Text(content="**📌 Discord Post Link:**"),

        ActionRow(
            components=[
                LinkButton(
                    label="View Discord Post",
                    url=discord_link,
                    emoji="🔗"
                )
            ]
        ),
    ]

    if notes:
        approval_components_list.append(Text(content=f"**📝 Notes:** {notes}"))

    approval_components_list.extend([
        ActionRow(
            components=[
                Button(
                    style=hikari.ButtonStyle.SUCCESS,
                    label="Approve",
                    emoji="✅",
                    custom_id=f"approve_points:discord_post_{clan_tag}_{user_id}"
                ),
                Button(
                    style=hikari.ButtonStyle.DANGER,
                    label="Deny",
                    emoji="❌",
                    custom_id=f"deny_points:discord_post_{clan_tag}_{user_id}"
                )
            ]
        ),

        Media(items=[MediaItem(media="assets/Purple_Footer.png")])
    ])

    approval_components = [
        Container(
            accent_color=MAGENTA_ACCENT,
            components=approval_components_list
        )
    ]

    try:
        await bot.rest.create_message(
            channel=APPROVAL_CHANNEL,
            components=approval_components,
            role_mentions=True
        )

        success_components = [
            Container(
                accent_color=GREEN_ACCENT,
                components=[
                    Text(content="## ✅ Submission Sent!"),
                    Text(content=(
                        f"Your Discord post submission for **{clan.name}** has been sent for approval.\n\n"
                        "You'll receive a DM once it's been reviewed by leadership."
                    )),

                    ActionRow(
                        components=[
                            Button(
                                style=hikari.ButtonStyle.PRIMARY,
                                label="Submit Another",
                                emoji="➕",
                                custom_id=f"report_another:{user_id}"
                            )
                        ]
                    ),

                    Media(items=[MediaItem(media="assets/Green_Footer.png")])
                ]
            )
        ]

        await ctx.respond(components=success_components, edit=True)

    except Exception as e:
        print(f"Error sending approval message: {e}")
        error_msg = f"❌ Error sending submission: {str(e)}"
        error_components = [
            Container(
                accent_color=RED_ACCENT,
                components=[
                    Text(content="## ❌ Submission Failed"),
                    Text(content=error_msg),
                    Text(content="Please contact an administrator."),

                    ActionRow(
                        components=[
                            Button(
                                style=hikari.ButtonStyle.SECONDARY,
                                label="Try Again",
                                emoji="🔄",
                                custom_id=f"cancel_report:{user_id}"
                            )
                        ]
                    ),

                    Media(items=[MediaItem(media="assets/Red_Footer.png")])
                ]
            )
        ]
        await ctx.respond(components=error_components, edit=True)
