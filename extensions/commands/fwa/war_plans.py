# extensions/commands/fwa/war_plans.py
"""
FWA War Plans command for generating war strategy messages.
Handles Win, Lose, Blacklisted, and Mismatch war scenarios.
"""

import hikari
import lightbulb
from datetime import datetime
from typing import Optional, Dict, List

from extensions.commands.fwa import fwa
from extensions.components import register_action
from extensions.autocomplete import fwa_clans

from utils.mongo import MongoClient
from utils.classes import Clan
from utils.constants import GREEN_ACCENT, DARK_MAGENTA_ACCENT, GOLD_ACCENT, BLUE_ACCENT
from .message_templates import (
    WarMessageTemplates,
    WarCopyTexts,
    sanitize_opponent_name
)

from hikari.impl import (
    MessageActionRowBuilder as ActionRow,
    InteractiveButtonBuilder as Button,
    ContainerComponentBuilder as Container,
    TextDisplayComponentBuilder as Text,
    SeparatorComponentBuilder as Separator,
    MediaGalleryComponentBuilder as Media,
    MediaGalleryItemBuilder as MediaItem,
)

# Configuration
FWA_WAR_PLANS_CONFIG = {
    "fwa_clan_rep_role_id": 1088914884999249940,
    "max_opponent_name_length": 50,
}


@fwa.register()
class WarPlans(
    lightbulb.SlashCommand,
    name="war-plans",
    description="Generate war strategy messages for different war outcomes"
):
    clan_name = lightbulb.string(
        "clan",
        "Select the FWA clan",
        autocomplete=fwa_clans  # Use the imported function directly
    )

    war_result = lightbulb.string(
        "result",
        "Select the war outcome type",
        choices=[
            lightbulb.Choice(name="Win", value="win"),
            lightbulb.Choice(name="Lose", value="lose"),
            lightbulb.Choice(name="Blacklisted", value="blacklisted"),
            lightbulb.Choice(name="Mismatch", value="mismatch")
        ]
    )

    opponent = lightbulb.string(
        "opponent",
        "Enter the opponent clan name",
        max_length=FWA_WAR_PLANS_CONFIG["max_opponent_name_length"]
    )

    @lightbulb.invoke
    @lightbulb.di.with_di
    async def invoke(
            self,
            ctx: lightbulb.Context,
            mongo: MongoClient = lightbulb.di.INJECTED,
    ) -> None:
        await ctx.defer(ephemeral=True)

        # Check if user has FWA Clan Rep role
        if not ctx.member or FWA_WAR_PLANS_CONFIG["fwa_clan_rep_role_id"] not in ctx.member.role_ids:
            await ctx.respond("❌ You must have the FWA Clan Rep role to use this command.", ephemeral=True)
            return

        # Extract clan info from autocomplete selection
        # Desktop returns format: "Clan Name|#TAG|role_id"
        # Mobile might return just: "Clan Name" (display text)
        parts = self.clan_name.split("|")
        
        if len(parts) >= 3:
            # Desktop format - parse normally
            clan_display_name = parts[0]
            clan_tag = parts[1]
            clan_role_id = parts[2]
        else:
            # Mobile format - just clan name, need to look up in database
            clan_display_name = self.clan_name.strip()
            
            # Look up clan details from database
            clan_data = await mongo.clans.find_one({"name": clan_display_name, "type": "FWA"})
            if not clan_data:
                await ctx.respond(
                    f"❌ Could not find FWA clan '{clan_display_name}' in database.\n"
                    f"Please try selecting the clan again.",
                    ephemeral=True
                )
                return
            
            clan_tag = clan_data.get("tag", "")
            clan_role_id = str(clan_data.get("role_id", ""))

        # Validate role_id
        if not clan_role_id or clan_role_id == "None":
            await ctx.respond("❌ This clan doesn't have a Discord role assigned.", ephemeral=True)
            return

        # Fetch the clan to get announcement channel
        raw = await mongo.clans.find_one({"tag": clan_tag})
        if not raw:
            await ctx.respond("❌ Clan not found in database!", ephemeral=True)
            return

        db_clan = Clan(data=raw)

        # Set target channel from clan data
        target_channel = db_clan.announcement_id
        if not target_channel:
            await ctx.respond("❌ This clan doesn't have an announcement channel set!", ephemeral=True)
            return

        # Sanitize opponent name (no validation needed - allow all characters)
        opponent_name = sanitize_opponent_name(self.opponent)

        # Get author name
        author_name = ctx.member.display_name if ctx.member else ctx.user.username

        # Generate appropriate message components using templates
        templates = WarMessageTemplates()
        message_components = None

        if self.war_result == "win":
            message_components = templates.win_message(opponent_name, author_name, clan_role_id)
        elif self.war_result == "lose":
            message_components = templates.lose_message(opponent_name, author_name, clan_role_id)
        elif self.war_result == "blacklisted":
            message_components = templates.blacklisted_message(
                opponent_name, author_name, clan_role_id,
                FWA_WAR_PLANS_CONFIG["fwa_clan_rep_role_id"]
            )
        elif self.war_result == "mismatch":
            message_components = templates.mismatch_message(opponent_name, author_name, clan_role_id)

        # Get the appropriate copy text
        copy_texts = WarCopyTexts()
        copy_text = ""
        if self.war_result == "win":
            copy_text = copy_texts.win_copy(opponent_name)
        elif self.war_result == "lose":
            copy_text = copy_texts.lose_copy(opponent_name)
        elif self.war_result == "blacklisted":
            copy_text = copy_texts.blacklisted_copy(opponent_name)
        elif self.war_result == "mismatch":
            copy_text = copy_texts.mismatch_copy(opponent_name)

        # Send main message to target channel
        try:
            # Create message with components only (no content field for Components V2)
            message = await ctx.client.rest.create_message(
                channel=target_channel,  # Now uses the clan's announcement channel
                components=message_components,
                role_mentions=[int(clan_role_id)]
            )

            # Store copy text and message info_hub in button store for later retrieval
            await mongo.button_store.insert_one({
                "_id": f"war_message_{message.id}",
                "copy_text": copy_text,
                "war_result": self.war_result,
                "opponent": opponent_name,
                "message_id": message.id,
                "channel_id": target_channel,
                "author_id": ctx.user.id,
                "clan_role_id": clan_role_id
            })

            # Send ephemeral response with just the copy text as plain text
            await ctx.respond(
                content=copy_text,
                ephemeral=True
            )

        except Exception as e:
            error_components = [
                Container(
                    accent_color=DARK_MAGENTA_ACCENT,
                    components=[
                        Text(content="## ❌ **Error Posting Message**"),
                        Text(content=f"Failed to post war message: {str(e)}"),
                        Text(content="Please check bot permissions and channel access."),
                        Media(items=[MediaItem(media="assets/Red_Footer.png")])
                    ]
                )
            ]
            await ctx.respond(components=error_components, ephemeral=True)