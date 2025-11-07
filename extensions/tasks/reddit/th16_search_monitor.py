import asyncio
import os
import re
from datetime import datetime, timezone
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
from utils.constants import RED_ACCENT

loader = lightbulb.Loader()

# Configuration
REDDIT_CHECK_INTERVAL = 60
DISCORD_CHANNEL_ID = 1436170049227460679  # TH16 recruitment notifications channel
PING_ROLE_ID = 1313898792046559302  # Role to ping for TH16 searches
MONITORED_SUBREDDIT = "ClashOfClansRecruit"

# Debug mode
DEBUG_MODE = os.getenv("TH16_SEARCH_DEBUG", "False").lower() == "true"


def debug_print(*args, **kwargs):
    """Only print if DEBUG_MODE is enabled"""
    if DEBUG_MODE:
        print(f"[TH16 Search Monitor] {args[0]}", *args[1:], **kwargs)


# Global variables
reddit_monitor_task = None
bot_instance = None
mongo_client = None
reddit_instance = None
reddit_instance_created_at = None  # Track when Reddit instance was created


def is_searching_post(title: str) -> bool:
    """Check if the post title starts with [Searching] (case insensitive)"""
    title_lower = title.lower().strip()
    return title_lower.startswith("[searching]") or title_lower.startswith("[searching ")


def contains_th16(text: str) -> bool:
    """Check if text contains TH16 or Town Hall 16 (case insensitive, ignoring spaces)"""
    text_lower = text.lower()

    # Check for TH16 (with or without spaces)
    th16_match = re.search(r'th\s*16', text_lower)
    if th16_match:
        debug_print(f"    Found TH16 match: '{th16_match.group()}'")
        return True

    # Check for Town Hall 16 (with flexible spacing)
    townhall_match = re.search(r'town\s*hall\s*16', text_lower)
    if townhall_match:
        debug_print(f"    Found Town Hall 16 match: '{townhall_match.group()}'")
        return True

    return False


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


async def create_th16_search_notification(post) -> List[Container]:
    """Create the Discord notification for a TH16 searching post"""
    # Format the post time
    post_timestamp = int(post.created_utc)

    # Extract any player tags mentioned in the post
    player_tags = re.findall(r'#[A-Z0-9]{8,9}', post.title.upper())
    player_tag_text = f"**Player Tag:** {', '.join(player_tags)}\n" if player_tags else ""

    # Process the post body
    post_body = post.selftext.strip() if post.selftext else ""

    # Build components
    components_list = [
        Text(content=f"<@&{PING_ROLE_ID}>"),
        Section(
            components=[
                Text(content="## 🔍 TH16 Player Looking for Clan"),
                Text(content=(
                    f"A TH16 player is searching for a clan to join!\n\n"
                    f"**Title:** {post.title}\n"
                    f"**Author:** u/{post.author.name if post.author else '[deleted]'}\n"
                    f"{player_tag_text}"
                    f"**Posted:** <t:{post_timestamp}:f>"
                )),
            ],
            accessory=Thumbnail(
                media="https://res.cloudinary.com/dxmtzuomk/image/upload/v1752266736/misc_images/Reddit.png"
            )
        ),
    ]

    # Add body as separate section if it exists
    if post_body:
        # Truncate to 300 characters for this style
        if len(post_body) > 300:
            body_display = post_body[:297] + "..."
        else:
            body_display = post_body

        components_list.append(Separator(divider=True, spacing=hikari.SpacingType.SMALL))
        components_list.append(
            Text(content=f"**Post Details:**\n```\n{body_display}\n```")
        )

    components_list.extend([
        ActionRow(
            components=[
                LinkButton(
                    url=f"https://reddit.com{post.permalink}",
                    label="View Post",
                    emoji="🔗"
                )
            ]
        ),
        Media(items=[MediaItem(media="assets/Red_Footer.png")]),
        Text(
            content=f"-# Posted by u/{post.author.name if post.author else '[deleted]'} on r/{post.subreddit.display_name}")
    ])

    components = [
        Container(
            accent_color=RED_ACCENT,
            components=components_list
        )
    ]

    return components


