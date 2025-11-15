# extensions/events/message/ticket_account_collection.py
"""
Ticket account collection automation system.

Handles the account collection step after screenshot upload:
- Prompts user for player tag via modal
- Validates player data with CoC API
- Stores player information
- Asks about additional accounts
- Transitions to questionnaire when complete
"""

import asyncio
import coc
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import hikari
import lightbulb

from hikari.impl import (
    ContainerComponentBuilder as Container,
    InteractiveButtonBuilder as Button,
    TextDisplayComponentBuilder as Text,
    SeparatorComponentBuilder as Separator,
    MediaGalleryComponentBuilder as Media,
    MediaGalleryItemBuilder as MediaItem,
    MessageActionRowBuilder as ActionRow,
    ModalActionRowBuilder as ModalActionRow,
    TextInputBuilder as TextInput,
)

from utils.constants import BLUE_ACCENT, GREEN_ACCENT, DARK_MAGENTA_ACCENT
from utils.mongo import MongoClient
from utils.emoji import emojis
from extensions.components import register_action

# Import FWA chocolate components
try:
    from extensions.events.message.ticket_automation.fwa.utils.chocolate_components import (
        send_chocolate_link
    )

    HAS_FWA_CHOCOLATE = True
except ImportError:
    HAS_FWA_CHOCOLATE = False
    print("[WARNING] FWA chocolate components not found, chocolate links will be disabled")

# Global instances
mongo_client: Optional[MongoClient] = None
bot_instance: Optional[hikari.GatewayBot] = None
coc_client: Optional[coc.Client] = None
loader = lightbulb.Loader()


async def send_account_collection_prompt(channel_id: int, user_id: int, ticket_info: Dict[str, Any]) -> bool:
    """Send the initial account collection prompt"""

    if not bot_instance or not mongo_client:
        print(f"[Account Collection] Bot or mongo instance not initialized")
        return False

    # Get ticket state to check for existing accounts
    ticket_state = await mongo_client.ticket_automation_state.find_one({"_id": str(channel_id)})
    if not ticket_state:
        print(f"[Account Collection] No ticket state found for channel {channel_id}")
        return False

    # Count accounts
    additional_accounts = ticket_state.get("step_data", {}).get("account_collection", {}).get("additional_accounts", [])
    has_primary = ticket_state.get("ticket_info", {}).get("user_tag") is not None
    account_count = len(additional_accounts) + (1 if has_primary else 0)

    # Create unique action IDs
    action_id_base = f"{channel_id}_{user_id}"

    # Check if this is the first time (no accounts yet)
    if account_count == 0:
        # First time - open modal directly
        components = [
            Container(
                accent_color=BLUE_ACCENT,
                components=[
                    Text(content=f"<@{user_id}>"),
                    Separator(divider=True),
                    Text(content="## 🔍 **Account Collection**"),
                    Separator(divider=True),
                    Text(content=(
                        "Let's gather information about your Clash of Clans account.\n\n"
                        "Click the button below to provide your player tag."
                    )),
                    ActionRow(
                        components=[
                            Button(
                                style=hikari.ButtonStyle.PRIMARY,
                                custom_id=f"provide_player_tag:{action_id_base}",
                                label="Provide Player Tag",
                                emoji="📝"
                            )
                        ]
                    ),
                    Media(items=[MediaItem(media="assets/Blue_Footer.png")])
                ]
            )
        ]
    else:
        # Already have accounts - ask if they want to add more
        components = [
            Container(
                accent_color=BLUE_ACCENT,
                components=[
                    Text(content=f"<@{user_id}>"),
                    Text(content="## 😀 **Do You Have Another Account?**"),
                    Separator(divider=True),
                    Text(content=(
                        f"If you'd like to apply with another account, let us know!\n\n"
                        f"**Current accounts linked:** {account_count}\n\n"
                        "• Click **Yes** if you want to provide the Player Tag of your other account.\n"
                        "• Click **No** to move to the next step.\n\n"
                        "*Multiple accounts? No problem!*"
                    )),
                    ActionRow(
                        components=[
                            Button(
                                style=hikari.ButtonStyle.SUCCESS,
                                custom_id=f"add_account_yes:{action_id_base}",
                                label="Yes, I have another account",
                                emoji="✅"
                            ),
                            Button(
                                style=hikari.ButtonStyle.PRIMARY,
                                custom_id=f"add_account_no:{action_id_base}",
                                label="No, move on",
                                emoji="➡️"
                            )
                        ]
                    ),
                    Media(items=[MediaItem(media="assets/Blue_Footer.png")])
                ]
            )
        ]

    try:
        message = await bot_instance.rest.create_message(
            channel=channel_id,
            components=components,
            user_mentions=True
        )

        # Store the message ID
        await mongo_client.ticket_automation_state.update_one(
            {"_id": str(channel_id)},
            {"$set": {"messages.account_collection": str(message.id)}}
        )

        print(f"[Account Collection] Sent prompt message in channel {channel_id}")
        return True

    except Exception as e:
        print(f"[Account Collection] Error sending prompt: {e}")
        return False


