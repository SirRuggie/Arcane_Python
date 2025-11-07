# extensions/commands/utilities/clone_forum.py
"""
Clone forum command - Clone a forum channel to a different category with updated roles
"""

import hikari
import lightbulb
import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from hikari.impl import (
    MessageActionRowBuilder as ActionRow,
    TextSelectMenuBuilder as TextSelectMenu,
    SelectOptionBuilder as SelectOption,
    InteractiveButtonBuilder as Button,
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
from utils.constants import GREEN_ACCENT, RED_ACCENT
from utils.emoji import emojis

# Import utility functions from clone_category
from extensions.commands.utilities.clone_category import (
    CloneLogger,
    clone_permission_overwrites,
    clone_forum_threads,
    get_clan_suffix,
    remove_existing_suffix
)

# Permission constants - same as clone_category
CLAN_MANAGEMENT_ROLE_ID = 1060318031575793694
ADDITIONAL_MANAGEMENT_ROLE_ID = 1371470242076954706
ALLOWED_MANAGEMENT_ROLES = [CLAN_MANAGEMENT_ROLE_ID, ADDITIONAL_MANAGEMENT_ROLE_ID]


@utilities.register()
class CloneForum(
    lightbulb.SlashCommand,
    name="clone-forum",
    description="Clone a forum channel to a different category with updated roles"
):
    forum = lightbulb.channel(
        "forum",
        "The forum channel to clone",
        channel_types=[hikari.ChannelType.GUILD_FORUM]
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
                    accent_color=RED_ACCENT,
                    components=[
                        Text(content="## ❌ Access Denied"),
                        Separator(divider=True),
                        Text(content=(
                            "You do not have permission to use the Clone Forum command.\n\n"
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

        # Verify the selected channel is a forum
        forum_id = self.forum.id
        try:
            source_forum = await bot.rest.fetch_channel(forum_id)
            if source_forum.type != hikari.ChannelType.GUILD_FORUM:
                await ctx.respond(
                    "❌ Please select a forum channel!",
                    flags=hikari.MessageFlag.EPHEMERAL
                )
                return
        except Exception as e:
            await ctx.respond(
                f"❌ Failed to fetch forum channel: {str(e)}",
                flags=hikari.MessageFlag.EPHEMERAL
            )
            return

        # Get all categories in the guild
        all_channels = await bot.rest.fetch_guild_channels(ctx.guild_id)
        categories = [ch for ch in all_channels if ch.type == hikari.ChannelType.GUILD_CATEGORY]

        if not categories:
            await ctx.respond(
                "❌ No categories found in this server!",
                flags=hikari.MessageFlag.EPHEMERAL
            )
            return

        # Sort categories by position
        categories.sort(key=lambda c: c.position)

        # Split categories: first 24 in dropdown, rest for pagination
        top_categories = categories[:24]
        remaining_categories = categories[24:]

        # Create category select menu options
        category_options = []
        for category in top_categories:
            category_options.append(
                SelectOption(
                    label=category.name,
                    value=str(category.id),
                    description=f"Position: {category.position}"
                )
            )

        # Create action ID
        action_id = str(uuid.uuid4())

        # Store data for the action
        store_data = {
            "_id": action_id,
            "source_forum_id": str(forum_id),
            "user_id": ctx.user.id,
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5)
        }

        # Store remaining categories if there are more than 24
        if remaining_categories:
            store_data["remaining_categories"] = [
                {"id": str(cat.id), "name": cat.name, "position": cat.position}
                for cat in remaining_categories
            ]
            store_data["category_page"] = 0

        await mongo.button_store.insert_one(store_data)

        # Build components list
        container_components = [
            Text(content=(
                f"## 📋 Clone Forum Channel\n\n"
                f"**Source Forum:** {source_forum.name}\n"
                f"**Current Category:** {source_forum.parent_id and (await bot.rest.fetch_channel(source_forum.parent_id)).name or 'None'}\n\n"
                f"**Step 1:** Select the target category where you want to clone this forum:"
            )),
            ActionRow(
                components=[
                    TextSelectMenu(
                        custom_id=f"clone_forum_category:{action_id}",
                        placeholder="Select target category",
                        max_values=1,
                        options=category_options
                    )
                ]
            )
        ]

        # Add "Show More" button if there are remaining categories
        if remaining_categories:
            container_components.append(
                ActionRow(
                    components=[
                        Button(
                            style=hikari.ButtonStyle.PRIMARY,
                            custom_id=f"clone_forum_show_more_categories:{action_id}",
                            label=f"Show More Categories ({len(remaining_categories)} more)",
                            emoji="🔍"
                        )
                    ]
                )
            )

        container_components.append(Media(items=[MediaItem(media="assets/Green_Footer.png")]))

        # Create response message with category selection
        components = [
            Container(
                accent_color=GREEN_ACCENT,
                components=container_components
            )
        ]

        await ctx.respond(components=components, flags=hikari.MessageFlag.EPHEMERAL)


@register_action("clone_forum_show_more_categories", no_return=True)
@lightbulb.di.with_di
async def handle_show_more_categories(
    ctx: lightbulb.components.MenuContext,
    action_id: str,
    bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    """Show paginated view of remaining categories"""
    await ctx.defer(edit=True)

    # Get stored data
    stored_data = await mongo.button_store.find_one({"_id": action_id})
    if not stored_data:
        return await ctx.respond("❌ Session expired. Please run the command again.")

    # Verify user
    if ctx.user.id != stored_data["user_id"]:
        return await ctx.respond("❌ Only the command user can browse categories!")

    remaining_cats = stored_data.get("remaining_categories", [])
    current_page = stored_data.get("category_page", 0)

    # Calculate pagination
    cats_per_page = 25
    total_pages = (len(remaining_cats) + cats_per_page - 1) // cats_per_page
    current_page = max(0, min(current_page, total_pages - 1))

    # Get categories for current page
    start_idx = current_page * cats_per_page
    end_idx = min(start_idx + cats_per_page, len(remaining_cats))
    cats_on_page = remaining_cats[start_idx:end_idx]

    # Build dropdown options
    category_options = []
    for cat_data in cats_on_page:
        category_options.append(
            SelectOption(
                label=cat_data["name"],
                value=cat_data["id"],
                description=f"Position: {cat_data['position']}"
            )
        )

    # Get source forum info
    source_forum_id = int(stored_data["source_forum_id"])
    source_forum = await bot.rest.fetch_channel(source_forum_id)

    # Build components
    container_components = [
        Text(content=(
            f"## 📋 Clone Forum Channel\n\n"
            f"**Source Forum:** {source_forum.name}\n\n"
            f"**Step 1:** Select the target category where you want to clone this forum:\n"
            f"📄 **Page {current_page + 2}** of {total_pages + 1} (showing categories {start_idx + 25} - {end_idx + 24})"
        )),
        ActionRow(
            components=[
                TextSelectMenu(
                    custom_id=f"clone_forum_category:{action_id}",
                    placeholder="Select target category",
                    max_values=1,
                    options=category_options
                )
            ]
        )
    ]

    # Add navigation buttons
    nav_buttons = []

    # Previous button
    if current_page > 0:
        nav_buttons.append(
            Button(
                style=hikari.ButtonStyle.PRIMARY,
                custom_id=f"clone_forum_category_browse_prev:{action_id}",
                label="Previous",
                emoji="◀️"
            )
        )

    # Next button
    if current_page < total_pages - 1:
        nav_buttons.append(
            Button(
                style=hikari.ButtonStyle.PRIMARY,
                custom_id=f"clone_forum_category_browse_next:{action_id}",
                label="Next",
                emoji="▶️"
            )
        )

    # Back to list button
    nav_buttons.append(
        Button(
            style=hikari.ButtonStyle.SECONDARY,
            custom_id=f"clone_forum_category_back:{action_id}",
            label="Back to List",
            emoji="↩️"
        )
    )

    if nav_buttons:
        container_components.append(
            ActionRow(components=nav_buttons)
        )

    container_components.append(Media(items=[MediaItem(media="assets/Green_Footer.png")]))

    components = [
        Container(
            accent_color=GREEN_ACCENT,
            components=container_components
        )
    ]

    await ctx.respond(components=components, edit=True)


@register_action("clone_forum_category_browse_next", no_return=True)
@lightbulb.di.with_di
async def handle_category_browse_next(
    ctx: lightbulb.components.MenuContext,
    action_id: str,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    """Handle next page button for category pagination"""
    # Update page in database
    await mongo.button_store.update_one(
        {"_id": action_id},
        {"$inc": {"category_page": 1}}
    )

    # Re-render with new page
    return await handle_show_more_categories(ctx, action_id, mongo=mongo, **kwargs)


@register_action("clone_forum_category_browse_prev", no_return=True)
@lightbulb.di.with_di
async def handle_category_browse_prev(
    ctx: lightbulb.components.MenuContext,
    action_id: str,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    """Handle previous page button for category pagination"""
    # Update page in database
    await mongo.button_store.update_one(
        {"_id": action_id},
        {"$inc": {"category_page": -1}}
    )

    # Re-render with new page
    return await handle_show_more_categories(ctx, action_id, mongo=mongo, **kwargs)


@register_action("clone_forum_category_back", no_return=True)
@lightbulb.di.with_di
async def handle_category_back_to_list(
    ctx: lightbulb.components.MenuContext,
    action_id: str,
    bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    """Return to initial category dropdown"""
    await ctx.defer(edit=True)

    # Get stored data
    stored_data = await mongo.button_store.find_one({"_id": action_id})
    if not stored_data:
        return await ctx.respond("❌ Session expired. Please run the command again.")

    # Get source forum
    source_forum_id = int(stored_data["source_forum_id"])
    source_forum = await bot.rest.fetch_channel(source_forum_id)

    # Get all categories again
    all_channels = await bot.rest.fetch_guild_channels(ctx.guild_id)
    categories = [ch for ch in all_channels if ch.type == hikari.ChannelType.GUILD_CATEGORY]
    categories.sort(key=lambda c: c.position)

    # Get first 24
    top_categories = categories[:24]
    remaining_categories = categories[24:]

    # Build dropdown
    category_options = []
    for category in top_categories:
        category_options.append(
            SelectOption(
                label=category.name,
                value=str(category.id),
                description=f"Position: {category.position}"
            )
        )

    # Build components
    container_components = [
        Text(content=(
            f"## 📋 Clone Forum Channel\n\n"
            f"**Source Forum:** {source_forum.name}\n"
            f"**Current Category:** {source_forum.parent_id and (await bot.rest.fetch_channel(source_forum.parent_id)).name or 'None'}\n\n"
            f"**Step 1:** Select the target category where you want to clone this forum:"
        )),
        ActionRow(
            components=[
                TextSelectMenu(
                    custom_id=f"clone_forum_category:{action_id}",
                    placeholder="Select target category",
                    max_values=1,
                    options=category_options
                )
            ]
        )
    ]

    # Add "Show More" button if there are remaining categories
    if remaining_categories:
        container_components.append(
            ActionRow(
                components=[
                    Button(
                        style=hikari.ButtonStyle.PRIMARY,
                        custom_id=f"clone_forum_show_more_categories:{action_id}",
                        label=f"Show More Categories ({len(remaining_categories)} more)",
                        emoji="🔍"
                    )
                ]
            )
        )

    container_components.append(Media(items=[MediaItem(media="assets/Green_Footer.png")]))

    components = [
        Container(
            accent_color=GREEN_ACCENT,
            components=container_components
        )
    ]

    await ctx.respond(components=components, edit=True)


@register_action("clone_forum_category", no_return=True)
@lightbulb.di.with_di
async def handle_category_selection(
    ctx: lightbulb.components.MenuContext,
    action_id: str,
    bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    """Handle category selection and show clan dropdown"""
    await ctx.defer(edit=True)

    # Get stored data
    stored_data = await mongo.button_store.find_one({"_id": action_id})
    if not stored_data:
        return await ctx.respond("❌ Session expired. Please run the command again.")

    # Verify user
    if ctx.user.id != stored_data["user_id"]:
        return await ctx.respond("❌ Only the command user can select options!")

    # Get selected category
    selected_category_id = int(ctx.interaction.values[0])
    target_category = await bot.rest.fetch_channel(selected_category_id)

    # Store the category selection
    await mongo.button_store.update_one(
        {"_id": action_id},
        {"$set": {"target_category_id": str(selected_category_id)}}
    )

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

    # Split clans: first 24 in dropdown, rest for pagination
    top_clans = clans[:24]
    remaining_clans = clans[24:]

    # Create select menu options for clans
    clan_options = []
    seen_tags = {}
    for clan in top_clans:
        # Handle duplicate clan tags by making values unique
        if clan.tag in seen_tags:
            seen_tags[clan.tag] += 1
            unique_value = f"{clan.tag}_{seen_tags[clan.tag]}"
        else:
            seen_tags[clan.tag] = 0
            unique_value = clan.tag

        # Create option with emoji if it exists, otherwise without
        # Show only name and tag (not type or TH requirements)
        if clan.partial_emoji:
            option = SelectOption(
                label=clan.name,
                value=unique_value,
                description=clan.tag,
                emoji=clan.partial_emoji
            )
        else:
            option = SelectOption(
                label=clan.name,
                value=unique_value,
                description=clan.tag
            )
        clan_options.append(option)

    # Store remaining clans if there are more than 24
    if remaining_clans:
        # Serialize clan data for storage
        remaining_clans_data = []
        for clan in remaining_clans:
            remaining_clans_data.append({
                "name": clan.name,
                "tag": clan.tag,
                "partial_emoji": clan.partial_emoji.name if clan.partial_emoji else None
            })

        await mongo.button_store.update_one(
            {"_id": action_id},
            {
                "$set": {
                    "remaining_clans": remaining_clans_data,
                    "clan_page": 0
                }
            }
        )

    # Get source forum
    source_forum_id = int(stored_data["source_forum_id"])
    source_forum = await bot.rest.fetch_channel(source_forum_id)

    # Build components list
    container_components = [
        Text(content=(
            f"## 📋 Clone Forum Channel\n\n"
            f"**Source Forum:** {source_forum.name}\n"
            f"**Target Category:** {target_category.name}\n\n"
            f"**Step 2:** Select the clan to assign roles for:"
        )),
        ActionRow(
            components=[
                TextSelectMenu(
                    custom_id=f"clone_forum_clan:{action_id}",
                    placeholder="Select a clan",
                    max_values=1,
                    options=clan_options
                )
            ]
        )
    ]

    # Add "Show More" button if there are remaining clans
    if remaining_clans:
        container_components.append(
            ActionRow(
                components=[
                    Button(
                        style=hikari.ButtonStyle.PRIMARY,
                        custom_id=f"clone_forum_show_more_clans:{action_id}",
                        label=f"Show More Clans ({len(remaining_clans)} more)",
                        emoji="🔍"
                    )
                ]
            )
        )

    container_components.append(Media(items=[MediaItem(media="assets/Green_Footer.png")]))

    # Create response message with clan selection
    components = [
        Container(
            accent_color=GREEN_ACCENT,
            components=container_components
        )
    ]

    await ctx.respond(components=components, edit=True)


@register_action("clone_forum_show_more_clans", no_return=True)
@lightbulb.di.with_di
async def handle_show_more_clans(
    ctx: lightbulb.components.MenuContext,
    action_id: str,
    bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    """Show paginated view of remaining clans"""
    await ctx.defer(edit=True)

    # Get stored data
    stored_data = await mongo.button_store.find_one({"_id": action_id})
    if not stored_data:
        return await ctx.respond("❌ Session expired. Please run the command again.")

    # Verify user
    if ctx.user.id != stored_data["user_id"]:
        return await ctx.respond("❌ Only the command user can browse clans!")

    remaining_clans_data = stored_data.get("remaining_clans", [])
    current_page = stored_data.get("clan_page", 0)

    # Calculate pagination
    clans_per_page = 25
    total_pages = (len(remaining_clans_data) + clans_per_page - 1) // clans_per_page
    current_page = max(0, min(current_page, total_pages - 1))

    # Get clans for current page
    start_idx = current_page * clans_per_page
    end_idx = min(start_idx + clans_per_page, len(remaining_clans_data))
    clans_on_page = remaining_clans_data[start_idx:end_idx]

    # Build dropdown options
    clan_options = []
    seen_tags = {}
    for clan_data in clans_on_page:
        # Handle duplicate clan tags by making values unique
        if clan_data["tag"] in seen_tags:
            seen_tags[clan_data["tag"]] += 1
            unique_value = f"{clan_data['tag']}_{seen_tags[clan_data['tag']]}"
        else:
            seen_tags[clan_data["tag"]] = 0
            unique_value = clan_data["tag"]

        # Create option with emoji if it exists, otherwise without
        if clan_data["partial_emoji"] and hasattr(emojis, clan_data["partial_emoji"]):
            option = SelectOption(
                label=clan_data["name"],
                value=unique_value,
                description=clan_data["tag"],
                emoji=getattr(emojis, clan_data["partial_emoji"]).partial_emoji
            )
        else:
            option = SelectOption(
                label=clan_data["name"],
                value=unique_value,
                description=clan_data["tag"]
            )
        clan_options.append(option)

    # Get source forum and target category info
    source_forum_id = int(stored_data["source_forum_id"])
    source_forum = await bot.rest.fetch_channel(source_forum_id)

    target_category_id = int(stored_data["target_category_id"])
    target_category = await bot.rest.fetch_channel(target_category_id)

    # Build components
    container_components = [
        Text(content=(
            f"## 📋 Clone Forum Channel\n\n"
            f"**Source Forum:** {source_forum.name}\n"
            f"**Target Category:** {target_category.name}\n\n"
            f"**Step 2:** Select the clan to assign roles for:\n"
            f"📄 **Page {current_page + 2}** of {total_pages + 1} (showing clans {start_idx + 25} - {end_idx + 24})"
        )),
        ActionRow(
            components=[
                TextSelectMenu(
                    custom_id=f"clone_forum_clan:{action_id}",
                    placeholder="Select a clan",
                    max_values=1,
                    options=clan_options
                )
            ]
        )
    ]

    # Add navigation buttons
    nav_buttons = []

    # Previous button
    if current_page > 0:
        nav_buttons.append(
            Button(
                style=hikari.ButtonStyle.PRIMARY,
                custom_id=f"clone_forum_clan_browse_prev:{action_id}",
                label="Previous",
                emoji="◀️"
            )
        )

    # Next button
    if current_page < total_pages - 1:
        nav_buttons.append(
            Button(
                style=hikari.ButtonStyle.PRIMARY,
                custom_id=f"clone_forum_clan_browse_next:{action_id}",
                label="Next",
                emoji="▶️"
            )
        )

    # Back to list button
    nav_buttons.append(
        Button(
            style=hikari.ButtonStyle.SECONDARY,
            custom_id=f"clone_forum_clan_back:{action_id}",
            label="Back to List",
            emoji="↩️"
        )
    )

    if nav_buttons:
        container_components.append(
            ActionRow(components=nav_buttons)
        )

    container_components.append(Media(items=[MediaItem(media="assets/Green_Footer.png")]))

    components = [
        Container(
            accent_color=GREEN_ACCENT,
            components=container_components
        )
    ]

    await ctx.respond(components=components, edit=True)


@register_action("clone_forum_clan_browse_next", no_return=True)
@lightbulb.di.with_di
async def handle_clan_browse_next(
    ctx: lightbulb.components.MenuContext,
    action_id: str,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    """Handle next page button for clan pagination"""
    # Update page in database
    await mongo.button_store.update_one(
        {"_id": action_id},
        {"$inc": {"clan_page": 1}}
    )

    # Re-render with new page
    return await handle_show_more_clans(ctx, action_id, mongo=mongo, **kwargs)


@register_action("clone_forum_clan_browse_prev", no_return=True)
@lightbulb.di.with_di
async def handle_clan_browse_prev(
    ctx: lightbulb.components.MenuContext,
    action_id: str,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    """Handle previous page button for clan pagination"""
    # Update page in database
    await mongo.button_store.update_one(
        {"_id": action_id},
        {"$inc": {"clan_page": -1}}
    )

    # Re-render with new page
    return await handle_show_more_clans(ctx, action_id, mongo=mongo, **kwargs)


@register_action("clone_forum_clan_back", no_return=True)
@lightbulb.di.with_di
async def handle_clan_back_to_list(
    ctx: lightbulb.components.MenuContext,
    action_id: str,
    bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    """Return to initial clan dropdown"""
    await ctx.defer(edit=True)

    # Get stored data
    stored_data = await mongo.button_store.find_one({"_id": action_id})
    if not stored_data:
        return await ctx.respond("❌ Session expired. Please run the command again.")

    # Verify user
    if ctx.user.id != stored_data["user_id"]:
        return await ctx.respond("❌ Only the command user can browse clans!")

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

    # Split clans: first 24 in dropdown, rest for pagination
    top_clans = clans[:24]
    remaining_clans = clans[24:]

    # Create select menu options for clans
    clan_options = []
    seen_tags = {}
    for clan in top_clans:
        # Handle duplicate clan tags by making values unique
        if clan.tag in seen_tags:
            seen_tags[clan.tag] += 1
            unique_value = f"{clan.tag}_{seen_tags[clan.tag]}"
        else:
            seen_tags[clan.tag] = 0
            unique_value = clan.tag

        # Create option with emoji if it exists, otherwise without
        if clan.partial_emoji:
            option = SelectOption(
                label=clan.name,
                value=unique_value,
                description=clan.tag,
                emoji=clan.partial_emoji
            )
        else:
            option = SelectOption(
                label=clan.name,
                value=unique_value,
                description=clan.tag
            )
        clan_options.append(option)

    # Store remaining clans if there are more than 24
    if remaining_clans:
        # Serialize clan data for storage
        remaining_clans_data = []
        for clan in remaining_clans:
            remaining_clans_data.append({
                "name": clan.name,
                "tag": clan.tag,
                "partial_emoji": clan.partial_emoji.name if clan.partial_emoji else None
            })

        await mongo.button_store.update_one(
            {"_id": action_id},
            {
                "$set": {
                    "remaining_clans": remaining_clans_data,
                    "clan_page": 0
                }
            }
        )

    # Get source forum and target category
    source_forum_id = int(stored_data["source_forum_id"])
    source_forum = await bot.rest.fetch_channel(source_forum_id)

    target_category_id = int(stored_data["target_category_id"])
    target_category = await bot.rest.fetch_channel(target_category_id)

    # Build components list
    container_components = [
        Text(content=(
            f"## 📋 Clone Forum Channel\n\n"
            f"**Source Forum:** {source_forum.name}\n"
            f"**Target Category:** {target_category.name}\n\n"
            f"**Step 2:** Select the clan to assign roles for:"
        )),
        ActionRow(
            components=[
                TextSelectMenu(
                    custom_id=f"clone_forum_clan:{action_id}",
                    placeholder="Select a clan",
                    max_values=1,
                    options=clan_options
                )
            ]
        )
    ]

    # Add "Show More" button if there are remaining clans
    if remaining_clans:
        container_components.append(
            ActionRow(
                components=[
                    Button(
                        style=hikari.ButtonStyle.PRIMARY,
                        custom_id=f"clone_forum_show_more_clans:{action_id}",
                        label="Show More Clans",
                        emoji="📋"
                    )
                ]
            )
        )

    container_components.append(Media(items=[MediaItem(media="assets/Green_Footer.png")]))

    components = [
        Container(
            accent_color=GREEN_ACCENT,
            components=container_components
        )
    ]

    await ctx.respond(components=components, edit=True)


@register_action("clone_forum_clan", no_return=True)
@lightbulb.di.with_di
async def handle_clan_selection(
    ctx: lightbulb.components.MenuContext,
    action_id: str,
    bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    """Handle clan selection and execute forum cloning"""
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

    # Get source forum and target category
    source_forum_id = int(stored_data["source_forum_id"])
    target_category_id = int(stored_data["target_category_id"])

    source_forum = await bot.rest.fetch_channel(source_forum_id)
    target_category = await bot.rest.fetch_channel(target_category_id)

    # Initialize logger
    logger = CloneLogger()

    # Build progress message
    progress_text = Text(content=(
        f"## ⏳ Cloning in Progress...\n\n"
        f"**Source Forum:** {source_forum.name}\n"
        f"**Target Category:** {target_category.name}\n"
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
        # Update forum permissions
        logger.info(f"Updating forum permissions for {clan.name}")
        forum_perms = await clone_permission_overwrites(
            source_forum.permission_overwrites,
            clan.role_id,
            clan.leader_role_id,
            mongo
        )

        # Create forum name with clan suffix
        clan_suffix = get_clan_suffix(clan.name)
        base_forum_name = remove_existing_suffix(source_forum.name)
        new_forum_name = f"{base_forum_name}{clan_suffix}"

        # Create the new forum in target category
        logger.info(f"Creating new forum: {new_forum_name}")
        new_forum = await bot.rest.create_guild_forum_channel(
            ctx.guild_id,
            new_forum_name,
            topic=source_forum.topic,
            rate_limit_per_user=source_forum.rate_limit_per_user,
            default_auto_archive_duration=source_forum.default_auto_archive_duration,
            permission_overwrites=list(forum_perms.values()),
            position=source_forum.position,
            category=target_category_id
        )
        logger.success(f"Created forum: {new_forum.name}")

        # Clone forum threads
        logger.info(f"Cloning threads from {source_forum.name}")
        threads_cloned = await clone_forum_threads(bot, source_forum.id, new_forum.id, logger)
        logger.success(f"Cloned {threads_cloned} threads")

        # Success message
        success_content_parts = [
            f"## ✅ Forum Cloned Successfully!\n\n",
            f"**New Forum:** {new_forum.name}\n",
            f"**Target Category:** {target_category.name}\n",
            f"**Threads Cloned:** {threads_cloned}\n\n",
            f"**Permissions Updated:**\n",
            f"• Clan Role: <@&{clan.role_id}>\n",
            f"• Leadership Role: <@&{clan.leader_role_id}>\n\n",
            f"*Forum name updated with suffix `{clan_suffix}`*"
        ]

        # Add logger summary if there are warnings or errors
        log_summary = logger.get_summary()
        if log_summary:
            success_content_parts.append(f"\n\n{log_summary}")

        final_content = "".join(success_content_parts)
        success_text = Text(content=final_content)

        # If clan has logo, use Section with thumbnail
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

        await ctx.respond(components=success_components, edit=True)

        # Clean up stored data
        await mongo.button_store.delete_one({"_id": action_id})

        return

    except Exception as e:
        # Log the error
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
                accent_color=RED_ACCENT,
                components=[
                    Text(content="".join(error_content_parts))
                ]
            )
        ]

        await ctx.respond(components=error_components, edit=True)
        return
