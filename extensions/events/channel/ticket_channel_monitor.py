# extensions/events/channel/ticket_channel_monitor.py
"""Event listener for monitoring new channel creation for ticket channels"""

import asyncio
import aiohttp
import hikari
import lightbulb
import coc
from datetime import datetime, timedelta, timezone
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
)

# Import FWA chocolate components
try:
    from extensions.events.message.ticket_automation.fwa.utils.chocolate_components import (
        send_chocolate_link
    )

    HAS_FWA_CHOCOLATE = True
except ImportError:
    HAS_FWA_CHOCOLATE = False
    print("[WARNING] FWA chocolate components not found, chocolate links will be disabled")

loader = lightbulb.Loader()

# Add debug print when module loads
print("[INFO] Loading ticket_channel_monitor extension...")

# Global variables to store instances
mongo_client = None
coc_client = None

# Define the patterns we're looking for
# These are the special characters/patterns to match
PATTERNS = {
    "TEST": "𝕋𝔼𝕊𝕋",  # Active
    "CLAN": "ℂ𝕃𝔸ℕ",  # Disabled for now
    "FWA": "𝔽𝕎𝔸",  # Disabled for now
    "FWA_TEST": "𝕋-𝔽𝕎𝔸"  # Add this!
}

# Define which patterns are currently active
ACTIVE_PATTERNS = ["TEST", "FWA_TEST", "CLAN", "FWA"]


@loader.listener(hikari.StartedEvent)
@lightbulb.di.with_di
async def on_bot_started(
        event: hikari.StartedEvent,
        mongo: MongoClient = lightbulb.di.INJECTED,
        coc_api: coc.Client = lightbulb.di.INJECTED
) -> None:
    """Store instances when bot starts"""
    global mongo_client, coc_client
    mongo_client = mongo
    coc_client = coc_api
    print("[INFO] Ticket channel monitor ready with MongoDB and CoC connections")


async def retry_api_for_full_data(
    channel_id: int,
    thread_id: str,
    user_id: str,
    matched_pattern: str,
    mongo: MongoClient,
    coc: coc.Client
) -> None:
    """Background task to retry API and get full ticket data after fallback"""
    print(f"[INFO] Background retry scheduled for channel {channel_id}, waiting 60 seconds...")
    await asyncio.sleep(60)
    
    print(f"[INFO] Starting background API retry for channel {channel_id}")
    
    try:
        async with aiohttp.ClientSession() as session:
            api_url = f"https://api.clashk.ing/ticketing/open/json/{channel_id}"
            print(f"[DEBUG] Background API call to: {api_url}")
            
            async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=20)) as response:
                if response.status == 200:
                    api_data = await response.json()
                    print(f"[SUCCESS] Background API call succeeded: {api_data}")
                    
                    # Only proceed if we got a player tag
                    if api_data.get('apply_account'):
                        player_tag = api_data.get('apply_account')
                        player_data = None
                        
                        # Try to fetch player data
                        if coc:
                            try:
                                player_data = await coc.get_player(player_tag)
                                print(f"[SUCCESS] Retrieved player data: {player_data.name} (TH{player_data.town_hall})")
                            except Exception as e:
                                print(f"[ERROR] Failed to fetch player data in background: {e}")
                        
                        # Update MongoDB with full data
                        if mongo:
                            try:
                                from datetime import datetime, timedelta, timezone
                                now = datetime.now(timezone.utc)
                                
                                # Update the existing new_recruits document with full data
                                update_result = await mongo.new_recruits.update_one(
                                    {"ticket_channel_id": str(channel_id)},
                                    {
                                        "$set": {
                                            "player_tag": player_tag,
                                            "player_name": player_data.name if player_data else None,
                                            "player_th_level": player_data.town_hall if player_data else None,
                                            "api_data_retrieved": True,
                                            "api_data_retrieved_at": now
                                        }
                                    }
                                )
                                
                                if update_result.modified_count > 0:
                                    print(f"[SUCCESS] Updated MongoDB with full ticket data for channel {channel_id}")
                                else:
                                    # Document doesn't exist yet, create it
                                    recruit_doc = {
                                        "player_tag": player_tag,
                                        "player_name": player_data.name if player_data else None,
                                        "player_th_level": player_data.town_hall if player_data else None,
                                        "discord_user_id": str(user_id),
                                        "ticket_channel_id": str(channel_id),
                                        "ticket_thread_id": str(thread_id) if thread_id else None,
                                        "created_at": now,
                                        "expires_at": now + timedelta(days=12),
                                        "recruitment_history": [],
                                        "current_clan": None,
                                        "total_clans_joined": 0,
                                        "is_expired": False,
                                        "activeBid": False,
                                        "ticket_open": True,
                                        "api_data_retrieved": True,
                                        "api_data_retrieved_at": now
                                    }
                                    await mongo.new_recruits.insert_one(recruit_doc)
                                    print(f"[SUCCESS] Created new MongoDB document with full ticket data")
                                    
                                # Also update ticket automation state if it exists
                                await mongo.ticket_automation_state.update_one(
                                    {"_id": str(channel_id)},
                                    {
                                        "$set": {
                                            "ticket_info.user_tag": player_tag,
                                            "player_info.player_tag": player_tag,
                                            "player_info.player_name": player_data.name if player_data else None,
                                            "player_info.town_hall": player_data.town_hall if player_data else None,
                                            "player_info.clan_tag": player_data.clan.tag if player_data and player_data.clan else None,
                                            "player_info.clan_name": player_data.clan.name if player_data and player_data.clan else None,
                                            "ticket_info.ticket_number": api_data.get('number'),
                                            "api_recovered": True,
                                            "api_recovered_at": now
                                        }
                                    }
                                )
                                print(f"[SUCCESS] Updated ticket automation state with recovered data")
                                
                            except Exception as e:
                                print(f"[ERROR] Failed to update MongoDB in background: {e}")
                    else:
                        print(f"[WARNING] Background API succeeded but no player tag found")
                else:
                    print(f"[ERROR] Background API returned status {response.status}")
                    
    except Exception as e:
        print(f"[ERROR] Background API retry failed: {e}")
    
    print(f"[INFO] Background retry completed for channel {channel_id}")


