# extensions/commands/say_announce.py
"""
Rich announcement command with Components V2
Extends the simple /say command with beautiful formatting, styles, and preview system
"""

import re
import lightbulb
import hikari
from datetime import datetime, timezone, timedelta

from hikari.impl import (
    ContainerComponentBuilder as Container,
    TextDisplayComponentBuilder as Text,
    SeparatorComponentBuilder as Separator,
    MediaGalleryComponentBuilder as Media,
    MediaGalleryItemBuilder as MediaItem,
    LinkButtonBuilder as LinkButton,
    MessageActionRowBuilder as ActionRow,
    ModalActionRowBuilder as ModalActionRow,
    InteractiveButtonBuilder as Button,
)

from utils.mongo import MongoClient
from utils.constants import BLUE_ACCENT, GREEN_ACCENT, GOLD_ACCENT, DARK_MAGENTA_ACCENT
from extensions.components import register_action

loader = lightbulb.Loader()

# Constants (same as say.py)
ALLOWED_ROLE_ID = 1060318031575793694
LOG_CHANNEL_ID = 1350318721771634699

# URL validation pattern
URL_PATTERN = re.compile(r'^https?://.+', re.IGNORECASE)

# Announcement style configurations
ANNOUNCEMENT_STYLES = {
    "announcement": {
        "emoji": "📢",
        "color": GOLD_ACCENT,
        "footer": "assets/Gold_Footer.png",
        "name": "Announcement",
        "header": "New Announcement!"
    },
    "info": {
        "emoji": "ℹ️",
        "color": BLUE_ACCENT,
        "footer": "assets/Blue_Footer.png",
        "name": "Information",
        "header": "Information Update"
    },
    "success": {
        "emoji": "✅",
        "color": GREEN_ACCENT,
        "footer": "assets/Green_Footer.png",
        "name": "Success",
        "header": "Success Notice"
    },
    "warning": {
        "emoji": "⚠️",
        "color": GOLD_ACCENT,
        "footer": "assets/Gold_Footer.png",
        "name": "Warning",
        "header": "Important Warning"
    },
    "urgent": {
        "emoji": "🚨",
        "color": DARK_MAGENTA_ACCENT,
        "footer": "assets/Red_Footer.png",
        "name": "Urgent",
        "header": "URGENT NOTICE"
    }
}


def build_announcement_components(
    style_config: dict,
    title: str,
    description: str,
    image_url: str = None,
    footer_text: str = None,
    role_id: str = None,
    creator_id: str = None,
    is_preview: bool = False
) -> list:
    """
    Build announcement components with proper formatting.

    Args:
        style_config: Style configuration dict
        title: Announcement title
        description: Announcement description
        image_url: Optional image URL
        footer_text: Optional custom footer text
        role_id: Optional role ID to ping
        creator_id: Creator user ID
        is_preview: If True, add preview indicator

    Returns:
        List of component builders
    """
    components = []

    # Role ping header (if specified)
    if role_id:
        components.append(
            Text(content=f"<@&{role_id}> **{style_config['header']}**")
        )
        components.append(Separator(divider=True))

    # Title with style emoji
    title_text = f"## {style_config['emoji']} {title}"
    if is_preview:
        title_text += " *(Preview)*"
    components.append(Text(content=title_text))

    # Optional banner image
    if image_url and URL_PATTERN.match(image_url):
        try:
            components.append(Media(items=[MediaItem(media=image_url)]))
            components.append(Separator(divider=False, spacing=hikari.SpacingType.SMALL))
        except Exception as e:
            # If image fails to add, just skip it
            print(f"[Announce] Failed to add image: {e}")

    components.append(Separator(divider=True))

    # Main description content
    components.append(Text(content=description))

    components.append(Separator(divider=True))

    # Attribution and timestamp
    timestamp = int(datetime.now(timezone.utc).timestamp())
    attribution = f"👤 **Posted by:** <@{creator_id}>\n🕐 **Time:** <t:{timestamp}:R>"
    components.append(Text(content=attribution))

    # Optional custom footer text
    if footer_text and footer_text.strip():
        components.append(Separator(divider=False, spacing=hikari.SpacingType.SMALL))
        components.append(Text(content=f"*{footer_text}*"))

    # Footer image based on style
    components.append(Media(items=[MediaItem(media=style_config["footer"])]))

    return components


