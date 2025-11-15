# extensions/commands/utilities/add_perms.py
"""
Add Permissions command - Add specific permissions to a role for a category and all child channels
Restricted to user ID 505227988229554179 only
"""

import hikari
import lightbulb
import asyncio
import uuid
from typing import Dict, List, Optional

from hikari.impl import (
    MessageActionRowBuilder as ActionRow,
    TextSelectMenuBuilder as TextSelectMenu,
    SelectOptionBuilder as SelectOption,
    ContainerComponentBuilder as Container,
    TextDisplayComponentBuilder as Text,
    SeparatorComponentBuilder as Separator,
    MediaGalleryComponentBuilder as Media,
    MediaGalleryItemBuilder as MediaItem,
    InteractiveButtonBuilder as Button,
)

from extensions.commands.utilities import loader, utilities
from extensions.components import register_action
from utils.mongo import MongoClient
from utils.constants import GREEN_ACCENT, DARK_MAGENTA_ACCENT, BLUE_ACCENT

# Hard-coded user ID restriction
ALLOWED_USER_ID = 505227988229554179

# Permission groups for UI organization (max 25 per menu)
PERMISSION_OPTIONS_BASIC = [
    ("VIEW_CHANNEL", "View Channel", hikari.Permissions.VIEW_CHANNEL),
    ("MANAGE_CHANNELS", "Manage Channels", hikari.Permissions.MANAGE_CHANNELS),
    ("MANAGE_ROLES", "Manage Permissions", hikari.Permissions.MANAGE_ROLES),
    ("MANAGE_WEBHOOKS", "Manage Webhooks", hikari.Permissions.MANAGE_WEBHOOKS),
    ("CREATE_INSTANT_INVITE", "Create Invite", hikari.Permissions.CREATE_INSTANT_INVITE),
]

PERMISSION_OPTIONS_MESSAGE = [
    ("SEND_MESSAGES", "Send Messages", hikari.Permissions.SEND_MESSAGES),
    ("SEND_MESSAGES_IN_THREADS", "Send Messages in Threads", hikari.Permissions.SEND_MESSAGES_IN_THREADS),
    ("SEND_TTS_MESSAGES", "Send TTS Messages", hikari.Permissions.SEND_TTS_MESSAGES),
    ("EMBED_LINKS", "Embed Links", hikari.Permissions.EMBED_LINKS),
    ("ATTACH_FILES", "Attach Files", hikari.Permissions.ATTACH_FILES),
    ("ADD_REACTIONS", "Add Reactions", hikari.Permissions.ADD_REACTIONS),
    ("USE_EXTERNAL_EMOJIS", "Use External Emojis", hikari.Permissions.USE_EXTERNAL_EMOJIS),
    ("USE_EXTERNAL_STICKERS", "Use External Stickers", hikari.Permissions.USE_EXTERNAL_STICKERS),
    ("MENTION_ROLES", "Mention @everyone, @here, All Roles", hikari.Permissions.MENTION_ROLES),
    ("MANAGE_MESSAGES", "Manage Messages", hikari.Permissions.MANAGE_MESSAGES),
    ("READ_MESSAGE_HISTORY", "Read Message History", hikari.Permissions.READ_MESSAGE_HISTORY),
    ("USE_APPLICATION_COMMANDS", "Use Application Commands", hikari.Permissions.USE_APPLICATION_COMMANDS),
]

PERMISSION_OPTIONS_THREAD = [
    ("MANAGE_THREADS", "Manage Threads", hikari.Permissions.MANAGE_THREADS),
    ("CREATE_PUBLIC_THREADS", "Create Public Threads", hikari.Permissions.CREATE_PUBLIC_THREADS),
    ("CREATE_PRIVATE_THREADS", "Create Private Threads", hikari.Permissions.CREATE_PRIVATE_THREADS),
]

