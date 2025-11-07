# commands/clan/report/recruitment_help.py

"""Recruitment help posting system for clans to share their member needs"""

import hikari
import lightbulb
from datetime import datetime, timedelta
from typing import Optional, Dict

loader = lightbulb.Loader()

from hikari.impl import (
    MessageActionRowBuilder as ActionRow,
    ContainerComponentBuilder as Container,
    InteractiveButtonBuilder as Button,
    TextDisplayComponentBuilder as Text,
    SeparatorComponentBuilder as Separator,
    MediaGalleryComponentBuilder as Media,
    MediaGalleryItemBuilder as MediaItem,
    ModalActionRowBuilder as ModalActionRow,
    ThumbnailComponentBuilder as Thumbnail,
    SectionComponentBuilder as Section,
    TextSelectMenuBuilder as TextSelectMenu,
    SelectOptionBuilder as SelectOption
)

from extensions.components import register_action
from utils.mongo import MongoClient
from utils.classes import Clan
from utils.constants import BLUE_ACCENT, GREEN_ACCENT, RED_ACCENT, GOLD_ACCENT
from utils.emoji import emojis

from .helpers import get_clan_by_tag, get_clan_options, get_categorized_clan_components, create_progress_header

# Channel IDs
RECRUITMENT_CHANNEL = 1378084731874185357
LOG_CHANNEL = 1436169870273413169


# ╔══════════════════════════════════════════════════════════════╗
# ║                 Recruitment Help Select Handler              ║
# ╚══════════════════════════════════════════════════════════════╝

async def recruitment_help_select(
        ctx: lightbulb.components.MenuContext,
        action_id: str,
        mongo: MongoClient,
        **kwargs
):
    """Initial handler when recruitment help button is clicked"""
    # action_id is just the user_id when called from router
    user_id = action_id

    # Check if user is authorized
    if str(ctx.user.id) != user_id:
        await ctx.respond("❌ This button is not for you!", ephemeral=True)
        return

    # Build component list
    component_list = [
        Text(content=create_progress_header(1, 3, ["Select Clan", "Fill Form", "Review"])),
        Separator(),
        Text(content="## 📢 Recruitment Help Post"),
        Text(content="Select the clan you want to post recruitment needs for:"),
    ]

    # Add categorized clan dropdowns
    component_list.extend(await get_categorized_clan_components("rh_select_clan", user_id, mongo))

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


# ╔══════════════════════════════════════════════════════════════╗
# ║                    Clan Selection Handler                    ║
# ╚══════════════════════════════════════════════════════════════╝

@register_action("rh_select_clan", no_return=True, opens_modal=True)
@lightbulb.di.with_di
async def rh_clan_selected(
        ctx: lightbulb.components.MenuContext,
        action_id: str,
        mongo: MongoClient = lightbulb.di.INJECTED,
        **kwargs
):
    """Handle clan selection and check posting eligibility"""
    # Parse category prefix from action_id (e.g., "competitive_user123")
    if "_" in action_id and action_id.split("_")[0] in ["competitive", "zen", "fwa"]:
        category, action_id = action_id.split("_", 1)

    user_id = action_id
    clan_tag = ctx.interaction.values[0]

    # Get clan
    clan = await get_clan_by_tag(mongo, clan_tag)
    if not clan:
        await ctx.respond("❌ Clan not found!", ephemeral=True)
        return

    # Check if clan can post (30-day restriction)
    recruitment_data = await mongo.clan_recruitment.find_one({"clan_tag": clan_tag})

    if recruitment_data and "last_post_timestamp" in recruitment_data:
        last_post = datetime.fromtimestamp(recruitment_data["last_post_timestamp"])
        next_allowed = last_post + timedelta(days=30)

        if datetime.now() < next_allowed:
            # Calculate days remaining
            days_remaining = (next_allowed - datetime.now()).days

            await ctx.respond(
                components=[
                    Container(
                        accent_color=RED_ACCENT,
                        components=[
                            Text(content="## ❌ Posting Restricted"),
                            Text(content=(
                                f"**{clan.name}** must wait **{days_remaining} more days** before posting again.\n\n"
                                f"**Last Posted:** <t:{int(last_post.timestamp())}:F>\n"
                                f"**Can Post Again:** <t:{int(next_allowed.timestamp())}:F>"
                            )),
                            ActionRow(
                                components=[
                                    Button(
                                        style=hikari.ButtonStyle.SECONDARY,
                                        label="Back",
                                        custom_id=f"cancel_report:{user_id}"
                                    )
                                ]
                            ),
                            Media(items=[MediaItem(media="assets/Red_Footer.png")])
                        ]
                    )
                ],
                edit=True
            )
            return

    # Get current type from database
    current_type = clan.type or "Not Set"

    # Create modal with all fields
    style_input = ModalActionRow().add_text_input(
        "clan_type",
        "Clan Style",
        placeholder="e.g., Casual, Competitive, Heroes Up B2B Wars, etc.",
        required=True,
        style=hikari.TextInputStyle.PARAGRAPH,
        max_length=200
    )

    goals_input = ModalActionRow().add_text_input(
        "clan_goals",
        "Current Clan Goals (3-4 bullet points)",
        placeholder="• More Champ Quality Players\n• More In Game Engagement\n• Higher League Performance",
        required=True,
        style=hikari.TextInputStyle.PARAGRAPH,
        max_length=300
    )

    requirements_input = ModalActionRow().add_text_input(
        "member_requirements",
        "Member Requirements (2-3 bullet points)",
        placeholder="• Strong TH17 Players\n• Communication",
        required=True,
        style=hikari.TextInputStyle.PARAGRAPH,
        max_length=200
    )

    profile_input = ModalActionRow().add_text_input(
        "clan_profile",
        "Clan Profile (Optional)",
        placeholder="Your clan's 'About Me' section...",
        required=False,
        style=hikari.TextInputStyle.PARAGRAPH,
        max_length=500
    )

    await ctx.respond_with_modal(
        title="Recruitment Help Form",
        custom_id=f"rh_submit_form:{clan_tag}_{user_id}",
        components=[style_input, goals_input, requirements_input, profile_input]
    )


