import asyncio
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List

import hikari
import lightbulb
import asyncpraw
import asyncprawcore

from dotenv import load_dotenv

load_dotenv()

from hikari.impl import (
    ContainerComponentBuilder as Container,
    SectionComponentBuilder as Section,
    TextDisplayComponentBuilder as Text,
    SeparatorComponentBuilder as Separator,
    MediaGalleryComponentBuilder as Media,
    MediaGalleryItemBuilder as MediaItem,
    MessageActionRowBuilder as ActionRow,
    LinkButtonBuilder as LinkButton,
    ThumbnailComponentBuilder as Thumbnail,
)

from utils.mongo import MongoClient
from utils.constants import DARK_MAGENTA_ACCENT

loader = lightbulb.Loader()

# Configuration
REDDIT_CHECK_INTERVAL = 60
DISCORD_CHANNEL_ID = 1436175845600526531
POINTS_CHANNEL_ID = 1436169870273413169
MONITORED_SUBREDDIT = "ClashOfClansRecruit"
SEARCH_KEYWORDS = ["Kings Alliance", "Kings Aliance", "King's Alliance"]  # Handle typos
REDDIT_POST_POINTS = 5

# Debug mode
DEBUG_MODE = os.getenv("CLAN_POST_DEBUG", "False").lower() == "true"


def debug_print(*args, **kwargs):
    """Only print if DEBUG_MODE is enabled"""
    if DEBUG_MODE:
        print(f"[Clan Post Monitor] {args[0]}", *args[1:], **kwargs)


# Global variables
reddit_monitor_task = None
bot_instance = None
mongo_client = None
reddit_instance = None
reddit_instance_created_at = None  # Track when Reddit instance was created


def extract_clan_tags(text: str) -> List[str]:
    """Extract potential clan tags from text (format: #XXXXXXXXX)"""
    # Match hashtags with 8-9 alphanumeric characters (typical COC clan tag format)
    pattern = r'#[A-Z0-9]{8,9}'
    tags = re.findall(pattern, text.upper())
    debug_print(f"Extracted tags from '{text}': {tags}")
    return tags


async def get_clan_by_tag_from_db(mongo: MongoClient, tag: str) -> Optional[Dict]:
    """Get clan data from MongoDB by tag"""
    # Remove # if present
    clean_tag = tag.replace("#", "")

    # Try with and without hashtag
    clan = await mongo.clans.find_one({"tag": f"#{clean_tag}"})
    if not clan:
        clan = await mongo.clans.find_one({"tag": clean_tag})

    return clan


async def check_and_refresh_reddit_connection():
    """Check Reddit connection health and refresh if needed"""
    global reddit_instance, reddit_instance_created_at
    
    try:
        # Check if we need to refresh (every 30 minutes)
        now = datetime.now(timezone.utc)
        if reddit_instance_created_at:
            time_since_creation = (now - reddit_instance_created_at).total_seconds()
            if time_since_creation > 1800:  # 30 minutes
                debug_print(f"Reddit instance is {time_since_creation:.0f} seconds old, refreshing...")
                if reddit_instance:
                    await reddit_instance.close()
                reddit_instance = await initialize_reddit()
                reddit_instance_created_at = now if reddit_instance else None
                return reddit_instance is not None
        
        # Test the connection
        if reddit_instance:
            try:
                # Simple test - try to get subreddit info
                test_subreddit = await reddit_instance.subreddit(MONITORED_SUBREDDIT, fetch=True)
                return True
            except Exception as e:
                debug_print(f"Reddit connection test failed: {e}")
                # Try to reconnect
                if reddit_instance:
                    await reddit_instance.close()
                reddit_instance = await initialize_reddit()
                reddit_instance_created_at = now if reddit_instance else None
                return reddit_instance is not None
        else:
            # No instance, try to create one
            reddit_instance = await initialize_reddit()
            reddit_instance_created_at = now if reddit_instance else None
            return reddit_instance is not None
            
    except Exception as e:
        debug_print(f"Error in connection check: {e}")
        return False