@loader.command
class SayAnnounce(
    lightbulb.SlashCommand,
    name="say-announce",
    description="Send a rich announcement with beautiful formatting and Components V2",
):
    style = lightbulb.string(
        "style",
        "Visual style for the announcement",
        choices=[
            lightbulb.Choice(name=f"{config['emoji']} {config['name']}", value=key)
            for key, config in ANNOUNCEMENT_STYLES.items()
        ],
        default="announcement"
    )

    role = lightbulb.role(
        "role",
        "Role to ping for the announcement (optional)",
        default=None
    )

    channel = lightbulb.channel(
        "channel",
        "Channel to send announcement to (defaults to current channel)",
        channel_types=[hikari.ChannelType.GUILD_TEXT],
        default=None
    )

    @lightbulb.invoke
    @lightbulb.di.with_di
    async def invoke(
        self,
        ctx: lightbulb.Context,
        mongo: MongoClient = lightbulb.di.INJECTED,
    ) -> None:
        # Check if user has the required role
        member = ctx.member
        if ALLOWED_ROLE_ID not in member.role_ids:
            await ctx.respond(
                "❌ You don't have permission to use this command.",
                ephemeral=True
            )
            return

        # Determine target channel
        target_channel = self.channel if self.channel else ctx.channel_id
        channel_id = str(target_channel.id) if hasattr(target_channel, 'id') else str(target_channel)

        # Get style config
        style_config = ANNOUNCEMENT_STYLES[self.style]

        # Store data for modal response
        announcement_data = {
            "style": self.style,
            "style_config": style_config,
            "role_id": str(self.role.id) if self.role else None,
            "channel_id": channel_id,
            "guild_id": str(ctx.guild_id),
            "creator_id": str(ctx.user.id),
        }

        # Create modal with 4 fields
        modal_rows = [
            ModalActionRow().add_text_input(
                "title",
                "Announcement Title",
                placeholder="Enter a clear, concise title",
                required=True,
                max_length=100
            ),
            ModalActionRow().add_text_input(
                "description",
                "Description",
                placeholder="Main content of your announcement (supports **markdown** formatting)",
                required=True,
                style=hikari.TextInputStyle.PARAGRAPH,
                max_length=2000
            ),
            ModalActionRow().add_text_input(
                "image_url",
                "Image URL (Optional)",
                placeholder="https://example.com/image.png - Banner image above content",
                required=False,
                max_length=200
            ),
            ModalActionRow().add_text_input(
                "footer_text",
                "Footer Text (Optional)",
                placeholder="Custom footer message",
                required=False,
                max_length=100
            ),
        ]

        # Store announcement data temporarily
        await mongo.button_store.insert_one({
            "_id": str(ctx.interaction.id),
            "type": "announce_create",
            "data": announcement_data,
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5)
        })

        await ctx.respond_with_modal(
            title=f"Create {style_config['name']} Announcement",
            custom_id=f"announce_modal:{ctx.interaction.id}",
            components=modal_rows
        )


@register_action("announce_modal", is_modal=True, no_return=True)
@lightbulb.di.with_di
async def handle_announce_modal(
    ctx: lightbulb.components.ModalContext,
    action_id: str,
    mongo: MongoClient = lightbulb.di.INJECTED,
    bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    **kwargs
) -> None:
    """Handle announcement creation modal submission and show preview"""

    # Get stored announcement data
    stored = await mongo.button_store.find_one({"_id": action_id})
    if not stored:
        await ctx.respond("❌ Announcement creation expired. Please try again.", ephemeral=True)
        return

    announcement_data = stored["data"]
    style_config = announcement_data["style_config"]

    # Extract modal values
    values = {}
    for row in ctx.interaction.components:
        for comp in row:
            values[comp.custom_id] = comp.value if comp.value else ""

    # Validate required fields
    title = values.get("title", "").strip()
    description = values.get("description", "").strip()

    if not title or not description:
        await ctx.respond("❌ Title and description are required!", ephemeral=True)
        return

    # Optional fields
    image_url = values.get("image_url", "").strip()
    footer_text = values.get("footer_text", "").strip()

    # Validate image URL if provided
    if image_url and not URL_PATTERN.match(image_url):
        await ctx.respond(
            "❌ Invalid image URL. Must start with http:// or https://",
            ephemeral=True
        )
        return

    # Build preview announcement
    preview_components = build_announcement_components(
        style_config=style_config,
        title=title,
        description=description,
        image_url=image_url,
        footer_text=footer_text,
        role_id=announcement_data["role_id"],
        creator_id=announcement_data["creator_id"],
        is_preview=True
    )

    # Add preview notice and confirm/cancel buttons
    preview_notice = [
        Separator(divider=True),
        Text(content="⚠️ **This is a preview.** Click Confirm to send or Cancel to discard.")
    ]

    # Create new action ID for confirmation
    confirm_action_id = str(ctx.interaction.id) + "_confirm"

    # Store all data for confirmation
    await mongo.button_store.insert_one({
        "_id": confirm_action_id,
        "type": "announce_confirm",
        "data": {
            **announcement_data,
            "title": title,
            "description": description,
            "image_url": image_url,
            "footer_text": footer_text,
        },
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5)
    })

    # Action buttons
    action_row = ActionRow()
    action_row.add_component(
        Button(
            style=hikari.ButtonStyle.SUCCESS,
            label="Confirm & Send",
            custom_id=f"announce_confirm:{confirm_action_id}",
            emoji="✅"
        )
    )
    action_row.add_component(
        Button(
            style=hikari.ButtonStyle.DANGER,
            label="Cancel",
            custom_id=f"announce_cancel:{confirm_action_id}",
            emoji="❌"
        )
    )

    # Build final preview container
    container = Container(
        accent_color=style_config["color"],
        components=preview_components + preview_notice + [action_row]
    )

    # Clean up original button store entry
    await mongo.button_store.delete_one({"_id": action_id})

    # Send preview
    await ctx.respond(
        components=[container],
        ephemeral=True
    )


