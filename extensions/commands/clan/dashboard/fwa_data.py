# extensions/commands/clan/dashboard/fwa_data.py
"""
Modern FWA data management system for updating base links and images.
Provides a streamlined interface for managing FWA base configurations.
"""

import lightbulb
import hikari
import re
from typing import Dict, List, Optional, Tuple
import asyncio

from extensions.components import register_action
from utils.mongo import MongoClient
from utils.cloudinary_client import CloudinaryClient
from utils.constants import RED_ACCENT, GREEN_ACCENT, BLUE_ACCENT, GOLD_ACCENT, FWA_WAR_BASE, FWA_ACTIVE_WAR_BASE
from utils.emoji import emojis
from extensions.commands.clan.dashboard.dashboard import dashboard_page

from hikari.impl import (
    MessageActionRowBuilder as ActionRow,
    TextSelectMenuBuilder as TextSelectMenu,
    SelectOptionBuilder as SelectOption,
    ContainerComponentBuilder as Container,
    InteractiveButtonBuilder as Button,
    TextDisplayComponentBuilder as Text,
    SeparatorComponentBuilder as Separator,
    MediaGalleryComponentBuilder as Media,
    MediaGalleryItemBuilder as MediaItem,
    ModalActionRowBuilder as ModalActionRow,
    ThumbnailComponentBuilder as Thumbnail,
    SectionComponentBuilder as Section,
)

FWA_REP_ROLE_ID = 1088914884999249940

# TH levels we support for FWA (ordered from highest to lowest)
FWA_TH_LEVELS = ["th18", "th18_new", "th17", "th17_new", "th16", "th16_new", "th15", "th14", "th13", "th12", "th11", "th10", "th9"]

# Cloudinary folders for FWA images
CLOUDINARY_WAR_BASE_FOLDER = "fwa/war_bases"
CLOUDINARY_ACTIVE_BASE_FOLDER = "fwa/active_bases"


# Helper function to generate public IDs
def get_fwa_public_id(th_level: str, base_type: str) -> str:
    """Generate consistent public ID for FWA images

    Args:
        th_level: e.g., "th15" or "TH15"
        base_type: "war" or "active"

    Returns:
        str: e.g., "TH15_WarBase" or "TH15_Active_WarBase"
    """
    th_num = th_level.upper().replace("TH", "")

    if base_type == "war":
        return f"TH{th_num}_WarBase"
    else:
        return f"TH{th_num}_Active_WarBase"


def get_th_emoji(th_level: str):
    """Get the appropriate TH emoji object"""
    # Handle _new variants by removing the suffix
    clean_th_level = th_level.replace("_new", "")
    th_num = clean_th_level.upper().replace("TH", "")
    emoji_attr = f"TH{th_num}"
    if hasattr(emojis, emoji_attr):
        return getattr(emojis, emoji_attr)
    return None


def validate_clash_link(link: str) -> bool:
    """Validate if a link is a valid Clash of Clans link"""
    # Simple validation - just check if it's a clash of clans link
    return link.startswith("https://link.clashofclans.com/")


def validate_image_url(url: str) -> bool:
    """Validate if a URL is a valid image URL"""
    pattern = r'^https?://.*\.(?:png|jpe?g|gif|webp)'
    return bool(re.match(pattern, url, re.IGNORECASE))


async def get_fwa_data(mongo: MongoClient) -> Dict:
    """Get current FWA data from MongoDB"""
    fwa_data = await mongo.fwa.find_one({"_id": "fwa_config"})
    if not fwa_data:
        # Initialize empty FWA data if none exists
        fwa_data = {
            "_id": "fwa_config",
            "fwa_base_links": {},
            "base_information": {},
            "base_upgrade_notes": {},
            "war_base_images": {},
            "active_base_images": {}
        }
        await mongo.fwa.insert_one(fwa_data)
    else:
        # Migration: Move old base_descriptions to base_information
        if "base_descriptions" in fwa_data and "base_information" not in fwa_data:
            await mongo.fwa.update_one(
                {"_id": "fwa_config"},
                {"$set": {"base_information": fwa_data["base_descriptions"]}}
            )
            fwa_data["base_information"] = fwa_data["base_descriptions"]

        # Ensure base_upgrade_notes exists
        if "base_upgrade_notes" not in fwa_data:
            await mongo.fwa.update_one(
                {"_id": "fwa_config"},
                {"$set": {"base_upgrade_notes": {}}}
            )
            fwa_data["base_upgrade_notes"] = {}

    return fwa_data


