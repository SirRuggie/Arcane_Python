# commands/clan/report/disboard_review.py

"""Disboard review submission functionality with event-based image handling"""

import hikari
import lightbulb
import asyncio
from datetime import datetime
from typing import Dict

loader = lightbulb.Loader()

# Session storage for multi-step Disboard review flow
disboard_review_sessions = {}

from hikari.impl import (
    MessageActionRowBuilder as ActionRow,
    TextSelectMenuBuilder as TextSelectMenu,
    ContainerComponentBuilder as Container,
    InteractiveButtonBuilder as Button,
    TextDisplayComponentBuilder as Text,
    SeparatorComponentBuilder as Separator,
    MediaGalleryComponentBuilder as Media,
    MediaGalleryItemBuilder as MediaItem,
    ThumbnailComponentBuilder as Thumbnail,
    SectionComponentBuilder as Section,
)

from extensions.components import register_action
from utils.mongo import MongoClient
from utils.classes import Clan
from utils.constants import BLUE_ACCENT, GREEN_ACCENT, MAGENTA_ACCENT, DARK_MAGENTA_ACCENT

from .helpers import (
    get_clan_options,
    get_categorized_clan_components,
    create_progress_header,
    create_submission_data,
    get_clan_by_tag,
    APPROVAL_CHANNEL,
    RECRUITMENT_PING
)

# Temporary storage for Disboard review data
disboard_review_data: Dict[str, dict] = {}

# Image collection sessions - exported for event listener
image_collection_sessions: Dict[str, dict] = {}


# ╔══════════════════════════════════════════════════════════╗
# ║        Show Disboard Review Flow (Step 1)               ║
# ╚══════════════════════════════════════════════════════════╝

@lightbulb.di.with_di
async def show_disboard_review_flow(
        ctx: lightbulb.components.MenuContext,
        user_id: str,
        mongo: MongoClient = lightbulb.di.INJECTED
):
    """Show the Disboard review reporting flow - Step 1: Clan Selection"""
    # Build component list
    component_list = [
        Text(content=create_progress_header(1, 3, ["Select Clan", "Upload Screenshot", "Review"])),
        Separator(),
        Text(content="## ⭐ Select Your Clan"),
        Text(content="Which clan should receive the Disboard review point?"),
    ]

    # Add categorized clan dropdowns
    component_list.extend(await get_categorized_clan_components("dr_select_clan", user_id, mongo))

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
        Text(content="-# Select the clan that should receive +1 point for your Disboard review"),
        Media(items=[MediaItem(media="assets/Blue_Footer.png")])
    ])

    components = [
        Container(
            accent_color=BLUE_ACCENT,
            components=component_list
        )
    ]

    await ctx.respond(components=components, edit=True)


# Handler to restart Disboard review flow
@register_action("show_disboard_review", no_return=True)
@lightbulb.di.with_di
async def restart_disboard_review(
        ctx: lightbulb.components.MenuContext,
        action_id: str,
        mongo: MongoClient = lightbulb.di.INJECTED,
        **kwargs
):
    """Restart the Disboard review flow"""
    user_id = action_id
    await show_disboard_review_flow(ctx, user_id, mongo)


# ╔══════════════════════════════════════════════════════════╗
# ║        Disboard Review Clan Selection (Step 2)          ║
# ╚══════════════════════════════════════════════════════════╝