async def create_points_notification(clan_data: Dict) -> List[Container]:
    """Create the points award notification"""
    clan_name = clan_data.get("name", "Unknown Clan")

    components = [
        Container(
            accent_color=DARK_MAGENTA_ACCENT,
            components=[
                Section(
                    components=[
                        Text(content=f"## {clan_name} +5"),
                        Text(content=(
                            f"• **{clan_name}** was awarded +5 points for posting on Reddit.\n"
                            f"• Clan now has {clan_data.get('points', 0) + 5:.1f} points."
                        )),
                    ],
                    accessory=Thumbnail(
                        media="https://res.cloudinary.com/dxmtzuomk/image/upload/v1752266736/misc_images/Reddit.png")
                ),
            ]
        )
    ]

    return components


async def create_reddit_post_notification(post, clan_data: Dict) -> List[Container]:
    """Create the Discord notification for a Reddit post"""
    # Format the post time
    post_timestamp = int(post.created_utc)

    # Get clan info
    clan_name = clan_data.get("name", "Unknown Clan")
    clan_tag = clan_data.get("tag", "#UNKNOWN")
    banner_url = clan_data.get("banner", None)

    # Build components
    components = [
        Container(
            accent_color=DARK_MAGENTA_ACCENT,
            components=[
                Section(
                    components=[
                        Text(content=f"## 📢 {clan_name} Weekly Reddit Post"),
                        Text(content=(
                            f"{clan_name} has submitted their weekly Reddit post!\n\n"
                            f"**Clan:** {clan_name} ({clan_tag})\n"
                            f"**Posted:** <t:{post_timestamp}:f>\n"
                            f"**Subreddit:** r/{post.subreddit.display_name}\n"
                            f"**Title:** {post.title}\n\n"
                            "Click the button below to check that it meets all posting requirements, "
                            "and don't forget to upvote to show your support!"
                        )),
                    ],
                    accessory=Thumbnail(
                        media="https://res.cloudinary.com/dxmtzuomk/image/upload/v1752266736/misc_images/Reddit.png")
                ),
                Media(items=[MediaItem(media=banner_url if banner_url else "assets/Red_Footer.png")]),
                ActionRow(
                    components=[
                        LinkButton(
                            url=f"https://reddit.com{post.permalink}",
                            label="View Post",
                            emoji="🔗"
                        )
                    ]
                ),
                Text(content=f"-# Posted by u/{post.author.name} on <t:{post_timestamp}:f>")
            ]
        )
    ]

    return components


