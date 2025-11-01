"""
Recruit bidding system implementation
Allows bidding on new recruits with time-limited auctions
"""

import asyncio
import random
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List
import uuid
from bson import ObjectId

import hikari
import lightbulb
from lightbulb.components import MenuContext, ModalContext

from hikari.impl import (
    MessageActionRowBuilder as ActionRow,
    TextSelectMenuBuilder as TextSelectMenu,
    SelectOptionBuilder as SelectOption,
    ContainerComponentBuilder as Container,
    SectionComponentBuilder as Section,
    InteractiveButtonBuilder as Button,
    TextDisplayComponentBuilder as Text,
    SeparatorComponentBuilder as Separator,
    MediaGalleryComponentBuilder as Media,
    MediaGalleryItemBuilder as MediaItem,
    ModalActionRowBuilder as ModalActionRow,
)

from extensions.components import register_action
from extensions.commands.recruit import recruit
from utils.mongo import MongoClient
from utils.classes import Clan
from utils.emoji import emojis
from utils.constants import RED_ACCENT, GREEN_ACCENT, BLUE_ACCENT, GOLD_ACCENT

# Helper function for safe placeholder_points adjustments
async def safe_adjust_placeholder_points(mongo: MongoClient, clan_tag: str, amount: float, operation: str = "inc"):
    """Safely adjust placeholder_points to prevent negative values
    
    Args:
        mongo: MongoDB client
        clan_tag: The clan tag to adjust
        amount: The amount to adjust (positive for increase, negative for decrease)
        operation: "inc" for increment, "set" for setting value
    
    Returns:
        bool: True if successful, False if would result in negative
    """
    clan = await mongo.clans.find_one({"tag": clan_tag})
    if not clan:
        print(f"[ERROR] Clan {clan_tag} not found for placeholder_points adjustment")
        return False
    
    current_placeholder = clan.get("placeholder_points", 0)
    
    if operation == "inc":
        new_value = current_placeholder + amount
    else:  # set
        new_value = amount
    
    # Prevent negative values
    if new_value < 0:
        print(f"[WARNING] Preventing negative placeholder_points for {clan_tag}: current={current_placeholder}, adjustment={amount}, would be={new_value}")
        # Set to 0 instead
        await mongo.clans.update_one(
            {"tag": clan_tag},
            {"$set": {"placeholder_points": 0}}
        )
        return False
    
    # Safe to proceed
    if operation == "inc":
        await mongo.clans.update_one(
            {"tag": clan_tag},
            {"$inc": {"placeholder_points": amount}}
        )
    else:
        await mongo.clans.update_one(
            {"tag": clan_tag},
            {"$set": {"placeholder_points": new_value}}
        )
    
    return True

# Constants
BIDDING_DURATION = 15  # minutes
LOG_CHANNEL_ID = 1381395856317747302  # Channel for bid logs

# Store active bidding sessions with their end times
active_bidding_sessions: Dict[str, datetime] = {}

# Store bidding tasks for cancellation
bidding_tasks: Dict[str, asyncio.Task] = {}


def get_th_emoji(th_level: int) -> Optional[object]:
    """Get the TH emoji for a given level"""
    emoji_attr = f"TH{th_level}"
    if hasattr(emojis, emoji_attr):
        return getattr(emojis, emoji_attr)
    return None


@recruit.register()
class Bidding(
    lightbulb.SlashCommand,
    name="bidding",
    description="Start a bidding process for available recruits"
):
    discord_user = lightbulb.user(
        "discord_user",
        "Select the Discord user whose accounts you want to bid on"
    )

    @lightbulb.invoke
    @lightbulb.di.with_di
    async def invoke(
            self,
            ctx: lightbulb.Context,
            mongo: MongoClient = lightbulb.di.INJECTED,
            bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    ) -> None:
        await ctx.defer(ephemeral=True)

        # Get recruits where activeBid is not true and ticket is still open
        recruits_cursor = mongo.new_recruits.find({
            "discord_user_id": str(self.discord_user.id),
            "activeBid": {"$ne": True},
            "$or": [
                {"ticket_open": True},
                {"ticket_open": {"$exists": False}}  # For backward compatibility
            ]
        })

        # Filter out already recruited players (have finalized bids)
        available_recruits = []
        for recruit in await recruits_cursor.to_list(length=None):
            finalized_bid = await mongo.clan_bidding.find_one({
                "player_tag": recruit["player_tag"],
                "is_finalized": True
            })
            if not finalized_bid:
                available_recruits.append(recruit)

        if not available_recruits:
            await ctx.respond(
                "No available accounts found for this Discord user. "
                "Accounts may already have active bidding or have been recruited.",
                ephemeral=True
            )
            return

        # Create dropdown options
        options = []
        for recruit in available_recruits[:25]:  # Discord limit is 25 options
            th_emoji = get_th_emoji(recruit.get("player_th_level", 0))

            option_kwargs = {
                "label": recruit.get("player_name", "Unknown"),
                "description": recruit.get("player_tag", "No tag"),
                "value": str(recruit["_id"])  # Convert ObjectId to string
            }

            # Only add emoji if it has partial_emoji attribute
            if th_emoji and hasattr(th_emoji, 'partial_emoji'):
                option_kwargs["emoji"] = th_emoji.partial_emoji

            option = SelectOption(**option_kwargs)
            options.append(option)

        # Store data for the action handler
        action_id = str(uuid.uuid4())

        await mongo.button_store.insert_one({
            "_id": action_id,
            "invoker_id": ctx.user.id,
            "channel_id": ctx.channel_id,
            "thread_id": ctx.channel_id  # The bidding will happen in the same channel/thread
        })

        # Create the selection menu
        components = [
            Container(
                accent_color=BLUE_ACCENT,
                components=[
                    Text(content="## Select a Recruit for Bidding"),
                    Text(content="Choose an account to start the bidding process:"),

                    ActionRow(
                        components=[
                            TextSelectMenu(
                                custom_id=f"select_recruit_bidding:{action_id}",
                                placeholder="Select a recruit...",
                                options=options
                            )
                        ]
                    ),

                    Media(items=[MediaItem(media="assets/Blue_Footer.png")])
                ]
            )
        ]

        await ctx.respond(components=components, ephemeral=True)


