"""
Command to verify ticket channels actually exist and fix ticket_open status
"""

import os
import hikari
import lightbulb
from typing import Dict, List

from hikari.impl import (
    ContainerComponentBuilder as Container,
    TextDisplayComponentBuilder as Text,
    SeparatorComponentBuilder as Separator,
    MediaGalleryComponentBuilder as Media,
    MediaGalleryItemBuilder as MediaItem,
    InteractiveButtonBuilder as Button,
    MessageActionRowBuilder as ActionRow,
)

from extensions.commands.recruit import recruit
from extensions.components import register_action
from utils.mongo import MongoClient
from utils.constants import GREEN_ACCENT, DARK_MAGENTA_ACCENT, BLUE_ACCENT, GOLD_ACCENT

# Check if debug commands are enabled
ENABLE_DEBUG_COMMANDS = os.getenv("ENABLE_DEBUG_COMMANDS", "false").lower() == "true"

if ENABLE_DEBUG_COMMANDS:
    @recruit.register()
    class VerifyTicketChannels(
        lightbulb.SlashCommand,
        name="verify-ticket-channels",
        description="Verify ticket channels exist and fix ticket_open status",
        default_member_permissions=hikari.Permissions.ADMINISTRATOR
    ):
        check_discord = lightbulb.boolean(
            "check_discord",
            "Actually check if channels exist in Discord (slower but more accurate)",
            default=False
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
            
            # Find all records with ticket_open = true
            open_tickets = await mongo.new_recruits.find({
                "ticket_open": True
            }).to_list(length=None)
            
            if not open_tickets:
                components = [
                    Container(
                        accent_color=GREEN_ACCENT,
                        components=[
                            Text(content="## ✅ No Open Tickets Found"),
                            Text(content="There are no recruit records with ticket_open=true."),
                            Media(items=[MediaItem(media="assets/Green_Footer.png")])
                        ]
                    )
                ]
                await ctx.respond(components=components, ephemeral=True)
                return
            
            # Analyze the tickets
            analysis = {
                "total_open": len(open_tickets),
                "has_channel_id": 0,
                "missing_channel_id": 0,
                "channels_to_check": [],
                "records_missing_channel": []
            }
            
            for record in open_tickets:
                if record.get("ticket_channel_id"):
                    analysis["has_channel_id"] += 1
                    analysis["channels_to_check"].append({
                        "record_id": record["_id"],
                        "channel_id": record["ticket_channel_id"],
                        "player_tag": record.get("player_tag", "Unknown"),
                        "player_name": record.get("player_name", "Unknown")
                    })
                else:
                    analysis["missing_channel_id"] += 1
                    analysis["records_missing_channel"].append(record["_id"])
            
            # If check_discord is enabled, verify channels exist
            checking_message_sent = False
            if self.check_discord and analysis["channels_to_check"]:
                components = [
                    Container(
                        accent_color=GOLD_ACCENT,
                        components=[
                            Text(content="## 🔍 Checking Discord Channels..."),
                            Text(content=f"Verifying {len(analysis['channels_to_check'])} channels..."),
                            Text(content="-# This may take a moment"),
                            Media(items=[MediaItem(media="assets/Gold_Footer.png")])
                        ]
                    )
                ]
                await ctx.respond(components=components, ephemeral=True)
                checking_message_sent = True
                
                # Check each channel
                channels_not_found = []
                channels_found = []
                
                for channel_info in analysis["channels_to_check"]:
                    try:
                        channel = await bot.rest.fetch_channel(int(channel_info["channel_id"]))
                        channels_found.append(channel_info)
                    except hikari.NotFoundError:
                        channels_not_found.append(channel_info)
                    except Exception as e:
                        print(f"[ERROR] Failed to check channel {channel_info['channel_id']}: {e}")
                        channels_not_found.append(channel_info)
                
                # Update analysis
                analysis["channels_found"] = len(channels_found)
                analysis["channels_not_found"] = len(channels_not_found)
                analysis["channels_not_found_list"] = channels_not_found
            
            # Create preview
            preview_text = f"## 📊 Ticket Channel Verification\n\n"
            preview_text += f"**Total records with ticket_open=true:** {analysis['total_open']}\n"
            preview_text += f"**Has channel ID:** {analysis['has_channel_id']}\n"
            preview_text += f"**Missing channel ID:** {analysis['missing_channel_id']}\n"
            
            if self.check_discord and analysis.get("channels_not_found_list"):
                preview_text += f"\n**Discord Verification Results:**\n"
                preview_text += f"✅ Channels that exist: {analysis.get('channels_found', 0)}\n"
                preview_text += f"❌ Channels not found: {analysis.get('channels_not_found', 0)}\n\n"
                preview_text += f"**Records with non-existent channels:**\n"
                for channel in analysis["channels_not_found_list"][:10]:  # Show first 10
                    preview_text += f"• {channel['player_name']} ({channel['player_tag']})\n"
                if len(analysis["channels_not_found_list"]) > 10:
                    preview_text += f"• ... and {len(analysis['channels_not_found_list']) - 10} more\n"
            
            # Store data for fix action
            fix_data_id = f"verify_{ctx.user.id}_{ctx.interaction.id}"
            await mongo.button_store.insert_one({
                "_id": fix_data_id,
                "type": "channel_verification",
                "analysis": analysis,
                "user_id": ctx.user.id
            })
            
            # Add fix button if issues found
            buttons = []
            if analysis["missing_channel_id"] > 0 or (self.check_discord and analysis.get("channels_not_found", 0) > 0):
                buttons.append(
                    Button(
                        style=hikari.ButtonStyle.DANGER,
                        label="Fix Issues",
                        emoji="🔧",
                        custom_id=f"fix_ticket_channels:{fix_data_id}"
                    )
                )
            
            container_components = [
                Text(content=preview_text),
                Separator(divider=True) if buttons else None,
                ActionRow(components=buttons) if buttons else None,
                Media(items=[MediaItem(media="assets/Blue_Footer.png")])
            ]
            # Filter out None values
            container_components = [c for c in container_components if c is not None]
            
            components = [
                Container(
                    accent_color=BLUE_ACCENT,
                    components=container_components
                )
            ]
            
            # Send or edit response based on whether we already sent one
            if checking_message_sent:
                # Edit the existing message
                await ctx.interaction.edit_initial_response(components=components)
            else:
                # Send new response
                await ctx.respond(components=components, ephemeral=True)


    @register_action("fix_ticket_channels", no_return=True)
    @lightbulb.di.with_di
    async def handle_fix_channels(
        ctx: lightbulb.components.MenuContext,
        action_id: str,
        mongo: MongoClient = lightbulb.di.INJECTED,
        **kwargs
    ):
        """Handle fixing ticket channel issues"""
        
        # Get verification data
        verify_data = await mongo.button_store.find_one({"_id": action_id})
        if not verify_data:
            await ctx.respond(
                components=[Container(
                    accent_color=DARK_MAGENTA_ACCENT,
                    components=[
                        Text(content="❌ Verification data expired. Please run the command again."),
                        Media(items=[MediaItem(media="assets/Red_Footer.png")])
                    ]
                )]
            )
            return
        
        analysis = verify_data["analysis"]
        updates_made = 0
        
        # Fix records missing channel IDs
        if analysis["records_missing_channel"]:
            result = await mongo.new_recruits.update_many(
                {"_id": {"$in": analysis["records_missing_channel"]}},
                {"$set": {"ticket_open": False}}
            )
            updates_made += result.modified_count
        
        # Fix records with non-existent channels
        if analysis.get("channels_not_found_list"):
            record_ids = [ch["record_id"] for ch in analysis["channels_not_found_list"]]
            result = await mongo.new_recruits.update_many(
                {"_id": {"$in": record_ids}},
                {"$set": {"ticket_open": False}}
            )
            updates_made += result.modified_count
        
        # Clean up
        await mongo.button_store.delete_one({"_id": action_id})
        
        # Success message
        success_text = (
            f"## ✅ Fixed Ticket Channel Issues\n\n"
            f"**Records updated:** {updates_made}\n\n"
            f"All records with missing or non-existent channels have been marked as ticket_open=false."
        )
        
        components = [
            Container(
                accent_color=GREEN_ACCENT,
                components=[
                    Text(content=success_text),
                    Media(items=[MediaItem(media="assets/Green_Footer.png")])
                ]
            )
        ]

        await ctx.respond(components=components)