# extensions/commands/utilities/clone_category.py
"""
Clone category command - Clone a category with all channels for a specific clan
"""

import hikari
import lightbulb
import asyncio
import uuid
import aiohttp
from typing import Dict, List, Optional, Tuple

from hikari.impl import (
    MessageActionRowBuilder as ActionRow,
    TextSelectMenuBuilder as TextSelectMenu,
    SelectOptionBuilder as SelectOption,
    ContainerComponentBuilder as Container,
    SectionComponentBuilder as Section,
    TextDisplayComponentBuilder as Text,
    SeparatorComponentBuilder as Separator,
    MediaGalleryComponentBuilder as Media,
    MediaGalleryItemBuilder as MediaItem,
    ThumbnailComponentBuilder as Thumbnail,
)

from extensions.commands.utilities import loader, utilities
from extensions.components import register_action
from utils.mongo import MongoClient
from utils.classes import Clan
from utils.constants import GREEN_ACCENT, DARK_MAGENTA_ACCENT
from utils.emoji import emojis

# Permission constants - same as clan dashboard
CLAN_MANAGEMENT_ROLE_ID = 1060318031575793694
ADDITIONAL_MANAGEMENT_ROLE_ID = 1371470242076954706
ALLOWED_MANAGEMENT_ROLES = [CLAN_MANAGEMENT_ROLE_ID, ADDITIONAL_MANAGEMENT_ROLE_ID]


class CloneLogger:
    """Collects log messages during cloning process"""
    def __init__(self):
        self.logs = []
        self.warnings = []
        self.errors = []
        
    def info(self, message: str):
        self.logs.append(f"ℹ️ {message}")
        print(f"[INFO] {message}")  # Still print for server logs
        
    def success(self, message: str):
        self.logs.append(f"✅ {message}")
        print(f"[SUCCESS] {message}")
        
    def warning(self, message: str):
        self.warnings.append(message)
        self.logs.append(f"⚠️ {message}")
        print(f"[WARNING] {message}")
        
    def error(self, message: str):
        self.errors.append(message)
        self.logs.append(f"❌ {message}")
        print(f"[ERROR] {message}")
        
    def get_summary(self) -> str:
        """Get a summary of warnings and errors"""
        summary = []
        if self.warnings:
            summary.append(f"**⚠️ Warnings ({len(self.warnings)}):**")
            for warning in self.warnings[:5]:  # Show first 5
                summary.append(f"• {warning}")
            if len(self.warnings) > 5:
                summary.append(f"• ...and {len(self.warnings) - 5} more")
                
        if self.errors:
            if summary:
                summary.append("")  # Empty line
            summary.append(f"**❌ Errors ({len(self.errors)}):**")
            for error in self.errors[:5]:  # Show first 5
                summary.append(f"• {error}")
            if len(self.errors) > 5:
                summary.append(f"• ...and {len(self.errors) - 5} more")
                
        return "\n".join(summary) if summary else ""

# Helper functions
def get_clan_suffix(clan_name: str, max_length: int = 6) -> str:
    """Create a clan suffix from clan name (max 6 chars)"""
    # Remove spaces and special characters
    clean_name = ''.join(c for c in clan_name if c.isalnum())
    return f"-{clean_name[:max_length]}"


def remove_existing_suffix(channel_name: str) -> str:
    """Remove existing clan suffix from channel name"""
    # Common clan suffixes to look for (can be expanded)
    # Split by last hyphen and check if suffix is 2-6 characters (typical clan abbreviations)
    parts = channel_name.rsplit('-', 1)
    
    if len(parts) == 2:
        base_name, suffix = parts
        # Check if suffix looks like a clan abbreviation (2-6 alphanumeric chars)
        if 2 <= len(suffix) <= 6 and suffix.replace('_', '').isalnum():
            # Return the base name without the suffix
            return base_name
    
    # No suffix detected, return original name
    return channel_name


def log_message(message: str, logger: Optional[CloneLogger] = None, level: str = "info"):
    """Log a message with optional logger"""
    if logger:
        if level == "success":
            logger.success(message)
        elif level == "warning":
            logger.warning(message)
        elif level == "error":
            logger.error(message)
        else:
            logger.info(message)
    else:
        print(f"[{level.upper()}] {message}")


