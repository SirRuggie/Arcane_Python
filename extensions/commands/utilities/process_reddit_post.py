# extensions/commands/utilities/process_reddit_post.py
"""
Manual Reddit post processing command for utilities group.
Allows manual processing of specific Reddit post URLs.
"""

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
from utils.constants import DARK_MAGENTA_ACCENT, GREEN_ACCENT
from ..utilities import utilities

loader = lightbulb.Loader()

# Configuration
DISCORD_CHANNEL_ID = 1345229148880371765
POINTS_CHANNEL_ID = 1345589195695194113
SEARCH_KEYWORDS = ["Kings Alliance", "Kings Aliance", "King's Alliance"]  # Handle typos
REDDIT_POST_POINTS = 5


def extract_clan_tags(text: str) -> List[str]:
    """Extract potential clan tags from text (format: #XXXXXXXXX)"""
    # Match hashtags with 8-9 alphanumeric characters (typical COC clan tag format)
    pattern = r'#[A-Z0-9]{8,9}'
    tags = re.findall(pattern, text.upper())
    return tags


def extract_post_id_from_url(url: str) -> Optional[str]:
    """Extract Reddit post ID from URL"""
    # Reddit URL patterns:
    # https://www.reddit.com/r/subreddit/comments/postid/title/
    # https://reddit.com/r/subreddit/comments/postid/title/
    # https://redd.it/postid
    
    patterns = [
        r'reddit\.com/r/[^/]+/comments/([a-z0-9]+)',
        r'redd\.it/([a-z0-9]+)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url, re.IGNORECASE)
        if match:
            return match.group(1)
    
    return None


async def get_clan_by_tag_from_db(mongo: MongoClient, tag: str) -> Optional[Dict]:
    """Get clan data from MongoDB by tag"""
    # Remove # if present
    clean_tag = tag.replace("#", "")

    # Try with and without hashtag
    clan = await mongo.clans.find_one({"tag": f"#{clean_tag}"})
    if not clan:
        clan = await mongo.clans.find_one({"tag": clean_tag})

    return clan


async def initialize_reddit():
    """Initialize Reddit instance"""
    try:
        client_id = os.getenv("REDDIT_CLIENT_ID")
        client_secret = os.getenv("REDDIT_CLIENT_SECRET")
        user_agent = os.getenv("REDDIT_USER_AGENT", "KingsAllianceBot/1.0")

        if not client_id or not client_secret:
            raise ValueError("Reddit credentials not found in environment variables")

        reddit = asyncpraw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent
        )

        return reddit

    except Exception as e:
        print(f"Failed to initialize Reddit: {type(e).__name__}: {e}")
        return None


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


async def create_reddit_post_notification(post, clan_data: Dict, manual: bool = True) -> List[Container]:
    """Create the Discord notification for a Reddit post"""
    # Format the post time
    post_timestamp = int(post.created_utc)

    # Get clan info
    clan_name = clan_data.get("name", "Unknown Clan")
    clan_tag = clan_data.get("tag", "#UNKNOWN")
    banner_url = clan_data.get("banner", None)

    # Build components
    prefix = "🔧 Manually Processed: " if manual else ""
    
    components = [
        Container(
            accent_color=DARK_MAGENTA_ACCENT,
            components=[
                Section(
                    components=[
                        Text(content=f"## {prefix}📢 {clan_name} Weekly Reddit Post"),
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


@utilities.register()
class ProcessRedditPost(
    lightbulb.SlashCommand,
    name="process-reddit-post",
    description="Manually process a Reddit post for clan recognition and points"
):
    url = lightbulb.string(
        "url",
        "Reddit post URL to process"
    )
    
    @lightbulb.invoke
    async def invoke(
        self,
        ctx: lightbulb.Context,
        bot: hikari.GatewayBot = lightbulb.di.INJECTED,
        mongo: MongoClient = lightbulb.di.INJECTED
    ) -> None:
        """Manually process a Reddit post URL"""
        
        await ctx.defer(ephemeral=True)
        
        try:
            url = self.url
            
            # Extract post ID from URL
            post_id = extract_post_id_from_url(url)
            if not post_id:
                await ctx.respond("❌ Invalid Reddit URL format. Please provide a valid Reddit post URL.")
                return
            
            # Initialize Reddit
            reddit = await initialize_reddit()
            if not reddit:
                await ctx.respond("❌ Failed to connect to Reddit API. Please try again later.")
                return
            
            try:
                # Get the post
                post = await reddit.submission(post_id)
                await post.load()
                
                # Check if title contains our keywords
                title_lower = post.title.lower()
                keyword_found = any(keyword.lower() in title_lower for keyword in SEARCH_KEYWORDS)
                
                if not keyword_found:
                    await ctx.respond(
                        f"❌ Post doesn't contain any monitored keywords ({', '.join(SEARCH_KEYWORDS)}). "
                        f"Title: '{post.title}'"
                    )
                    await reddit.close()
                    return
                
                # Extract clan tags from title
                clan_tags = extract_clan_tags(post.title)
                
                if not clan_tags:
                    await ctx.respond(
                        f"❌ No clan tags found in post title. "
                        f"Title: '{post.title}'"
                    )
                    await reddit.close()
                    return
                
                processed_clans = []
                
                # Process each clan tag found
                for tag in clan_tags:
                    # Check if clan exists in our database
                    clan_data = await get_clan_by_tag_from_db(mongo, tag)
                    
                    if clan_data:
                        # Check if we've already notified about this post
                        notification_id = f"{post.id}_{tag}"
                        existing_notification = await mongo.reddit_notifications.find_one({
                            "_id": notification_id
                        })
                        
                        if existing_notification:
                            processed_clans.append(f"**{clan_data.get('name')} ({tag})** - Already processed")
                            continue
                        
                        # Create and send notification
                        components = await create_reddit_post_notification(post, clan_data, manual=True)
                        
                        try:
                            await bot.rest.create_message(
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
                            await bot.rest.create_message(
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
                                "processed_manually": True,
                                "processed_by": ctx.user.id
                            })
                            
                            processed_clans.append(f"**{clan_data.get('name')} ({tag})** - ✅ Processed successfully (+{REDDIT_POST_POINTS} points)")
                            
                        except Exception as e:
                            processed_clans.append(f"**{clan_data.get('name')} ({tag})** - ❌ Error: {str(e)}")
                    else:
                        processed_clans.append(f"**{tag}** - ❌ Not found in database")
                
                await reddit.close()
                
                # Build response - truncate if too long
                post_title = post.title[:100] + "..." if len(post.title) > 100 else post.title
                response = f"✅ **Reddit Post Processing Complete**\n\n"
                response += f"**Post:** {post_title}\n"
                response += f"**Author:** u/{post.author.name}\n"
                response += f"**Subreddit:** r/{post.subreddit.display_name}\n\n"
                response += f"**Results:**\n" + "\n".join(processed_clans)
                
                # Truncate if too long for Discord
                if len(response) > 1900:
                    response = response[:1900] + "\n... (truncated)"
                
                await ctx.respond(response)
                
            except asyncprawcore.exceptions.NotFound:
                await ctx.respond("❌ Reddit post not found. Please check the URL.")
                await reddit.close()
            except Exception as e:
                await ctx.respond(f"❌ Error fetching Reddit post: {str(e)}")
                await reddit.close()
                
        except Exception as e:
            await ctx.respond(f"❌ Unexpected error: {str(e)}")