async def build_fwa_management_screen(
        ctx: lightbulb.components.MenuContext,
        mongo: MongoClient
) -> List[Container]:
    """Build the FWA management screen components

    Returns:
        List of Container components for the FWA management screen
    """
    # Get current FWA data
    fwa_data = await get_fwa_data(mongo)
    base_links = fwa_data.get("fwa_base_links", {})
    base_information = fwa_data.get("base_information", {})
    base_upgrade_notes = fwa_data.get("base_upgrade_notes", {})

    # Load stored image URLs into memory if available
    war_images = fwa_data.get("war_base_images", {})
    active_images = fwa_data.get("active_base_images", {})

    # Update the constants with stored URLs
    if war_images:
        FWA_WAR_BASE.update(war_images)
    if active_images:
        FWA_ACTIVE_WAR_BASE.update(active_images)

    # Build overview of all TH levels
    overview_lines = []
    for th in FWA_TH_LEVELS:
        emoji_obj = get_th_emoji(th)
        emoji_str = str(emoji_obj) if emoji_obj else "🏛️"
        base_link = base_links.get(th)
        war_image = FWA_WAR_BASE.get(th)
        active_image = FWA_ACTIVE_WAR_BASE.get(th)
        base_info = base_information.get(th)
        upgrade_notes = base_upgrade_notes.get(th)

        status = format_th_status(th, base_link, war_image, active_image, base_info, upgrade_notes)
        th_num = th.upper().replace("TH", "")

        overview_lines.append(f"{emoji_str} **TH{th_num}** {status}")

    # Build dropdown options for TH selection
    options = []
    for th in FWA_TH_LEVELS:
        emoji_obj = get_th_emoji(th)
        th_num = th.upper().replace("TH", "")

        # Check what data exists
        has_link = "✅" if base_links.get(th) else "❌"
        has_war = "✅" if FWA_WAR_BASE.get(th) else "❌"
        has_active = "✅" if FWA_ACTIVE_WAR_BASE.get(th) else "❌"
        has_info = "✅" if base_information.get(th) else "❌"
        has_notes = "✅" if base_upgrade_notes.get(th) else "❌"

        description = f"Link {has_link} | War {has_war} | Active {has_active} | Info {has_info} | Notes {has_notes}"

        option_kwargs = {
            "label": f"Town Hall {th_num}",
            "value": th,
            "description": description
        }

        # Only add emoji if it has partial_emoji attribute
        if emoji_obj and hasattr(emoji_obj, 'partial_emoji'):
            option_kwargs["emoji"] = emoji_obj.partial_emoji

        options.append(SelectOption(**option_kwargs))

    components = [
        Container(
            accent_color=BLUE_ACCENT,
            components=[
                Text(content="## 🏰 **FWA Data Management**"),
                Text(content="Manage base links and images for each Town Hall level"),
                Separator(divider=True),
                Text(content=(
                    "**Status Icons:**\n"
                    "🔗 = Base Link | 🖼️ = War Image | 🎯 = Active Image\n"
                    "📝 = Base Information | 📋 = Upgrade Notes | ❌ = Missing Data"
                )),
                Separator(divider=True),
                Text(content="### 📊 **Current Status**"),
                Text(content="\n".join(overview_lines)),
                Separator(divider=True),
                Text(content="### 🔧 **Select Town Hall to Edit**"),

                ActionRow(
                    components=[
                        TextSelectMenu(
                            custom_id="fwa_th_select:main",
                            placeholder="Select a Town Hall to edit...",
                            max_values=1,
                            options=options,
                        )
                    ]
                ),

                Media(items=[MediaItem(media="assets/Blue_Footer.png")]),
            ]
        )
    ]

    return components


def format_th_status(th_level: str, base_link: Optional[str], war_image: Optional[str],
                     active_image: Optional[str], base_info: Optional[str],
                     upgrade_notes: Optional[str]) -> str:
    """Format the status of a TH level for display"""
    statuses = []

    if base_link:
        statuses.append("🔗")
    else:
        statuses.append("❌")

    if war_image:
        statuses.append("🖼️")
    else:
        statuses.append("❌")

    if active_image:
        statuses.append("🎯")
    else:
        statuses.append("❌")

    if base_info:
        statuses.append("📝")
    else:
        statuses.append("❌")

    if upgrade_notes:
        statuses.append("📋")
    else:
        statuses.append("❌")

    return " ".join(statuses)