@register_action("announce_confirm", no_return=True)
@lightbulb.di.with_di
async def handle_announce_confirm(
    ctx: lightbulb.components.MenuContext,
    action_id: str,
    mongo: MongoClient = lightbulb.di.INJECTED,
    bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    **kwargs
) -> None:
    """Handle announcement confirmation and send to target channel"""

    # Get stored data
    stored = await mongo.button_store.find_one({"_id": action_id})
    if not stored:
        await ctx.respond("❌ Announcement expired. Please try again.", ephemeral=True)
        return

    data = stored["data"]
    style_config = data["style_config"]

    try:
        # Build final announcement (without preview flag)
        announcement_components = build_announcement_components(
            style_config=style_config,
            title=data["title"],
            description=data["description"],
            image_url=data["image_url"],
            footer_text=data["footer_text"],
            role_id=data["role_id"],
            creator_id=data["creator_id"],
            is_preview=False
        )

        # Create final container
        container = Container(
            accent_color=style_config["color"],
            components=announcement_components
        )

        # Send announcement to target channel
        sent_message = await bot.rest.create_message(
            channel=int(data["channel_id"]),
            components=[container],
            user_mentions=True,
            role_mentions=True if data["role_id"] else False
        )

        # Create message link
        message_link = f"https://discord.com/channels/{data['guild_id']}/{data['channel_id']}/{sent_message.id}"

        # Log to audit channel (same as say.py)
        log_components = [
            Container(
                accent_color=style_config["color"],
                components=[
                    Text(content=f"## {style_config['emoji']} **Say-Announce Command Used**"),
                    Separator(divider=True),
                    Text(content=(
                        f"**User:** <@{data['creator_id']}>\n"
                        f"**Channel:** <#{data['channel_id']}>\n"
                        f"**Style:** {style_config['name']}\n"
                        f"**Time:** <t:{int(datetime.now(timezone.utc).timestamp())}:F>"
                    )),
                    Separator(divider=True),
                    Text(content=f"**Title:** {data['title']}"),
                    Text(content=f"**Description:**\n{data['description'][:500]}{'...' if len(data['description']) > 500 else ''}"),
                    *(
                        [Text(content=f"**Image:** {data['image_url']}")]
                        if data['image_url']
                        else []
                    ),
                    *(
                        [Text(content=f"**Role Pinged:** <@&{data['role_id']}>")]
                        if data['role_id']
                        else []
                    ),
                    Separator(divider=True),
                    ActionRow(
                        components=[
                            LinkButton(
                                label="Jump to Announcement",
                                url=message_link
                            ),
                            LinkButton(
                                label="Go to Channel",
                                url=f"https://discord.com/channels/{data['guild_id']}/{data['channel_id']}"
                            )
                        ]
                    ),
                    Media(items=[MediaItem(media=style_config["footer"])])
                ]
            )
        ]

        # Send log
        await bot.rest.create_message(
            channel=LOG_CHANNEL_ID,
            components=log_components
        )

        # Confirm to user with Components V2
        success_container = Container(
            accent_color=GREEN_ACCENT,
            components=[
                Text(content="## ✅ Announcement Sent Successfully!"),
                Separator(divider=True),
                Text(content="Your announcement has been posted."),
                ActionRow(
                    components=[
                        LinkButton(
                            label="Jump to Announcement",
                            url=message_link
                        )
                    ]
                ),
                Media(items=[MediaItem(media="assets/Green_Footer.png")])
            ]
        )
        await ctx.respond(components=[success_container], edit=True)

        # Clean up button store
        await mongo.button_store.delete_one({"_id": action_id})

        print(f"[Announce] Sent {style_config['name']} announcement to channel {data['channel_id']}")

    except Exception as e:
        print(f"[Announce] Error sending announcement: {e}")
        error_container = Container(
            accent_color=DARK_MAGENTA_ACCENT,
            components=[
                Text(content="## ❌ Failed to Send Announcement"),
                Separator(divider=True),
                Text(content=f"**Error:** {str(e)[:500]}"),
                Media(items=[MediaItem(media="assets/Red_Footer.png")])
            ]
        )
        await ctx.respond(components=[error_container], edit=True)


@register_action("announce_cancel", no_return=True)
@lightbulb.di.with_di
async def handle_announce_cancel(
    ctx: lightbulb.components.MenuContext,
    action_id: str,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
) -> None:
    """Handle announcement cancellation"""

    # Clean up button store
    await mongo.button_store.delete_one({"_id": action_id})

    # Confirm cancellation with Components V2
    cancel_container = Container(
        accent_color=DARK_MAGENTA_ACCENT,
        components=[
            Text(content="## ❌ Announcement Cancelled"),
            Separator(divider=True),
            Text(content="No message was sent. The announcement has been discarded."),
            Media(items=[MediaItem(media="assets/Red_Footer.png")])
        ]
    )
    await ctx.respond(components=[cancel_container], edit=True)


loader.command(SayAnnounce)