# ╔══════════════════════════════════════════════════════════════╗
# ║                   Form Submission Handler                    ║
# ╚══════════════════════════════════════════════════════════════╝

@register_action("rh_submit_form", no_return=True, is_modal=True)
@lightbulb.di.with_di
async def rh_submit_form(
        ctx: lightbulb.components.ModalContext,
        action_id: str,
        mongo: MongoClient = lightbulb.di.INJECTED,
        bot: hikari.GatewayBot = lightbulb.di.INJECTED,
        **kwargs
):
    """Handle form submission and show review"""
    parts = action_id.split("_")
    clan_tag = parts[0]
    user_id = parts[1]

    # Extract form data
    form_data = {}
    for row in ctx.interaction.components:
        for comp in row:
            form_data[comp.custom_id] = comp.value.strip() if comp.value else ""

    # Get clan data
    clan = await get_clan_by_tag(mongo, clan_tag)
    if not clan:
        await ctx.respond("❌ Clan not found!", ephemeral=True)
        return

    # Store submission data temporarily
    submission_id = f"rh_{clan_tag}_{user_id}_{int(datetime.now().timestamp())}"
    submission_data = {
        "_id": submission_id,
        "data": form_data,
        "clan_tag": clan_tag,
        "user_id": user_id
    }
    await mongo.button_store.insert_one(submission_data)

    # Create review components
    review_components = create_review_components(clan, form_data, submission_id)

    # Only call create_initial_response ONCE
    await ctx.interaction.create_initial_response(
        hikari.ResponseType.DEFERRED_MESSAGE_UPDATE
    )
    await ctx.interaction.edit_initial_response(components=review_components)


def truncate_text(text: str, max_length: int = 1000) -> str:
    """Truncate text to fit Discord's limits"""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."