async def check_th16_posts():
    """Check Reddit for new TH16 searching posts"""
    global reddit_instance, mongo_client, bot_instance

    debug_print("Starting check_th16_posts()...")

    if not mongo_client:
        debug_print("ERROR: mongo_client is None!")
        return
    if not bot_instance:
        debug_print("ERROR: bot_instance is None!")
        return

    # Check and refresh Reddit connection if needed
    if not await check_and_refresh_reddit_connection():
        debug_print("Failed to establish Reddit connection")
        return

    debug_print("All instances are available, proceeding...")

    try:
        # Get last checked timestamp from MongoDB BEFORE we start
        last_check_doc = await mongo_client.reddit_monitor.find_one({"_id": "th16_last_check"})
        last_check_time = last_check_doc.get("timestamp", 0) if last_check_doc else 0

        # Store when we started checking
        now = datetime.now(timezone.utc).timestamp()
        check_start_time = now
        
        # If no last check or it's very old, check posts from last 24 hours
        if last_check_time == 0 or (now - last_check_time) > 86400:  # 86400 seconds = 24 hours
            debug_print("First run or stale timestamp detected, checking posts from last 24 hours")
            last_check_time = now - 86400
        
        # Update timestamp at the START
        # This prevents missing posts if there's an error during processing
        await mongo_client.reddit_monitor.update_one(
            {"_id": "th16_last_check"},
            {"$set": {
                "timestamp": check_start_time,
                "last_check_start": check_start_time,
                "status": "checking"
            }},
            upsert=True
        )

        # Get subreddit
        subreddit = await reddit_instance.subreddit(MONITORED_SUBREDDIT)

        # Get recent posts (last 25)
        new_posts = [post async for post in subreddit.new(limit=25)]

        debug_print(
            f"Checking {len(new_posts)} posts. Last check: {datetime.fromtimestamp(last_check_time) if last_check_time else 'Never'}"
        )

        # ENHANCED DEBUG: Show all posts
        debug_print("=== ALL POSTS IN SUBREDDIT ===")
        for i, post in enumerate(new_posts):
            debug_print(f"Post #{i + 1}: {post.title[:80]}... (created: {datetime.fromtimestamp(post.created_utc)})")

        # Process posts from oldest to newest
        matched_count = 0
        for post in reversed(new_posts):
            # Skip if we've already processed this post
            if post.created_utc <= last_check_time:
                debug_print(f"Skipping old post: {post.title[:50]}...")
                continue

            # ENHANCED DEBUG: Check each condition separately
            title_lower = post.title.lower().strip()
            is_searching = is_searching_post(post.title)
            has_th16 = contains_th16(post.title)

            # Always show what we're checking in debug mode
            if is_searching or has_th16:
                debug_print(f"\nChecking: {post.title}")
                debug_print(f"  - Lower title: '{title_lower}'")
                debug_print(f"  - Starts with [searching]: {is_searching}")
                debug_print(f"  - Contains TH16: {has_th16}")

            # Check if it's a searching post and contains TH16
            if is_searching and has_th16:
                matched_count += 1
                debug_print(f"✅ MATCH #{matched_count}! Found TH16 searching post: {post.title}")

                # Check if we've already notified about this post
                notification_id = f"th16_{post.id}"
                existing_notification = await mongo_client.reddit_notifications.find_one({
                    "_id": notification_id
                })

                if existing_notification:
                    debug_print(f"  → Already notified about this post")
                else:
                    # Create and send notification
                    components = await create_th16_search_notification(post)

                    try:
                        debug_print(f"  → Sending notification to channel {DISCORD_CHANNEL_ID}...")
                        await bot_instance.rest.create_message(
                            channel=DISCORD_CHANNEL_ID,
                            components=components,
                            role_mentions=True
                        )

                        # Mark as notified
                        await mongo_client.reddit_notifications.insert_one({
                            "_id": notification_id,
                            "post_id": post.id,
                            "post_title": post.title,
                            "author": post.author.name if post.author else "deleted",
                            "notified_at": datetime.now(timezone.utc).isoformat()
                        })

                        debug_print(
                            f"  → ✅ Sent notification for TH16 searching post by u/{post.author.name if post.author else '[deleted]'}")
                    except Exception as e:
                        debug_print(f"  → ❌ Error sending notification: {type(e).__name__}: {e}")

        debug_print(f"\n=== SUMMARY: Found {matched_count} matching posts ===")

        # Update completion status (but don't change timestamp - it was set at start)
        await mongo_client.reddit_monitor.update_one(
            {"_id": "th16_last_check"},
            {"$set": {
                "last_check_complete": datetime.now(timezone.utc).timestamp(),
                "status": "completed",
                "posts_checked": len(new_posts),
                "posts_matched": matched_count
            }},
            upsert=True
        )

    except asyncprawcore.exceptions.ResponseException as e:
        debug_print(f"Reddit API error: {e}")
    except Exception as e:
        debug_print(f"Error checking Reddit: {type(e).__name__}: {e}")


