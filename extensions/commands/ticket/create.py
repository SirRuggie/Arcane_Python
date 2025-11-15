"""Manual ticket creation command for when ClashKing bot fails"""

import re
import hikari
import lightbulb
import coc
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

from extensions.commands.ticket import loader, ticket
from extensions.components import register_action
from utils.mongo import MongoClient
from utils.constants import DARK_MAGENTA_ACCENT, GOLD_ACCENT
from utils.emoji import emojis

# Import Components V2
from hikari.impl import (
    ContainerComponentBuilder as Container,
    TextDisplayComponentBuilder as Text,
    SeparatorComponentBuilder as Separator,
    MediaGalleryComponentBuilder as Media,
    MediaGalleryItemBuilder as MediaItem,
    ModalActionRowBuilder as ModalActionRow,
)

# Recruitment staff role ID
RECRUITMENT_STAFF_ROLE = 999140213953671188

# Special character patterns for manual tickets (same as ClashKing for compatibility)
TICKET_PATTERNS = {
    "FWA": "𝔽𝕎𝔸",
    "CLAN": "ℂ𝕃𝔸ℕ"
}

# Player tag regex pattern
PLAYER_TAG_PATTERN = re.compile(r'^#?[0289PYLQGRJCUV]{3,}$', re.IGNORECASE)

# Recruitment category ID - hardcoded for reliability
RECRUITMENT_CATEGORY_ID = 1020517908230709308


async def generate_ticket_number(mongo: MongoClient) -> str:
    """Generate a unique ticket number"""
    # Get the highest existing ticket number from automation state
    try:
        pipeline = [
            {"$match": {"ticket_info.ticket_number": {"$exists": True, "$ne": None}}},
            {"$addFields": {
                "numeric_ticket": {
                    "$convert": {
                        "input": "$ticket_info.ticket_number",
                        "to": "int",
                        "onError": 0
                    }
                }
            }},
            {"$sort": {"numeric_ticket": -1}},
            {"$limit": 1}
        ]

        result = await mongo.ticket_automation_state.aggregate(pipeline).to_list(length=1)

        if result:
            highest_number = result[0].get("numeric_ticket", 0)
            return str(highest_number + 1)
        else:
            # Start from 1000 if no tickets exist
            return "1000"

    except Exception as e:
        print(f"[ERROR] Failed to generate ticket number: {e}")
        # Fallback to timestamp-based number
        timestamp = int(datetime.now().timestamp())
        return str(timestamp)[-4:]  # Last 4 digits of timestamp


async def find_recruitment_category(bot: hikari.GatewayBot, guild_id: hikari.Snowflake) -> Optional[hikari.Snowflake]:
    """Find the recruitment category by looking for existing ticket channels"""
    try:
        channels = await bot.rest.fetch_guild_channels(guild_id)

        # Look for channels with ticket patterns to find the category
        for channel in channels:
            if hasattr(channel, 'name') and channel.name:
                if any(pattern in channel.name for pattern in TICKET_PATTERNS.values()):
                    if hasattr(channel, 'parent_id') and channel.parent_id:
                        print(f"[DEBUG] Found recruitment category ID: {channel.parent_id}")
                        return channel.parent_id

        # If not found, look for a category named something like "recruitment"
        for channel in channels:
            if (channel.type == hikari.ChannelType.GUILD_CATEGORY and
                hasattr(channel, 'name') and
                'recruit' in channel.name.lower()):
                print(f"[DEBUG] Found recruitment category by name: {channel.id}")
                return channel.id

        print("[WARNING] Could not find recruitment category")
        return None

    except Exception as e:
        print(f"[ERROR] Failed to find recruitment category: {e}")
        return None


@ticket.register()
class CreateTicketCommand(
    lightbulb.SlashCommand,
    name="create",
    description="Manually create a recruitment ticket when ClashKing fails",
):
    user = lightbulb.user(
        "user",
        "Discord user to create the ticket for"
    )

    ticket_type = lightbulb.string(
        "type",
        "Type of ticket to create",
        choices=[
            lightbulb.Choice(name="FWA", value="FWA"),
            lightbulb.Choice(name="CLAN", value="CLAN")
        ]
    )

    @lightbulb.invoke
    @lightbulb.di.with_di
    async def invoke(
        self,
        ctx: lightbulb.Context,
        bot: hikari.GatewayBot = lightbulb.di.INJECTED,
        mongo: MongoClient = lightbulb.di.INJECTED,
    ) -> None:
        # Get the selected user and ticket type
        selected_user = self.user
        ticket_type = self.ticket_type

        print(f"[DEBUG] Manual ticket creation - User: {selected_user.id}, Type: {ticket_type}")

        # Show modal to get player tag
        player_tag_input = ModalActionRow().add_text_input(
            "player_tag",
            "Player Tag",
            placeholder="#PLAYERTAG or PLAYERTAG",
            required=True,
            max_length=15
        )

        await ctx.respond_with_modal(
            title=f"Create {ticket_type} Ticket",
            custom_id=f"manual_ticket_modal:{selected_user.id}:{ticket_type}",
            components=[player_tag_input]
        )