async def clone_permission_overwrites(
    overwrites: Dict[hikari.Snowflake, hikari.PermissionOverwrite],
    new_clan_role_id: Optional[hikari.Snowflake],
    new_leader_role_id: Optional[hikari.Snowflake],
    mongo: MongoClient
) -> Dict[hikari.Snowflake, hikari.PermissionOverwrite]:
    """
    Clone permission overwrites, removing ALL clan roles and adding new ones with preserved permissions
    """
    # Find what clan roles exist and get their permissions
    sample_clan_overwrite, sample_leader_overwrite, all_found_clan_roles = await find_clan_roles_in_overwrites(overwrites, mongo)

    # Get complete list of clan role IDs to remove
    all_clan_role_ids, all_leader_role_ids = await get_all_clan_role_ids(mongo)

    # Start with clean overwrites, removing all clan-related roles
    new_overwrites = {}

    for target_id, overwrite in overwrites.items():
        # Skip all clan roles and leader roles - we'll add new ones
        if target_id not in all_clan_role_ids and target_id not in all_leader_role_ids:
            new_overwrites[target_id] = overwrite

    # Add new clan role with preserved permissions (or defaults)
    if new_clan_role_id:
        if sample_clan_overwrite:
            # Use the same permissions as the old clan role
            new_overwrites[new_clan_role_id] = hikari.PermissionOverwrite(
                id=new_clan_role_id,
                type=hikari.PermissionOverwriteType.ROLE,
                allow=sample_clan_overwrite.allow,
                deny=sample_clan_overwrite.deny
            )
        else:
            # No existing clan role found, use default permissions
            new_overwrites[new_clan_role_id] = hikari.PermissionOverwrite(
                id=new_clan_role_id,
                type=hikari.PermissionOverwriteType.ROLE,
                allow=hikari.Permissions.VIEW_CHANNEL | hikari.Permissions.SEND_MESSAGES | hikari.Permissions.READ_MESSAGE_HISTORY,
                deny=hikari.Permissions.NONE
            )

    # Add new leader role with preserved permissions (or defaults)
    if new_leader_role_id:
        if sample_leader_overwrite:
            # Use the same permissions as the old leader role
            new_overwrites[new_leader_role_id] = hikari.PermissionOverwrite(
                id=new_leader_role_id,
                type=hikari.PermissionOverwriteType.ROLE,
                allow=sample_leader_overwrite.allow,
                deny=sample_leader_overwrite.deny
            )
        else:
            # No existing leader role found, use default elevated permissions
            new_overwrites[new_leader_role_id] = hikari.PermissionOverwrite(
                id=new_leader_role_id,
                type=hikari.PermissionOverwriteType.ROLE,
                allow=hikari.Permissions.VIEW_CHANNEL | hikari.Permissions.SEND_MESSAGES | hikari.Permissions.READ_MESSAGE_HISTORY | hikari.Permissions.MANAGE_MESSAGES,
                deny=hikari.Permissions.NONE
            )

    return new_overwrites


async def get_all_clan_role_ids(mongo: MongoClient) -> Tuple[List[hikari.Snowflake], List[hikari.Snowflake]]:
    """
    Get all clan role IDs and leader role IDs from the database
    Returns: (clan_role_ids, leader_role_ids)
    """
    clan_data = await mongo.clans.find(
        {"$or": [{"role_id": {"$exists": True, "$ne": None}}, {"leader_role_id": {"$exists": True, "$ne": None}}]}
    ).to_list(length=None)

    clan_role_ids = []
    leader_role_ids = []

    for clan in clan_data:
        if clan.get("role_id"):
            clan_role_ids.append(hikari.Snowflake(clan["role_id"]))
        if clan.get("leader_role_id"):
            leader_role_ids.append(hikari.Snowflake(clan["leader_role_id"]))

    return clan_role_ids, leader_role_ids