def build_th_edit_components(th_level: str, base_link: str, base_info: str,
                             upgrade_notes: str, war_image: str, active_image: str) -> List[Container]:
    """Build the TH edit screen components

    Args:
        th_level: The TH level (e.g., "th15")
        base_link: The base link URL
        base_info: Base information description
        upgrade_notes: Upgrade notes description
        war_image: War base image URL
        active_image: Active base image URL

    Returns:
        List of Container components for the TH edit screen
    """
    th_num = th_level.upper().replace("TH", "")
    emoji_obj = get_th_emoji(th_level)
    emoji_str = str(emoji_obj) if emoji_obj else "🏛️"

    # Build components
    component_list = [
        Text(content=f"## {emoji_str} **Editing TH{th_num} FWA Data**"),
        Separator(divider=True),
    ]

    # Base Link Section
    component_list.extend([
        Text(content="### 🔗 **Base Link**"),
        Text(content=f"```\n{base_link if base_link else 'No link set'}\n```"),
    ])

    # War Base Image Section
    if war_image:
        component_list.extend([
            Text(content="### 🖼️ **Current War Base**"),
            Media(items=[MediaItem(media=war_image)]),
        ])
    else:
        component_list.append(Text(content="### 🖼️ **War Base** - ❌ Not Set"))

    # Active Base Image Section
    if active_image:
        component_list.extend([
            Text(content="### 🎯 **Current Active Base**"),
            Media(items=[MediaItem(media=active_image)]),
        ])
    else:
        component_list.append(Text(content="### 🎯 **Active Base** - ❌ Not Set"))

    # Description Sections
    component_list.extend([
        Text(content="### 📝 **Base Information**"),
        Text(content=f"{base_info if base_info else 'Not set'}"),
        Separator(divider=True),
        Text(content="### 📋 **Upgrade Notes (What's New)**"),
        Text(content=f"{upgrade_notes if upgrade_notes else 'Not set'}"),
        Separator(divider=True),
    ])

    # Action Buttons
    component_list.extend([
        ActionRow(
            components=[
                Button(
                    style=hikari.ButtonStyle.PRIMARY,
                    label="Update Link",
                    emoji="🔗",
                    custom_id=f"fwa_update_link:{th_level}",
                ),
                Button(
                    style=hikari.ButtonStyle.PRIMARY,
                    label="Update Images",
                    emoji="🖼️",
                    custom_id=f"fwa_update_images:{th_level}",
                ),
                Button(
                    style=hikari.ButtonStyle.PRIMARY,
                    label="Update Descriptions",
                    emoji="📝",
                    custom_id=f"fwa_update_descriptions:{th_level}",
                ),
            ]
        ),
        ActionRow(
            components=[
                Button(
                    style=hikari.ButtonStyle.SECONDARY,
                    label="Back",
                    emoji="◀️",
                    custom_id="fwa_back_to_main:main",
                ),
            ]
        ),
    ])

    components = [
        Container(
            accent_color=BLUE_ACCENT,
            components=component_list
        )
    ]

    return components