def create_review_components(clan: Clan, form_data: Dict, submission_id: str) -> list:
    """Create the review screen components"""
    current_db_type = clan.type or "Not Set"

    # Truncate long content for display
    clan_type_display = truncate_text(form_data['clan_type'], 800)
    goals_display = truncate_text(form_data['clan_goals'], 800)
    requirements_display = truncate_text(form_data['member_requirements'], 800)
    profile_display = truncate_text(form_data.get('clan_profile', ''), 800) if form_data.get('clan_profile') else ''

    # Build components list
    component_list = [
        Text(content=create_progress_header(3, 3, ["Select Clan", "Fill Form", "Review"])),
        Separator(),
        Text(content="## 📋 Review Your Recruitment Needs Post"),
        Section(
            components=[
                Text(content=f"## {clan.emoji if clan.emoji else ''} **{clan.name}**"),
                Text(content=f"**Posting as:** <@{submission_id.split('_')[2]}>")
            ],
            accessory=Thumbnail(
                media=clan.logo if clan.logo else "https://cdn-icons-png.flaticon.com/512/845/845665.png"
            )
        ),
        Separator(),
        # Preview the post
        Text(content="### 📝 Post Preview:"),
        Text(content="**Clan Style:**"),
        Text(content=clan_type_display),
        Text(content=f"-# Current Set Style: `{current_db_type}`\n"),
        Text(content="**Current Goals:**"),
        Text(content=goals_display + "\n"),
        Text(content="**Member Requirements:**"),
        Text(content=requirements_display),
    ]

    # Add profile if provided
    if profile_display:
        component_list.extend([
            Text(content="\n**Clan Profile:**"),
            Text(content=profile_display)
        ])

    # Add action buttons
    component_list.extend([
        Separator(),
        ActionRow(
            components=[
                Button(
                    style=hikari.ButtonStyle.SUCCESS,
                    label="Submit to Recruitment Channel",
                    emoji="✅",
                    custom_id=f"rh_confirm:{submission_id}"
                ),
                Button(
                    style=hikari.ButtonStyle.DANGER,
                    label="Cancel",
                    custom_id=f"cancel_report:{submission_id.split('_')[2]}"
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

    return components


# ╔══════════════════════════════════════════════════════════════╗
# ║                    Confirm Submission Handler                ║
# ╚══════════════════════════════════════════════════════════════╝

@register_action("rh_confirm", ephemeral=True, no_return=True)
@lightbulb.di.with_di
async def rh_confirm_submission(
        ctx: lightbulb.components.MenuContext,
        action_id: str,
        mongo: MongoClient = lightbulb.di.INJECTED,
        bot: hikari.GatewayBot = lightbulb.di.INJECTED,
        **kwargs
):
    """Confirm and post the recruitment help"""
    submission_id = action_id

    # Show processing message
    await ctx.respond(
        components=[
            Container(
                accent_color=GREEN_ACCENT,
                components=[
                    Text(content="⏳ Processing your recruitment post...")
                ]
            )
        ],
        edit=True
    )

    # Get submission data
    submission = await mongo.button_store.find_one({"_id": submission_id})
    if not submission:
        await ctx.interaction.edit_initial_response(
            components=[
                Container(
                    accent_color=RED_ACCENT,
                    components=[Text(content="❌ Submission data not found!")]
                )
            ]
        )
        return

    form_data = submission["data"]
    clan_tag = submission["clan_tag"]
    user_id = submission["user_id"]

    # Get clan data including current DB type
    clan = await get_clan_by_tag(mongo, clan_tag)
    current_db_type = clan.type or "Not Set"

    # Create the recruitment post
    # Truncate content for the actual post too
    clan_type_post = truncate_text(form_data['clan_type'], 1000)
    goals_post = truncate_text(form_data['clan_goals'], 1000)
    requirements_post = truncate_text(form_data['member_requirements'], 1000)
    profile_post = truncate_text(form_data.get('clan_profile', ''), 1000) if form_data.get('clan_profile') else ''

    # Build component list
    post_component_list = [
        Section(
            components=[
                Text(content=f"# {clan.name}\n"),
            ],
            accessory=Thumbnail(
                media=clan.logo if clan.logo else "https://cdn-icons-png.flaticon.com/512/845/845665.png"
            )
        ),
        Text(content="## **Clan Style:**"),
        Text(content=clan_type_post),
        Text(content=f"-# Current Set Style: `{current_db_type}`\n"),
        Text(content="## **Current Goals:**"),
        Text(content=goals_post + "\n"),
        Text(content="## **Member Requirements:**"),
        Text(content=requirements_post + "\n"),
    ]

    # Add profile if provided
    if profile_post:
        post_component_list.extend([
            Text(content="## **Clan Profile:**"),
            Text(content=profile_post + "\n"),
        ])

    # Add posting info_hub
    posted_timestamp = int(datetime.now().timestamp())
    can_post_again_timestamp = int((datetime.now() + timedelta(days=30)).timestamp())

    post_component_list.extend([
        Separator(),
        Text(content=(
            f"-# Posted on: <t:{posted_timestamp}:D> at <t:{posted_timestamp}:t>\n"
            f"-# Can post again on: <t:{can_post_again_timestamp}:D>"
        )),
        Media(items=[MediaItem(media="assets/Gold_Footer.png")])
    ])

    # Create container with all components
    post_components = [
        Container(
            accent_color=GOLD_ACCENT,
            components=post_component_list
        )
    ]

    # Post to recruitment channel
    try:
        recruitment_msg = await bot.rest.create_message(
            channel=RECRUITMENT_CHANNEL,
            components=post_components
        )

        # Update clan points (+1)
        new_points = clan.points + 1
        await mongo.clans.update_one(
            {"tag": clan_tag},
            {"$inc": {"points": 1}}
        )

        # Update last post timestamp
        await mongo.clan_recruitment.update_one(
            {"clan_tag": clan_tag},
            {
                "$set": {
                    "last_post_timestamp": posted_timestamp,
                    "last_post_by": user_id,
                    "last_post_message_id": str(recruitment_msg.id),
                    "updated_at": datetime.now()
                },
                "$setOnInsert": {
                    "created_at": datetime.now()
                }
            },
            upsert=True
        )

        # Send log message
        # Get guild ID from context or use hardcoded value for your server
        guild_id = ctx.guild_id if ctx.guild_id else 1133045570211143680  # Replace with your server ID

        log_components = [
            Container(
                accent_color=GREEN_ACCENT,
                components=[
                    Section(
                        components=[
                            Text(content=f"## ✅ Recruitment Help: Clan Points - {clan.name}"),
                            Text(content=(
                                f"**{clan.name}**: Awarded +1 Point for posting recruitment needs\n"
                                f"• Clan now has **{new_points:.1f}** points.\n\n"
                                f"**Posted by:** <@{user_id}>\n"
                                f"**Posted in:** <#{RECRUITMENT_CHANNEL}>\n"
                                f"**Message:** [Jump to Post](https://discord.com/channels/{guild_id}/{RECRUITMENT_CHANNEL}/{recruitment_msg.id})"
                            )),
                        ],
                        accessory=Thumbnail(
                            media=clan.logo if clan.logo else "https://cdn-icons-png.flaticon.com/512/845/845665.png"
                        )
                    ),
                    Text(content=f"-# <t:{posted_timestamp}:F>"),
                    Media(items=[MediaItem(media="assets/Green_Footer.png")])
                ]
            )
        ]

        await bot.rest.create_message(
            channel=LOG_CHANNEL,
            components=log_components
        )

        # Send DM to user about points
        try:
            user = await bot.rest.fetch_user(int(user_id))
            dm_channel = await user.fetch_dm_channel()

            dm_components = [
                Container(
                    accent_color=GREEN_ACCENT,
                    components=[
                        Text(content="## ✅ Points Awarded!"),
                        Text(content=(
                            f"You've received **+1 point** for posting recruitment needs for **{clan.name}**!\n\n"
                            f"**New Clan Total:** {new_points:.1f} points\n\n"
                            "Thank you for helping alliance recruiters understand your clan's needs!"
                        )),
                        Media(items=[MediaItem(media="assets/Green_Footer.png")])
                    ]
                )
            ]

            await bot.rest.create_message(
                channel=dm_channel.id,
                components=dm_components
            )
        except Exception as e:
            print(f"Failed to DM user {user_id}: {e}")

        # Success message
        await ctx.interaction.edit_initial_response(
            components=[
                Container(
                    accent_color=GREEN_ACCENT,
                    components=[
                        Text(content="## ✅ Recruitment Needs Posted!"),
                        Text(content=(
                            f"Your recruitment needs for **{clan.name}** have been posted.\n\n"
                            f"Alliance recruiters can now see what you're looking for and help find suitable members.\n\n"
                            f"**Points Awarded:** +1\n"
                            f"**New Clan Total:** {new_points:.1f} points\n"
                            f"**Next Post Available:** <t:{can_post_again_timestamp}:R>\n\n"
                            f"[View Post](https://discord.com/channels/{guild_id}/{RECRUITMENT_CHANNEL}/{recruitment_msg.id})"
                        )),
                        ActionRow(
                            components=[
                                Button(
                                    style=hikari.ButtonStyle.PRIMARY,
                                    label="Done",
                                    custom_id=f"cancel_report:{user_id}"
                                )
                            ]
                        ),
                        Media(items=[MediaItem(media="assets/Green_Footer.png")])
                    ]
                )
            ]
        )

    except Exception as e:
        await ctx.interaction.edit_initial_response(
            components=[
                Container(
                    accent_color=RED_ACCENT,
                    components=[
                        Text(content=f"❌ Error posting recruitment help: {str(e)}")
                    ]
                )
            ]
        )
    finally:
        # Clean up submission data
        await mongo.button_store.delete_one({"_id": submission_id})