async def reddit_monitor_loop():
    """Main loop that monitors Reddit for TH16 posts"""
    debug_print("Starting TH16 Reddit monitoring loop...")

    while True:
        try:
            await check_th16_posts()
            await asyncio.sleep(REDDIT_CHECK_INTERVAL)

        except asyncio.CancelledError:
            debug_print("Monitor loop cancelled")
            break
        except Exception as e:
            debug_print(f"Error in monitor loop: {type(e).__name__}: {e}")
            await asyncio.sleep(60)  # Wait a minute before retrying


async def initialize_reddit():
    """Initialize Reddit instance with detailed debugging"""
    global reddit_instance_created_at
    
    try:
        # Debug: Check if env vars are loaded
        client_id = os.getenv("REDDIT_CLIENT_ID")
        client_secret = os.getenv("REDDIT_CLIENT_SECRET")
        user_agent = os.getenv("REDDIT_USER_AGENT", "KingsAllianceBot/1.0")

        # print(
        #     f"[TH16 REDDIT DEBUG] Client ID: {client_id[:10]}..." if client_id else "[TH16 REDDIT DEBUG] Client ID is None!")
        # print(f"[TH16 REDDIT DEBUG] Secret exists: {bool(client_secret)}")
        # print(f"[TH16 REDDIT DEBUG] User Agent: {user_agent}")

        # Try to create Reddit instance
        # print("[TH16 REDDIT DEBUG] Creating Reddit instance...")
        reddit = asyncpraw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent
        )
        # print("[TH16 REDDIT DEBUG] Reddit instance created")

        # Test the connection
        # print(f"[TH16 REDDIT DEBUG] Testing connection to r/{MONITORED_SUBREDDIT}...")
        test_subreddit = await reddit.subreddit(MONITORED_SUBREDDIT)
        subreddit_name = test_subreddit.display_name
        # print(f"[TH16 REDDIT DEBUG] Successfully connected! Subreddit: {subreddit_name}")

        # Set creation timestamp
        reddit_instance_created_at = datetime.now(timezone.utc)
        debug_print(f"Reddit connection successful, instance created at {reddit_instance_created_at.isoformat()}")
        return reddit

    except Exception as e:
        print(f"[TH16 REDDIT DEBUG] Exception type: {type(e).__name__}")
        print(f"[TH16 REDDIT DEBUG] Exception message: {str(e)}")

        # Print full traceback
        import traceback
        print("[TH16 REDDIT DEBUG] Full traceback:")
        traceback.print_exc()

        debug_print(f"Failed to initialize Reddit: {type(e).__name__}: {e}")
        return None


@loader.listener(hikari.StartedEvent)
@lightbulb.di.with_di
async def on_bot_started(
        event: hikari.StartedEvent,
        mongo: MongoClient = lightbulb.di.INJECTED
) -> None:
    """Start the TH16 Reddit monitor when bot starts"""
    global reddit_monitor_task, bot_instance, mongo_client, reddit_instance

    # Store instances
    bot_instance = event.app
    mongo_client = mongo

    # Initialize Reddit
    reddit_instance = await initialize_reddit()

    if reddit_instance:
        # Start monitoring task
        reddit_monitor_task = asyncio.create_task(reddit_monitor_loop())
        debug_print("TH16 Search Monitor task started!")
    else:
        print("[TH16 Search Monitor] Failed to initialize Reddit API. Check your credentials.")