@register_action("dr_select_clan", no_return=True)
@lightbulb.di.with_di
async def dr_select_clan(
        ctx: lightbulb.components.MenuContext,
        action_id: str,
        mongo: MongoClient = lightbulb.di.INJECTED,
        bot: hikari.GatewayBot = lightbulb.di.INJECTED,
        **kwargs
):
    """Handle clan selection for Disboard review - show screenshot upload prompt"""
    # Parse category prefix from action_id (e.g., "competitive_user123")
    if "_" in action_id and action_id.split("_")[0] in ["competitive", "zen", "fwa"]:
        category, action_id = action_id.split("_", 1)

    user_id = action_id
    selected_clan = ctx.interaction.values[0]

    # Store the selected clan in session for later
    session_key = f"dr_{user_id}"
    disboard_review_sessions[session_key] = {
        "clan_tag": selected_clan,
        "user_id": user_id
    }

    # Get clan details for display
    clan_data = await mongo.clans.find_one({"tag": selected_clan})
    clan_name = clan_data.get("name", "Unknown Clan") if clan_data else "Unknown Clan"

    clan = await get_clan_by_tag(mongo, selected_clan)
    if not clan:
        await ctx.respond("❌ Clan not found!", ephemeral=True)
        return

    # Create session for image collection
    timestamp = int(datetime.now().timestamp())
    session_key = f"{selected_clan}_{user_id}_{timestamp}"

    # Show image upload prompt components
    components = [
        Container(
            accent_color=BLUE_ACCENT,
            components=[
                Text(content=create_progress_header(2, 3, ["Select Clan", "Upload Screenshot", "Review"])),
                Separator(),

                Text(content="## ⭐ **UPLOAD YOUR DISBOARD REVIEW SCREENSHOT NOW**"),
                Separator(divider=False, spacing=hikari.SpacingType.SMALL),
                Text(content="### 🎯 **DO THIS RIGHT NOW:**"),
                Text(content=(
                    "1. Click the **[+]** button or **📎 paperclip** at the bottom of **THIS chat**\n"
                    "2. Select your Disboard review screenshot from your computer\n"
                    "3. Press **Enter** to send it **RIGHT HERE**"
                )),
                Separator(divider=True, spacing=hikari.SpacingType.SMALL),
                Text(content="### ⚠️ **IMPORTANT:**"),
                Text(content=(
                    "• Upload it **in THIS channel** (not a DM, not another channel)\n"
                    "• Send it as your **very next message**\n"
                    "• Don't type anything - just send the image file\n"
                    "• The bot is watching and will automatically detect it"
                )),
                Separator(divider=True, spacing=hikari.SpacingType.SMALL),
                Text(content="### 💎 **What counts as a valid review:**"),
                Text(content=(
                    "• Must be a **5-star review** on Disboard\n"
                    "• Must have **meaningful content** (not just \"good server\")\n"
                    "• Must show your **Discord username** in the screenshot\n"
                    "• Awards your clan **+1 point** when approved!"
                )),
                Separator(divider=True, spacing=hikari.SpacingType.SMALL),
                Text(content=(
                    "⏱️ **You have 2 minutes** - Bot will clean up your message after"
                )),
                Separator(divider=True, spacing=hikari.SpacingType.SMALL),
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

                Text(content="-# 🟢 Bot is actively monitoring this channel for your upload..."),
                Media(items=[MediaItem(media="assets/Blue_Footer.png")])
            ]
        )
    ]

    # Update the message with upload instructions
    await ctx.respond(components=components, edit=True)

    # Store message ID
    message_id = ctx.interaction.message.id if ctx.interaction.message else None

    if not message_id:
        print(f"[ERROR] No message ID available for Disboard review upload prompt!")

    print(f"[Disboard Review] Stored message ID: {message_id} for session {session_key}")

    # Store session data with the message ID
    image_collection_sessions[session_key] = {
        "channel_id": ctx.channel_id,
        "user_id": int(user_id),
        "clan": clan,
        "timestamp": datetime.now(),
        "upload_prompt_message_id": message_id
    }

    # Also store in MongoDB for persistence
    await mongo.button_store.insert_one({
        "_id": f"dr_upload_{session_key}",
        "message_id": message_id,
        "channel_id": ctx.channel_id,
        "session_key": session_key
    })

    # Start timeout timer - cleanup session if no upload within 2 minutes
    async def cleanup_stale_session():
        await asyncio.sleep(120)  # 2 minutes as promised in UI
        if session_key in image_collection_sessions:
            # Session still exists = user never uploaded
            del image_collection_sessions[session_key]
            print(f"[Disboard Review] Cleaned up stale session {session_key} (no upload)")
            # Also cleanup MongoDB storage
            try:
                await mongo.button_store.delete_one({"_id": f"dr_upload_{session_key}"})
            except:
                pass

    asyncio.create_task(cleanup_stale_session())


# ╔══════════════════════════════════════════════════════════╗
# ║              Review Screen Functions                     ║
# ╚══════════════════════════════════════════════════════════╝