PERMISSION_OPTIONS_VOICE = [
    ("CONNECT", "Connect to Voice", hikari.Permissions.CONNECT),
    ("SPEAK", "Speak in Voice", hikari.Permissions.SPEAK),
    ("STREAM", "Video/Stream", hikari.Permissions.STREAM),
    ("USE_VOICE_ACTIVITY", "Use Voice Activity", hikari.Permissions.USE_VOICE_ACTIVITY),
    ("MUTE_MEMBERS", "Mute Members", hikari.Permissions.MUTE_MEMBERS),
    ("DEAFEN_MEMBERS", "Deafen Members", hikari.Permissions.DEAFEN_MEMBERS),
    ("MOVE_MEMBERS", "Move Members", hikari.Permissions.MOVE_MEMBERS),
    ("PRIORITY_SPEAKER", "Priority Speaker", hikari.Permissions.PRIORITY_SPEAKER),
]

PERMISSION_OPTIONS_OTHER = [
    ("CREATE_EVENTS", "Create Events", hikari.Permissions.CREATE_EVENTS),
    ("MANAGE_EVENTS", "Manage Events", hikari.Permissions.MANAGE_EVENTS),
]

# Combine all permissions for lookup
ALL_PERMISSIONS = {}
for group in [PERMISSION_OPTIONS_BASIC, PERMISSION_OPTIONS_MESSAGE, PERMISSION_OPTIONS_THREAD,
              PERMISSION_OPTIONS_VOICE, PERMISSION_OPTIONS_OTHER]:
    for perm_id, perm_label, perm_value in group:
        ALL_PERMISSIONS[perm_id] = (perm_label, perm_value)

# Permission category mapping for grouped display
PERMISSION_CATEGORIES = {
    "basic": {
        "name": "📋 Basic Permissions",
        "perms": [perm_id for perm_id, _, _ in PERMISSION_OPTIONS_BASIC]
    },
    "message": {
        "name": "💬 Message Permissions",
        "perms": [perm_id for perm_id, _, _ in PERMISSION_OPTIONS_MESSAGE]
    },
    "thread": {
        "name": "🧵 Thread Permissions",
        "perms": [perm_id for perm_id, _, _ in PERMISSION_OPTIONS_THREAD]
    },
    "voice": {
        "name": "🎙️ Voice Permissions",
        "perms": [perm_id for perm_id, _, _ in PERMISSION_OPTIONS_VOICE]
    },
    "other": {
        "name": "🎉 Other Permissions",
        "perms": [perm_id for perm_id, _, _ in PERMISSION_OPTIONS_OTHER]
    }
}


def build_basic_permissions_screen(stored_data: dict, action_id: str) -> List[Container]:
    """
    Build the first permission selection screen UI (Basic + Message permissions)

    Args:
        stored_data: MongoDB document containing category/role info
        action_id: UUID for this interaction session

    Returns:
        List of Container components for the first screen
    """
    # Create permission selection UI
    # Due to Discord's 25 option limit, we combine into one menu with most common permissions
    combined_options = []

    # Add Basic permissions
    for perm_id, perm_label, _ in PERMISSION_OPTIONS_BASIC:
        combined_options.append(
            SelectOption(label=perm_label, value=perm_id, description="Basic")
        )

    # Add Message permissions (most commonly used)
    for perm_id, perm_label, _ in PERMISSION_OPTIONS_MESSAGE:
        combined_options.append(
            SelectOption(label=perm_label, value=perm_id, description="Message")
        )

    # Limit to 25 options (Discord limit)
    combined_options = combined_options[:25]

    components = [
        Container(
            accent_color=BLUE_ACCENT,
            components=[
                Text(content=(
                    f"## 🔐 Add Permissions\n\n"
                    f"**Category:** {stored_data['category_name']}\n"
                    f"**Role:** <@&{stored_data['role_id']}>\n"
                    f"**Channels Affected:** {stored_data['child_channel_count'] + 1} (category + {stored_data['child_channel_count']} channels)\n\n"
                    f"Select the permissions you want to ADD to this role:\n"
                    f"*These permissions will be added without affecting other roles*"
                )),
                Separator(divider=True),
                Text(content="### Select Permissions (Basic + Message)"),
                ActionRow(
                    components=[
                        TextSelectMenu(
                            custom_id=f"add_perms_select_basic:{action_id}",
                            placeholder="Select permissions to add...",
                            min_values=1,
                            max_values=len(combined_options),
                            options=combined_options
                        )
                    ]
                ),
                Separator(divider=True),
                Text(content="*💡 Voice and thread permissions available on next screen*"),
                ActionRow(
                    components=[
                        Button(
                            style=hikari.ButtonStyle.PRIMARY,
                            label="Show More Permissions",
                            custom_id=f"add_perms_show_more:{action_id}"
                        ),
                        Button(
                            style=hikari.ButtonStyle.SECONDARY,
                            label="Cancel",
                            custom_id=f"add_perms_cancel:{action_id}"
                        )
                    ]
                ),
                Media(items=[MediaItem(media="assets/Blue_Footer.png")])
            ]
        )
    ]

    return components