@recruit.register()
class FixPlaceholderPoints(
    lightbulb.SlashCommand,
    name="fix-placeholder-points",
    description="Fix negative placeholder points for all clans"
):
    @lightbulb.invoke
    @lightbulb.di.with_di
    async def invoke(
            self,
            ctx: lightbulb.Context,
            mongo: MongoClient = lightbulb.di.INJECTED,
    ) -> None:
        await ctx.defer(ephemeral=True)
        
        # Find all clans with negative placeholder_points
        negative_clans = await mongo.clans.find({
            "placeholder_points": {"$lt": 0}
        }).to_list(length=None)
        
        if not negative_clans:
            await ctx.respond("✅ No clans found with negative placeholder points!", ephemeral=True)
            return
        
        # Fix each clan
        fixed_clans = []
        for clan in negative_clans:
            fixed_clans.append({
                "name": clan.get("name", "Unknown"),
                "tag": clan.get("tag"),
                "old_value": clan.get("placeholder_points", 0)
            })
            
            # Reset to 0
            await mongo.clans.update_one(
                {"tag": clan["tag"]},
                {"$set": {"placeholder_points": 0}}
            )
        
        # Build response
        response_text = "## 🔧 Fixed Negative Placeholder Points\n\n"
        for clan_info in fixed_clans:
            response_text += f"**{clan_info['name']}** ({clan_info['tag']}): {clan_info['old_value']} → 0\n"
        
        response_text += f"\n✅ Fixed {len(fixed_clans)} clan(s)"
        
        components = [
            Container(
                accent_color=GREEN_ACCENT,
                components=[
                    Text(content=response_text),
                    Media(items=[MediaItem(media="assets/Green_Footer.png")])
                ]
            )
        ]
        
        await ctx.respond(components=components, ephemeral=True)

@register_action("select_recruit_bidding", no_return=True)
@lightbulb.di.with_di
async def handle_recruit_selection(
        ctx: lightbulb.components.MenuContext,
        action_id: str,
        mongo: MongoClient = lightbulb.di.INJECTED,
        bot: hikari.GatewayBot = lightbulb.di.INJECTED,
        **kwargs
):
    """Handle recruit selection and start bidding"""
    recruit_id = ctx.interaction.values[0]

    # Get button store data
    store_data = await mongo.button_store.find_one({"_id": action_id})
    if not store_data:
        await ctx.respond("Session expired. Please try again.", ephemeral=True)
        return

    # Check if bidding already active (race condition protection)
    recruit = await mongo.new_recruits.find_one({"_id": ObjectId(recruit_id)})
    if not recruit:
        error_components = [
            Container(
                accent_color=RED_ACCENT,
                components=[
                    Text(content="❌ Recruit not found."),
                    Media(items=[MediaItem(media="assets/Red_Footer.png")])
                ]
            )
        ]
        await ctx.interaction.edit_initial_response(components=error_components)
        return

    # Check for ticket_thread_id
    if not recruit.get("ticket_thread_id"):
        error_components = [
            Container(
                accent_color=RED_ACCENT,
                components=[
                    Text(content="❌ No thread found for this recruit."),
                    Media(items=[MediaItem(media="assets/Red_Footer.png")])
                ]
            )
        ]
        await ctx.interaction.edit_initial_response(components=error_components)
        return

    # Use the recruit's clan thread ID
    ticket_thread_id = recruit["ticket_thread_id"]

    if recruit.get("activeBid", False):
        error_components = [
            Container(
                accent_color=RED_ACCENT,
                components=[
                    Text(content="❌ Bidding is already active for this recruit."),
                    Media(items=[MediaItem(media="assets/Red_Footer.png")])
                ]
            )
        ]
        await ctx.interaction.edit_initial_response(components=error_components)
        return

    # Check if there's an existing unfinalized bid
    existing_bid_doc = await mongo.clan_bidding.find_one({
        "player_tag": recruit["player_tag"],
        "is_finalized": False
    })

    if existing_bid_doc:
        # Clean up any empty/invalid bids
        valid_bids = [b for b in existing_bid_doc.get("bids", []) if b.get("clan_tag")]
        if valid_bids:
            error_components = [
                Container(
                    accent_color=RED_ACCENT,
                    components=[
                        Text(
                            content="❌ There's already an active bidding session for this recruit. Please wait for it to complete."),
                        Media(items=[MediaItem(media="assets/Red_Footer.png")])
                    ]
                )
            ]
            await ctx.interaction.edit_initial_response(components=error_components)
            return
        else:
            # Clean up the invalid document
            await mongo.clan_bidding.delete_one({"player_tag": recruit["player_tag"]})

    # Atomically set activeBid to true
    result = await mongo.new_recruits.find_one_and_update(
        {
            "_id": ObjectId(recruit_id),
            "activeBid": {"$ne": True}  # Matches false, null, or missing
        },
        {"$set": {"activeBid": True}},
        return_document=True
    )

    if not result:
        error_components = [
            Container(
                accent_color=RED_ACCENT,
                components=[
                    Text(content="❌ Bidding is already active for this recruit."),
                    Media(items=[MediaItem(media="assets/Red_Footer.png")])
                ]
            )
        ]
        await ctx.interaction.edit_initial_response(components=error_components)
        return

    # Create bidding session entry in button_store
    bid_end_time = datetime.now(timezone.utc) + timedelta(minutes=BIDDING_DURATION)

    bidding_session_id = f"bidding_{recruit_id}_{str(uuid.uuid4())}"
    bidding_session_data = {
        "_id": bidding_session_id,
        "type": "bidding_session",
        "channelId": recruit["ticket_channel_id"],
        "threadId": recruit["ticket_thread_id"],
        "discordUserId": recruit["discord_user_id"],
        "playerName": recruit["player_name"],
        "playerTag": recruit["player_tag"],
        "townHallLevel": recruit.get("player_th_level", 0),
        "createdAt": datetime.now(timezone.utc),
        "bidEndTime": bid_end_time,
        "recruitId": recruit_id,
        "startedBy": store_data["invoker_id"],
        "messageId": None
    }

    await mongo.button_store.insert_one(bidding_session_data)

    # Store active session
    active_bidding_sessions[recruit_id] = bid_end_time

    # Create the bidding embed
    components = await create_bidding_embed(
        recruit,
        bid_end_time,
        store_data["invoker_id"],
        bidding_session_id
    )

    # Send the bidding message in the recruit's clan thread
    try:
        message = await bot.rest.create_message(
            channel=ticket_thread_id,  # Use clan thread ID
            components=components
        )

        # Update session with message ID
        await mongo.button_store.update_one(
            {"_id": bidding_session_id},
            {"$set": {"messageId": message.id}}
        )

        # Clean up the original button store entry
        await mongo.button_store.delete_one({"_id": action_id})

        # Create success message using Components V2
        success_components = [
            Container(
                accent_color=GREEN_ACCENT,
                components=[
                    Text(content="✅ Bidding started successfully!"),
                    Text(content=f"Check <#{ticket_thread_id}> for the active bidding."),
                    Media(items=[MediaItem(media="assets/Green_Footer.png")])
                ]
            )
        ]

        # Just edit the initial response - no defer needed
        await ctx.interaction.edit_initial_response(components=success_components)

        # Create clan_bidding document if it doesn't exist
        # Using upsert to avoid duplicate key errors
        await mongo.clan_bidding.update_one(
            {"player_tag": recruit["player_tag"]},
            {
                "$setOnInsert": {
                    "bids": [],
                    "is_finalized": False,
                    "winner": "",
                    "amount": 0
                }
            },
            upsert=True
        )

        # Schedule the bidding end
        task = asyncio.create_task(
            end_bidding_timer(
                bot, mongo, recruit_id, bidding_session_id,
                ticket_thread_id, message.id
            )
        )
        bidding_tasks[recruit_id] = task

    except Exception as e:
        print(f"[Bidding] Error creating bidding message: {e}")
        # Rollback on error
        await mongo.new_recruits.update_one(
            {"_id": ObjectId(recruit_id)},
            {"$set": {"activeBid": False}}
        )
        await mongo.button_store.delete_one({"_id": bidding_session_id})

        error_components = [
            Container(
                accent_color=RED_ACCENT,
                components=[
                    Text(content="❌ Failed to start bidding. Please try again."),
                    Text(content=f"Error: {str(e)[:100]}"),
                    Media(items=[MediaItem(media="assets/Red_Footer.png")])
                ]
            )
        ]

        await ctx.interaction.edit_initial_response(components=error_components)