# Handler for initial "Provide Player Tag" button
@register_action("provide_player_tag", opens_modal=True, no_return=True)
@lightbulb.di.with_di
async def handle_provide_player_tag(
        ctx,
        action_id: str,
        **kwargs
):
    """Handle the initial player tag button"""

    channel_id, user_id = action_id.split("_")

    # Verify it's the correct user
    if str(ctx.user.id) != user_id:
        await ctx.respond(
            content="❌ This button is only for the ticket creator!",
            ephemeral=True
        )
        return

    # Create modal for player tag input
    player_tag_input = ModalActionRow().add_text_input(
        "player_tag",  # custom_id
        "Player Tag",  # label
        placeholder="Enter your player tag (e.g., #ABC123)",
        style=hikari.TextInputStyle.SHORT,
        required=True,
        min_length=3,
        max_length=20
    )

    await ctx.respond_with_modal(
        title="Provide Your Player Tag",
        custom_id=f"player_tag_modal:{action_id}",
        components=[player_tag_input]
    )


# Handler for "Yes, I have another account" button
@register_action("add_account_yes", opens_modal=True, no_return=True)
@lightbulb.di.with_di
async def handle_add_account_yes(
        ctx,
        action_id: str,
        **kwargs
):
    """Handle when user wants to add another account"""

    channel_id, user_id = action_id.split("_")

    # Verify it's the correct user
    if str(ctx.user.id) != user_id:
        await ctx.respond(
            content="❌ This button is only for the ticket creator!",
            ephemeral=True
        )
        return

    # Create modal for player tag input
    player_tag_input = ModalActionRow().add_text_input(
        "player_tag",  # custom_id
        "Player Tag",  # label
        placeholder="Enter your player tag (e.g., #ABC123)",
        style=hikari.TextInputStyle.SHORT,
        required=True,
        min_length=3,
        max_length=20
    )

    await ctx.respond_with_modal(
        title="Add Another Account",
        custom_id=f"add_account_modal:{action_id}",
        components=[player_tag_input]
    )


