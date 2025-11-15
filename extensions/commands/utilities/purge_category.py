# extensions/commands/utilities/purge_category.py
"""
Purge category command - Delete a category and all its channels
"""

import hikari
import lightbulb
import asyncio
import uuid
from typing import List

from hikari.impl import (
    MessageActionRowBuilder as ActionRow,
    InteractiveButtonBuilder as Button,
    ContainerComponentBuilder as Container,
    SectionComponentBuilder as Section,
    TextDisplayComponentBuilder as Text,
    SeparatorComponentBuilder as Separator,
    MediaGalleryComponentBuilder as Media,
    MediaGalleryItemBuilder as MediaItem,
)

from extensions.commands.utilities import loader, utilities
from extensions.components import register_action
from utils.mongo import MongoClient
from utils.constants import DARK_MAGENTA_ACCENT, GREEN_ACCENT
from utils.emoji import emojis


def get_error_reason(error: Exception) -> str:
    """Get a user-friendly reason for a Discord API error"""
    error_str = str(error)
    
    # Common Discord error codes
    if "50001" in error_str:
        return "Missing access (check channel permissions)"
    elif "50013" in error_str:
        return "Missing permissions"
    elif "50074" in error_str:
        return "Cannot delete community server channel"
    elif "10003" in error_str:
        return "Channel not found"
    else:
        # Extract just the error message if possible
        if "Missing Access" in error_str:
            return "Missing access"
        elif "Missing Permissions" in error_str:
            return "Missing permissions"
        else:
            return error_str.split(":")[-1].strip() if ":" in error_str else str(error)