@utilities.register()
class AddPerms(
    lightbulb.SlashCommand,
    name="add-perms",
    description="Add permissions to a role for a category and all child channels"
):
    category = lightbulb.channel(
        "category",
        "The category to add permissions to",
        channel_types=[hikari.ChannelType.GUILD_CATEGORY]
    )

    role = lightbulb.role(
        "role",
        "The role to add permissions to"
    )

    @lightbulb.invoke
    async def invoke(
        self,
        ctx: lightbulb.Context,
        bot: hikari.GatewayBot = lightbulb.di.INJECTED,
        mongo: MongoClient = lightbulb.di.INJECTED,
    ) -> None:
        await ctx.defer(ephemeral=True)

        # Hard-coded user restriction
        if ctx.user.id != ALLOWED_USER_ID:
            components = [
                Container(
                    accent_color=DARK_MAGENTA_ACCENT,
                    components=[
                        Text(content="## ❌ Access Denied"),
                        Separator(divider=True),
                        Text(content=(
                            "You do not have permission to use the Add Permissions command.\n\n"
                            "This command is restricted to a specific user only."
                        )),
                        Media(items=[MediaItem(media="assets/Red_Footer.png")])
                    ]
                )
            ]
            await ctx.respond(components=components, flags=hikari.MessageFlag.EPHEMERAL)
            return

        # Verify the selected channel is a category
        category_id = self.category.id
        try:
            source_category = await bot.rest.fetch_channel(category_id)
            if source_category.type != hikari.ChannelType.GUILD_CATEGORY:
                await ctx.respond(
                    "❌ Please select a category, not a channel!",
                    flags=hikari.MessageFlag.EPHEMERAL
                )
                return
        except Exception as e:
            await ctx.respond(
                f"❌ Failed to fetch category: {str(e)}",
                flags=hikari.MessageFlag.EPHEMERAL
            )
            return

        # Get role
        role_id = self.role.id
        role = self.role

        # Count child channels
        all_channels = await bot.rest.fetch_guild_channels(ctx.guild_id)
        child_channels = [ch for ch in all_channels if ch.parent_id == category_id]

        # Create action ID for storing state
        action_id = str(uuid.uuid4())

        # Store data
        stored_data = {
            "_id": action_id,
            "category_id": str(category_id),
            "category_name": source_category.name,
            "role_id": str(role_id),
            "role_name": role.name,
            "user_id": ctx.user.id,
            "child_channel_count": len(child_channels)
        }
        await mongo.button_store.insert_one(stored_data)

        # Build and show the first permission selection screen
        components = build_basic_permissions_screen(stored_data, action_id)
        await ctx.respond(components=components, flags=hikari.MessageFlag.EPHEMERAL)