async def create_bidding_embed(
    recruit: Dict,
    bid_end_time: datetime,
    started_by: int,
    session_id: str
) -> List[Container]:
    """Create the bidding embed components"""
    th_emoji = get_th_emoji(recruit.get("player_th_level", 0))
    th_str = f"{th_emoji} " if th_emoji else ""

    components = [
        Container(
            accent_color=GOLD_ACCENT,
            components=[
                Text(content=f"# {th_str} Bidding open for {recruit['player_name']}!"),

                Separator(divider=True),

                Text(content="## Recruit Information"),
                Text(content=(
                    f"• **Discord ID:** <@{recruit['discord_user_id']}>\n"
                    f"• **Player Name:** {recruit['player_name']}\n"
                    f"• **Player Tag:** {recruit['player_tag']}\n"
                    f"• **Town Hall Level:** {recruit.get('player_th_level', 'Unknown')}"
                )),

                Separator(divider=True),

                Text(content="## Bidding Information"),
                Text(content=(
                    f"• **Started by:** <@{started_by}>\n"
                    f"• **Ends at:** <t:{int(bid_end_time.timestamp())}:T> (<t:{int(bid_end_time.timestamp())}:R>)\n"
                    f"• **Duration:** {BIDDING_DURATION} minutes\n\n"
                )),

                Separator(divider=True),

                Text(content=(
                    f"Submit your bids for this player account, the highest bid wins automatically.\n\n"
                    f"-# Note: If you don't meet the clan's criteria, you will still forfeit your points. Please review the player requirements.\n"
                    f"-# Note: In the event of a tie, the system will select the winning clan at random."
                )),

                Separator(divider=True),

                ActionRow(
                    components=[
                        Button(
                            style=hikari.ButtonStyle.SUCCESS,
                            label="Place Bid",
                            emoji="💰",
                            custom_id=f"place_bid:{session_id}"
                        ),
                        Button(
                            style=hikari.ButtonStyle.DANGER,
                            label="Remove Bid",
                            emoji="❌",
                            custom_id=f"remove_bid:{session_id}"
                        )
                    ]
                ),

                Media(items=[MediaItem(media="assets/Gold_Footer.png")]),
                Text(content="-# Bids will be processed automatically when timer expires")
            ]
        )
    ]

    return components