@loader.listener(hikari.StoppingEvent)
async def on_bot_stopping(event: hikari.StoppingEvent) -> None:
    """Stop the TH16 Reddit monitor when bot stops"""
    global reddit_monitor_task, reddit_instance

    if reddit_monitor_task and not reddit_monitor_task.done():
        reddit_monitor_task.cancel()
        try:
            await reddit_monitor_task
        except asyncio.CancelledError:
            pass
        debug_print("TH16 Search Monitor task cancelled")

    # Close Reddit connection
    if reddit_instance:
        await reddit_instance.close()


# Check if Reddit debug commands are enabled
ENABLE_REDDIT_DEBUG_COMMANDS = os.getenv("ENABLE_REDDIT_DEBUG_COMMANDS", "false").lower() == "true"

if ENABLE_REDDIT_DEBUG_COMMANDS:
    @loader.command
    class TH16SearchDebug(
        lightbulb.SlashCommand,
        name="th16-search-debug",
        description="Toggle TH16 Search Monitor debug mode",
        default_member_permissions=hikari.Permissions.ADMINISTRATOR
    ):
        @lightbulb.invoke
        async def invoke(self, ctx: lightbulb.Context) -> None:
            global DEBUG_MODE
            DEBUG_MODE = not DEBUG_MODE
            status = "ON" if DEBUG_MODE else "OFF"
            # Also update the environment variable
            os.environ["TH16_SEARCH_DEBUG"] = "true" if DEBUG_MODE else "false"
            await ctx.respond(f"🔧 TH16 Search Monitor debug mode: **{status}**", ephemeral=True)


    @loader.command
    class TH16SearchTest(
        lightbulb.SlashCommand,
        name="th16-search-test",
        description="Manually trigger TH16 search check",
        default_member_permissions=hikari.Permissions.ADMINISTRATOR
    ):
        @lightbulb.invoke
        async def invoke(self, ctx: lightbulb.Context) -> None:
            await ctx.defer(ephemeral=True)

            try:
                await check_th16_posts()
                await ctx.respond("✅ TH16 search check completed!")
            except Exception as e:
                await ctx.respond(f"❌ TH16 search check failed: {str(e)}")


    @loader.command
    class TH16SearchStatus(
        lightbulb.SlashCommand,
        name="th16-search-status",
        description="Check TH16 Search Monitor status",
        default_member_permissions=hikari.Permissions.ADMINISTRATOR
    ):
        @lightbulb.invoke
        @lightbulb.di.with_di
        async def invoke(self, ctx: lightbulb.Context, mongo: MongoClient = lightbulb.di.INJECTED) -> None:
            await ctx.defer(ephemeral=True)

            status_lines = []

            # Check if monitor is running
            if reddit_monitor_task and not reddit_monitor_task.done():
                status_lines.append("✅ Monitor is running")
            else:
                status_lines.append("❌ Monitor is not running")

            # Check Reddit connection
            if reddit_instance:
                status_lines.append("✅ Reddit connection established")
            else:
                status_lines.append("❌ Reddit connection not established")

            # Check last check time
            last_check_doc = await mongo.reddit_monitor.find_one({"_id": "th16_last_check"})
            if last_check_doc:
                last_check_time = datetime.fromtimestamp(last_check_doc.get("timestamp", 0))
                status_lines.append(f"📅 Last check: <t:{int(last_check_doc.get('timestamp', 0))}:R>")
            else:
                status_lines.append("📅 Last check: Never")

            # Get recent notifications count
            recent_notifications = await mongo.reddit_notifications.count_documents({
                "_id": {"$regex": "^th16_"}
            })
            status_lines.append(f"📊 Total notifications sent: {recent_notifications}")

            await ctx.respond("\n".join(status_lines), ephemeral=True)


    @loader.command
    class TH16SearchTestTitle(
        lightbulb.SlashCommand,
        name="th16-search-test-title",
        description="Test if a title would match TH16 search criteria",
        default_member_permissions=hikari.Permissions.ADMINISTRATOR
    ):
        title = lightbulb.string(
            "title",
            "The post title to test"
        )

        @lightbulb.invoke
        async def invoke(self, ctx: lightbulb.Context) -> None:
            test_title = self.title

            # Test the conditions
            is_searching = is_searching_post(test_title)
            has_th16 = contains_th16(test_title)
            would_match = is_searching and has_th16

            response = f"**Testing:** `{test_title}`\n\n"
            response += f"Starts with [Searching]: {'✅ Yes' if is_searching else '❌ No'}\n"
            response += f"Contains TH16: {'✅ Yes' if has_th16 else '❌ No'}\n"
            response += f"**Would be detected:** {'✅ YES' if would_match else '❌ NO'}"

            await ctx.respond(response, ephemeral=True)


    @loader.command
    class TH16SearchReset(
        lightbulb.SlashCommand,
        name="th16-search-reset",
        description="Reset TH16 search timestamp to check all posts",
        default_member_permissions=hikari.Permissions.ADMINISTRATOR
    ):
        @lightbulb.invoke
        @lightbulb.di.with_di
        async def invoke(self, ctx: lightbulb.Context, mongo: MongoClient = lightbulb.di.INJECTED) -> None:
            await ctx.defer(ephemeral=True)

            # Delete the timestamp record
            result = await mongo.reddit_monitor.delete_one({"_id": "th16_last_check"})

            if result.deleted_count > 0:
                await ctx.respond(
                    "✅ TH16 search timestamp reset!\n"
                    "The next check will process ALL posts in the subreddit.\n"
                    "Use `/th16-search-test` to trigger an immediate check."
                )
            else:
                await ctx.respond(
                    "ℹ️ No timestamp to reset. The monitor will check all posts on next run."
                )


    @loader.command
    class TH16SearchForceCheck(
        lightbulb.SlashCommand,
        name="th16-search-force-check",
        description="Force check ALL posts regardless of timestamp (one-time bypass)",
        default_member_permissions=hikari.Permissions.ADMINISTRATOR
    ):
        @lightbulb.invoke
        async def invoke(self, ctx: lightbulb.Context) -> None:
            await ctx.defer(ephemeral=True)

            global reddit_instance, mongo_client, bot_instance

            if not reddit_instance or not mongo_client or not bot_instance:
                await ctx.respond("❌ Missing required instances!")
                return

            try:
                # Get subreddit
                subreddit = await reddit_instance.subreddit(MONITORED_SUBREDDIT)
                new_posts = [post async for post in subreddit.new(limit=25)]

                found_count = 0
                notified_count = 0

                # Process ALL posts without timestamp check
                for post in new_posts:
                    # Check if it's a searching post and contains TH16
                    if is_searching_post(post.title) and contains_th16(post.title):
                        found_count += 1

                        # Check if we've already notified about this post
                        notification_id = f"th16_{post.id}"
                        existing_notification = await mongo_client.reddit_notifications.find_one({
                            "_id": notification_id
                        })

                        if not existing_notification:
                            # Create and send notification
                            components = await create_th16_search_notification(post)

                            try:
                                await bot_instance.rest.create_message(
                                    channel=DISCORD_CHANNEL_ID,
                                    components=components,
                                    role_mentions=True
                                )

                                # Mark as notified
                                await mongo_client.reddit_notifications.insert_one({
                                    "_id": notification_id,
                                    "post_id": post.id,
                                    "post_title": post.title,
                                    "author": post.author.name if post.author else "deleted",
                                    "notified_at": datetime.now(timezone.utc).isoformat()
                                })

                                notified_count += 1
                            except Exception as e:
                                debug_print(f"Error sending notification: {e}")

                await ctx.respond(
                    f"✅ Force check completed!\n"
                    f"Found {found_count} TH16 searching posts\n"
                    f"Sent {notified_count} new notifications"
                )

            except Exception as e:
                await ctx.respond(f"❌ Error: {str(e)}")