# Handler for player tag modal submission
@register_action("player_tag_modal", is_modal=True, no_return=True)
@register_action("add_account_modal", is_modal=True, no_return=True)
@lightbulb.di.with_di
async def handle_player_tag_modal_submit(
        ctx,
        action_id: str,
        mongo: MongoClient = lightbulb.di.INJECTED,
        coc_client: coc.Client = lightbulb.di.INJECTED,
        **kwargs
):
    """Handle the modal submission with player tag"""

    channel_id, user_id = action_id.split("_")

    # Get the player tag from modal
    def get_modal_value(custom_id: str) -> str:
        for row in ctx.interaction.components:
            for component in row:
                if hasattr(component, 'custom_id') and component.custom_id == custom_id:
                    return component.value
        return ""

    player_tag = get_modal_value("player_tag").strip()

    # Normalize the tag
    if not player_tag.startswith("#"):
        player_tag = f"#{player_tag}"

    # Defer the response
    await ctx.interaction.create_initial_response(
        hikari.ResponseType.DEFERRED_MESSAGE_UPDATE
    )

    try:
        # Fetch player data
        player = await coc_client.get_player(player_tag)

        # Get ticket state
        ticket_state = await mongo.ticket_automation_state.find_one({"_id": str(channel_id)})
        if not ticket_state:
            raise Exception("Ticket state not found")

        # Check if this is the primary account
        is_primary = not ticket_state.get("ticket_info", {}).get("user_tag")

        if is_primary:
            # Store as primary account
            await mongo.ticket_automation_state.update_one(
                {"_id": str(channel_id)},
                {
                    "$set": {
                        "ticket_info.user_tag": player.tag,
                        "ticket_info.player_name": player.name,
                        "player_info.player_tag": player.tag,
                        "player_info.player_name": player.name,
                        "player_info.town_hall": player.town_hall,
                        "player_info.clan_tag": player.clan.tag if player.clan else None,
                        "player_info.clan_name": player.clan.name if player.clan else None,
                    }
                }
            )
        else:
            # Store as additional account
            await mongo.ticket_automation_state.update_one(
                {"_id": str(channel_id)},
                {
                    "$push": {
                        "step_data.account_collection.additional_accounts": {
                            "tag": player.tag,
                            "name": player.name,
                            "town_hall": player.town_hall,
                            "collected_at": datetime.now(timezone.utc)
                        }
                    }
                }
            )

            # Create new recruit entry for additional account
            new_recruit_data = {
                "player_tag": player.tag,
                "player_name": player.name,
                "player_th_level": player.town_hall,
                "discord_user_id": str(user_id),
                "ticket_channel_id": str(channel_id),
                "ticket_thread_id": str(ticket_state["ticket_info"]["thread_id"]),
                "ticket_type": ticket_state["ticket_info"]["ticket_type"],
                "ticket_number": ticket_state["ticket_info"]["ticket_number"],
                "timestamp": datetime.now(timezone.utc),
                "is_additional_account": True,
                "primary_account_tag": ticket_state["ticket_info"].get("user_tag", None),

                "activeBid": False,
                "ticket_open": True
            }

            await mongo.new_recruits.insert_one(new_recruit_data)

            # Check if this additional account is in a family clan
            try:
                family_clans = await mongo.clans.find().to_list(length=None)
                if family_clans:
                    family_clan_lookup = {clan["tag"]: clan for clan in family_clans}

                    # Check if player is in a family clan
                    if player.clan and player.clan.tag in family_clan_lookup:
                        clan_data = family_clan_lookup[player.clan.tag]
                        thread_id = ticket_state["ticket_info"]["thread_id"]

                        # Send early detection alert to thread
                        alert_content = (
                            f"⚠️ **EARLY DETECTION:** Additional account is already in a family clan:\n\n"
                            f"• **{player.name}** (`{player.tag}`) is in **{clan_data.get('name', player.clan.name)}**\n"
                        )

                        if clan_data.get('leader_id') and clan_data.get('leader_role_id'):
                            alert_content += f"  → Contact: <@{clan_data['leader_id']}> and <@&{clan_data['leader_role_id']}>\n\n"

                        alert_content += (
                            "This candidate may be trying to transfer between family clans.\n"
                            "Please verify with their current leadership before proceeding."
                        )

                        await bot_instance.rest.create_message(
                            channel=int(thread_id),
                            content=alert_content,
                            role_mentions=True
                        )

                        print(f"[Account Collection] Additional account {player.name} found in family clan {clan_data.get('name')}")
            except Exception as e:
                print(f"[Account Collection] Error checking additional account family clan: {e}")

        # For FWA tickets, send chocolate link
        if HAS_FWA_CHOCOLATE:
            channel = bot_instance.cache.get_guild_channel(int(channel_id))
            if channel and any(pattern in channel.name for pattern in ["𝔽𝕎𝔸", "𝕋-𝔽𝕎𝔸"]):
                thread_id = ticket_state["ticket_info"]["thread_id"]
                await send_chocolate_link(
                    bot=bot_instance,
                    channel_id=int(thread_id),
                    player_tag=player.tag,
                    player_name=player.name
                )
                print(f"[Account Collection] Sent FWA chocolate link for {player.name}")

        # Show success and account info
        account_components = [
            Container(
                accent_color=GREEN_ACCENT,
                components=[
                    Text(content=f"## ✅ **{'Primary' if is_primary else 'Additional'} Account Verified**"),
                    Separator(divider=True),
                    Text(content=(
                        f"**Player Name:** {player.name}\n"
                        f"**Player Tag:** {player.tag}\n"
                        f"**Town Hall Level:** {player.town_hall}\n"
                        f"**Current Clan:** {getattr(player.clan, 'name', 'No Clan') if player.clan else 'No Clan'}"
                    )),
                    Separator(divider=True),
                    Text(content="*Account information saved successfully!*"),
                    Media(items=[MediaItem(media="assets/Green_Footer.png")])
                ]
            )
        ]

        await ctx.interaction.edit_initial_response(components=account_components)

        # Wait then ask if they have more accounts
        await asyncio.sleep(3)
        await send_account_collection_prompt(int(channel_id), int(user_id), ticket_state["ticket_info"])

    except coc.NotFound:
        # Invalid player tag
        error_components = [
            Container(
                accent_color=DARK_MAGENTA_ACCENT,
                components=[
                    Text(content="## ❌ **Invalid Player Tag**"),
                    Text(content=f"Could not find a player with tag: **{player_tag}**"),
                    Text(content="Please check the tag and try again."),
                    Media(items=[MediaItem(media="assets/Red_Footer.png")])
                ]
            )
        ]

        await ctx.interaction.edit_initial_response(components=error_components)

        # Resend the prompt after delay
        await asyncio.sleep(3)
        ticket_state = await mongo.ticket_automation_state.find_one({"_id": str(channel_id)})
        await send_account_collection_prompt(int(channel_id), int(user_id), ticket_state["ticket_info"])

    except Exception as e:
        print(f"[Account Collection] Error processing player tag: {e}")
        # General error
        error_components = [
            Container(
                accent_color=DARK_MAGENTA_ACCENT,
                components=[
                    Text(content="## ❌ **Error**"),
                    Text(content="An error occurred processing your request."),
                    Text(content="Please try again."),
                    Media(items=[MediaItem(media="assets/Red_Footer.png")])
                ]
            )
        ]

        await ctx.interaction.edit_initial_response(components=error_components)