@utilities.register()
class PurgeCategory(
    lightbulb.SlashCommand,
    name="purge-category",
    description="Delete a category and all its child channels (DESTRUCTIVE)"
):
    category = lightbulb.channel(
        "category",
        "The category to delete along with all its channels",
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
        
        # Verify the selected channel is a category
        category_id = self.category.id
        try:
            category = await bot.rest.fetch_channel(category_id)
            if category.type != hikari.ChannelType.GUILD_CATEGORY:
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
        
        # Get all channels in this category
        all_channels = await bot.rest.fetch_guild_channels(ctx.guild_id)
        child_channels = [ch for ch in all_channels if ch.parent_id == category_id]
        
        # Count channels by type
        text_channels = sum(1 for ch in child_channels if ch.type == hikari.ChannelType.GUILD_TEXT)
        voice_channels = sum(1 for ch in child_channels if ch.type == hikari.ChannelType.GUILD_VOICE)
        forum_channels = sum(1 for ch in child_channels if ch.type == hikari.ChannelType.GUILD_FORUM)
        other_channels = len(child_channels) - text_channels - voice_channels - forum_channels
        
        # Create action ID for confirmation
        action_id = str(uuid.uuid4())
        
        # Store data for the action
        await mongo.button_store.insert_one({
            "_id": action_id,
            "category_id": str(category_id),
            "category_name": category.name,
            "channel_count": len(child_channels),
            "user_id": ctx.user.id
        })
        
        # Create warning message
        channel_breakdown = []
        if text_channels > 0:
            channel_breakdown.append(f"• **{text_channels}** text channel{'s' if text_channels != 1 else ''}")
        if voice_channels > 0:
            channel_breakdown.append(f"• **{voice_channels}** voice channel{'s' if voice_channels != 1 else ''}")
        if forum_channels > 0:
            channel_breakdown.append(f"• **{forum_channels}** forum channel{'s' if forum_channels != 1 else ''}")
        if other_channels > 0:
            channel_breakdown.append(f"• **{other_channels}** other channel{'s' if other_channels != 1 else ''}")
        
        components = [
            Container(
                accent_color=DARK_MAGENTA_ACCENT,
                components=[
                    Text(content=(
                        f"## ⚠️ Confirm Category Deletion\n\n"
                        f"**Category:** {category.name}\n"
                        f"**Total Channels:** {len(child_channels)}\n"
                    )),
                    Separator(divider=True),
                    Text(content=(
                        "**This will permanently delete:**\n" +
                        "\n".join(channel_breakdown) +
                        "\n• The category itself\n\n"
                        "⚠️ **This action cannot be undone!**"
                    )),
                    Separator(divider=True),
                    ActionRow(
                        components=[
                            Button(
                                style=hikari.ButtonStyle.DANGER,
                                label="Yes, Delete Everything",
                                custom_id=f"purge_category_confirm:{action_id}",
                                emoji="🗑️"
                            ),
                            Button(
                                style=hikari.ButtonStyle.SECONDARY,
                                label="Cancel",
                                custom_id=f"purge_category_cancel:{action_id}",
                                emoji="❌"
                            )
                        ]
                    ),
                    Media(items=[MediaItem(media="assets/Red_Footer.png")])
                ]
            )
        ]
        
        await ctx.respond(components=components, flags=hikari.MessageFlag.EPHEMERAL)


@register_action("purge_category_confirm", no_return=True)
@lightbulb.di.with_di
async def handle_purge_confirm(
    ctx: lightbulb.components.MenuContext,
    action_id: str,
    bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    """Handle confirmation of category purge"""
    await ctx.defer(edit=True)
    
    # Get stored data
    stored_data = await mongo.button_store.find_one({"_id": action_id})
    if not stored_data:
        return await ctx.respond("❌ Session expired. Please run the command again.")
    
    # Verify user
    if ctx.user.id != stored_data["user_id"]:
        return await ctx.respond("❌ Only the command user can confirm deletion!")
    
    category_id = int(stored_data["category_id"])
    category_name = stored_data["category_name"]
    
    # Start deletion process
    progress_components = [
        Container(
            accent_color=DARK_MAGENTA_ACCENT,
            components=[
                Text(content=(
                    f"## 🗑️ Purging Category...\n\n"
                    f"**Category:** {category_name}\n\n"
                    f"*Deleting channels...*"
                ))
            ]
        )
    ]
    
    await ctx.respond(components=progress_components, edit=True)
    
    try:
        # Get all channels in the category
        all_channels = await bot.rest.fetch_guild_channels(ctx.guild_id)
        child_channels = [ch for ch in all_channels if ch.parent_id == category_id]
        
        deleted_count = 0
        failed_deletions = []
        
        # Delete all child channels concurrently
        async def delete_channel(channel):
            try:
                await bot.rest.delete_channel(channel.id)
                return True, channel.name, None
            except Exception as e:
                reason = get_error_reason(e)
                return False, channel.name, reason
        
        # Create tasks for all deletions INCLUDING the category
        delete_tasks = [delete_channel(channel) for channel in child_channels]
        
        # Also create a task for deleting the category
        async def delete_category_after_channels():
            # Wait a tiny bit to ensure channels start deleting first
            await asyncio.sleep(0.1)
            try:
                await bot.rest.delete_channel(category_id)
                return True, None
            except Exception as e:
                return False, get_error_reason(e)
        
        # Add category deletion to tasks
        category_task = delete_category_after_channels()
        
        # Execute all deletions concurrently (channels + category)
        results = await asyncio.gather(*delete_tasks, category_task)
        
        # Process channel results (all except last)
        for success, channel_name, error_reason in results[:-1]:
            if success:
                deleted_count += 1
            else:
                failed_deletions.append(f"{channel_name}: {error_reason}")
        
        # Process category result (last result)
        category_deleted, category_error = results[-1]
        if not category_deleted and not category_error:
            category_error = "Unknown error"
        
        # Prepare result message
        if category_deleted and not failed_deletions:
            # Complete success
            result_components = [
                Container(
                    accent_color=GREEN_ACCENT,
                    components=[
                        Text(content=(
                            f"## ✅ Category Purged Successfully!\n\n"
                            f"**Deleted Category:** {category_name}\n"
                            f"**Channels Deleted:** {deleted_count}\n\n"
                            f"*All channels and the category have been permanently deleted.*"
                        )),
                        Separator(),
                        Text(content=f"-# Purged by {ctx.user.mention}")
                    ]
                )
            ]
        else:
            # Partial success or failure
            error_details = []
            if failed_deletions:
                error_details.append(f"**Failed to delete {len(failed_deletions)} channel(s):**")
                for failure in failed_deletions[:5]:  # Show first 5 failures
                    error_details.append(f"• {failure}")
                if len(failed_deletions) > 5:
                    error_details.append(f"• ...and {len(failed_deletions) - 5} more")
            
            if not category_deleted:
                error_details.append(f"\n**Failed to delete category:** {category_error}")
            
            result_components = [
                Container(
                    accent_color=DARK_MAGENTA_ACCENT,
                    components=[
                        Text(content=(
                            f"## ⚠️ Partial Deletion\n\n"
                            f"**Category:** {category_name}\n"
                            f"**Channels Deleted:** {deleted_count}/{len(child_channels)}\n"
                            f"**Category Deleted:** {'Yes' if category_deleted else 'No'}\n\n"
                        )),
                        Text(content="\n".join(error_details)) if error_details else Text(content=""),
                        Separator(),
                        Text(content=f"-# Attempted by {ctx.user.mention}")
                    ]
                )
            ]
        
        await ctx.respond(components=result_components, edit=True)
        
        # Clean up stored data
        await mongo.button_store.delete_one({"_id": action_id})
        
    except Exception as e:
        error_components = [
            Container(
                accent_color=DARK_MAGENTA_ACCENT,
                components=[
                    Text(content=(
                        f"## ❌ Purge Failed\n\n"
                        f"**Error:** {str(e)}\n\n"
                        f"Please check bot permissions and try again."
                    ))
                ]
            )
        ]
        
        await ctx.respond(components=error_components, edit=True)
        return


@register_action("purge_category_cancel", no_return=True)
@lightbulb.di.with_di
async def handle_purge_cancel(
    ctx: lightbulb.components.MenuContext,
    action_id: str,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    """Handle cancellation of category purge"""
    # Get stored data
    stored_data = await mongo.button_store.find_one({"_id": action_id})
    if not stored_data:
        return await ctx.respond("❌ Session expired.")
    
    # Verify user
    if ctx.user.id != stored_data["user_id"]:
        return await ctx.respond("❌ Only the command user can cancel!")
    
    # Send cancellation message
    cancel_components = [
        Container(
            accent_color=GREEN_ACCENT,
            components=[
                Text(content=(
                    f"## ✅ Purge Cancelled\n\n"
                    f"The category **{stored_data['category_name']}** and its channels were not deleted."
                ))
            ]
        )
    ]
    
    await ctx.respond(components=cancel_components, edit=True)
    
    # Clean up stored data
    await mongo.button_store.delete_one({"_id": action_id})