@register_action("place_bid", no_return=True)
@lightbulb.di.with_di
async def handle_place_bid(
        ctx: lightbulb.components.MenuContext,
        action_id: str,
        mongo: MongoClient = lightbulb.di.INJECTED,
        **kwargs
):
    """Handle placing a bid"""
    session_id = action_id

    # Get bidding session data
    session = await mongo.button_store.find_one({
        "_id": session_id,
        "type": "bidding_session"
    })
    if not session:
        await ctx.respond("Bidding session not found.", ephemeral=True)
        return

    # Get user's clans where they have leader role
    user_roles = ctx.interaction.member.role_ids
    clans = await mongo.clans.find({
        "leader_role_id": {"$in": user_roles}
    }).to_list(length=None)

    if not clans:
        await ctx.respond("You must have a clan leader role to place bids.", ephemeral=True)
        return

    # Create select menu options
    options = []
    seen_tags = {}
    for clan_data in clans[:25]:
        clan = Clan(data=clan_data)
        available_points = clan.points - clan.placeholder_points

        # Handle duplicate clan tags by making values unique
        if clan.tag in seen_tags:
            seen_tags[clan.tag] += 1
            unique_value = f"{clan.tag}_{seen_tags[clan.tag]}"
        else:
            seen_tags[clan.tag] = 0
            unique_value = clan.tag

        option_kwargs = {
            "label": clan.name,
            "value": unique_value,
            "description": f"{available_points:.1f} pts available"
        }
        if clan.partial_emoji:
            option_kwargs["emoji"] = clan.partial_emoji
        options.append(SelectOption(**option_kwargs))

    # Store session for next step
    bid_session_id = f"bid_select_{str(uuid.uuid4())}"
    await mongo.button_store.insert_one({
        "_id": bid_session_id,
        "type": "bid_placement",
        "bidding_session_id": session_id,
        "user_id": ctx.user.id,
        "player_tag": session["playerTag"]
    })

    # Create select menu components
    components = [
        Container(
            accent_color=BLUE_ACCENT,
            components=[
                Text(content="## 💰 Select Clan for Bidding"),
                Text(content="Choose which clan will place the bid:"),
                ActionRow(
                    components=[
                        TextSelectMenu(
                            custom_id=f"select_clan_bid:{bid_session_id}",
                            placeholder="Select a clan...",
                            options=options
                        )
                    ]
                ),
                Media(items=[MediaItem(media="assets/Blue_Footer.png")])
            ]
        )
    ]

    # Send as new ephemeral message, NOT editing the bidding embed
    await ctx.respond(components=components, ephemeral=True)


@register_action("select_clan_bid", opens_modal=True, no_return=True)
@lightbulb.di.with_di
async def handle_clan_selection(
        ctx: lightbulb.components.MenuContext,
        action_id: str,
        mongo: MongoClient = lightbulb.di.INJECTED,
        **kwargs
):
    """Handle clan selection and show amount modal"""
    # Remove the manual deferral - opens_modal=True handles this

    session_id = action_id
    selected_value = ctx.interaction.values[0]

    # Extract original tag from potentially modified value (remove _1, _2 etc.)
    selected_clan = selected_value.split("_")[0] if "_" in selected_value else selected_value

    # Get session data
    session = await mongo.button_store.find_one({"_id": session_id})
    if not session:
        # Can't edit when opening modal, so just show modal with error
        await ctx.respond_with_modal(
            title="Session Expired",
            custom_id=f"error_modal:{session_id}",
            components=[ModalActionRow().add_text_input(
                "error",
                "Error",
                value="Session expired. Please try again.",
                required=False
            )]
        )
        return

    # Update session with selected clan
    await mongo.button_store.update_one(
        {"_id": session_id},
        {"$set": {"selected_clan": selected_clan}}
    )

    # Show the modal for bid amount
    amount_modal = ModalActionRow().add_text_input(
        "bid_amount",
        "Bid Amount (0.5 increments)",
        placeholder="Enter amount (e.g., 5.0, 10.5)",
        required=True,
        min_length=1,
        max_length=10
    )

    await ctx.respond_with_modal(
        title="Enter Bid Amount",
        custom_id=f"place_bid_modal:{session_id}",
        components=[amount_modal]
    )


@register_action("place_bid_modal", is_modal=True, no_return=True)
@lightbulb.di.with_di
async def handle_bid_amount_modal(
    ctx: lightbulb.components.ModalContext,
    action_id: str,
    mongo: MongoClient = lightbulb.di.INJECTED,
    bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    **kwargs
):
    """Handle the bid amount submission"""
    session_id = action_id

    # Defer the modal response to edit the select menu
    await ctx.interaction.create_initial_response(
        hikari.ResponseType.DEFERRED_MESSAGE_UPDATE
    )

    # Get session data
    session = await mongo.button_store.find_one({"_id": session_id})
    if not session:
        await ctx.interaction.edit_initial_response(
            components=[Container(
                accent_color=RED_ACCENT,
                components=[
                    Text(content="❌ Session expired."),
                    Media(items=[MediaItem(media="assets/Red_Footer.png")])
                ]
            )]
        )
        return

    # Get bidding session
    bidding_session = await mongo.button_store.find_one({
        "_id": session["bidding_session_id"],
        "type": "bidding_session"
    })
    if not bidding_session:
        await ctx.interaction.edit_initial_response(
            components=[Container(
                accent_color=RED_ACCENT,
                components=[
                    Text(content="❌ Bidding session not found."),
                    Media(items=[MediaItem(media="assets/Red_Footer.png")])
                ]
            )]
        )
        return

    # Helper function to show error
    async def show_error(error_message: str):
        await ctx.interaction.edit_initial_response(
            components=[Container(
                accent_color=RED_ACCENT,
                components=[
                    Text(content=f"❌ {error_message}"),
                    Media(items=[MediaItem(media="assets/Red_Footer.png")])
                ]
            )]
        )

    # Parse bid amount
    try:
        bid_amount = float(ctx.interaction.components[0][0].value)
        if bid_amount % 0.5 != 0 or bid_amount < 0:
            await show_error("Bid must be in 0.5 increments and positive.")
            return
    except ValueError:
        await show_error("Invalid bid amount. Please enter a number.")
        return

    # Verify clan and available points
    clan = await mongo.clans.find_one({"tag": session["selected_clan"]})
    if not clan:
        await show_error("Clan not found.")
        return

    available_points = clan["points"] - clan.get("placeholder_points", 0)
    if bid_amount > available_points:
        await show_error(f"Insufficient points! Available: {available_points} points")
        return

    # Check for existing bid
    existing_bid = await mongo.clan_bidding.find_one({
        "player_tag": bidding_session["playerTag"],
        "bids.clan_tag": session["selected_clan"]
    })

    if existing_bid:
        await show_error("Your clan already has a bid on this recruit. Use 'Remove Bid' first.")
        return

    # Place the bid
    bid_data = {
        "clan_tag": session["selected_clan"],
        "amount": bid_amount,
        "placed_by": ctx.user.id,
        "placed_at": datetime.now(timezone.utc)
    }

    await mongo.clan_bidding.update_one(
        {"player_tag": bidding_session["playerTag"]},
        {
            "$push": {"bids": bid_data},
            "$setOnInsert": {
                "player_tag": bidding_session["playerTag"],
                "created_at": datetime.now(timezone.utc)
            }
        },
        upsert=True
    )

    # Update placeholder points
    await safe_adjust_placeholder_points(mongo, session["selected_clan"], bid_amount)

    # Edit the select menu to show success
    await ctx.interaction.edit_initial_response(
        components=[Container(
            accent_color=GREEN_ACCENT,
            components=[
                Text(content="## ✅ Bid Placed Successfully!"),
                Text(content=f"**Clan:** {clan['name']}"),
                Text(content=f"**Amount:** {bid_amount} points"),
                Separator(divider=True),
                Text(content="Your bid has been registered. Good luck!"),
                Media(items=[MediaItem(media="assets/Green_Footer.png")])
            ]
        )]
    )

    # Log the bid
    log_components = [
        Container(
            accent_color=BLUE_ACCENT,
            components=[
                Text(content="New Bid Placed"),
                Separator(divider=True),
                Text(content=(
                    f"**Player:** {bidding_session['playerTag']}\n"
                    f"**Clan:** {clan['name']}\n"
                    f"**Amount:** {bid_amount} points\n"
                    f"**Placed by:** <@{ctx.user.id}>\n"
                    f"**Thread:** <#{bidding_session['threadId']}>"
                )),
                Media(items=[MediaItem(media="assets/Blue_Footer.png")])
            ]
        )
    ]
    log_channel = await bot.rest.fetch_channel(LOG_CHANNEL_ID)
    await log_channel.send(components=log_components)

    # Clean up session
    await mongo.button_store.delete_one({"_id": session_id})