@register_action("manual_ticket_modal", no_return=True, is_modal=True)
@lightbulb.di.with_di
async def handle_manual_ticket_modal(
    ctx: lightbulb.components.ModalContext,
    action_id: str,
    bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    mongo: MongoClient = lightbulb.di.INJECTED,
    coc_client: coc.Client = lightbulb.di.INJECTED,
    **kwargs
):
    """Handle the modal submission for manual ticket creation"""
    # Parse action_id to get user_id and ticket_type
    try:
        user_id, ticket_type = action_id.split(":")
        user_id = int(user_id)
    except ValueError:
        await ctx.respond("❌ Invalid request format", ephemeral=True)
        return

    # Extract player tag from modal
    def get_val(cid: str) -> str:
        for row in ctx.interaction.components:
            for comp in row:
                if comp.custom_id == cid:
                    return comp.value
        return ""

    player_tag = get_val("player_tag").strip()

    # Validate player tag format
    if not player_tag:
        await ctx.respond("❌ Player tag is required", ephemeral=True)
        return

    # Clean and validate player tag
    if not player_tag.startswith('#'):
        player_tag = '#' + player_tag

    if not PLAYER_TAG_PATTERN.match(player_tag):
        await ctx.respond("❌ Invalid player tag format. Please use format: #PLAYERTAG", ephemeral=True)
        return

    # Defer the response (for modal, we need to create a new message)
    await ctx.interaction.create_initial_response(
        hikari.ResponseType.DEFERRED_MESSAGE_CREATE,
        flags=hikari.MessageFlag.EPHEMERAL
    )

    try:
        # Check if an active ticket already exists for this player
        existing_active_ticket = await mongo.new_recruits.find_one({
            "player_tag": player_tag,
            "ticket_open": True
        })

        if existing_active_ticket:
            await ctx.interaction.edit_initial_response(
                components=[
                    Container(
                        accent_color=DARK_MAGENTA_ACCENT,
                        components=[
                            Text(content="## ❌ Active Ticket Already Exists"),
                            Text(content=f"An active ticket already exists for player tag `{player_tag}`\n"
                                        f"Ticket Channel: <#{existing_active_ticket.get('ticket_channel_id')}>"),
                            Media(items=[MediaItem(media="assets/Red_Footer.png")])
                        ]
                    )
                ]
            )
            return

        # Check for any previous closed tickets (for info purposes)
        previous_tickets = await mongo.new_recruits.find({
            "player_tag": player_tag,
            "ticket_open": False
        }).to_list(length=5)  # Limit to 5 most recent

        print(f"[DEBUG] Found {len(previous_tickets)} previous closed tickets for {player_tag}")

        # Get player data from CoC API
        player_data = None
        try:
            player_data = await coc_client.get_player(player_tag)
            print(f"[DEBUG] Found player: {player_data.name} (TH{player_data.town_hall})")
        except coc.NotFound:
            print(f"[WARNING] Player not found in CoC API: {player_tag}")
        except Exception as e:
            print(f"[ERROR] Failed to fetch player data: {e}")

        # Get the target user
        try:
            target_user = await bot.rest.fetch_member(ctx.guild_id, user_id)
        except Exception as e:
            await ctx.interaction.edit_initial_response(
                components=[
                    Container(
                        accent_color=DARK_MAGENTA_ACCENT,
                        components=[
                            Text(content="## ❌ User Not Found"),
                            Text(content=f"Could not find user with ID {user_id}"),
                            Media(items=[MediaItem(media="assets/Red_Footer.png")])
                        ]
                    )
                ]
            )
            return

        # Use hardcoded recruitment category ID
        category_id = RECRUITMENT_CATEGORY_ID

        # Generate ticket number (still needed for tracking)
        ticket_number = await generate_ticket_number(mongo)

        # Create channel name with pattern using town hall level (ClashKing format)
        pattern = TICKET_PATTERNS[ticket_type]
        town_hall = player_data.town_hall if player_data else "unknown"
        # Format: pattern-townhall-username (same as ClashKing)
        channel_name = f"{pattern}-{town_hall}-{target_user.display_name}"
        # Clean channel name (Discord requirements)
        channel_name = re.sub(r'[^a-zA-Z0-9\-_𝔽𝕎𝔸ℂ𝕃𝔸ℕ𝕋𝔼𝕊]', '', channel_name).lower()

        print(f"[DEBUG] Creating channel: {channel_name}")

        # Create the ticket channel
        ticket_channel = await bot.rest.create_guild_text_channel(
            ctx.guild_id,
            channel_name,
            category=category_id,
            permission_overwrites=[
                # Default deny for @everyone
                hikari.PermissionOverwrite(
                    id=ctx.guild_id,  # @everyone role
                    type=hikari.PermissionOverwriteType.ROLE,
                    deny=(
                        hikari.Permissions.VIEW_CHANNEL |
                        hikari.Permissions.SEND_MESSAGES
                    )
                ),
                # Allow target user
                hikari.PermissionOverwrite(
                    id=user_id,
                    type=hikari.PermissionOverwriteType.MEMBER,
                    allow=(
                        hikari.Permissions.VIEW_CHANNEL |
                        hikari.Permissions.SEND_MESSAGES |
                        hikari.Permissions.READ_MESSAGE_HISTORY |
                        hikari.Permissions.ATTACH_FILES |
                        hikari.Permissions.EMBED_LINKS
                    )
                ),
                # Allow recruitment staff
                hikari.PermissionOverwrite(
                    id=RECRUITMENT_STAFF_ROLE,
                    type=hikari.PermissionOverwriteType.ROLE,
                    allow=(
                        hikari.Permissions.VIEW_CHANNEL |
                        hikari.Permissions.SEND_MESSAGES |
                        hikari.Permissions.READ_MESSAGE_HISTORY |
                        hikari.Permissions.ATTACH_FILES |
                        hikari.Permissions.EMBED_LINKS |
                        hikari.Permissions.MANAGE_MESSAGES
                    )
                )
            ]
        )

        print(f"[DEBUG] Created ticket channel: {ticket_channel.id}")

        # Create private thread for staff discussions
        try:
            private_thread = await bot.rest.create_thread(
                ticket_channel.id,
                hikari.ChannelType.GUILD_PRIVATE_THREAD,
                "Private",
                auto_archive_duration=10080  # 7 days
            )
            thread_id = str(private_thread.id)
            print(f"[DEBUG] Created private thread: {thread_id}")

            # Delete the "started a thread" system message
            try:
                await asyncio.sleep(0.5)  # Small delay to ensure message exists
                messages = await bot.rest.fetch_messages(ticket_channel.id).limit(5)
                for message in messages:
                    if message.type == hikari.MessageType.THREAD_CREATED:
                        await bot.rest.delete_message(ticket_channel.id, message.id)
                        break
            except Exception as e:
                print(f"[DEBUG] Could not delete thread creation message: {e}")

            # Send notification in private thread pinging recruitment staff
            try:
                notification_components = [
                    Container(
                        accent_color=GOLD_ACCENT,
                        components=[
                            Text(content="## 🎫 New Ticket Created"),
                            Separator(divider=True),
                            Text(content=(
                                f"<@&{RECRUITMENT_STAFF_ROLE}>\n\n"
                                f"**Ticket Type:** {ticket_type}\n"
                                f"**Recruit:** {target_user.mention}\n"
                                f"**Player Tag:** `{player_tag}`\n"
                                f"**Player Name:** {player_data.name if player_data else 'Unknown'}\n"
                                f"**Town Hall:** {player_data.town_hall if player_data else 'Unknown'}\n\n"
                                f"Use this thread for staff-only discussions about this recruitment."
                            )),
                            Text(content=f"-# Created by {ctx.user.mention}"),
                            Media(items=[MediaItem(media="assets/Gold_Footer.png")])
                        ]
                    )
                ]

                await bot.rest.create_message(
                    channel=private_thread.id,
                    components=notification_components,
                    role_mentions=True
                )
                print(f"[DEBUG] Sent recruitment staff notification in private thread")
            except Exception as e:
                print(f"[ERROR] Failed to send private thread notification: {e}")

        except Exception as e:
            print(f"[ERROR] Failed to create private thread: {e}")
            thread_id = None

        # Create MongoDB documents
        now = datetime.now(timezone.utc)

        # Create new_recruits document
        recruit_doc = {
            "player_tag": player_tag,
            "player_name": player_data.name if player_data else None,
            "player_th_level": player_data.town_hall if player_data else None,
            "discord_user_id": str(user_id),
            "ticket_channel_id": str(ticket_channel.id),
            "ticket_thread_id": thread_id,
            "created_at": now,
            "expires_at": now + timedelta(days=12),
            "recruitment_history": [],
            "current_clan": None,
            "total_clans_joined": 0,
            "is_expired": False,
            "activeBid": False,
            "ticket_open": True,
            "manual_creation": True,  # Flag to indicate manual creation
            "created_by": str(ctx.user.id)  # Who created the ticket manually
        }

        await mongo.new_recruits.insert_one(recruit_doc)
        print(f"[DEBUG] Created new_recruits document")

        # Create ticket_automation_state document
        automation_doc = {
            "_id": str(ticket_channel.id),
            "ticket_info": {
                "channel_id": str(ticket_channel.id),
                "thread_id": thread_id or "",
                "user_id": str(user_id),
                "user_tag": player_tag,
                "ticket_type": ticket_type,
                "ticket_number": ticket_number,
                "created_at": now,
                "last_updated": now,
                "manual_creation": True,
                "created_by": str(ctx.user.id)
            },
            "player_info": {
                "player_tag": player_tag,
                "player_name": player_data.name if player_data else None,
                "town_hall": player_data.town_hall if player_data else None,
                "clan_tag": player_data.clan.tag if player_data and player_data.clan else None,
                "clan_name": player_data.clan.name if player_data and player_data.clan else None
            },
            "automation_state": {
                "current_step": "awaiting_screenshot",
                "current_step_index": 1,
                "total_steps": 5,
                "status": "active",
                "completed_steps": [
                    {
                        "step_name": "ticket_created",
                        "completed_at": now,
                        "data": {"manual_creation": True, "player_tag": player_tag}
                    }
                ]
            },
            "step_data": {
                "screenshot": {
                    "uploaded": False,
                    "uploaded_at": None,
                    "reminder_sent": False,
                    "reminder_count": 0,
                    "last_reminder_at": None
                },
                "clan_selection": {
                    "selected_clan_type": None,
                    "selected_at": None
                },
                "questionnaire": {
                    "responses": {},
                    "completed_at": None
                },
                "final_placement": {
                    "assigned_clan": None,
                    "assigned_at": None,
                    "approved_by": None
                }
            },
            "messages": {
                "initial_prompt": str(ticket_channel.id)
            },
            "interaction_history": [
                {
                    "timestamp": now,
                    "action": "manual_ticket_created",
                    "details": f"Manual ticket created by {ctx.user.display_name} for user {target_user.display_name}",
                    "created_by": str(ctx.user.id),
                    "player_tag": player_tag
                }
            ]
        }

        await mongo.ticket_automation_state.insert_one(automation_doc)
        print(f"[DEBUG] Created ticket_automation_state document")

        print(f"[DEBUG] Ticket channel created - automation will handle initial message")

        # Send success response
        success_components = [
            Container(
                accent_color=0x00FF00,  # Green
                components=[
                    Text(content="## ✅ Ticket Created Successfully!"),
                    Separator(divider=True),
                    Text(content=(
                        f"**Ticket Type:** {ticket_type}\n"
                        f"**User:** {target_user.mention}\n"
                        f"**Player Tag:** `{player_tag}`\n"
                        f"**Player Name:** {player_data.name if player_data else 'Unknown'}\n"
                        f"**Town Hall:** {player_data.town_hall if player_data else 'Unknown'}\n"
                        f"**Ticket Number:** #{ticket_number}\n"
                        f"**Channel:** {ticket_channel.mention}"
                    )),
                    Media(items=[MediaItem(media="assets/Red_Footer.png")])
                ]
            )
        ]

        await ctx.interaction.edit_initial_response(components=success_components)

        print(f"[SUCCESS] Manual ticket created successfully - Channel: {ticket_channel.id}, User: {user_id}, Type: {ticket_type}")

    except Exception as e:
        print(f"[ERROR] Failed to create manual ticket: {e}")

        error_components = [
            Container(
                accent_color=DARK_MAGENTA_ACCENT,
                components=[
                    Text(content="## ❌ Ticket Creation Failed"),
                    Separator(divider=True),
                    Text(content=f"An error occurred while creating the ticket:\n```{str(e)[:500]}```"),
                    Text(content="Please contact an administrator if this issue persists."),
                    Media(items=[MediaItem(media="assets/Red_Footer.png")])
                ]
            )
        ]

        try:
            await ctx.interaction.edit_initial_response(components=error_components)
        except:
            # If edit fails, try to respond
            await ctx.respond(components=error_components, ephemeral=True)