async def check_reddit_posts(startup_mode=False):
    """Check Reddit for new posts matching our criteria"""
    global reddit_instance, mongo_client, bot_instance

    if not mongo_client or not bot_instance:
        debug_print("Missing required instances")
        return

    # Check and refresh Reddit connection if needed
    if not await check_and_refresh_reddit_connection():
        debug_print("Failed to establish Reddit connection")
        return

    try:
        # Get last checked timestamp from MongoDB BEFORE we start
        last_check_doc = await mongo_client.reddit_monitor.find_one({"_id": "last_check"})
        last_check_time = last_check_doc.get("timestamp", 0) if last_check_doc else 0
        
        # On startup mode, check posts from last 48 hours
        now = datetime.now(timezone.utc).timestamp()
        check_start_time = now  # Store when we started checking
        
        if startup_mode:
            print(f"[Clan Post Monitor] Startup mode: checking posts from last 48 hours")
            last_check_time = now - 172800  # 48 hours in seconds
            print(f"[Clan Post Monitor] Will check posts newer than {datetime.fromtimestamp(last_check_time, tz=timezone.utc).isoformat()}")
        elif last_check_time == 0 or (now - last_check_time) > 86400:  # 86400 seconds = 24 hours
            debug_print("First run or stale timestamp detected, checking posts from last 24 hours")
            last_check_time = now - 86400  # Check posts from last 24 hours
        
        # Update timestamp at the START (only if not in startup mode)
        # This prevents missing posts if there's an error during processing
        if not startup_mode:
            await mongo_client.reddit_monitor.update_one(
                {"_id": "last_check"},
                {"$set": {
                    "timestamp": check_start_time,
                    "last_check_start": check_start_time,
                    "status": "checking"
                }},
                upsert=True
            )

        # Get subreddit
        subreddit = await reddit_instance.subreddit(MONITORED_SUBREDDIT)

        # Get recent posts (increase limit on startup to catch older posts)
        post_limit = 100 if startup_mode else 50
        new_posts = [post async for post in subreddit.new(limit=post_limit)]

        debug_print(f"Checking {len(new_posts)} posts. Keywords: {', '.join(SEARCH_KEYWORDS)}")
        debug_print(
            f"Last check: {datetime.fromtimestamp(last_check_time) if last_check_time else 'Never'}")

        # Process posts from oldest to newest
        posts_checked = 0
        posts_matched = 0
        for post in reversed(new_posts):
            debug_print(f"Checking post: '{post.title}' (created: {datetime.fromtimestamp(post.created_utc)})")
            
            # Skip if we've already processed this post
            if post.created_utc <= last_check_time:
                debug_print(f"  -> Skipping: Post created before last check ({datetime.fromtimestamp(last_check_time)})")
                continue
            
            posts_checked += 1

            # Check if title contains our keywords
            title_lower = post.title.lower()
            keyword_found = any(keyword.lower() in title_lower for keyword in SEARCH_KEYWORDS)
            
            if keyword_found:
                matching_keyword = next(keyword for keyword in SEARCH_KEYWORDS if keyword.lower() in title_lower)
                debug_print(f"  -> Match found! Keyword: '{matching_keyword}' in title: '{post.title}'")
                posts_matched += 1

                # Extract clan tags from title
                clan_tags = extract_clan_tags(post.title)

                # Process each clan tag found
                for tag in clan_tags:
                    # Check if clan exists in our database
                    clan_data = await get_clan_by_tag_from_db(mongo_client, tag)

                    if clan_data:
                        debug_print(f"Found clan in database: {clan_data.get('name')} ({tag})")

                        # Check if we've already notified about this post
                        notification_id = f"{post.id}_{tag}"
                        existing_notification = await mongo_client.reddit_notifications.find_one({
                            "_id": notification_id
                        })

                        if not existing_notification:
                            # Create and send notification
                            components = await create_reddit_post_notification(post, clan_data)

                            try:
                                await bot_instance.rest.create_message(
                                    channel=DISCORD_CHANNEL_ID,
                                    components=components
                                )

                                # Award points to the clan
                                current_points = clan_data.get("points", 0)
                                new_points = current_points + REDDIT_POST_POINTS

                                await mongo_client.clans.update_one(
                                    {"tag": tag},
                                    {"$set": {"points": new_points}}
                                )

                                debug_print(
                                    f"Awarded {REDDIT_POST_POINTS} points to {clan_data.get('name')} - Total: {new_points}")

                                # Send points notification
                                points_components = await create_points_notification(clan_data)
                                await bot_instance.rest.create_message(
                                    channel=POINTS_CHANNEL_ID,
                                    components=points_components
                                )

                                # Mark as notified
                                await mongo_client.reddit_notifications.insert_one({
                                    "_id": notification_id,
                                    "post_id": post.id,
                                    "clan_tag": tag,
                                    "points_awarded": REDDIT_POST_POINTS,
                                    "notified_at": datetime.now(timezone.utc).isoformat()
                                })

                                debug_print(f"Sent notification for clan {tag}")
                            except Exception as e:
                                debug_print(f"Error sending notification: {e}")
                    else:
                        debug_print(f"  -> Clan tag {tag} not found in database")
            else:
                debug_print(f"  -> No matching keywords found in title")

        # Log summary
        if startup_mode:
            print(f"[Clan Post Monitor] Startup check complete: {posts_checked} posts checked, {posts_matched} matches found")
        
        # Update completion status (but don't change timestamp - it was set at start)
        if not startup_mode:
            await mongo_client.reddit_monitor.update_one(
                {"_id": "last_check"},
                {"$set": {
                    "last_check_complete": datetime.now(timezone.utc).timestamp(),
                    "status": "completed",
                    "posts_checked": posts_checked,
                    "posts_matched": posts_matched
                }},
                upsert=True
            )

    except asyncprawcore.exceptions.ResponseException as e:
        debug_print(f"Reddit API error: {e}")
    except Exception as e:
        debug_print(f"Error checking Reddit: {type(e).__name__}: {e}")


