# extensions/commands/player/discord_id.py
"""
Player Discord ID Lookup Command
Uses ClashKing API to find Discord account linked to a Clash of Clans player tag
"""

import re
import aiohttp
import hikari
import lightbulb
from typing import Optional

from extensions.commands.player import loader, player
from utils.constants import GREEN_ACCENT, DARK_MAGENTA_ACCENT, GOLD_ACCENT

from hikari.impl import (
    ContainerComponentBuilder as Container,
    TextDisplayComponentBuilder as Text,
    SeparatorComponentBuilder as Separator,
    MediaGalleryComponentBuilder as Media,
    MediaGalleryItemBuilder as MediaItem,
)

# Player tag validation pattern (same as ticket/create.py)
PLAYER_TAG_PATTERN = re.compile(r'^#?[0289PYLQGRJCUV]{3,}$', re.IGNORECASE)


async def get_discord_id_for_player(player_tag: str) -> Optional[str]:
    """
    Call ClashKing API to get Discord ID for a single player tag.

    Args:
        player_tag: Player tag WITH # prefix

    Returns:
        Discord ID string or None if not found
    """
    # Remove # prefix for API call
    clean_tag = player_tag.lstrip('#')

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.clashk.ing/discord_links",
                json=[clean_tag],  # API expects array of tags
                headers={'Content-Type': 'application/json'}
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    # API returns dict with # prefix: {#TAG: discord_id or None}
                    return result.get(player_tag)
                else:
                    print(f"ClashKing API error {response.status}: {await response.text()}")
                    return None
    except Exception as e:
        print(f"ClashKing API request failed: {e}")
        return None


@player.register()
class PlayerDiscordId(
    lightbulb.SlashCommand,
    name="discord-id",
    description="Find the Discord account linked to a Clash of Clans player tag",
):
    playertag = lightbulb.string(
        "playertag",
        "The player tag to lookup (with or without #)",
        min_length=3,
        max_length=15
    )

    @lightbulb.invoke
    async def invoke(
        self,
        ctx: lightbulb.Context,
        bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    ) -> None:
        await ctx.defer(ephemeral=True)

        # Get and clean player tag
        player_tag = self.playertag.strip().upper()

        # Add # if not present
        if not player_tag.startswith('#'):
            player_tag = '#' + player_tag

        # Validate player tag format
        if not PLAYER_TAG_PATTERN.match(player_tag):
            components = [
                Container(
                    accent_color=DARK_MAGENTA_ACCENT,
                    components=[
                        Text(content="## ❌ Invalid Player Tag"),
                        Separator(divider=True),
                        Text(content=(
                            f"The player tag `{player_tag}` is not in a valid format.\n\n"
                            "**Valid format**: `#ABC123XYZ` (letters and numbers only)\n"
                            "**Allowed characters**: 0, 2, 8, 9, P, Y, L, Q, G, R, J, C, U, V"
                        )),
                        Media(items=[MediaItem(media="assets/Red_Footer.png")])
                    ]
                )
            ]
            await ctx.respond(components=components, ephemeral=True)
            return

        # Query ClashKing API
        print(f"[Player Discord ID] Looking up Discord ID for {player_tag}")
        discord_id = await get_discord_id_for_player(player_tag)

        # Handle result
        if discord_id is None:
            # API failed or player not found
            components = [
                Container(
                    accent_color=GOLD_ACCENT,
                    components=[
                        Text(content="## ⚠️ No Discord Account Found"),
                        Separator(divider=True),
                        Text(content=(
                            f"**Player Tag**: `{player_tag}`\n\n"
                            "This player either:\n"
                            "• Has not linked their Discord account with ClashKing\n"
                            "• Does not exist in Clash of Clans\n"
                            "• Has an API sync issue\n\n"
                            "*Players can link their account using ClashKing bot's `/link` command.*"
                        )),
                        Media(items=[MediaItem(media="assets/Gold_Footer.png")])
                    ]
                )
            ]
            await ctx.respond(components=components, ephemeral=True)
            print(f"[Player Discord ID] No Discord ID found for {player_tag}")
            return

        # Success - Discord ID found
        try:
            # Try to fetch user to verify they exist
            user = await bot.rest.fetch_user(int(discord_id))
            user_mention = f"<@{discord_id}>"
            user_tag = f"{user.username}"
            user_exists = True
        except Exception as e:
            # User doesn't exist or can't be fetched
            print(f"[Player Discord ID] Could not fetch user {discord_id}: {e}")
            user_mention = "*User not found*"
            user_tag = "*Unknown*"
            user_exists = False

        # Build success message
        components = [
            Container(
                accent_color=GREEN_ACCENT,
                components=[
                    Text(content="## ✅ Discord Account Found"),
                    Separator(divider=True),
                    Text(content=f"**Player Tag**: `{player_tag}`"),
                    Separator(spacing=hikari.SpacingType.SMALL, divider=False),
                    Text(content=f"**Discord ID**: `{discord_id}`"),
                    Text(content=f"**Discord User**: {user_mention}"),
                    *(
                        [Text(content=f"**Username**: {user_tag}")]
                        if user_exists
                        else [Text(content="⚠️ *This Discord account may no longer exist or the bot cannot access it.*")]
                    ),
                    Separator(divider=True),
                    Text(content=(
                        f"*You can copy the Discord ID above or click the user mention to view their profile.*"
                    )),
                    Media(items=[MediaItem(media="assets/Green_Footer.png")])
                ]
            )
        ]

        await ctx.respond(components=components, ephemeral=True)
        print(f"[Player Discord ID] Found Discord ID {discord_id} for {player_tag}")