# Handler for "No, move on" button
@register_action("add_account_no", no_return=True)
@lightbulb.di.with_di
async def handle_add_account_no(
        ctx,
        action_id: str,
        mongo: MongoClient = lightbulb.di.INJECTED,
        **kwargs
):
    """Handle when user doesn't want to add another account"""

    channel_id, user_id = action_id.split("_")

    # Verify it's the correct user
    if str(ctx.user.id) != user_id:
        await ctx.respond(
            content="❌ This button is only for the ticket creator!",
            ephemeral=True
        )
        return

    print(f"[Account Collection] User clicked 'No, move on' - channel: {channel_id}")

    # Update the message to show completion
    completion_components = [
        Container(
            accent_color=GREEN_ACCENT,
            components=[
                Text(content="## ✅ **Account Collection Complete**"),
                Text(content="Moving to the interview process..."),
                Media(items=[MediaItem(media="assets/Green_Footer.png")])
            ]
        )
    ]

    await ctx.interaction.edit_initial_response(components=completion_components)

    # Get ticket state
    ticket_state = await mongo.ticket_automation_state.find_one({"_id": str(channel_id)})
    if not ticket_state:
        return

    # Update ticket state to next step
    await mongo.ticket_automation_state.update_one(
        {"_id": str(channel_id)},
        {
            "$set": {
                "automation_state.current_step": "questionnaire",
                "step_data.account_collection.completed": True
            },
            "$addToSet": {
                "automation_state.completed_steps": "account_collection"
            },
            "$push": {
                "interaction_history": {
                    "timestamp": datetime.now(timezone.utc),
                    "action": "account_collection_completed",
                    "details": {}
                }
            }
        }
    )

    print(f"[Account Collection] Updated MongoDB state to questionnaire")

    # Wait a moment for smooth transition
    await asyncio.sleep(2)

    try:
        # Check if this is FWA ticket and handle accordingly
        channel = bot_instance.cache.get_guild_channel(int(channel_id))
        if channel and any(pattern in channel.name for pattern in ["𝔽𝕎𝔸", "𝕋-𝔽𝕎𝔸"]):
            # For FWA tickets, trigger FWA flow
            from extensions.events.message.ticket_automation.fwa.core import FWAFlow, FWAStep
            thread_id = ticket_state["ticket_info"]["thread_id"]
            await FWAFlow.proceed_to_next_step(
                int(channel_id),
                int(thread_id),
                int(user_id),
                FWAStep.INTERVIEW_SELECTION
            )
            print(f"[Account Collection] Triggered FWA interview selection")
        else:
            # Regular flow - trigger questionnaire
            from extensions.events.message.ticket_automation import trigger_questionnaire
            print(f"[Account Collection] Triggering questionnaire for channel {channel_id}")
            await trigger_questionnaire(int(channel_id), int(user_id))
            print(f"[Account Collection] Successfully triggered questionnaire")
    except Exception as e:
        print(f"[Account Collection] ERROR triggering next step: {e}")
        import traceback
        traceback.print_exc()


async def trigger_account_collection(channel_id: int, user_id: int, ticket_info: Dict[str, Any]):
    """Trigger the account collection step for a ticket"""

    print(f"[Account Collection] Triggering for channel {channel_id}, user {user_id}")

    # Get mongo client from bot_data if needed
    global mongo_client
    if not mongo_client:
        from utils import bot_data
        mongo_client = bot_data.data.get("mongo")

    if not mongo_client:
        print(f"[Account Collection] ERROR: MongoDB client not available!")
        return

    try:
        # Update ticket state
        await mongo_client.ticket_automation_state.update_one(
            {"_id": str(channel_id)},
            {
                "$set": {
                    "automation_state.current_step": "account_collection",
                    "step_data.account_collection": {
                        "started": True,
                        "completed": False,
                        "timestamp": datetime.now(timezone.utc)
                    }
                }
            }
        )

        # Send the account collection prompt
        result = await send_account_collection_prompt(channel_id, user_id, ticket_info)
        if result:
            print(f"[Account Collection] Successfully triggered for channel {channel_id}")
        else:
            print(f"[Account Collection] Failed to send prompt for channel {channel_id}")

    except Exception as e:
        print(f"[Account Collection] ERROR in trigger: {e}")
        import traceback
        traceback.print_exc()


# Initialize global references when extension loads
@loader.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent):
    global mongo_client, bot_instance, coc_client

    from utils import bot_data
    mongo_client = bot_data.data.get("mongo")
    bot_instance = bot_data.data.get("bot")
    coc_client = bot_data.data.get("coc_client")

    print("[Account Collection] System initialized")