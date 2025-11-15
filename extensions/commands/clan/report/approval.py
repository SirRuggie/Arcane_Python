# commands/clan/report/approval.py

"""Approval workflow handlers for clan points"""

import hikari
import lightbulb
from datetime import datetime

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
    SectionComponentBuilder as Section
)

from extensions.components import register_action
from utils.mongo import MongoClient
from utils.classes import Clan
from utils.constants import GREEN_ACCENT, DARK_MAGENTA_ACCENT

from .helpers import get_clan_by_tag, LOG_CHANNEL


# ╔══════════════════════════════════════════════════════════════╗
# ║                    Approve Points Handler                    ║
# ╚══════════════════════════════════════════════════════════════╝

@register_action("approve_points", ephemeral=True, no_return=True)
@lightbulb.di.with_di
async def approve_points(
        ctx: lightbulb.components.MenuContext,
        action_id: str,
        mongo: MongoClient = lightbulb.di.INJECTED,
        bot: hikari.GatewayBot = lightbulb.di.INJECTED,
        **kwargs
):
    """Handle point approval"""
    # Use MongoDB to prevent duplicate processing
    approval_key = f"approval_{ctx.interaction.message.id}"
    try:
        await mongo.button_store.insert_one({
            "_id": approval_key,
            "timestamp": datetime.now()
        })
    except:
        # Already being processed
        return

    # Show processing message
    processing_components = [
        Container(
            accent_color=GREEN_ACCENT,
            components=[
                Text(content="⏳ Processing approval...")
            ]
        )
    ]
    await ctx.respond(components=processing_components, edit=True)

    # Parse action_id format: "submission_type_clan_tag_user_id"
    parts = action_id.split("_")

    # Handle multi-word submission types
    if parts[0] == "discord" and parts[1] == "post":
        submission_type = "discord_post"
        clan_tag = parts[2]
        user_id = parts[3]
    elif parts[0] == "dm" and parts[1] == "recruit":
        submission_type = "dm_recruit"
        clan_tag = parts[2]
        user_id = parts[3]
    elif parts[0] == "disboard" and parts[1] == "review":
        submission_type = "disboard_review"
        clan_tag = parts[2]
        user_id = parts[3]
    else:
        submission_type = parts[0]
        clan_tag = parts[1]
        user_id = parts[2]

    # Get clan data
    clan = await get_clan_by_tag(mongo, clan_tag)
    if not clan:
        await ctx.interaction.edit_initial_response(
            components=[
                Container(
                    accent_color=DARK_MAGENTA_ACCENT,
                    components=[
                        Text(content="❌ Clan not found in database!")
                    ]
                )
            ]
        )
        await mongo.button_store.delete_one({"_id": approval_key})
        return

    # Update clan points
    new_points = clan.points + 1
    await mongo.clans.update_one(
        {"tag": clan_tag},
        {"$inc": {"points": 1}}
    )

    # Update recruit count for DM recruitment
    if submission_type == "dm_recruit":
        await mongo.clans.update_one(
            {"tag": clan_tag},
            {"$inc": {"recruit_count": 1}}
        )

    # Format submission type for display
    submission_display = {
        "discord_post": "Discord Server Posts",
        "dm_recruit": "Discord DM Recruiting",
        "disboard_review": "Disboard 5-Star Review",
        "member_left": "Member Left"
    }.get(submission_type, submission_type)

    # Send to log channel
    log_components = [
        Container(
            accent_color=GREEN_ACCENT,
            components=[
                Text(content=f"## ✅ Approval: Clan Points - {clan.name}"),

                Section(
                    components=[
                        Text(content=(
                            f"**{clan.name}**: Awarded +1 Point submitted by\n"
                            f"<@{user_id}> for {submission_display}.\n\n"
                            f"**Current Clan Points**\n"
                            f"• Clan now has **{new_points}** points."
                        ))
                    ],
                    accessory=Thumbnail(
                        media=clan.logo if clan.logo else "https://cdn-icons-png.flaticon.com/512/845/845665.png"
                    )
                ),

                Text(
                    content=f"-# Approved by {ctx.user.mention} • <t:{int(datetime.now().timestamp())}:f>"),

                Media(items=[MediaItem(media="assets/Green_Footer.png")])
            ]
        )
    ]

    await bot.rest.create_message(
        channel=LOG_CHANNEL,
        components=log_components
    )

    # Send DM to user
    try:
        user = await bot.rest.fetch_user(int(user_id))
        dm_channel = await user.fetch_dm_channel()

        dm_components = [
            Container(
                accent_color=GREEN_ACCENT,
                components=[
                    Text(content=f"## ✅ Clan Points Approved!"),
                    Text(content=(
                        f"Your clan point submission for **{clan.name}** has been approved!\n\n"
                        f"**Points Awarded:** 1\n"
                        f"**Submission Type:** {submission_display}\n"
                        f"**Clan Total:** {new_points} points\n\n"
                        "Thank you for your contribution!"
                    )),
                    Text(
                        content=f"-# Approved by {ctx.user.mention} • <t:{int(datetime.now().timestamp())}:f>"),
                    Media(items=[MediaItem(media="assets/Green_Footer.png")])
                ]
            )
        ]

        await bot.rest.create_message(
            channel=dm_channel.id,
            components=dm_components
        )
    except:
        pass  # User has DMs disabled

    # Delete the approval message
    await ctx.interaction.delete_initial_response()

    # Clean up MongoDB
    await mongo.button_store.delete_one({"_id": approval_key})