async def show_disboard_review_in_channel(bot: hikari.GatewayBot, session_key: str, user_id: str, channel_id: int,
                                    mongo: MongoClient):
    """Update the upload prompt message with review screen"""
    parts = session_key.split("_")
    clan_tag = parts[0]

    clan = await get_clan_by_tag(mongo, clan_tag)
    data = disboard_review_data[session_key]

    review_components = create_review_components(clan, data, session_key, user_id)

    # Get the upload prompt message ID from session
    session_data = image_collection_sessions.get(session_key, {})
    upload_message_id = session_data.get("upload_prompt_message_id")

    if not upload_message_id:
        # Try to get from MongoDB as backup
        stored_data = await mongo.button_store.find_one({"_id": f"dr_upload_{session_key}"})
        if stored_data:
            upload_message_id = stored_data.get("message_id")

    if upload_message_id:
        try:
            print(f"[Disboard Review] Attempting to edit message {upload_message_id} in channel {channel_id}")
            await bot.rest.edit_message(
                channel=channel_id,
                message=upload_message_id,
                components=review_components
            )
            print(f"[Disboard Review] Updated upload prompt message with review form")

            # Clean up MongoDB storage
            await mongo.button_store.delete_one({"_id": f"dr_upload_{session_key}"})

            # Start auto-cleanup timer (5 minutes)
            async def auto_cleanup():
                await asyncio.sleep(300)  # 5 minutes
                if session_key in disboard_review_data:
                    try:
                        await bot.rest.delete_message(
                            channel=channel_id,
                            message=upload_message_id
                        )
                        del disboard_review_data[session_key]
                        if session_key in disboard_review_sessions:
                            del disboard_review_sessions[session_key]
                        print(f"[Disboard Review] Auto-cleanup: Deleted review message after 5 minutes")
                    except:
                        pass

            asyncio.create_task(auto_cleanup())

        except hikari.NotFoundError:
            print(f"[Disboard Review] Message {upload_message_id} not found, creating new message")
            new_msg = await bot.rest.create_message(
                channel=channel_id,
                components=review_components
            )
        except Exception as e:
            print(f"[Disboard Review] Failed to edit message: {e}")
            new_msg = await bot.rest.create_message(
                channel=channel_id,
                components=review_components
            )
    else:
        print(f"[Disboard Review] No upload message ID found, creating new message")
        new_msg = await bot.rest.create_message(
            channel=channel_id,
            components=review_components
        )


def create_review_components(clan: Clan, data: dict, session_key: str, user_id: str) -> list:
    """Create review screen components"""
    review_components = [
        Text(content=create_progress_header(3, 3, ["Select Clan", "Upload Screenshot", "Review"])),
        Separator(),

        Text(content="## 📋 Review Your Submission"),

        Section(
            components=[
                Text(content=(
                    f"**Clan:** {clan.emoji if clan.emoji else ''} {clan.name}\n"
                    f"**Type:** Disboard Review\n"
                    f"**Points to Award:** 1"
                ))
            ],
            accessory=Thumbnail(
                media=clan.logo if clan.logo else "https://cdn-icons-png.flaticon.com/512/845/845665.png"
            )
        ),

        Separator(),
    ]

    # Add screenshot if available
    if data.get('screenshot_url'):
        review_components.extend([
            Text(content="**📸 Disboard Review Screenshot:**"),
            Media(items=[MediaItem(media=data['screenshot_url'])]),
            Separator(),
        ])
    else:
        review_components.append(
            Text(content="-# No screenshot provided")
        )

    # Add action buttons
    review_components.extend([
        ActionRow(
            components=[
                Button(
                    style=hikari.ButtonStyle.SUCCESS,
                    label="Submit for Approval",
                    emoji="✅",
                    custom_id=f"dr_confirm_submit:{session_key}"
                ),
                Button(
                    style=hikari.ButtonStyle.SECONDARY,
                    label="Cancel",
                    emoji="❌",
                    custom_id=f"dr_cancel_review:{session_key}_{user_id}"
                )
            ]
        ),

        Text(content="-# Your submission will be reviewed by leadership"),
        Text(content="-# This message will auto-delete in 5 minutes if not submitted"),
        Media(items=[MediaItem(media="assets/Green_Footer.png")])
    ])

    # Return wrapped in container
    return [
        Container(
            accent_color=GREEN_ACCENT,
            components=review_components
        )
    ]


# ╔══════════════════════════════════════════════════════════╗
# ║            Cancel Review Handler                         ║
# ╚══════════════════════════════════════════════════════════╝

@register_action("dr_cancel_review", no_return=True)
@lightbulb.di.with_di
async def dr_cancel_review(
        ctx: lightbulb.components.MenuContext,
        action_id: str,
        bot: hikari.GatewayBot = lightbulb.di.INJECTED,
        **kwargs
):
    """Cancel the review and delete the message"""
    parts = action_id.split("_")
    session_key = "_".join(parts[:-1])
    user_id = parts[-1]

    # Clean up data
    if session_key in disboard_review_data:
        del disboard_review_data[session_key]
    if session_key in disboard_review_sessions:
        del disboard_review_sessions[session_key]

    try:
        await bot.rest.delete_message(
            channel=ctx.channel_id,
            message=ctx.interaction.message.id
        )
        print(f"[Disboard Review] User {user_id} cancelled submission")
    except Exception as e:
        print(f"[Disboard Review] Failed to delete message on cancel: {e}")
        await ctx.interaction.create_initial_response(
            hikari.ResponseType.DEFERRED_MESSAGE_UPDATE
        )
        cancelled_components = [
            Container(
                accent_color=DARK_MAGENTA_ACCENT,
                components=[
                    Text(content="## ❌ Submission Cancelled"),
                    Text(content="This Disboard review submission has been cancelled."),
                    Media(items=[MediaItem(media="assets/Red_Footer.png")])
                ]
            )
        ]
        await ctx.interaction.edit_initial_response(components=cancelled_components)