@register_action("remove_bid", no_return=True)
@lightbulb.di.with_di
async def handle_remove_bid(
    ctx: lightbulb.components.MenuContext,
    action_id: str,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    """Handle removing a bid"""
    session_id = action_id

    # Get bidding session data
    session = await mongo.button_store.find_one({
        "_id": session_id,
        "type": "bidding_session"
    })
    if not session:
        await ctx.respond("Bidding session not found.", ephemeral=True)
        return

    # Get user's clans
    user_roles = ctx.interaction.member.role_ids
    clans = await mongo.clans.find({
        "leader_role_id": {"$in": user_roles}
    }).to_list(length=None)

    if not clans:
        await ctx.respond("No clans found with your leader role.", ephemeral=True)
        return

    # Get bids for this player
    bid_doc = await mongo.clan_bidding.find_one({"player_tag": session["playerTag"]})
    if not bid_doc or not bid_doc.get("bids"):
        await ctx.respond("No bids found.", ephemeral=True)
        return

    # Filter bids to only user's clans
    clan_tags = [c["tag"] for c in clans]
    user_bids = [b for b in bid_doc["bids"] if b["clan_tag"] in clan_tags]

    if not user_bids:
        await ctx.respond("You have no bids to remove.", ephemeral=True)
        return

    # Create select options for clans with bids
    options = []
    seen_tags = {}
    for bid in user_bids:
        clan_data = next((c for c in clans if c["tag"] == bid["clan_tag"]), None)
        if clan_data:
            clan = Clan(data=clan_data)

            # Handle duplicate clan tags by making values unique
            if clan.tag in seen_tags:
                seen_tags[clan.tag] += 1
                unique_value = f"{clan.tag}_{seen_tags[clan.tag]}"
            else:
                seen_tags[clan.tag] = 0
                unique_value = clan.tag

            option_kwargs = {
                "label": clan.name,
                "value": unique_value,
                "description": "Has active bid"
            }
            if clan.partial_emoji:
                option_kwargs["emoji"] = clan.partial_emoji
            options.append(SelectOption(**option_kwargs))

    # Store session
    remove_session_id = f"remove_select_{str(uuid.uuid4())}"
    await mongo.button_store.insert_one({
        "_id": remove_session_id,
        "type": "remove_bid_selection",
        "user_id": ctx.user.id,
        "bidding_session_id": session_id,
        "player_tag": session["playerTag"]
    })

    # Show select menu
    components = [
        Container(
            accent_color=RED_ACCENT,
            components=[
                Text(content="## ❌ Remove Bid"),
                Text(content="Select which clan's bid to remove:"),
                ActionRow(
                    components=[
                        TextSelectMenu(
                            custom_id=f"select_remove_clan:{remove_session_id}",
                            placeholder="Select a clan...",
                            options=options
                        )
                    ]
                ),
                Media(items=[MediaItem(media="assets/Red_Footer.png")])
            ]
        )
    ]

    await ctx.respond(components=components, ephemeral=True)


@register_action("select_remove_clan", opens_modal=True, no_return=True)
@lightbulb.di.with_di
async def handle_remove_clan_selection(
        ctx: lightbulb.components.MenuContext,
        action_id: str,
        mongo: MongoClient = lightbulb.di.INJECTED,
        **kwargs
):
    """Handle clan selection for bid removal"""
    # Remove manual deferral - opens_modal=True handles this

    session_id = action_id
    selected_value = ctx.interaction.values[0]

    # Extract original tag from potentially modified value (remove _1, _2 etc.)
    selected_clan = selected_value.split("_")[0] if "_" in selected_value else selected_value

    # Get session data
    session = await mongo.button_store.find_one({"_id": session_id})
    if not session:
        # Show error modal
        await ctx.respond_with_modal(
            title="Session Expired",
            custom_id=f"error_modal:{session_id}",
            components=[ModalActionRow().add_text_input(
                "error",
                "Error",
                value="Session expired. Please try again.",
                required=False
            )]
        )
        return

    # Update session with selected clan
    await mongo.button_store.update_one(
        {"_id": session_id},
        {"$set": {"clan_to_remove": selected_clan}}
    )

    # Show confirmation modal - use the correct handler name
    confirm_modal = ModalActionRow().add_text_input(
        "confirm",
        "Type REMOVE to confirm",
        placeholder="Type REMOVE exactly",
        required=True,
        max_length=6
    )

    await ctx.respond_with_modal(
        title="Confirm Bid Removal",
        custom_id=f"confirm_remove_bid:{session_id}",  # Changed to match the handler
        components=[confirm_modal]
    )


@register_action("confirm_remove_bid", is_modal=True, no_return=True)
@lightbulb.di.with_di
async def confirm_bid_removal(
        ctx: lightbulb.components.ModalContext,
        action_id: str,
        mongo: MongoClient = lightbulb.di.INJECTED,
        bot: hikari.GatewayBot = lightbulb.di.INJECTED,
        **kwargs
):
    """Confirm and process bid removal"""
    session_id = action_id

    # Defer the modal response
    await ctx.interaction.create_initial_response(
        hikari.ResponseType.DEFERRED_MESSAGE_UPDATE
    )

    # Get session
    session = await mongo.button_store.find_one({"_id": session_id})
    if not session:
        await ctx.interaction.edit_initial_response(
            components=[Container(
                accent_color=RED_ACCENT,
                components=[
                    Text(content="❌ Session expired."),
                    Media(items=[MediaItem(media="assets/Red_Footer.png")])
                ]
            )]
        )
        return

    # Check confirmation text
    if ctx.interaction.components[0][0].value != "REMOVE":
        # Get user's clans for recreating the select menu
        user_roles = ctx.interaction.member.role_ids
        clans = await mongo.clans.find({
            "leader_role_id": {"$in": user_roles}
        }).to_list(length=None)

        # Get current bids to filter which clans have bids
        bid_doc = await mongo.clan_bidding.find_one({"player_tag": session["player_tag"]})
        if bid_doc and bid_doc.get("bids"):
            clan_tags = [c["tag"] for c in clans]
            user_bids = [b for b in bid_doc["bids"] if b["clan_tag"] in clan_tags]

            # Recreate options
            options = []
            seen_tags = {}
            for bid in user_bids:
                clan_data = next((c for c in clans if c["tag"] == bid["clan_tag"]), None)
                if clan_data:
                    clan = Clan(data=clan_data)

                    # Handle duplicate clan tags by making values unique
                    if clan.tag in seen_tags:
                        seen_tags[clan.tag] += 1
                        unique_value = f"{clan.tag}_{seen_tags[clan.tag]}"
                    else:
                        seen_tags[clan.tag] = 0
                        unique_value = clan.tag

                    option_kwargs = {
                        "label": clan.name,
                        "value": unique_value,
                        "description": "Has active bid"
                    }
                    if clan.partial_emoji:
                        option_kwargs["emoji"] = clan.partial_emoji
                    options.append(SelectOption(**option_kwargs))

            if options:
                # Recreate the select menu with error message
                await ctx.interaction.edit_initial_response(
                    components=[Container(
                        accent_color=RED_ACCENT,
                        components=[
                            Text(content="## ❌ Remove Bid"),
                            Text(content="⚠️ You must type 'REMOVE' exactly. Please try again:"),
                            ActionRow(
                                components=[
                                    TextSelectMenu(
                                        custom_id=f"select_remove_clan:{session['_id']}",
                                        placeholder="Select a clan...",
                                        options=options
                                    )
                                ]
                            ),
                            Media(items=[MediaItem(media="assets/Red_Footer.png")])
                        ]
                    )]
                )
                return

        # If no options, show error
        await ctx.interaction.edit_initial_response(
            components=[Container(
                accent_color=RED_ACCENT,
                components=[
                    Text(content="❌ No bids found to remove."),
                    Media(items=[MediaItem(media="assets/Red_Footer.png")])
                ]
            )]
        )
        return

    # Get bidding session and bid data
    main_session = await mongo.button_store.find_one({
        "_id": session["bidding_session_id"],
        "type": "bidding_session"
    })

    if not main_session:
        await ctx.interaction.edit_initial_response(
            components=[Container(
                accent_color=RED_ACCENT,
                components=[
                    Text(content="❌ Bidding session not found."),
                    Media(items=[MediaItem(media="assets/Red_Footer.png")])
                ]
            )]
        )
        return

    clan_tag = session.get("clan_to_remove")
    player_tag = main_session["playerTag"]

    # First, get the bid amount before removing
    bid_data = await mongo.clan_bidding.find_one(
        {"player_tag": player_tag},
        {"bids": {"$elemMatch": {"clan_tag": clan_tag}}}
    )
    
    bid_amount = 10.0  # Default fallback
    if bid_data and bid_data.get("bids"):
        for bid in bid_data["bids"]:
            if bid["clan_tag"] == clan_tag:
                bid_amount = bid["amount"]
                break

    # Remove the bid
    result = await mongo.clan_bidding.update_one(
        {"player_tag": player_tag},
        {"$pull": {"bids": {"clan_tag": clan_tag}}}
    )

    if result.modified_count == 0:
        await ctx.interaction.edit_initial_response(
            components=[Container(
                accent_color=RED_ACCENT,
                components=[
                    Text(content="❌ No bid found to remove."),
                    Media(items=[MediaItem(media="assets/Red_Footer.png")])
                ]
            )]
        )
        return

    # Restore placeholder points
    clan = await mongo.clans.find_one({"tag": clan_tag})
    if clan:
        await safe_adjust_placeholder_points(mongo, clan_tag, -bid_amount)

    # Edit the message to show success
    await ctx.interaction.edit_initial_response(
        components=[Container(
            accent_color=GREEN_ACCENT,
            components=[
                Text(content="## ✅ Bid Removed Successfully!"),
                Text(content=f"**Clan:** {clan['name'] if clan else 'Unknown'}"),
                Text(content=f"**Amount:** {bid_amount} points"),
                Separator(divider=True),
                Text(content="Points have been restored to your clan."),
                Media(items=[MediaItem(media="assets/Green_Footer.png")])
            ]
        )]
    )

    # Log the removal
    log_components = [
        Container(
            accent_color=RED_ACCENT,
            components=[
                Text(content="Bid Removed"),
                Separator(divider=True),
                Text(content=(
                    f"**Player:** {player_tag}\n"
                    f"**Clan:** {clan['name'] if clan else clan_tag}\n"
                    f"**Amount:** {bid_amount} points\n"
                    f"**Removed by:** <@{ctx.user.id}>\n"
                    f"**Thread:** <#{main_session['threadId']}>"
                )),
                Media(items=[MediaItem(media="assets/Red_Footer.png")])
            ]
        )
    ]
    log_channel = await bot.rest.fetch_channel(LOG_CHANNEL_ID)
    await log_channel.send(components=log_components)

    # Clean up session data
    await mongo.button_store.delete_many({
        "_id": {"$in": [session_id, session.get("_id")]}
    })

async def end_bidding_timer(
    bot: hikari.GatewayBot,
    mongo: MongoClient,
    recruit_id: str,
    session_id: str,
    thread_id: int,
    message_id: int
):
    """Timer to end bidding after duration expires"""
    try:
        # Wait for bidding duration
        await asyncio.sleep(BIDDING_DURATION * 60)

        # Process the bidding results
        await process_bidding_end(bot, mongo, recruit_id, session_id, thread_id, message_id)

    except asyncio.CancelledError:
        print(f"[Bidding] Timer cancelled for recruit {recruit_id}")
    except Exception as e:
        print(f"[Bidding] Error in timer for recruit {recruit_id}: {e}")
    finally:
        # Clean up
        if recruit_id in active_bidding_sessions:
            del active_bidding_sessions[recruit_id]
        if recruit_id in bidding_tasks:
            del bidding_tasks[recruit_id]


async def process_bidding_end(
        bot: hikari.GatewayBot,
        mongo: MongoClient,
        recruit_id: str,
        session_id: str,
        thread_id: int,
        message_id: int
):
    """Process the end of bidding"""

    # Get recruit and session data
    recruit = await mongo.new_recruits.find_one({"_id": ObjectId(recruit_id)})
    session = await mongo.button_store.find_one({
        "_id": session_id,
        "type": "bidding_session"
    })

    if not recruit or not session:
        print(f"[Bidding] Missing data for recruit {recruit_id}")
        return

    # Get auction data
    auction = await mongo.clan_bidding.find_one({"player_tag": session["playerTag"]})

    # Delete the original bidding message
    try:
        await bot.rest.delete_message(thread_id, message_id)
    except:
        pass

    if not auction or not auction.get("bids"):
        # No bids scenario
        await handle_no_bids(bot, mongo, recruit, session, thread_id)
    elif len(auction["bids"]) == 1:
        # Single bid scenario
        await handle_single_bid(bot, mongo, recruit, session, auction, thread_id)
    else:
        # Multiple bids scenario
        await handle_multiple_bids(bot, mongo, recruit, session, auction, thread_id)

    # ALWAYS set activeBid to false - bidding is no longer active
    await mongo.new_recruits.update_one(
        {"_id": ObjectId(recruit_id)},
        {"$set": {"activeBid": False}}
    )

    # Clean up bidding session data
    await mongo.button_store.delete_one({"_id": session_id})


async def handle_no_bids(
    bot: hikari.GatewayBot,
    mongo: MongoClient,
    recruit: Dict,
    session: Dict,
    thread_id: int
):
    """Handle scenario where no bids were placed"""

    components = [
        Container(
            accent_color=RED_ACCENT,
            components=[
                Text(content=f"# Bids for {recruit['player_name']}"),

                Separator(divider=True),

                Text(content="## No bids were submitted."),

                Text(content=(
                    f"<@&1039311270614142977>\n\n" 
                    f"Please check interest in this account and assign it to a clan\n"
                )),
                Separator(divider=True),
                Text(content="## Candidate Information"),
                Text(content=(
                    f"• **Discord ID:** <@{recruit['discord_user_id']}>\n"
                    f"• **Player Name:** {recruit['player_name']}\n"
                    f"• **Player Tag:** {recruit['player_tag']}\n"
                    f"• **Town Hall Level:** {recruit.get('player_th_level', '??')}"
                )),
                Media(items=[MediaItem(media="assets/Red_Footer.png")]),
                Text(content=f"Bidding ended <t:{int(datetime.now(timezone.utc).timestamp())}:R>")
            ]
        )
    ]

    await bot.rest.create_message(
        channel=thread_id,
        components=components,
        role_mentions=True
    )


async def handle_single_bid(
        bot: hikari.GatewayBot,
        mongo: MongoClient,
        recruit: Dict,
        session: Dict,
        auction: Dict,
        thread_id: int
):
    """Handle scenario where single bid wins"""

    winner = auction["bids"][0]
    winning_clan = await mongo.clans.find_one({"tag": winner["clan_tag"]})

    if not winning_clan:
        print(f"[Bidding] Warning: Winning clan {winner['clan_tag']} not found")
        return

    # Reduce placeholder points only (no actual deduction)
    await safe_adjust_placeholder_points(mongo, winner["clan_tag"], -winner["amount"])

    # Mark as finalized
    await mongo.clan_bidding.update_one(
        {"player_tag": auction["player_tag"]},
        {
            "$set": {
                "is_finalized": True,
                "winner": winner["clan_tag"],
                "amount": winner["amount"],
                "finalized_at": datetime.now(timezone.utc)
            }
        }
    )

    winning_clan_obj = Clan(data=winning_clan)

    components = [
        Container(
            accent_color=BLUE_ACCENT,
            components=[
                Text(content=f"# Single Bid for {recruit['player_name']}"),
                Text(content=f"<@&{winning_clan['leader_role_id']}>"),
                Separator(divider=True),
                Text(content=(
                    f"Only one bid was submitted by **{winning_clan_obj.name}**.\n"
                    f"Since there was no competition, no points will be deducted."
                )),
                Separator(divider=True),
                Text(content="## Candidate Information"),
                Text(content=(
                    f"• **Discord ID:** <@{recruit['discord_user_id']}>\n"
                    f"• **Player Name:** {recruit['player_name']}\n"
                    f"• **Player Tag:** {recruit['player_tag']}\n"
                    f"• **Town Hall Level:** {recruit.get('player_th_level', '??')}"
                )),
                Separator(divider=True),
                Text(content=f"Bidding ended <t:{int(datetime.now(timezone.utc).timestamp())}:R>"),
                Media(items=[MediaItem(media="assets/Blue_Footer.png")])
            ]
        )
    ]

    await bot.rest.create_message(
        channel=thread_id,
        components=components,
        role_mentions=[winning_clan['leader_role_id']]
    )

    # Log the single bid win
    log_channel = await bot.rest.fetch_channel(LOG_CHANNEL_ID)
    await log_channel.send(
        f"🎯 **Single Bid Win**: {winning_clan_obj.name} won {recruit['player_name']} (no competition, no points deducted)"
    )


async def handle_multiple_bids(
    bot: hikari.GatewayBot,
    mongo: MongoClient,
    recruit: Dict,
    session: Dict,
    auction: Dict,
    thread_id: int
):
    """Handle scenario where multiple bids were placed"""

    bids = sorted(auction["bids"], key=lambda x: x["amount"], reverse=True)
    highest_amount = bids[0]["amount"]

    # Check for ties
    top_bids = [b for b in bids if b["amount"] == highest_amount]
    is_tie = len(top_bids) > 1

    if is_tie:
        # Randomly select winner from tied bids
        winning_bid = random.choice(top_bids)
    else:
        winning_bid = bids[0]

    # Deduct points from winner and release placeholder hold
    winning_clan = await mongo.clans.find_one({"tag": winning_bid["clan_tag"]})
    if winning_clan:
        # Deduct actual points AND release placeholder in one atomic operation
        # This converts the placeholder hold into an actual payment
        await mongo.clans.update_one(
            {"tag": winning_bid["clan_tag"]},
            {
                "$inc": {
                    "points": -winning_bid["amount"],  # Deduct actual points (payment)
                    "placeholder_points": -winning_bid["amount"]  # Release the hold
                }
            }
        )

    # Silently release placeholder points for losing clans (no refund needed - they never paid)
    for bid in bids:
        if bid["clan_tag"] != winning_bid["clan_tag"]:
            await safe_adjust_placeholder_points(mongo, bid["clan_tag"], -bid["amount"])

    # Build all bids display
    all_bids_text = []
    for i, bid in enumerate(bids, 1):
        clan_data = await mongo.clans.find_one({"tag": bid["clan_tag"]})
        if clan_data:
            clan_name = Clan(data=clan_data).name
            bidder = await bot.rest.fetch_user(bid["placed_by"])
            bidder_name = bidder.display_name if bidder else "Unknown"
        else:
            clan_name = "Unknown Clan"
            bidder_name = "Unknown"

        if bid["clan_tag"] == winning_bid["clan_tag"]:
            bid_text = f"{emojis.blank}**{i}** {emojis.BulletPoint} 🏆 **{clan_name}** {emojis.BulletPoint} _Bid by {bidder_name}_ {emojis.BulletPoint} `{bid['amount']}`"
        else:
            bid_text = f"{emojis.blank}**{i}** {emojis.BulletPoint} **{clan_name}** {emojis.BulletPoint} _Bid by {bidder_name}_ {emojis.BulletPoint} `{bid['amount']}`"
        all_bids_text.append(bid_text)

    # Build the message
    winning_clan_obj = Clan(data=winning_clan) if winning_clan else None
    title = f"## Winning Bid: {winning_clan_obj.name if winning_clan_obj else 'Unknown'} – {winning_bid['amount']}"
    if is_tie:
        title += "\n-# Tie-breaker: randomly selected"

    components = [
        Container(
            accent_color=GREEN_ACCENT,
            components=[
                Text(content=title),

                Text(content=(
                    f"<@&{winning_clan['leader_role_id'] if winning_clan else 0}>\n\n"  # Role ping inside
                    f"Congratulations <@&{winning_clan['leader_role_id'] if winning_clan else 0}> Leadership! "
                    f"You've won the bid for this recruit, come claim your new player now!"
                )),

                Separator(divider=True),

                Text(content="## Candidate Information"),
                Text(content=(
                    f"• **Discord ID:** <@{recruit['discord_user_id']}>\n"
                    f"• **Player Name:** {recruit['player_name']}\n"
                    f"• **Player Tag:** {recruit['player_tag']}\n"
                    f"• **Town Hall Level:** {recruit.get('player_th_level', 'Unknown')}"
                )),

                Separator(divider=True),

                Text(content="## All Bids"),
                Text(content="\n".join(all_bids_text)),

                Media(items=[MediaItem(media="assets/Red_Footer.png")]),
                Text(content=f"Bidding ended <t:{int(datetime.now(timezone.utc).timestamp())}:R>"),
            ]
        )
    ]

    # Send message WITHOUT content parameter
    await bot.rest.create_message(
        channel=thread_id,
        components=components,
        role_mentions=[winning_clan['leader_role_id']] if winning_clan else []
    )

    # Send success message to feed channel
    log_channel = await bot.rest.fetch_channel(LOG_CHANNEL_ID)
    winning_clan_obj = Clan(data=winning_clan) if winning_clan else None
    await log_channel.send(
        f"🏆 **Multi-Bid Win**: {winning_clan_obj.name if winning_clan_obj else 'Unknown'} won {recruit['player_name']} "
        f"for {winning_bid['amount']} points ({len(bids)} bids total)"
    )

    # Finalize the auction
    await mongo.clan_bidding.update_one(
        {"player_tag": session["playerTag"]},
        {
            "$set": {
                "is_finalized": True,
                "winner": winning_bid["clan_tag"],
                "amount": winning_bid["amount"]
            }
        }
    )


# Cleanup on module unload
def cleanup_tasks():
    """Cancel all active bidding tasks"""
    for task in bidding_tasks.values():
        if not task.done():
            task.cancel()
    bidding_tasks.clear()
    active_bidding_sessions.clear()