async def find_clan_roles_in_overwrites(
    overwrites: Dict[hikari.Snowflake, hikari.PermissionOverwrite],
    mongo: MongoClient
) -> Tuple[Optional[hikari.PermissionOverwrite], Optional[hikari.PermissionOverwrite], List[hikari.Snowflake]]:
    """
    Find clan roles in overwrites using database lookup
    Returns: (sample_clan_overwrite, sample_leader_overwrite, all_clan_role_ids_found)
    """
    # Get all clan role IDs from database
    all_clan_role_ids, all_leader_role_ids = await get_all_clan_role_ids(mongo)

    sample_clan_overwrite = None
    sample_leader_overwrite = None
    found_clan_role_ids = []

    # Check each overwrite to see if it's a clan role
    for role_id, overwrite in overwrites.items():
        if role_id in all_clan_role_ids:
            found_clan_role_ids.append(role_id)
            if sample_clan_overwrite is None:
                sample_clan_overwrite = overwrite  # Save the first one as a template
        elif role_id in all_leader_role_ids:
            if sample_leader_overwrite is None:
                sample_leader_overwrite = overwrite  # Save the first one as a template

    return sample_clan_overwrite, sample_leader_overwrite, found_clan_role_ids


async def clone_forum_threads(
    bot: hikari.GatewayBot,
    source_forum_id: hikari.Snowflake,
    target_forum_id: hikari.Snowflake,
    logger: Optional[CloneLogger] = None
) -> int:
    """Clone all threads from source forum to target forum"""
    threads_created = 0
    
    try:
        # Get the forum channel info
        forum_channel = await bot.rest.fetch_channel(source_forum_id)
        guild_id = forum_channel.guild_id
        
        if logger:
            logger.info(f"Fetching threads for forum: {forum_channel.name}")
        else:
            print(f"\n=== Fetching threads for forum {source_forum_id} ===")
            print(f"Forum name: {forum_channel.name}")
            print(f"Guild ID: {guild_id}")
        
        forum_threads = []
        thread_ids = set()
        
        # Method 1: Try active threads endpoint for the whole guild
        print("\n1. Checking active threads in guild...")
        try:
            active_threads = await bot.rest.fetch_active_threads(guild_id)
            print(f"   Active threads response type: {type(active_threads)}")
            
            # active_threads should be a sequence of threads
            active_count = 0
            for thread in active_threads:
                if hasattr(thread, 'parent_id') and thread.parent_id == source_forum_id:
                    forum_threads.append(thread)
                    thread_ids.add(thread.id)
                    active_count += 1
                    print(f"   ✓ Found active thread: {thread.name} (ID: {thread.id})")
            
            print(f"   Found {active_count} active threads in this forum")
            
        except Exception as e:
            print(f"   ✗ Error fetching active threads: {type(e).__name__}: {e}")
        
        # Method 2: Try guild channels approach
        print("\n2. Checking all guild channels...")
        try:
            all_channels = await bot.rest.fetch_guild_channels(guild_id)
            print(f"   Total channels in guild: {len(all_channels)}")
            
            channel_count = 0
            for channel in all_channels:
                if hasattr(channel, 'parent_id') and channel.parent_id == source_forum_id:
                    channel_count += 1
                    if channel.id not in thread_ids:
                        forum_threads.append(channel)
                        thread_ids.add(channel.id)
                        print(f"   ✓ Found channel/thread: {channel.name} (type: {channel.type}, ID: {channel.id})")
            
            print(f"   Found {channel_count} channels with forum as parent")
            
        except Exception as e:
            print(f"   ✗ Error fetching guild channels: {type(e).__name__}: {e}")
        
        # Method 3: Try archived threads
        print("\n3. Checking archived threads...")
        try:
            archived_response = await bot.rest.fetch_public_archived_threads(source_forum_id)
            print(f"   Archived response type: {type(archived_response)}")
            
            archived_count = 0
            # The response should be iterable
            for thread in archived_response:
                if thread.id not in thread_ids:
                    forum_threads.append(thread)
                    thread_ids.add(thread.id)
                    archived_count += 1
                    print(f"   ✓ Found archived thread: {thread.name} (ID: {thread.id})")
            
            print(f"   Found {archived_count} archived threads")
            
        except Exception as e:
            print(f"   ✗ Error fetching archived threads: {type(e).__name__}: {e}")
        
        print(f"\n=== Total threads found: {len(forum_threads)} ===")
        
        if len(forum_threads) == 0:
            print("\nDEBUG: No threads found. Possible reasons:")
            print("- Forum might not have any threads")
            print("- Bot might not have permission to view threads")
            print("- Threads might be in a different format")
            return 0
        
        # Create threads in target forum
        print(f"\n=== Cloning {len(forum_threads)} threads to target forum ===")
        
        for i, thread in enumerate(forum_threads, 1):
            try:
                print(f"\n[{i}/{len(forum_threads)}] Cloning thread: {thread.name}")
                
                # Get the starter message (thread ID = starter message ID in Discord forums)
                print("   Fetching starter message...")
                first_message = None
                attachments = []
                
                try:
                    # In Discord forums, the thread ID is the same as the starter message ID
                    first_message = await bot.rest.fetch_message(thread.id, thread.id)
                    print(f"   ✓ Found starter message (ID: {first_message.id})")
                    if first_message.attachments:
                        attachments = first_message.attachments
                        print(f"   ✓ Found {len(attachments)} attachment(s)")
                        for att in attachments:
                            print(f"     - {att.filename} ({att.size} bytes) - {att.url}")
                    else:
                        print("   • No attachments in starter message")
                except Exception as e:
                    print(f"   ✗ Failed to fetch starter message directly: {type(e).__name__}: {e}")
                    # Fallback: get the oldest message
                    try:
                        messages = await bot.rest.fetch_messages(thread.id)
                        if messages:
                            first_message = min(messages, key=lambda m: m.created_at)
                            if first_message.attachments:
                                attachments = first_message.attachments
                                print(f"   Found {len(attachments)} attachment(s) in oldest message")
                                for att in attachments:
                                    print(f"     - {att.filename} ({att.size} bytes) - {att.url}")
                    except Exception as fallback_error:
                        print(f"   Fallback also failed: {fallback_error}")
                
                # No default content - just the image
                content = ""
                
                # Handle attachments
                attachment_resources = []
                if attachments:
                    print("   Processing attachments...")
                    for attachment in attachments:
                        try:
                            # Download the attachment data
                            print(f"     Downloading {attachment.filename}...")
                            async with aiohttp.ClientSession() as session:
                                async with session.get(attachment.url) as response:
                                    if response.status == 200:
                                        file_data = await response.read()
                                        # Create a bytes resource
                                        bytes_resource = hikari.files.Bytes(
                                            file_data,
                                            attachment.filename
                                        )
                                        attachment_resources.append(bytes_resource)
                                        print(f"     ✓ Downloaded {attachment.filename} ({len(file_data)} bytes)")
                                    else:
                                        print(f"     ✗ Failed to download {attachment.filename}: HTTP {response.status}")
                        except Exception as e:
                            print(f"     ✗ Error downloading {attachment.filename}: {e}")
                            # Fallback to URL method
                            try:
                                url_resource = hikari.files.URL(
                                    url=attachment.url,
                                    filename=attachment.filename
                                )
                                attachment_resources.append(url_resource)
                                print(f"     ★ Using URL fallback for {attachment.filename}")
                            except Exception as e2:
                                print(f"     ✗ URL fallback also failed: {e2}")
                
                # Create the forum post
                print("   Creating forum post...")
                try:
                    if attachment_resources:
                        print(f"   Uploading with {len(attachment_resources)} attachment(s)...")
                        new_thread = await bot.rest.create_forum_post(
                            target_forum_id,
                            thread.name,
                            content=content,
                            attachments=attachment_resources,
                            auto_archive_duration=thread.auto_archive_duration,
                            rate_limit_per_user=thread.rate_limit_per_user
                        )
                    else:
                        print("   Creating post without attachments...")
                        # Discord requires some content, use a minimal placeholder
                        new_thread = await bot.rest.create_forum_post(
                            target_forum_id,
                            thread.name,
                            content="." if not content else content,  # Minimal content if empty
                            auto_archive_duration=thread.auto_archive_duration,
                            rate_limit_per_user=thread.rate_limit_per_user
                        )
                    
                    threads_created += 1
                    print(f"   ✓ Successfully cloned thread: {thread.name} (new ID: {new_thread.id})")
                    
                except Exception as e:
                    print(f"   ✗ Failed to create forum post: {type(e).__name__}: {e}")
                    raise
                
                # Small delay to avoid rate limits
                await asyncio.sleep(0.5)
                
            except Exception as e:
                print(f"\n✗ Failed to clone thread {thread.name}: {type(e).__name__}: {e}")
                import traceback
                traceback.print_exc()
        
        print(f"\n=== Forum cloning complete: {threads_created}/{len(forum_threads)} threads cloned ===")
                
    except Exception as e:
        print(f"\n✗ Failed to fetch threads from forum {source_forum_id}: {e}")
        import traceback
        traceback.print_exc()
    
    return threads_created