# ╔══════════════════════════════════════════════════════════╗
# ║            Confirm Submission Handler                    ║
# ╚══════════════════════════════════════════════════════════╝

@register_action("dr_confirm_submit", no_return=True)
@lightbulb.di.with_di
async def dr_confirm_submission(
        ctx: lightbulb.components.MenuContext,
        action_id: str,
        mongo: MongoClient = lightbulb.di.INJECTED,
        bot: hikari.GatewayBot = lightbulb.di.INJECTED,
        **kwargs
):
    """Finalize Disboard review submission and send to approval"""
    session_key = action_id

    if session_key not in disboard_review_data:
        await ctx.respond("❌ Error: Session expired. Please start over.", ephemeral=True)
        return

    data = disboard_review_data[session_key]
    parts = session_key.split("_")
    clan_tag = parts[0]
    user_id = parts[1]

    clan = await get_clan_by_tag(mongo, clan_tag)
    if not clan:
        await ctx.respond("❌ Error: Clan not found!", ephemeral=True)
        return

    try:
        approval_components_list = [
            Text(content=f"<@&{RECRUITMENT_PING}>"),
            Separator(divider=True, spacing=hikari.SpacingType.SMALL),
            Text(content="## 🔔 Clan Points Submission"),

            Section(
                components=[
                    Text(content=(
                        f"**Submitted by:** <@{user_id}>\n"
                        f"**Clan:** {clan.emoji if clan.emoji else ''} {clan.name}\n"
                        f"**Type:** Disboard Review\n"
                        f"**Time:** <t:{int(datetime.now().timestamp())}:R>"
                    ))
                ],
                accessory=Thumbnail(media=clan.logo if clan.logo else "https://cdn-icons-png.flaticon.com/512/845/845665.png")
            ),

            Separator(),
        ]

        if data.get('screenshot_url'):
            approval_components_list.extend([
                Text(content="**📸 Review Screenshot:**"),
                Media(items=[MediaItem(media=data['screenshot_url'])]),
                Separator(),
            ])

        approval_components_list.extend([
            Text(content="### ⚠️ **Verify:**"),
            Text(content=(
                "• Review is **5 stars**\n"
                "• Contains **meaningful content**\n"
                "• Shows **Discord username**\n"
                "• Is for **Kings Alliance** server"
            )),
            Separator(),
            ActionRow(
                components=[
                    Button(
                        style=hikari.ButtonStyle.SUCCESS,
                        label="Approve",
                        emoji="✅",
                        custom_id=f"approve_points:disboard_review_{clan_tag}_{user_id}"
                    ),
                    Button(
                        style=hikari.ButtonStyle.DANGER,
                        label="Deny",
                        emoji="❌",
                        custom_id=f"deny_points:disboard_review_{clan_tag}_{user_id}"
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

        # Send to approval channel
        await bot.rest.create_message(
            channel=APPROVAL_CHANNEL,
            components=approval_components,
            role_mentions=True
        )

        # Clean up data
        del disboard_review_data[session_key]

        # Delete the review message
        await bot.rest.delete_message(
            channel=ctx.channel_id,
            message=ctx.interaction.message.id
        )

        success_components = [
            Container(
                accent_color=GREEN_ACCENT,
                components=[
                    Text(content="## ✅ Submission Sent!"),
                    Text(content=(
                        f"Your Disboard review submission for **{clan.name}** has been sent for approval.\n\n"
                        "You'll receive a DM once it's been reviewed by leadership."
                    )),
                    Media(items=[MediaItem(media="assets/Green_Footer.png")])
                ]
            )
        ]

        await ctx.respond(components=success_components, ephemeral=True)

    except Exception as e:
        import traceback
        print(f"[Disboard Review] Failed to submit for approval: {e}")
        print(f"[Disboard Review] Traceback: {traceback.format_exc()}")

        await ctx.respond(
            f"❌ Error submitting for approval: {str(e)[:200]}\n\nPlease try again or contact an administrator.",
            ephemeral=True
        )