# ╔══════════════════════════════════════════════════════════════╗
# ║                    Deny Points Handler                       ║
# ╚══════════════════════════════════════════════════════════════╝

@register_action("deny_points", no_return=True, opens_modal=True)
@lightbulb.di.with_di
async def deny_points(
        ctx: lightbulb.components.MenuContext,
        action_id: str,
        mongo: MongoClient = lightbulb.di.INJECTED,
        **kwargs
):
    """Show denial modal"""
    # Store the message info_hub in the database before opening modal
    message_id = ctx.interaction.message.id
    channel_id = ctx.interaction.channel_id

    # Store in button_store temporarily
    denial_key = f"denial_{message_id}_{int(datetime.now().timestamp())}"
    await mongo.button_store.insert_one({
        "_id": denial_key,
        "message_id": message_id,
        "channel_id": channel_id,
        "action_id": action_id
    })

    # Parse action_id (same format as approve_points)
    parts = action_id.split("_")

    # Handle multi-word submission types
    if parts[0] == "discord" and parts[1] == "post":
        submission_type = "discord_post"
        clan_tag = parts[2]
        user_id = parts[3]
    elif parts[0] == "dm" and parts[1] == "recruit":
        submission_type = "dm_recruit"
        clan_tag = parts[2]
        user_id = parts[3]
    elif parts[0] == "disboard" and parts[1] == "review":
        submission_type = "disboard_review"
        clan_tag = parts[2]
        user_id = parts[3]
    else:
        submission_type = parts[0]
        clan_tag = parts[1]
        user_id = parts[2]

    reason_input = ModalActionRow().add_text_input(
        "denial_reason",
        "Denial Reason",
        placeholder="Please provide a reason for denying this submission",
        required=True,
        style=hikari.TextInputStyle.PARAGRAPH,
        max_length=500
    )

    await ctx.respond_with_modal(
        title="Deny Clan Points Submission",
        custom_id=f"confirm_deny:{denial_key}",  # Pass the denial_key instead
        components=[reason_input]
    )


# ╔══════════════════════════════════════════════════════════════╗
# ║                    Confirm Denial Handler                    ║
# ╚══════════════════════════════════════════════════════════════╝