async def reddit_monitor_loop():
    """Main loop that monitors Reddit"""
    debug_print("Starting Reddit monitoring loop...")
    
    # Run initial check immediately on startup
    try:
        print("[Clan Post Monitor] Running initial startup check for posts from last 48 hours...")
        await check_reddit_posts(startup_mode=True)
    except Exception as e:
        print(f"[Clan Post Monitor] Error in startup check: {type(e).__name__}: {e}")

    while True:
        try:
            await check_reddit_posts()
            await asyncio.sleep(REDDIT_CHECK_INTERVAL)

        except asyncio.CancelledError:
            debug_print("Monitor loop cancelled")
            break
        except Exception as e:
            debug_print(f"Error in monitor loop: {type(e).__name__}: {e}")
            await asyncio.sleep(60)  # Wait a minute before retrying


async def initialize_reddit():  # Note: async
    """Initialize Reddit instance with detailed debugging"""
    global reddit_instance_created_at
    
    try:
        # Debug: Check if env vars are loaded
        client_id = os.getenv("REDDIT_CLIENT_ID")
        client_secret = os.getenv("REDDIT_CLIENT_SECRET")
        user_agent = os.getenv("REDDIT_USER_AGENT", "KingsAllianceBot/1.0")

        # print(f"[REDDIT DEBUG] Client ID: {client_id[:10]}..." if client_id else "[REDDIT DEBUG] Client ID is None!")
        # print(f"[REDDIT DEBUG] Secret exists: {bool(client_secret)}")
        # print(f"[REDDIT DEBUG] User Agent: {user_agent}")

        # Try to create Reddit instance
        # print("[REDDIT DEBUG] Creating Reddit instance...")
        reddit = asyncpraw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent
        )
        # print("[REDDIT DEBUG] Reddit instance created")

        # Test the connection
        # print(f"[REDDIT DEBUG] Testing connection to r/{MONITORED_SUBREDDIT}...")
        test_subreddit = await reddit.subreddit(MONITORED_SUBREDDIT)
        subreddit_name = test_subreddit.display_name
        # print(f"[REDDIT DEBUG] Successfully connected! Subreddit: {subreddit_name}")

        # Set creation timestamp
        reddit_instance_created_at = datetime.now(timezone.utc)
        debug_print(f"Reddit connection successful, instance created at {reddit_instance_created_at.isoformat()}")
        return reddit

    except Exception as e:
        print(f"[REDDIT DEBUG] Exception type: {type(e).__name__}")
        print(f"[REDDIT DEBUG] Exception message: {str(e)}")

        # Print full traceback
        import traceback
        print("[REDDIT DEBUG] Full traceback:")
        traceback.print_exc()

        debug_print(f"Failed to initialize Reddit: {type(e).__name__}: {e}")
        return None


@loader.listener(hikari.StartedEvent)
@lightbulb.di.with_di
async def on_bot_started(
        event: hikari.StartedEvent,
        mongo: MongoClient = lightbulb.di.INJECTED
) -> None:
    """Start the Reddit monitor when bot starts"""
    global reddit_monitor_task, bot_instance, mongo_client, reddit_instance

    # Store instances
    bot_instance = event.app
    mongo_client = mongo

    # Initialize Reddit
    reddit_instance = await initialize_reddit()  # Add await

    if reddit_instance:
        # Start monitoring task
        reddit_monitor_task = asyncio.create_task(reddit_monitor_loop())
        print(f"[Clan Post Monitor] Task started at {datetime.now(timezone.utc).isoformat()}")
        print(f"[Clan Post Monitor] Monitoring r/{MONITORED_SUBREDDIT} for keywords: {', '.join(SEARCH_KEYWORDS)}")
        print(f"[Clan Post Monitor] Check interval: {REDDIT_CHECK_INTERVAL} seconds")
        debug_print("Clan Post Monitor task started!")
    else:
        print("[Clan Post Monitor] Failed to initialize Reddit API. Check your credentials.")