@register_action("manage_fwa_data", group="clan_database")
@lightbulb.di.with_di
async def manage_fwa_data(
        ctx: lightbulb.components.MenuContext,
        mongo: MongoClient = lightbulb.di.INJECTED,
        **kwargs
):
    """Main FWA data management dashboard"""

    # Check if user has the required role
    member = ctx.member
    if not member:
        await ctx.respond(
            "❌ Unable to verify permissions. Please try again.",
            ephemeral=True
        )
        return

    # Check if the user has the FWA Rep role
    user_role_ids = [role.id for role in member.get_roles()]
    if FWA_REP_ROLE_ID not in user_role_ids:
        # User doesn't have permission - show access denied message
        components = [
            Container(
                accent_color=RED_ACCENT,
                components=[
                    Text(content="## ❌ Access Denied"),
                    Separator(divider=True),
                    Text(content=(
                        "You do not have permission to access FWA Data Management.\n\n"
                        "This feature is restricted to users with the FWA Rep role.\n"
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
        await ctx.respond(components=components, ephemeral=True)
        return await dashboard_page(ctx=ctx, mongo=mongo)

    # If we get here, user has permission - build and show the FWA management screen
    components = await build_fwa_management_screen(ctx, mongo)

    await ctx.respond(components=components, ephemeral=True)

    return await dashboard_page(ctx=ctx, mongo=mongo)


@register_action("fwa_back_to_main", ephemeral=True)
@lightbulb.di.with_di
async def fwa_back_to_main(
        ctx: lightbulb.components.MenuContext,
        mongo: MongoClient = lightbulb.di.INJECTED,
        **kwargs
):
    """Return to FWA management main screen from TH edit or other sub-screens"""
    return await build_fwa_management_screen(ctx, mongo)


@register_action("fwa_th_select", ephemeral=True)
@lightbulb.di.with_di
async def fwa_th_select(
        ctx: lightbulb.components.MenuContext,
        mongo: MongoClient = lightbulb.di.INJECTED,
        cloudinary: CloudinaryClient = lightbulb.di.INJECTED,
        **kwargs
):
    """Display detailed edit view for selected TH"""

    th_level = ctx.interaction.values[0]

    # Get current data
    fwa_data = await get_fwa_data(mongo)
    base_link = fwa_data.get("fwa_base_links", {}).get(th_level, "")
    base_info = fwa_data.get("base_information", {}).get(th_level, "")
    upgrade_notes = fwa_data.get("base_upgrade_notes", {}).get(th_level, "")
    war_image = FWA_WAR_BASE.get(th_level, "")
    active_image = FWA_ACTIVE_WAR_BASE.get(th_level, "")

    # Build and return the TH edit screen
    return build_th_edit_components(th_level, base_link, base_info, upgrade_notes, war_image, active_image)


@register_action("fwa_update_link", no_return=True, is_modal=True)
async def fwa_update_link(
        ctx: lightbulb.components.MenuContext,
        action_id: str,
        **kwargs
):
    """Modal for updating base link"""
    th_level = action_id
    th_num = th_level.upper().replace("TH", "")

    link_input = ModalActionRow().add_text_input(
        "base_link",
        f"TH{th_num} Base Link",
        placeholder="https://link.clashofclans.com/?action=OpenLayout&id=...",
        required=True,
        max_length=500
    )

    await ctx.respond_with_modal(
        title=f"Update TH{th_num} Base Link",
        custom_id=f"fwa_link_submit:{th_level}",
        components=[link_input]
    )


@register_action("fwa_link_submit", no_return=True, is_modal=True)
@lightbulb.di.with_di
async def fwa_link_submit(
        ctx: lightbulb.components.ModalContext,
        action_id: str,
        mongo: MongoClient = lightbulb.di.INJECTED,
        **kwargs
):
    """Process base link update"""
    th_level = action_id
    th_num = th_level.upper().replace("TH", "")

    def get_value(custom_id: str) -> str:
        for row in ctx.interaction.components:
            for comp in row:
                if comp.custom_id == custom_id:
                    return comp.value
        return ""

    base_link = get_value("base_link").strip()

    # Validate the link
    if not validate_clash_link(base_link):
        await ctx.respond(
            "❌ Invalid base link! Please use a valid Clash of Clans layout link.",
            ephemeral=True
        )
        return

    # Update in database
    await mongo.fwa.update_one(
        {"_id": "fwa_config"},
        {"$set": {f"fwa_base_links.{th_level}": base_link}},
        upsert=True
    )

    # Success response
    await ctx.interaction.create_initial_response(
        hikari.ResponseType.MESSAGE_UPDATE,
        components=[
            Container(
                accent_color=GREEN_ACCENT,
                components=[
                    Text(content=f"## ✅ TH{th_num} Base Link Updated!"),
                    Text(content=f"```\n{base_link}\n```"),
                    Separator(divider=True),
                    ActionRow(
                        components=[
                            Button(
                                style=hikari.ButtonStyle.PRIMARY,
                                label=f"Back to TH{th_num} Edit",
                                custom_id=f"fwa_th_select_return:{th_level}",
                            ),
                            Button(
                                style=hikari.ButtonStyle.SECONDARY,
                                label="Back to Main Menu",
                                custom_id="fwa_back_to_main:main",
                            )
                        ]
                    )
                ]
            )
        ]
    )

@register_action("fwa_update_images", ephemeral=True)
@lightbulb.di.with_di
async def fwa_update_images(
        ctx: lightbulb.components.MenuContext,
        action_id: str,
        **kwargs
):
    """Show options for updating images"""
    th_level = action_id
    th_num = th_level.upper().replace("TH", "")

    components = [
        Container(
            accent_color=GOLD_ACCENT,
            components=[
                Text(content=f"## 🖼️ **Update TH{th_num} Images**"),
                Text(content="Choose how to update the base images:"),
                Separator(divider=True),

                Section(
                    components=[
                        Text(content=(
                            "**Option 1: Image URLs**\n"
                            "Provide direct links to images already hosted online"
                        ))
                    ],
                    accessory=Button(
                        style=hikari.ButtonStyle.PRIMARY,
                        label="Use URLs",
                        emoji="🔗",
                        custom_id=f"fwa_image_urls:{th_level}",
                    )
                ),

                Section(
                    components=[
                        Text(content=(
                            "**Option 2: Upload Command**\n"
                            "Use `/fwa upload-images` to upload files directly"
                        ))
                    ],
                    accessory=Button(
                        style=hikari.ButtonStyle.PRIMARY,
                        label="Instructions",
                        emoji="📤",
                        custom_id=f"fwa_upload_guide:{th_level}",
                    )
                ),

                ActionRow(
                    components=[
                        Button(
                            style=hikari.ButtonStyle.SECONDARY,
                            label="Back",
                            emoji="◀️",
                            custom_id=f"fwa_th_select_return:{th_level}",
                        )
                    ]
                ),

                Media(items=[MediaItem(media="assets/Gold_Footer.png")]),
            ]
        )
    ]

    return components


@register_action("fwa_image_urls", no_return=True, is_modal=True)
async def fwa_image_urls(
        ctx: lightbulb.components.MenuContext,
        action_id: str,
        **kwargs
):
    """Modal for updating image URLs"""
    th_level = action_id
    th_num = th_level.upper().replace("TH", "")

    war_input = ModalActionRow().add_text_input(
        "war_image",
        f"TH{th_num} War Base Image URL",
        placeholder="https://example.com/war_base.png",
        required=False,
        max_length=500
    )

    active_input = ModalActionRow().add_text_input(
        "active_image",
        f"TH{th_num} Active Base Image URL",
        placeholder="https://example.com/active_base.png",
        required=False,
        max_length=500
    )

    await ctx.respond_with_modal(
        title=f"Update TH{th_num} Images",
        custom_id=f"fwa_images_submit:{th_level}",
        components=[war_input, active_input]
    )


@register_action("fwa_images_submit", no_return=True, is_modal=True)
@lightbulb.di.with_di
async def fwa_images_submit(
        ctx: lightbulb.components.ModalContext,
        action_id: str,
        cloudinary: CloudinaryClient = lightbulb.di.INJECTED,
        mongo: MongoClient = lightbulb.di.INJECTED,
        **kwargs
):
    """Process image URL updates"""
    th_level = action_id
    th_num = th_level.upper().replace("TH", "")

    def get_value(custom_id: str) -> str:
        for row in ctx.interaction.components:
            for comp in row:
                if comp.custom_id == custom_id:
                    return comp.value
        return ""

    war_url = get_value("war_image").strip()
    active_url = get_value("active_image").strip()

    if not war_url and not active_url:
        await ctx.respond(
            "❌ Please provide at least one image URL!",
            ephemeral=True
        )
        return

    # Validate URLs
    if war_url and not validate_image_url(war_url):
        await ctx.respond(
            "❌ Invalid war base image URL!",
            ephemeral=True
        )
        return

    if active_url and not validate_image_url(active_url):
        await ctx.respond(
            "❌ Invalid active base image URL!",
            ephemeral=True
        )
        return

    # Initial response
    await ctx.interaction.create_initial_response(
        hikari.ResponseType.MESSAGE_UPDATE,
        components=[
            Container(
                accent_color=BLUE_ACCENT,
                components=[
                    Text(content="## ⏳ Uploading Images..."),
                    Text(content="Please wait while we upload your images to Cloudinary...")
                ]
            )
        ]
    )

    try:
        updates = []

        # Upload war base image
        if war_url:
            war_public_id = get_fwa_public_id(th_level, "war")

            result = await cloudinary.upload_image_from_url(
                war_url,
                folder=CLOUDINARY_WAR_BASE_FOLDER,
                public_id=war_public_id
            )
            war_cloudinary_url = result["secure_url"]

            # Update the constant in memory (for this session)
            FWA_WAR_BASE[th_level] = war_cloudinary_url

            # Update in database
            await mongo.fwa.update_one(
                {"_id": "fwa_config"},
                {"$set": {f"war_base_images.{th_level}": war_cloudinary_url}},
                upsert=True
            )

            updates.append(f"✅ War base image uploaded")

        # Upload active base image
        if active_url:
            active_public_id = get_fwa_public_id(th_level, "active")

            result = await cloudinary.upload_image_from_url(
                active_url,
                folder=CLOUDINARY_ACTIVE_BASE_FOLDER,
                public_id=active_public_id
            )
            active_cloudinary_url = result["secure_url"]

            # Update the constant in memory (for this session)
            FWA_ACTIVE_WAR_BASE[th_level] = active_cloudinary_url

            # Update in database
            await mongo.fwa.update_one(
                {"_id": "fwa_config"},
                {"$set": {f"active_base_images.{th_level}": active_cloudinary_url}},
                upsert=True
            )

            updates.append(f"✅ Active base image uploaded")

        # Success response
        await ctx.interaction.edit_initial_response(
            components=[
                Container(
                    accent_color=GREEN_ACCENT,
                    components=[
                        Text(content=f"## ✅ TH{th_num} Images Updated!"),
                        Text(content="\n".join(updates)),
                        Separator(divider=True),
                        Text(content="*Images have been uploaded successfully!*"),
                        ActionRow(
                            components=[
                                Button(
                                    style=hikari.ButtonStyle.PRIMARY,
                                    label=f"Back to TH{th_num} Edit",
                                    custom_id=f"fwa_th_select_return:{th_level}",
                                ),
                                Button(
                                    style=hikari.ButtonStyle.SECONDARY,
                                    label="Back to Main Menu",
                                    custom_id="manage_fwa_data:main",
                                )
                            ]
                        )
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
                        Text(content="## ❌ Upload Failed"),
                        Text(content=f"Error: {str(e)[:200]}"),
                        ActionRow(
                            components=[
                                Button(
                                    style=hikari.ButtonStyle.SECONDARY,
                                    label="Back",
                                    custom_id=f"fwa_th_select_return:{th_level}",
                                )
                            ]
                        )
                    ]
                )
            ]
        )

@register_action("fwa_update_descriptions", no_return=True, is_modal=True)
@lightbulb.di.with_di
async def fwa_update_descriptions(
        ctx: lightbulb.components.MenuContext,
        action_id: str,
        mongo: MongoClient = lightbulb.di.INJECTED,
        **kwargs
):
    """Modal for updating base descriptions"""
    th_level = action_id
    th_num = th_level.upper().replace("TH", "")

    # Fetch existing data from MongoDB
    fwa_data = await get_fwa_data(mongo)
    existing_base_info = fwa_data.get("base_information", {}).get(th_level, "")
    existing_upgrade_notes = fwa_data.get("base_upgrade_notes", {}).get(th_level, "")

    info_input = ModalActionRow().add_text_input(
        "base_information",
        "Base Information",
        placeholder="General information about this base layout",
        required=False,
        max_length=4000,
        style=hikari.TextInputStyle.PARAGRAPH,
        value=existing_base_info
    )

    notes_input = ModalActionRow().add_text_input(
        "upgrade_notes",
        "Upgrade Notes (What's New)",
        placeholder="What changed from previous TH (new buildings, defense levels, etc.)",
        required=False,
        max_length=4000,
        style=hikari.TextInputStyle.PARAGRAPH,
        value=existing_upgrade_notes
    )

    await ctx.respond_with_modal(
        title=f"Update TH{th_num} Descriptions",
        custom_id=f"fwa_descriptions_submit:{th_level}",
        components=[info_input, notes_input]
    )


@register_action("fwa_th_select_return", ephemeral=True)
@lightbulb.di.with_di
async def fwa_th_select_return(
        ctx: lightbulb.components.MenuContext,
        action_id: str,
        mongo: MongoClient = lightbulb.di.INJECTED,
        cloudinary: CloudinaryClient = lightbulb.di.INJECTED,
        **kwargs
):
    """Return to TH edit view"""
    # Manually set the interaction values to simulate selection
    ctx.interaction.values = [action_id]

    # Call fwa_th_select and get its components
    return await fwa_th_select(ctx=ctx, mongo=mongo, cloudinary=cloudinary, **kwargs)


@register_action("fwa_descriptions_submit", no_return=True, is_modal=True)
@lightbulb.di.with_di
async def fwa_descriptions_submit(
        ctx: lightbulb.components.ModalContext,
        action_id: str,
        mongo: MongoClient = lightbulb.di.INJECTED,
        **kwargs
):
    """Process description updates"""
    th_level = action_id
    th_num = th_level.upper().replace("TH", "")

    def get_value(custom_id: str) -> str:
        for row in ctx.interaction.components:
            for comp in row:
                if comp.custom_id == custom_id:
                    return comp.value
        return ""

    base_info = get_value("base_information").strip()
    upgrade_notes = get_value("upgrade_notes").strip()

    # Check if at least one field is provided
    if not base_info and not upgrade_notes:
        await ctx.respond(
            "❌ Please provide at least one description!",
            ephemeral=True
        )
        return

    # Update in database
    update_fields = {}
    if base_info:
        update_fields[f"base_information.{th_level}"] = base_info
    if upgrade_notes:
        update_fields[f"base_upgrade_notes.{th_level}"] = upgrade_notes

    await mongo.fwa.update_one(
        {"_id": "fwa_config"},
        {"$set": update_fields},
        upsert=True
    )

    # Initial response - show loading screen immediately
    await ctx.interaction.create_initial_response(
        hikari.ResponseType.MESSAGE_UPDATE,
        components=[
            Container(
                accent_color=BLUE_ACCENT,
                components=[
                    Text(content="## ⏳ Updating Descriptions..."),
                    Text(content="Please wait while we update the descriptions...")
                ]
            )
        ]
    )

    # Fetch UPDATED data from database
    fwa_data = await get_fwa_data(mongo)
    base_link = fwa_data.get("fwa_base_links", {}).get(th_level, "")
    updated_base_info = fwa_data.get("base_information", {}).get(th_level, "")
    updated_upgrade_notes = fwa_data.get("base_upgrade_notes", {}).get(th_level, "")
    war_image = FWA_WAR_BASE.get(th_level, "")
    active_image = FWA_ACTIVE_WAR_BASE.get(th_level, "")

    # Build TH edit screen with updated descriptions
    components = build_th_edit_components(
        th_level, base_link, updated_base_info, updated_upgrade_notes, war_image, active_image
    )

    # Edit the response to show the updated TH edit screen
    await ctx.interaction.edit_initial_response(components=components)


@register_action("fwa_upload_guide", ephemeral=True)
@lightbulb.di.with_di
async def fwa_upload_guide(
        ctx: lightbulb.components.MenuContext,
        action_id: str,  # th_level
        **kwargs
):
    """Show upload instructions"""
    th_level = action_id
    th_num = th_level.upper().replace("TH", "")

    components = [
        Container(
            accent_color=BLUE_ACCENT,
            components=[
                Text(content=f"## 📤 **Upload Images for TH{th_num}**"),
                Separator(divider=True),

                Text(content=(
                    "**To upload images using the command:**\n\n"
                    "1. Copy this command:\n"
                    f"```/fwa upload-images town-hall:Town Hall {th_num[2:]}```\n\n"
                    "2. Paste it in any channel\n\n"
                    "3. Attach your images:\n"
                    "   • Click the ➕ button\n"
                    "   • Select war base image\n"
                    "   • Select active base image\n\n"
                    "4. Press Enter to upload\n\n"
                    "**File Requirements:**\n"
                    "• Formats: PNG, JPG, GIF, or WEBP\n"
                    "• Maximum size: 8MB per file"
                )),

                ActionRow(
                    components=[
                        Button(
                            style=hikari.ButtonStyle.SECONDARY,
                            label="Back",
                            emoji="◀️",
                            custom_id=f"fwa_update_images:{th_level}",
                        )
                    ]
                ),

                Media(items=[MediaItem(media="assets/Blue_Footer.png")]),
            ]
        )
    ]

    return components