@loader.listener(hikari.GuildChannelCreateEvent)
async def on_channel_create(event: hikari.GuildChannelCreateEvent) -> None:
    """Handle channel creation events"""

    # Get the channel name
    channel_name = event.channel.name

    # Debug logging
    print(f"[DEBUG] New channel created: {channel_name} (ID: {event.channel.id})")

    # Check if the channel name contains any of the active patterns
    matched = False
    matched_pattern = None
    for pattern_key in ACTIVE_PATTERNS:
        if pattern_key in PATTERNS and PATTERNS[pattern_key] in channel_name:
            matched = True
            matched_pattern = pattern_key
            print(f"[DEBUG] Channel matches pattern: {pattern_key}")
            break

    # If no match, return early
    if not matched:
        return

    # Wait 3 seconds before proceeding
    await asyncio.sleep(5)

    # Get the channel ID
    channel_id = event.channel.id

    # Try to find any threads in this channel
    thread_id = None
    try:
        # Fetch active threads for the guild
        active_threads = await event.app.rest.fetch_active_threads(event.guild_id)

        # Look for a thread in our channel
        for thread in active_threads:
            if thread.parent_id == channel_id:
                thread_id = thread.id
                print(f"[DEBUG] Found thread {thread_id} in channel {channel_id}")
                break

        # If no active thread found, try to fetch the channel to see if it's a thread
        if not thread_id:
            # Sometimes the "channel" itself might be a thread
            channel_info = await event.app.rest.fetch_channel(channel_id)
            if channel_info.type in [hikari.ChannelType.GUILD_PUBLIC_THREAD,
                                     hikari.ChannelType.GUILD_PRIVATE_THREAD,
                                     hikari.ChannelType.GUILD_NEWS_THREAD]:
                # The channel itself is a thread
                thread_id = channel_id
                channel_id = channel_info.parent_id
                print(f"[DEBUG] The created channel is actually a thread")

        # If still no thread found, wait a bit more and check again
        # (sometimes thread creation is delayed)
        if not thread_id:
            await asyncio.sleep(2)  # Wait 2 more seconds
            try:
                active_threads = await event.app.rest.fetch_active_threads(event.guild_id)
                for thread in active_threads:
                    if thread.parent_id == channel_id:
                        thread_id = thread.id
                        print(f"[DEBUG] Found thread {thread_id} after additional wait")
                        break
            except Exception as e:
                print(f"[DEBUG] Error on second thread fetch attempt: {e}")

        # Also check for archived threads (in case it was instantly archived)
        if not thread_id:
            try:
                # Check if the channel is a forum channel
                if event.channel.type == hikari.ChannelType.GUILD_FORUM:
                    # For forum channels, threads are the posts
                    threads = await event.app.rest.fetch_public_archived_threads(channel_id)
                    if threads:
                        # Get the most recent thread
                        thread_id = threads[0].id
                        print(f"[DEBUG] Found forum post/thread: {thread_id}")
            except Exception as e:
                print(f"[DEBUG] Error checking for forum threads: {e}")

    except Exception as e:
        print(f"[DEBUG] Error fetching threads: {e}")

    # Check MongoDB first for existing ticket data (e.g., from manual creation)
    api_data = None
    player_data = None
    stored_in_db = False

    # First, check if we already have ticket automation state for this channel
    existing_state = None
    if mongo_client:
        try:
            existing_state = await mongo_client.ticket_automation_state.find_one({"_id": str(channel_id)})
            if existing_state:
                print(f"[INFO] Found existing ticket automation state for channel {channel_id} - using stored data")
                # Create api_data from existing MongoDB document
                ticket_info = existing_state.get("ticket_info", {})
                player_info = existing_state.get("player_info", {})

                api_data = {
                    "user": ticket_info.get("user_id"),
                    "channel": str(channel_id),
                    "thread": ticket_info.get("thread_id", ""),
                    "apply_account": ticket_info.get("user_tag") or player_info.get("player_tag"),
                    "number": ticket_info.get("ticket_number", "Unknown"),
                    "from_mongodb": True  # Flag to indicate this came from MongoDB
                }

                # Get player data if we have a player tag
                player_tag = api_data.get("apply_account")
                if player_tag and coc_client:
                    try:
                        player_data = await coc_client.get_player(player_tag)
                        print(f"[DEBUG] Retrieved player data from CoC API: {player_data.name} (TH{player_data.town_hall})")
                    except Exception as e:
                        print(f"[DEBUG] Could not fetch fresh player data, using stored: {e}")
                        # Use stored player data if API fails
                        if player_info:
                            class MockPlayer:
                                def __init__(self, name, town_hall, tag, clan_tag=None, clan_name=None):
                                    self.name = name
                                    self.town_hall = town_hall
                                    self.tag = tag
                                    self.clan = None
                                    if clan_tag and clan_name:
                                        class MockClan:
                                            def __init__(self, tag, name):
                                                self.tag = tag
                                                self.name = name
                                        self.clan = MockClan(clan_tag, clan_name)

                            player_data = MockPlayer(
                                name=player_info.get("player_name"),
                                town_hall=player_info.get("town_hall"),
                                tag=player_info.get("player_tag"),
                                clan_tag=player_info.get("clan_tag"),
                                clan_name=player_info.get("clan_name")
                            )

                stored_in_db = True
                print(f"[SUCCESS] Using existing MongoDB data for manual ticket")
        except Exception as e:
            print(f"[ERROR] Failed to check MongoDB for existing state: {e}")

    # Only make API call if we don't have data from MongoDB
    if not api_data:
        print(f"[INFO] No existing MongoDB data found, proceeding with API call")
        max_api_retries = 3
        api_retry_count = 0
        retry_delays = [3, 15, 30]  # Custom delays in seconds for each retry
    
    while not api_data and api_retry_count < max_api_retries:
        try:
            async with aiohttp.ClientSession() as session:
                api_url = f"https://api.clashk.ing/ticketing/open/json/{channel_id}"
                print(f"[DEBUG] Making API call to: {api_url} (attempt {api_retry_count + 1}/{max_api_retries})")

                async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=15)) as response:
                    if response.status == 200:
                        api_data = await response.json()
                        print(f"[DEBUG] API response: {api_data}")
                        break  # Success, exit retry loop
                    elif 400 <= response.status < 500:
                        # Client error (4xx) - don't retry
                        print(f"[ERROR] API returned client error status {response.status}")
                        break
                    else:
                        # Server error (5xx) or other - retry
                        print(f"[ERROR] API returned status {response.status}")
                        api_retry_count += 1
                        if api_retry_count < max_api_retries:
                            wait_time = retry_delays[api_retry_count - 1]  # Use custom delays: 3s, 15s, 30s
                            print(f"[INFO] Retrying API call in {wait_time} seconds...")
                            await asyncio.sleep(wait_time)
                        else:
                            print(f"[ERROR] Max API retries reached")
                            
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            api_retry_count += 1
            print(f"[ERROR] Failed to call API (attempt {api_retry_count}/{max_api_retries}): {e}")
            if api_retry_count < max_api_retries:
                wait_time = retry_delays[api_retry_count - 1]  # Use custom delays: 3s, 15s, 30s
                print(f"[INFO] Retrying API call in {wait_time} seconds...")
                await asyncio.sleep(wait_time)
            else:
                print(f"[ERROR] Max API retries reached due to connection error")
        except Exception as e:
            print(f"[ERROR] Unexpected error calling API: {e}")
            break  # Don't retry on unexpected errors
    
    # If API failed, try to extract user from channel permissions as fallback
    if not api_data:
        print(f"[INFO] API failed, attempting to extract user from channel permissions")
        try:
            # Fetch full channel details to access permission overwrites
            channel_details = await event.app.rest.fetch_channel(channel_id)
            
            if hasattr(channel_details, 'permission_overwrites') and channel_details.permission_overwrites:
                print(f"[DEBUG] Found {len(channel_details.permission_overwrites)} permission overwrites")
                
                # Look for user (member) type permission overrides
                for override_id, override in channel_details.permission_overwrites.items():
                    # Check if this is a user override (not a role)
                    # User IDs are typically 17-19 digits, role IDs are similar but we check the type
                    if override.type == hikari.PermissionOverwriteType.MEMBER:
                        print(f"[INFO] Found user permission override for user ID: {override_id}")
                        # Create minimal API data with extracted user ID
                        api_data = {
                            "user": str(override_id),
                            "channel": str(channel_id),
                            "thread": str(thread_id) if thread_id else "",
                            "fallback_mode": True,  # Flag to indicate this is fallback data
                            "number": "Unknown"  # We don't have ticket number from permissions
                        }
                        print(f"[SUCCESS] Extracted user {override_id} from channel permissions")
                        
                        # Schedule background retry to get full data after 60 seconds
                        print(f"[INFO] Scheduling background API retry for full data")
                        asyncio.create_task(
                            retry_api_for_full_data(
                                channel_id=channel_id,
                                thread_id=str(thread_id) if thread_id else "",
                                user_id=str(override_id),
                                matched_pattern=matched_pattern,
                                mongo=mongo_client,
                                coc=coc_client
                            )
                        )
                        break
                else:
                    print(f"[WARNING] No user permission overrides found in channel")
            else:
                print(f"[WARNING] Channel has no permission overwrites or property not accessible")
                
        except Exception as e:
            print(f"[ERROR] Failed to extract user from channel permissions: {e}")
    
    # Fetch player data if we got API data
    if api_data and api_data.get('apply_account') and coc_client:
        player_tag = api_data.get('apply_account')
        print(f"[DEBUG] Fetching player data for tag: {player_tag}")

        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                player_data = await coc_client.get_player(player_tag)
                print(f"[DEBUG] Player found: {player_data.name} (TH{player_data.town_hall})")
                break  # Success, exit retry loop
            except coc.NotFound:
                print(f"[ERROR] Player not found: {player_tag}")
                break  # Don't retry for not found
            except Exception as e:
                retry_count += 1
                print(f"[ERROR] Failed to fetch player (attempt {retry_count}/{max_retries}): {e}")
                if retry_count < max_retries:
                    await asyncio.sleep(1)  # Wait 1 second before retry
                else:
                    print(f"[ERROR] Max retries reached for player fetch")

    # Store in MongoDB if we have API data and player info (but not if data came from MongoDB already)
    if api_data and api_data.get('apply_account') and mongo_client and not api_data.get('from_mongodb'):
        try:
            # Create new recruit entry
            from datetime import datetime, timedelta, timezone

            now = datetime.now(timezone.utc)
            recruit_doc = {
                # Player info
                "player_tag": api_data.get('apply_account'),
                "player_name": player_data.name if player_data else None,
                "player_th_level": player_data.town_hall if player_data else None,

                # Discord/Ticket (store as strings)
                "discord_user_id": str(api_data.get('user')),
                "ticket_channel_id": str(api_data.get('channel')),
                "ticket_thread_id": str(api_data.get('thread')),

                # Timestamps
                "created_at": now,
                "expires_at": now + timedelta(days=12),

                # Initial state
                "recruitment_history": [],
                "current_clan": None,
                "total_clans_joined": 0,
                "is_expired": False,

                "activeBid": False,
                "ticket_open": True
            }

            # Insert into MongoDB
            result = await mongo_client.new_recruits.insert_one(recruit_doc)
            print(f"[DEBUG] Stored new recruit in MongoDB: {result.inserted_id}")
            stored_in_db = True

            # Create ticket automation state
            try:
                automation_doc = {
                    "_id": str(channel_id),
                    "ticket_info": {
                        "channel_id": str(channel_id),
                        "thread_id": str(api_data.get('thread', '')),
                        "user_id": str(api_data.get('user')),
                        "user_tag": api_data.get('apply_account'),  # Add this for FWA
                        "ticket_type": matched_pattern,  # TEST, CLAN, or FWA
                        "ticket_number": api_data.get('number'),
                        "created_at": now,
                        "last_updated": now
                    },
                    "player_info": {
                        "player_tag": api_data.get('apply_account'),
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
                                "data": {"api_response": api_data}
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
                        "initial_prompt": str(event.channel.id)  # The message we're about to send
                    },
                    "interaction_history": [
                        {
                            "timestamp": now,
                            "action": "ticket_created",
                            "details": f"Ticket created for user {api_data.get('user')}"
                        }
                    ]
                }

                # Insert the automation state
                await mongo_client.ticket_automation_state.insert_one(automation_doc)
                print(f"[DEBUG] Created ticket automation state for channel {channel_id}")

            except Exception as e:
                print(f"[ERROR] Failed to create ticket automation state: {e}")
                # Don't fail the whole process if automation state fails

        except Exception as e:
            print(f"[ERROR] Failed to store in MongoDB: {e}")
            stored_in_db = False
    else:
        # Only set to False if we're not using existing MongoDB data
        if not api_data or not api_data.get('from_mongodb'):
            stored_in_db = False

    # Prepare the message components
    # Check if we have API data (either from API or fallback)
    if api_data and (stored_in_db or api_data.get('fallback_mode')):
        # Check if this is an FWA ticket
        is_fwa = matched_pattern in ["FWA", "FWA_TEST"]

        if is_fwa:
            # For FWA tickets, send war weight request using exact recruit questions format
            fwa_components = [
                Text(content=f"## ⚖️ **War Weight Check** · <@{api_data.get('user', '')}>"),
                Separator(divider=True),
                Text(content=(
                    "We need your **current war weight** to ensure fair matchups. Please:\n\n"
                    f"{emojis.red_arrow_right} **Post** a Friendly Challenge in-game.\n"
                    f"{emojis.red_arrow_right} **Scout** that challenge you posted\n"
                    f"{emojis.red_arrow_right} **Tap** on your Town Hall, then hit **Info**.\n"
                    f"{emojis.red_arrow_right} **Upload** a screenshot of the Town Hall info popup here.\n\n"
                    "*See the example below for reference.*"
                )),
                Media(
                    items=[
                        MediaItem(
                            media="https://res.cloudinary.com/dxmtzuomk/image/upload/v1751550804/TH_Weight.png"),
                        ]
                ),
                Text(content=f"-# Requested by Kings Alliance FWA Recruitment"),
            ]
            
            # Add fallback mode warning if applicable
            if api_data.get('fallback_mode'):
                fwa_components.append(Text(content=(
                    "-# ⚠️ Limited ticket data available. Please also provide your player tag in chat."
                )))
            
            components = [
                Container(
                    accent_color=GOLD_ACCENT,
                    components=fwa_components
                )
            ]

            # Send chocolate link to thread using centralized function
            if player_data and thread_id and HAS_FWA_CHOCOLATE:
                await send_chocolate_link(
                    bot=event.app,
                    channel_id=thread_id,
                    player_tag=player_data.tag,
                    player_name=player_data.name
                )
                print(f"[DEBUG] Sent chocolate link to thread {thread_id}")
        else:
            # Regular ticket - existing screenshot request
            regular_components = [
                Text(content=f"<@{api_data.get('user', '')}>\n\n"),
                Separator(divider=True, spacing=hikari.SpacingType.LARGE),
                Text(content=(
                    f"{emojis.Alert_Strobing} **SCREENSHOT REQUIRED** {emojis.Alert_Strobing}\n"
                    "-# Provide a screenshot of your base."
                )),
                Media(items=[MediaItem(media="assets/Red_Footer.png")]),
                Text(content=(
                    f"-# **Kings Alliance Recruitment** - Your base layout says a lot about you—make it a good one!"
                ))
            ]
            
            # Add fallback mode warning if applicable
            if api_data.get('fallback_mode'):
                regular_components.append(Text(content=(
                    "-# ⚠️ Limited ticket data available. Please also provide your player tag in chat."
                )))
            
            components = [
                Container(
                    accent_color=DARK_MAGENTA_ACCENT,
                    components=regular_components
                )
            ]
    else:
        # Fallback error message if something went wrong
        # Try to get user ID from the channel name pattern
        user_mention = ""
        if api_data and api_data.get('user'):
            user_mention = f"<@{api_data.get('user')}> "

        components = [
            Container(
                accent_color=DARK_MAGENTA_ACCENT,
                components=[
                    Text(content=f"{emojis.Alert} **Error Processing Ticket** {emojis.Alert}"),
                    Separator(divider=True),
                    Text(content=(
                        f"{user_mention}**Channel ID:** `{channel_id}`\n"
                        f"**Thread ID:** `{thread_id if thread_id else 'No thread found'}`\n\n"
                        f"**Status:** {'❌ Failed to store in database' if api_data else '❌ API unavailable'}\n\n"
                        f"Please contact an administrator if this issue persists."
                    )),
                    Media(items=[MediaItem(media="assets/Red_Footer.png")])
                ]
            )
        ]

    # Send message in the new channel
    try:
        await event.app.rest.create_message(
            channel=event.channel.id,
            components=components,
            user_mentions=True  # Enable user mentions so the ping works
        )
        print(f"[DEBUG] Successfully sent message to channel {event.channel.id}")

        # Early detection: Check if candidate is already in a family clan
        # Run this in background after a small delay to ensure everything is initialized
        async def check_family_clan_membership():
            try:
                # Small delay to ensure ticket is fully initialized
                await asyncio.sleep(2)

                # Only check if we have player data and thread_id
                if not player_data or not thread_id or not mongo_client:
                    return

                # Get all family clans
                family_clans = await mongo_client.clans.find().to_list(length=None)
                if not family_clans:
                    return

                # Create lookup dict
                family_clan_lookup = {clan["tag"]: clan for clan in family_clans}

                # Check if player is in a family clan
                if player_data.clan and player_data.clan.tag in family_clan_lookup:
                    clan_data = family_clan_lookup[player_data.clan.tag]

                    # Send early detection alert to thread
                    alert_content = (
                        f"⚠️ **EARLY DETECTION:** Candidate's account is already in a family clan:\n\n"
                        f"• **{player_data.name}** (`{player_data.tag}`) is in **{clan_data.get('name', player_data.clan.name)}**\n"
                    )

                    if clan_data.get('leader_id') and clan_data.get('leader_role_id'):
                        alert_content += f"  → Contact: <@{clan_data['leader_id']}> and <@&{clan_data['leader_role_id']}>\n\n"

                    alert_content += (
                        "This candidate may be trying to transfer between family clans.\n"
                        "Please verify with their current leadership before proceeding."
                    )

                    await event.app.rest.create_message(
                        channel=int(thread_id),
                        content=alert_content,
                        role_mentions=True
                    )

                    print(f"[Early Detection] {player_data.name} found in family clan {clan_data.get('name')}")

            except Exception as e:
                print(f"[Early Detection] Error checking family clan membership: {e}")

        # Run the check in background
        asyncio.create_task(check_family_clan_membership())

    except Exception as e:
        print(f"[ERROR] Failed to send message to channel {event.channel.id}: {e}")