@register_action("confirm_deny", no_return=True, is_modal=True)
@lightbulb.di.with_di
async def confirm_denial(
        ctx: lightbulb.components.ModalContext,
        action_id: str,
        mongo: MongoClient = lightbulb.di.INJECTED,
        bot: hikari.GatewayBot = lightbulb.di.INJECTED,
        **kwargs
):
    """Process denial with reason"""
    # Defer the response immediately to prevent timeout
    await ctx.interaction.create_initial_response(
        hikari.ResponseType.DEFERRED_MESSAGE_CREATE,
        flags=hikari.MessageFlag.EPHEMERAL
    )
    
    denial_key = action_id

    # Retrieve stored denial info_hub
    denial_info = await mongo.button_store.find_one({"_id": denial_key})
    if not denial_info:
        await ctx.interaction.edit_initial_response(
            "❌ Error: Session expired. Please try again."
        )
        return

    # Clean up stored data
    await mongo.button_store.delete_one({"_id": denial_key})

    # Get the original action_id
    original_action_id = denial_info["action_id"]
    message_id = denial_info["message_id"]
    channel_id = denial_info["channel_id"]

    # Parse action_id (same format as approve_points)
    parts = original_action_id.split("_")

    # Handle multi-word submission types
    if parts[0] == "discord" and parts[1] == "post":
        submission_type = "discord_post"
        clan_tag = parts[2]
        user_id = parts[3]
    elif parts[0] == "dm" and parts[1] == "recruit":
        submission_type = "dm_recruit"
        clan_tag = parts[2]
        user_id = parts[3]
    elif parts[0] == "disboard" and parts[1] == "review":
        submission_type = "disboard_review"
        clan_tag = parts[2]
        user_id = parts[3]
    else:
        submission_type = parts[0]
        clan_tag = parts[1]
        user_id = parts[2]

    # Extract denial reason
    reason = ""
    for row in ctx.interaction.components:
        for comp in row:
            if comp.custom_id == "denial_reason":
                reason = comp.value.strip()

    # Get clan data
    clan = await get_clan_by_tag(mongo, clan_tag)
    if not clan:
        await ctx.interaction.edit_initial_response("❌ Clan not found!")
        return

    # Format submission type
    submission_display = {
        "discord_post": "Discord Server Posts",
        "dm_recruit": "Discord DM Recruiting",
        "member_left": "Member Left"
    }.get(submission_type, submission_type)

    # Send to log channel
    log_components = [
        Container(
            accent_color=DARK_MAGENTA_ACCENT,
            components=[
                Text(content=f"## ❌ Denial: Clan Points - {clan.name}"),

                Section(
                    components=[
                        Text(content=(
                            f"**{clan.name}**: Denied submission by\n"
                            f"<@{user_id}> for {submission_display}.\n\n"
                            f"**Reason:** {reason}"
                        ))
                    ],
                    accessory=Thumbnail(
                        media=clan.logo if clan.logo else "https://cdn-icons-png.flaticon.com/512/845/845665.png"
                    )
                ),

                Text(
                    content=f"-# Denied by {ctx.user.mention} • <t:{int(datetime.now().timestamp())}:f>"),

                Media(items=[MediaItem(media="assets/Red_Footer.png")])
            ]
        )
    ]

    await bot.rest.create_message(
        channel=LOG_CHANNEL,
        components=log_components
    )

    # Send DM to user
    try:
        user = await bot.rest.fetch_user(int(user_id))
        dm_channel = await user.fetch_dm_channel()

        dm_components = [
            Container(
                accent_color=DARK_MAGENTA_ACCENT,
                components=[
                    Text(content=f"## ❌ Clan Points Denied"),
                    Text(content=(
                        f"Your clan point submission for **{clan.name}** was not approved.\n\n"
                        f"**Submission Type:** {submission_display}\n"
                        f"**Reason:** {reason}\n\n"
                        "If you have questions, please contact leadership."
                    )),
                    Text(
                        content=f"-# Denied by {ctx.user.mention} • <t:{int(datetime.now().timestamp())}:f>"),
                    Media(items=[MediaItem(media="assets/Red_Footer.png")])
                ]
            )
        ]

        await bot.rest.create_message(
            channel=dm_channel.id,
            components=dm_components
        )
    except:
        pass  # User has DMs disabled

    # Delete the approval message first
    try:
        await bot.rest.delete_message(
            channel=channel_id,
            message=message_id
        )
    except Exception as e:
        print(f"Error deleting approval message: {e}")
    
    # Then update the deferred response
    await ctx.interaction.edit_initial_response(
        "✅ Denial processed successfully. The approval message has been removed."
    )