@utilities.register()
class CloneCategory(
    lightbulb.SlashCommand,
    name="clone-category",
    description="Clone a category with all channels for a specific clan"
):
    category = lightbulb.channel(
        "category",
        "The category to clone",
        channel_types=[hikari.ChannelType.GUILD_CATEGORY]
    )
    
    @lightbulb.invoke
    async def invoke(
        self,
        ctx: lightbulb.Context,
        bot: hikari.GatewayBot = lightbulb.di.INJECTED,
        mongo: MongoClient = lightbulb.di.INJECTED,
    ) -> None:
        await ctx.defer(ephemeral=True)

        # Check if user has the required role
        member = ctx.member
        if not member:
            await ctx.respond(
                "❌ Unable to verify permissions. Please try again.",
                flags=hikari.MessageFlag.EPHEMERAL
            )
            return

        # Check if the user has any of the allowed management roles
        user_role_ids = [role.id for role in member.get_roles()]
        if not any(role_id in user_role_ids for role_id in ALLOWED_MANAGEMENT_ROLES):
            # User doesn't have permission - show access denied message
            components = [
                Container(
                    accent_color=DARK_MAGENTA_ACCENT,
                    components=[
                        Text(content="## ❌ Access Denied"),
                        Separator(divider=True),
                        Text(content=(
                            "You do not have permission to use the Clone Category command.\n\n"
                            "This feature is restricted to users with Clan Management roles.\n"
                            "If you believe you should have access, please contact an administrator."
                        )),
                        Media(
                            items=[
                                MediaItem(media="assets/Red_Footer.png")
                            ]
                        ),
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
        
        # Get all clans from MongoDB
        clans_data = await mongo.clans.find({"role_id": {"$exists": True}}).to_list(length=None)
        
        if not clans_data:
            await ctx.respond(
                "❌ No clans found in the database!",
                flags=hikari.MessageFlag.EPHEMERAL
            )
            return
        
        # Create clan objects
        clans = [Clan(data=data) for data in clans_data]
        
        # Sort clans by name
        clans.sort(key=lambda c: c.name)
        
        # Create select menu options
        options = []
        seen_tags = {}
        for clan in clans[:25]:  # Discord limit is 25 options
            # Handle duplicate clan tags by making values unique
            if clan.tag in seen_tags:
                seen_tags[clan.tag] += 1
                unique_value = f"{clan.tag}_{seen_tags[clan.tag]}"
            else:
                seen_tags[clan.tag] = 0
                unique_value = clan.tag

            # Create option with emoji if it exists, otherwise without
            if clan.partial_emoji:
                # Use the partial_emoji property which properly parses the emoji format
                option = SelectOption(
                    label=clan.name,
                    value=unique_value,
                    description=f"{clan.type} - TH{clan.th_requirements}+",
                    emoji=clan.partial_emoji
                )
            else:
                option = SelectOption(
                    label=clan.name,
                    value=unique_value,
                    description=f"{clan.type} - TH{clan.th_requirements}+"
                )
            options.append(option)
        
        # Create action ID
        action_id = str(uuid.uuid4())
        
        # Store data for the action
        await mongo.button_store.insert_one({
            "_id": action_id,
            "source_category_id": str(category_id),
            "user_id": ctx.user.id
        })
        
        # Create response message
        components = [
            Container(
                accent_color=GREEN_ACCENT,
                components=[
                    Text(content=(
                        f"## 📋 Clone Category\n\n"
                        f"**Source Category:** {source_category.name}\n"
                        f"**Channels:** {len([ch for ch in await bot.rest.fetch_guild_channels(ctx.guild_id) if ch.parent_id == category_id])} channels\n\n"
                        f"Select a clan from the dropdown below to clone this category for:"
                    )),
                    ActionRow(
                        components=[
                            TextSelectMenu(
                                custom_id=f"clone_category_select:{action_id}",
                                placeholder="Select a clan to clone the category for",
                                max_values=1,
                                options=options
                            )
                        ]
                    ),
                    Media(items=[MediaItem(media="assets/Green_Footer.png")])
                ]
            )
        ]
        
        await ctx.respond(components=components, flags=hikari.MessageFlag.EPHEMERAL)


@register_action("clone_category_select", no_return=True)
@lightbulb.di.with_di
async def handle_clan_selection(
    ctx: lightbulb.components.MenuContext,
    action_id: str,
    bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    """Handle clan selection for category cloning"""
    # Defer the response - for component interactions, we edit the original message
    await ctx.defer(edit=True)
    
    # Get stored data
    stored_data = await mongo.button_store.find_one({"_id": action_id})
    if not stored_data:
        return await ctx.respond("❌ Session expired. Please run the command again.")
    
    # Verify user
    if ctx.user.id != stored_data["user_id"]:
        return await ctx.respond("❌ Only the command user can select a clan!")
    
    # Get selected clan
    selected_value = ctx.interaction.values[0]

    # Extract original tag from potentially modified value (remove _1, _2 etc.)
    selected_clan_tag = selected_value.split("_")[0] if "_" in selected_value else selected_value

    clan_data = await mongo.clans.find_one({"tag": selected_clan_tag})
    
    if not clan_data:
        return await ctx.respond("❌ Could not find clan data!")
    
    clan = Clan(data=clan_data)
    
    # Get source category
    source_category_id = int(stored_data["source_category_id"])
    source_category = await bot.rest.fetch_channel(source_category_id)
    
    # Initialize logger
    logger = CloneLogger()
    
    # Start cloning process
    # Build progress message components
    progress_text = Text(content=(
        f"## ⏳ Cloning in Progress...\n\n"
        f"**Source:** {source_category.name}\n"
        f"**Target Clan:** {clan.name}\n\n"
        f"*Starting clone process...*"
    ))
    
    # If clan has logo, use Section with thumbnail, otherwise just use Text
    if clan.logo:
        progress_content = Section(
            components=[progress_text],
            accessory=Thumbnail(media=clan.logo)
        )
    else:
        progress_content = progress_text
    
    progress_components = [
        Container(
            accent_color=GREEN_ACCENT,
            components=[progress_content]
        )
    ]
    
    await ctx.respond(components=progress_components, edit=True)
    
    try:
        # Create new category with updated permissions
        logger.info(f"Updating category permissions for {clan.name}")
        new_category_perms = await clone_permission_overwrites(
            source_category.permission_overwrites,
            clan.role_id,
            clan.leader_role_id,
            mongo
        )
        
        # Create the new category
        logger.info(f"Creating new category: {clan.name}")
        new_category = await bot.rest.create_guild_category(
            ctx.guild_id,
            name=clan.name,
            position=source_category.position + 1,
            permission_overwrites=list(new_category_perms.values())
        )
        logger.success(f"Created category: {new_category.name}")
        
        # Get all channels in source category
        all_channels = await bot.rest.fetch_guild_channels(ctx.guild_id)
        source_channels = [ch for ch in all_channels if ch.parent_id == source_category_id]
        
        # Sort channels by position
        source_channels.sort(key=lambda ch: ch.position)
        
        # Clone statistics
        channels_cloned = 0
        forums_cloned = 0
        threads_cloned = 0
        
        # Clone each channel
        clan_suffix = get_clan_suffix(clan.name)
        
        for channel in source_channels:
            try:
                # Update permissions for this channel
                logger.info(f"Updating permissions for channel: {channel.name}")
                channel_perms = await clone_permission_overwrites(
                    channel.permission_overwrites,
                    clan.role_id,
                    clan.leader_role_id,
                    mongo
                )
                
                # Create channel name with suffix (replacing any existing suffix)
                base_channel_name = remove_existing_suffix(channel.name)
                new_channel_name = f"{base_channel_name}{clan_suffix}"
                
                # Clone based on channel type
                if channel.type == hikari.ChannelType.GUILD_TEXT:
                    new_channel = await bot.rest.create_guild_text_channel(
                        ctx.guild_id,
                        new_channel_name,
                        topic=channel.topic,
                        rate_limit_per_user=channel.rate_limit_per_user,
                        nsfw=channel.is_nsfw,
                        permission_overwrites=list(channel_perms.values()),
                        position=channel.position,
                        category=new_category.id
                    )
                    channels_cloned += 1
                    logger.success(f"Cloned text channel: {new_channel.name}")
                    
                elif channel.type == hikari.ChannelType.GUILD_VOICE:
                    new_channel = await bot.rest.create_guild_voice_channel(
                        ctx.guild_id,
                        new_channel_name,
                        bitrate=channel.bitrate,
                        user_limit=channel.user_limit,
                        permission_overwrites=list(channel_perms.values()),
                        position=channel.position,
                        category=new_category.id
                    )
                    channels_cloned += 1
                    logger.success(f"Cloned voice channel: {new_channel.name}")
                    
                elif channel.type == hikari.ChannelType.GUILD_FORUM:
                    # Create forum channel
                    new_forum = await bot.rest.create_guild_forum_channel(
                        ctx.guild_id,
                        new_channel_name,
                        topic=channel.topic,
                        rate_limit_per_user=channel.rate_limit_per_user,
                        default_auto_archive_duration=channel.default_auto_archive_duration,
                        permission_overwrites=list(channel_perms.values()),
                        position=channel.position,
                        category=new_category.id
                    )
                    forums_cloned += 1
                    logger.success(f"Cloned forum channel: {new_forum.name}")
                    
                    # Clone forum threads
                    threads_created = await clone_forum_threads(bot, channel.id, new_forum.id, logger)
                    threads_cloned += threads_created
                
                # Small delay to avoid rate limits
                await asyncio.sleep(0.3)
                
            except Exception as e:
                logger.error(f"Failed to clone channel {channel.name}: {str(e)}")
        
        # Success message
        success_content_parts = [
            f"## ✅ Category Cloned Successfully!\n\n",
            f"**New Category:** {new_category.name}\n",
            f"**Channels Cloned:** {channels_cloned}\n",
            f"**Forums Cloned:** {forums_cloned}\n",
            f"**Forum Threads Created:** {threads_cloned}\n\n",
            f"**Permissions Updated:**\n",
            f"• Clan Role: <@&{clan.role_id}>\n",
            f"• Leadership Role: <@&{clan.leader_role_id}>\n\n",
            f"*All channels have been cloned with the suffix `{clan_suffix}`*"
        ]
        
        # Add logger summary if there are warnings or errors
        log_summary = logger.get_summary()
        if log_summary:
            success_content_parts.append(f"\n\n{log_summary}")
            
        final_content = "".join(success_content_parts)
        # Debug: ensure we have content
        if not final_content.strip():
            final_content = "## ✅ Category Cloned Successfully!\n\nOperation completed."
        success_text = Text(content=final_content)
        
        # If clan has logo, use Section with thumbnail, otherwise just use Text
        if clan.logo:
            success_content = Section(
                components=[success_text],
                accessory=Thumbnail(media=clan.logo)
            )
        else:
            success_content = success_text
        
        success_components = [
            Container(
                accent_color=GREEN_ACCENT,
                components=[
                    success_content,
                    Separator(),
                    Text(content=f"-# Cloned by {ctx.user.mention}")
                ]
            )
        ]
        
        # Debug: Log the final message content
        logger.info(f"Sending success message with {len(success_components)} components")
        logger.info(f"Success content: {final_content[:100]}...")
        
        await ctx.respond(components=success_components, edit=True)
        
        # Clean up stored data
        await mongo.button_store.delete_one({"_id": action_id})
        
        # Important: Return immediately to prevent any further processing
        return
        
    except Exception as e:
        # Log the main error
        logger.error(f"Clone operation failed: {str(e)}")
        
        error_content_parts = [
            f"## ❌ Cloning Failed\n\n",
            f"**Main Error:** {str(e)}\n\n"
        ]
        
        # Add detailed log summary
        log_summary = logger.get_summary()
        if log_summary:
            error_content_parts.append(log_summary)
        else:
            error_content_parts.append("Please check bot permissions and try again.")
            
        error_components = [
            Container(
                accent_color=DARK_MAGENTA_ACCENT,
                components=[
                    Text(content="".join(error_content_parts))
                ]
            )
        ]
        
        await ctx.respond(components=error_components, edit=True)
        return