@register_action("add_perms_select_basic", no_return=True)
@lightbulb.di.with_di
async def handle_basic_permissions(
    ctx: lightbulb.components.MenuContext,
    action_id: str,
    bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    """Handle basic permission selection"""
    # Get stored data
    stored_data = await mongo.button_store.find_one({"_id": action_id})
    if not stored_data:
        return await ctx.respond("❌ Session expired. Please run the command again.")

    # Verify user
    if ctx.user.id != stored_data["user_id"]:
        return await ctx.respond("❌ Only the command user can select permissions!")

    # Get selected permissions
    selected_perm_ids = ctx.interaction.values

    # Store selected permissions
    await mongo.button_store.update_one(
        {"_id": action_id},
        {"$set": {"selected_basic_perms": selected_perm_ids}}
    )

    # Show confirmation or additional permission selection
    await show_more_permissions(ctx, action_id, bot, mongo)


@register_action("add_perms_show_more", no_return=True)
@lightbulb.di.with_di
async def show_more_permissions(
    ctx: lightbulb.components.MenuContext,
    action_id: str,
    bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    """Show voice, thread, and other permissions"""
    # Get stored data
    stored_data = await mongo.button_store.find_one({"_id": action_id})
    if not stored_data:
        return await ctx.respond("❌ Session expired. Please run the command again.")

    # Combine voice, thread, and other permissions
    additional_options = []

    for perm_id, perm_label, _ in PERMISSION_OPTIONS_VOICE:
        additional_options.append(
            SelectOption(label=perm_label, value=perm_id, description="Voice")
        )

    for perm_id, perm_label, _ in PERMISSION_OPTIONS_THREAD:
        additional_options.append(
            SelectOption(label=perm_label, value=perm_id, description="Thread")
        )

    for perm_id, perm_label, _ in PERMISSION_OPTIONS_OTHER:
        additional_options.append(
            SelectOption(label=perm_label, value=perm_id, description="Other")
        )

    components = [
        Container(
            accent_color=BLUE_ACCENT,
            components=[
                Text(content=(
                    f"## 🔐 Add Permissions (Step 2)\n\n"
                    f"**Category:** {stored_data['category_name']}\n"
                    f"**Role:** <@&{stored_data['role_id']}>\n\n"
                    f"Select additional permissions (Voice, Thread, Other):\n"
                    f"*Optional - skip if not needed*"
                )),
                Separator(divider=True),
                Text(content="### Additional Permissions"),
                ActionRow(
                    components=[
                        TextSelectMenu(
                            custom_id=f"add_perms_select_more:{action_id}",
                            placeholder="Select additional permissions (optional)...",
                            min_values=0,
                            max_values=len(additional_options),
                            options=additional_options
                        )
                    ]
                ),
                Separator(divider=True),
                ActionRow(
                    components=[
                        Button(
                            style=hikari.ButtonStyle.SUCCESS,
                            label="Continue with Selected",
                            custom_id=f"add_perms_confirm:{action_id}"
                        ),
                        Button(
                            style=hikari.ButtonStyle.SECONDARY,
                            label="Back",
                            custom_id=f"add_perms_back:{action_id}"
                        )
                    ]
                ),
                Media(items=[MediaItem(media="assets/Blue_Footer.png")])
            ]
        )
    ]

    await ctx.respond(components=components, edit=True)


@register_action("add_perms_select_more", no_return=True)
@lightbulb.di.with_di
async def handle_additional_permissions(
    ctx: lightbulb.components.MenuContext,
    action_id: str,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    """Handle additional permission selection"""
    # Get stored data
    stored_data = await mongo.button_store.find_one({"_id": action_id})
    if not stored_data:
        return await ctx.respond("❌ Session expired. Please run the command again.")

    # Get selected permissions
    selected_perm_ids = ctx.interaction.values

    # Store additional permissions
    await mongo.button_store.update_one(
        {"_id": action_id},
        {"$set": {"selected_additional_perms": selected_perm_ids}}
    )

    # Auto-advance to confirmation
    await show_confirmation(ctx, action_id, mongo)


@register_action("add_perms_confirm", ephemeral=True)
@lightbulb.di.with_di
async def show_confirmation(
    ctx: lightbulb.components.MenuContext,
    action_id: str,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    """Show confirmation screen before applying permissions"""
    # Get stored data
    stored_data = await mongo.button_store.find_one({"_id": action_id})
    if not stored_data:
        return await ctx.respond("❌ Session expired. Please run the command again.")

    # Collect all selected permissions
    basic_perms = stored_data.get("selected_basic_perms", [])
    additional_perms = stored_data.get("selected_additional_perms", [])
    all_selected = basic_perms + additional_perms

    if not all_selected:
        return await ctx.respond("❌ No permissions selected! Please select at least one permission.")

    # Build grouped permission list for display
    permission_text_parts = []

    # Group permissions by category
    for category_key, category_info in PERMISSION_CATEGORIES.items():
        category_perms = []

        # Find all selected permissions in this category
        for perm_id in all_selected:
            if perm_id in category_info["perms"]:
                if perm_id in ALL_PERMISSIONS:
                    perm_label, _ = ALL_PERMISSIONS[perm_id]
                    category_perms.append(perm_label)

        # Only add category if it has permissions
        if category_perms:
            permission_text_parts.append(
                f"**{category_info['name']}** ({len(category_perms)})\n" +
                "\n".join([f"• {perm}" for perm in category_perms])
            )

    # Join all category sections with blank lines
    permission_display = "\n\n".join(permission_text_parts)

    components = [
        Container(
            accent_color=GREEN_ACCENT,
            components=[
                Text(content=(
                    f"## ✅ Confirm Permission Changes\n\n"
                    f"**Category:** {stored_data['category_name']}\n"
                    f"**Role:** <@&{stored_data['role_id']}>\n"
                    f"**Channels to Update:** {stored_data['child_channel_count'] + 1}\n\n"
                    f"**Permissions to ADD:**\n\n"
                    f"{permission_display}\n\n"
                    f"⚠️ **This will ADD these permissions without removing any existing permissions**"
                )),
                Separator(divider=True),
                ActionRow(
                    components=[
                        Button(
                            style=hikari.ButtonStyle.SUCCESS,
                            label="Apply Permissions",
                            emoji="✅",
                            custom_id=f"add_perms_apply:{action_id}"
                        ),
                        Button(
                            style=hikari.ButtonStyle.DANGER,
                            label="Cancel",
                            emoji="❌",
                            custom_id=f"add_perms_cancel:{action_id}"
                        )
                    ]
                ),
                Media(items=[MediaItem(media="assets/Green_Footer.png")])
            ]
        )
    ]

    await ctx.respond(components=components, edit=True)


@register_action("add_perms_apply", no_return=True)
@lightbulb.di.with_di
async def apply_permissions(
    ctx: lightbulb.components.MenuContext,
    action_id: str,
    bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    """Apply the selected permissions to category and all child channels"""
    # Get stored data
    stored_data = await mongo.button_store.find_one({"_id": action_id})
    if not stored_data:
        return await ctx.respond("❌ Session expired. Please run the command again.")

    # Show processing message
    processing_components = [
        Container(
            accent_color=BLUE_ACCENT,
            components=[
                Text(content=(
                    f"## ⏳ Applying Permissions...\n\n"
                    f"Please wait while permissions are being updated..."
                ))
            ]
        )
    ]
    await ctx.respond(components=processing_components, edit=True)

    try:
        # Collect all selected permissions
        basic_perms = stored_data.get("selected_basic_perms", [])
        additional_perms = stored_data.get("selected_additional_perms", [])
        all_selected = basic_perms + additional_perms

        # Convert permission IDs to hikari.Permissions and combine with OR
        combined_permissions = hikari.Permissions.NONE
        for perm_id in all_selected:
            if perm_id in ALL_PERMISSIONS:
                _, perm_value = ALL_PERMISSIONS[perm_id]
                combined_permissions = combined_permissions | perm_value

        category_id = int(stored_data["category_id"])
        role_id = int(stored_data["role_id"])

        # Get category
        category = await bot.rest.fetch_channel(category_id)

        # Update category permissions
        await update_channel_permissions(bot, category, role_id, combined_permissions)

        # Get and update all child channels
        all_channels = await bot.rest.fetch_guild_channels(ctx.guild_id)
        child_channels = [ch for ch in all_channels if ch.parent_id == category_id]

        updated_count = 1  # Category itself

        for channel in child_channels:
            try:
                await update_channel_permissions(bot, channel, role_id, combined_permissions)
                updated_count += 1
                await asyncio.sleep(0.3)  # Rate limit protection
            except Exception as e:
                print(f"Failed to update channel {channel.name}: {e}")

        # Success message
        success_components = [
            Container(
                accent_color=GREEN_ACCENT,
                components=[
                    Text(content=(
                        f"## ✅ Permissions Applied Successfully!\n\n"
                        f"**Category:** {stored_data['category_name']}\n"
                        f"**Role:** <@&{stored_data['role_id']}>\n"
                        f"**Channels Updated:** {updated_count} / {stored_data['child_channel_count'] + 1}\n\n"
                        f"**Permissions Added:** {len(all_selected)} permissions\n\n"
                        f"*All channels have been updated with the new permissions*"
                    )),
                    Separator(divider=True),
                    Text(content=f"-# Applied by <@{stored_data['user_id']}>"),
                    Media(items=[MediaItem(media="assets/Green_Footer.png")])
                ]
            )
        ]

        await ctx.respond(components=success_components, edit=True)

        # Clean up stored data
        await mongo.button_store.delete_one({"_id": action_id})

    except Exception as e:
        error_components = [
            Container(
                accent_color=DARK_MAGENTA_ACCENT,
                components=[
                    Text(content=(
                        f"## ❌ Failed to Apply Permissions\n\n"
                        f"**Error:** {str(e)}\n\n"
                        f"Please check bot permissions and try again."
                    )),
                    Media(items=[MediaItem(media="assets/Red_Footer.png")])
                ]
            )
        ]
        await ctx.respond(components=error_components, edit=True)


async def update_channel_permissions(
    bot: hikari.GatewayBot,
    channel: hikari.GuildChannel,
    role_id: int,
    new_permissions: hikari.Permissions
) -> None:
    """
    Update channel permissions for a role by ADDING new permissions to existing ones
    Does NOT affect other roles' permissions
    """
    # Get existing overwrites
    existing_overwrites = dict(channel.permission_overwrites)

    # Find target role's existing overwrite (if any)
    target_overwrite = existing_overwrites.get(hikari.Snowflake(role_id))

    if target_overwrite:
        # Combine with existing ALLOW permissions using bitwise OR
        new_allow = target_overwrite.allow | new_permissions
        updated_overwrite = hikari.PermissionOverwrite(
            id=hikari.Snowflake(role_id),
            type=hikari.PermissionOverwriteType.ROLE,
            allow=new_allow,
            deny=target_overwrite.deny  # Keep existing denies unchanged
        )
    else:
        # Create new overwrite
        updated_overwrite = hikari.PermissionOverwrite(
            id=hikari.Snowflake(role_id),
            type=hikari.PermissionOverwriteType.ROLE,
            allow=new_permissions,
            deny=hikari.Permissions.NONE
        )

    # Update the overwrites dict
    existing_overwrites[hikari.Snowflake(role_id)] = updated_overwrite

    # Apply to channel
    await bot.rest.edit_channel(
        channel.id,
        permission_overwrites=list(existing_overwrites.values())
    )


@register_action("add_perms_back", no_return=True)
@lightbulb.di.with_di
async def go_back(
    ctx: lightbulb.components.MenuContext,
    action_id: str,
    bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    """Go back to basic permissions screen"""
    # Get stored data
    stored_data = await mongo.button_store.find_one({"_id": action_id})
    if not stored_data:
        return await ctx.respond("❌ Session expired. Please run the command again.")

    # Clear any previously selected additional permissions (keep basic perms if already selected)
    await mongo.button_store.update_one(
        {"_id": action_id},
        {"$unset": {"selected_additional_perms": ""}}
    )

    # Recreate the first permission selection screen
    components = build_basic_permissions_screen(stored_data, action_id)
    await ctx.respond(components=components, edit=True)


@register_action("add_perms_cancel", no_return=True)
@lightbulb.di.with_di
async def cancel_command(
    ctx: lightbulb.components.MenuContext,
    action_id: str,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    """Cancel the permission addition"""
    # Clean up stored data
    await mongo.button_store.delete_one({"_id": action_id})

    components = [
        Container(
            accent_color=DARK_MAGENTA_ACCENT,
            components=[
                Text(content="## ❌ Cancelled\n\nPermission changes have been cancelled."),
                Media(items=[MediaItem(media="assets/Red_Footer.png")])
            ]
        )
    ]

    await ctx.respond(components=components, edit=True)