@loader.listener(hikari.StoppingEvent)
async def on_bot_stopping(event: hikari.StoppingEvent) -> None:
    """Stop the Reddit monitor when bot stops"""
    global reddit_monitor_task, reddit_instance

    if reddit_monitor_task and not reddit_monitor_task.done():
        reddit_monitor_task.cancel()
        try:
            await reddit_monitor_task
        except asyncio.CancelledError:
            pass
        debug_print("Clan Post Monitor task cancelled")

    # Close Reddit connection
    if reddit_instance:
        await reddit_instance.close()


# Check if Reddit debug commands are enabled
ENABLE_REDDIT_DEBUG_COMMANDS = os.getenv("ENABLE_REDDIT_DEBUG_COMMANDS", "false").lower() == "true"

if ENABLE_REDDIT_DEBUG_COMMANDS:
    @loader.command
    class ClanPostDebug(
        lightbulb.SlashCommand,
        name="clan-post-debug",
        description="Toggle Clan Post Monitor debug mode",
        default_member_permissions=hikari.Permissions.ADMINISTRATOR
    ):
        @lightbulb.invoke
        async def invoke(self, ctx: lightbulb.Context) -> None:
            global DEBUG_MODE
            DEBUG_MODE = not DEBUG_MODE
            status = "ON" if DEBUG_MODE else "OFF"
            await ctx.respond(f"🔧 Clan Post Monitor debug mode: **{status}**", ephemeral=True)


    @loader.command
    class ClanPostTest(
        lightbulb.SlashCommand,
        name="clan-post-test",
        description="Manually trigger clan post check",
        default_member_permissions=hikari.Permissions.ADMINISTRATOR
    ):
        @lightbulb.invoke
        async def invoke(self, ctx: lightbulb.Context) -> None:
            await ctx.defer(ephemeral=True)

            try:
                await check_reddit_posts()
                await ctx.respond("✅ Clan post check completed!")
            except Exception as e:
                await ctx.respond(f"❌ Clan post check failed: {str(e)}")


    @loader.command
    class ClanPostCheckUrl(
        lightbulb.SlashCommand,
        name="clan-post-check-url",
        description="Check a specific Reddit post URL for clan recruitment",
        default_member_permissions=hikari.Permissions.ADMINISTRATOR
    ):
        url = lightbulb.string("url", "The Reddit post URL to check")

        @lightbulb.invoke
        @lightbulb.di.with_di
        async def invoke(self, ctx: lightbulb.Context, mongo: MongoClient = lightbulb.di.INJECTED) -> None:
            await ctx.defer(ephemeral=True)

            try:
                global reddit_instance
                if not reddit_instance:
                    await ctx.respond("❌ Reddit instance not initialized")
                    return

                # Extract post ID from URL
                import re
                url_pattern = r'reddit\.com/r/\w+/comments/([a-z0-9]+)'
                match = re.search(url_pattern, self.url)
                
                if not match:
                    await ctx.respond("❌ Invalid Reddit URL format")
                    return

                post_id = match.group(1)
                
                # Get the post
                post = await reddit_instance.submission(id=post_id)
                await post.load()  # Load post data
                
                response = f"**Post Title:** {post.title}\n"
                response += f"**Author:** u/{post.author.name if post.author else '[deleted]'}\n"
                response += f"**Posted:** <t:{int(post.created_utc)}:f>\n\n"
                
                # Check if title contains keywords
                title_lower = post.title.lower()
                keyword_found = any(keyword.lower() in title_lower for keyword in SEARCH_KEYWORDS)
                
                if keyword_found:
                    matching_keyword = next(keyword for keyword in SEARCH_KEYWORDS if keyword.lower() in title_lower)
                    response += f"✅ **Keyword Found:** '{matching_keyword}'\n\n"
                    
                    # Extract clan tags
                    clan_tags = extract_clan_tags(post.title)
                    response += f"**Clan Tags Found:** {', '.join(clan_tags) if clan_tags else 'None'}\n\n"
                    
                    # Check each clan tag in database
                    if clan_tags:
                        for tag in clan_tags:
                            clan_data = await get_clan_by_tag_from_db(mongo, tag)
                            if clan_data:
                                response += f"✅ **{tag}**: {clan_data.get('name')} (found in database)\n"
                                
                                # Check if already notified
                                notification_id = f"{post.id}_{tag}"
                                existing = await mongo.reddit_notifications.find_one({"_id": notification_id})
                                if existing:
                                    response += f"   ⚠️ Already notified on {existing.get('notified_at')}\n"
                                else:
                                    response += f"   ✨ Not yet notified\n"
                            else:
                                response += f"❌ **{tag}**: Not found in database\n"
                    else:
                        response += "❌ No clan tags found in title\n"
                else:
                    response += f"❌ **No matching keywords found**\n"
                    response += f"Looking for: {', '.join(SEARCH_KEYWORDS)}\n"
                
                await ctx.respond(response)
                
            except Exception as e:
                await ctx.respond(f"❌ Error checking post: {str(e)}")


    @loader.command
    class ClanPostTimestamp(
        lightbulb.SlashCommand,
        name="clan-post-timestamp",
        description="Check or reset the Reddit monitor timestamp",
        default_member_permissions=hikari.Permissions.ADMINISTRATOR
    ):
        reset = lightbulb.boolean("reset", "Reset the timestamp to check all recent posts", default=False)

        @lightbulb.invoke
        @lightbulb.di.with_di
        async def invoke(self, ctx: lightbulb.Context, mongo: MongoClient = lightbulb.di.INJECTED) -> None:
            await ctx.defer(ephemeral=True)

            try:
                if self.reset:
                    # Reset to 24 hours ago
                    new_timestamp = (datetime.now(timezone.utc) - timedelta(days=1)).timestamp()
                    await mongo.reddit_monitor.update_one(
                        {"_id": "last_check"},
                        {"$set": {"timestamp": new_timestamp}},
                        upsert=True
                    )
                    await ctx.respond(f"✅ Reset timestamp to 24 hours ago\n"
                                    f"New timestamp: <t:{int(new_timestamp)}:f>")
                else:
                    # Check current timestamp
                    last_check_doc = await mongo.reddit_monitor.find_one({"_id": "last_check"})
                    if last_check_doc:
                        timestamp = last_check_doc.get("timestamp", 0)
                        if timestamp:
                            await ctx.respond(f"📅 Last check timestamp: <t:{int(timestamp)}:f>\n"
                                            f"That's {datetime.now(timezone.utc).timestamp() - timestamp:.0f} seconds ago")
                        else:
                            await ctx.respond("❌ No timestamp found in database")
                    else:
                        await ctx.respond("❌ No last check record found")
            except Exception as e:
                await ctx.respond(f"❌ Error: {str(e)}")


    @loader.command
    class ClanPostCheckConnection(
        lightbulb.SlashCommand,
        name="clan-post-check-connection",
        description="Check Reddit connection health and refresh if needed",
        default_member_permissions=hikari.Permissions.ADMINISTRATOR
    ):
        @lightbulb.invoke
        async def invoke(self, ctx: lightbulb.Context) -> None:
            await ctx.defer(ephemeral=True)
            
            global reddit_instance, reddit_instance_created_at
            
            response = "## 🔍 Reddit Connection Check\n\n"
            
            # Check current status
            if reddit_instance:
                response += "✅ **Reddit instance exists**\n"
                if reddit_instance_created_at:
                    age = (datetime.now(timezone.utc) - reddit_instance_created_at).total_seconds()
                    response += f"📅 **Instance age:** {age:.0f} seconds ({age/60:.1f} minutes)\n"
                    response += f"🕐 **Created at:** <t:{int(reddit_instance_created_at.timestamp())}:f>\n\n"
                else:
                    response += "⚠️ **Creation time unknown**\n\n"
            else:
                response += "❌ **No Reddit instance**\n\n"
            
            # Test connection
            response += "**Testing connection...**\n"
            
            if await check_and_refresh_reddit_connection():
                response += "✅ Connection test passed!\n"
                
                # Show updated status if refreshed
                if reddit_instance and reddit_instance_created_at:
                    new_age = (datetime.now(timezone.utc) - reddit_instance_created_at).total_seconds()
                    if new_age < 60:  # Recently refreshed
                        response += "♻️ Connection was refreshed!\n"
            else:
                response += "❌ Connection test failed!\n"
            
            await ctx.respond(response)


    @loader.command
    class ClanPostProcessUrl(
        lightbulb.SlashCommand,
        name="clan-post-process-url",
        description="Manually process a Reddit post URL and award points",
        default_member_permissions=hikari.Permissions.ADMINISTRATOR
    ):
        url = lightbulb.string("url", "The Reddit post URL to process")

        @lightbulb.invoke
        @lightbulb.di.with_di
        async def invoke(self, ctx: lightbulb.Context, mongo: MongoClient = lightbulb.di.INJECTED) -> None:
            await ctx.defer(ephemeral=True)

            try:
                global reddit_instance, bot_instance
                if not reddit_instance:
                    await ctx.respond("❌ Reddit instance not initialized")
                    return

                # Extract post ID from URL
                import re
                url_pattern = r'reddit\.com/r/\w+/comments/([a-z0-9]+)'
                match = re.search(url_pattern, self.url)
                
                if not match:
                    await ctx.respond("❌ Invalid Reddit URL format")
                    return

                post_id = match.group(1)
                
                # Get the post
                post = await reddit_instance.submission(id=post_id)
                await post.load()  # Load post data
                
                # Check if title contains keywords
                title_lower = post.title.lower()
                keyword_found = any(keyword.lower() in title_lower for keyword in SEARCH_KEYWORDS)
                
                if not keyword_found:
                    await ctx.respond(f"❌ Post does not contain required keywords: {', '.join(SEARCH_KEYWORDS)}")
                    return
                
                # Extract clan tags
                clan_tags = extract_clan_tags(post.title)
                if not clan_tags:
                    await ctx.respond("❌ No clan tags found in post title")
                    return
                
                processed_clans = []
                already_processed = []
                
                for tag in clan_tags:
                    # Check if clan exists in database
                    clan_data = await get_clan_by_tag_from_db(mongo, tag)
                    
                    if not clan_data:
                        continue
                    
                    # Check if already notified
                    notification_id = f"{post.id}_{tag}"
                    existing_notification = await mongo.reddit_notifications.find_one({
                        "_id": notification_id
                    })
                    
                    if existing_notification:
                        already_processed.append(f"{clan_data.get('name')} ({tag})")
                        continue
                    
                    # Process the post
                    # Create and send notification
                    components = await create_reddit_post_notification(post, clan_data)
                    
                    try:
                        await bot_instance.rest.create_message(
                            channel=DISCORD_CHANNEL_ID,
                            components=components
                        )
                        
                        # Award points to the clan
                        current_points = clan_data.get("points", 0)
                        new_points = current_points + REDDIT_POST_POINTS
                        
                        await mongo.clans.update_one(
                            {"tag": tag},
                            {"$set": {"points": new_points}}
                        )
                        
                        # Send points notification
                        points_components = await create_points_notification(clan_data)
                        await bot_instance.rest.create_message(
                            channel=POINTS_CHANNEL_ID,
                            components=points_components
                        )
                        
                        # Mark as notified
                        await mongo.reddit_notifications.insert_one({
                            "_id": notification_id,
                            "post_id": post.id,
                            "clan_tag": tag,
                            "points_awarded": REDDIT_POST_POINTS,
                            "notified_at": datetime.now(timezone.utc).isoformat(),
                            "manually_processed": True,
                            "processed_by": str(ctx.user.id)
                        })
                        
                        processed_clans.append(f"{clan_data.get('name')} ({tag}) - +{REDDIT_POST_POINTS} points")
                        
                    except Exception as e:
                        await ctx.respond(f"❌ Error processing {tag}: {str(e)}")
                        return
                
                # Build response
                response = "## 📋 Manual Reddit Post Processing\n\n"
                response += f"**Post:** {post.title}\n"
                response += f"**Author:** u/{post.author.name if post.author else '[deleted]'}\n\n"
                
                if processed_clans:
                    response += "✅ **Successfully Processed:**\n"
                    for clan in processed_clans:
                        response += f"• {clan}\n"
                
                if already_processed:
                    response += "\n⚠️ **Already Processed:**\n"
                    for clan in already_processed:
                        response += f"• {clan}\n"
                
                if not processed_clans and not already_processed:
                    response += "❌ No clans found in our database from this post."
                
                await ctx.respond(response)
                
            except Exception as e:
                await ctx.respond(f"❌ Error processing post: {str(e)}")