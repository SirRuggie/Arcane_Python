"""
Migration command to add ticket_open field to existing recruit records
"""

import os
import hikari
import lightbulb
from lightbulb.components import ModalContext
from typing import Dict, List

from hikari.impl import (
    ContainerComponentBuilder as Container,
    TextDisplayComponentBuilder as Text,
    SeparatorComponentBuilder as Separator,
    MediaGalleryComponentBuilder as Media,
    MediaGalleryItemBuilder as MediaItem,
    InteractiveButtonBuilder as Button,
    MessageActionRowBuilder as ActionRow,
    ModalActionRowBuilder as ModalActionRow,
)

from extensions.commands.recruit import recruit
from extensions.components import register_action
from utils.mongo import MongoClient
from utils.constants import GREEN_ACCENT, DARK_MAGENTA_ACCENT, BLUE_ACCENT

# Check if debug commands are enabled
ENABLE_DEBUG_COMMANDS = os.getenv("ENABLE_DEBUG_COMMANDS", "false").lower() == "true"

if ENABLE_DEBUG_COMMANDS:
    @recruit.register()
    class MigrateTicketOpen(
        lightbulb.SlashCommand,
        name="migrate-ticket-open",
        description="Migrate existing recruit records to add ticket_open field",
        default_member_permissions=hikari.Permissions.ADMINISTRATOR
    ):
        @lightbulb.invoke
        @lightbulb.di.with_di
        async def invoke(
            self,
            ctx: lightbulb.Context,
            mongo: MongoClient = lightbulb.di.INJECTED,
            bot: hikari.GatewayBot = lightbulb.di.INJECTED,
        ) -> None:
            await ctx.defer(ephemeral=True)
            
            # Analyze existing records
            analysis = await analyze_records(mongo)
            
            if analysis["total_without_field"] == 0:
                components = [
                    Container(
                        accent_color=GREEN_ACCENT,
                        components=[
                            Text(content="## ✅ No Migration Needed"),
                            Text(content="All recruit records already have the ticket_open field."),
                            Media(items=[MediaItem(media="assets/Green_Footer.png")])
                        ]
                    )
                ]
                await ctx.respond(components=components, ephemeral=True)
                return
            
            # Create preview message
            preview_text = (
                f"## 📊 Migration Preview\n\n"
                f"**Total recruits without ticket_open field:** {analysis['total_without_field']}\n\n"
                f"**Will set to CLOSED:**\n"
                f"• Has ticket_closed_at: {analysis['has_ticket_closed_at']}\n"
                f"• Has recruitment_outcome: {analysis['has_recruitment_outcome']}\n"
                f"• Has external_clan_tag: {analysis['has_external_clan']}\n"
                f"• **Total to close:** {analysis['total_to_close']}\n\n"
                f"**Will set to OPEN:**\n"
                f"• No closure indicators: {analysis['total_to_open']}\n\n"
                f"Click 'Confirm Migration' to proceed."
            )
            
            # Store migration data for the button handler
            migration_id = f"migration_{ctx.user.id}_{ctx.interaction.id}"
            await mongo.button_store.insert_one({
                "_id": migration_id,
                "type": "migration_data",
                "analysis": analysis,
                "user_id": ctx.user.id
            })
            
            components = [
                Container(
                    accent_color=BLUE_ACCENT,
                    components=[
                        Text(content=preview_text),
                        Separator(divider=True),
                        ActionRow(
                            components=[
                                Button(
                                    style=hikari.ButtonStyle.SUCCESS,
                                    label="Confirm Migration",
                                    emoji="✅",
                                    custom_id=f"confirm_migration:{migration_id}"
                                ),
                                Button(
                                    style=hikari.ButtonStyle.DANGER,
                                    label="Cancel",
                                    emoji="❌",
                                    custom_id=f"cancel_migration:{migration_id}"
                                )
                            ]
                        ),
                        Media(items=[MediaItem(media="assets/Blue_Footer.png")])
                    ]
                )
            ]
            
            await ctx.respond(components=components, ephemeral=True)


    async def analyze_records(mongo: MongoClient) -> Dict:
        """Analyze existing records to determine migration needs"""
        
        # Find all records without ticket_open field
        records_without_field = await mongo.new_recruits.find({
            "ticket_open": {"$exists": False}
        }).to_list(length=None)
        
        total_without_field = len(records_without_field)
        
        # Categorize records
        has_ticket_closed_at = 0
        has_recruitment_outcome = 0
        has_external_clan = 0
        no_closure_indicators = 0
        
        records_to_close = []
        records_to_open = []
        
        for record in records_without_field:
            should_close = False
            
            # Check closure indicators
            if record.get("ticket_closed_at"):
                has_ticket_closed_at += 1
                should_close = True
            
            if record.get("recruitment_outcome"):
                has_recruitment_outcome += 1
                should_close = True
                
            if record.get("external_clan_tag"):
                has_external_clan += 1
                should_close = True
            
            if should_close:
                records_to_close.append(record["_id"])
            else:
                no_closure_indicators += 1
                records_to_open.append(record["_id"])
        
        return {
            "total_without_field": total_without_field,
            "has_ticket_closed_at": has_ticket_closed_at,
            "has_recruitment_outcome": has_recruitment_outcome,
            "has_external_clan": has_external_clan,
            "total_to_close": len(records_to_close),
            "total_to_open": len(records_to_open),
            "records_to_close": records_to_close,
            "records_to_open": records_to_open
        }


    @register_action("confirm_migration", no_return=True)
    @lightbulb.di.with_di
    async def handle_confirm_migration(
        ctx: lightbulb.components.MenuContext,
        action_id: str,
        mongo: MongoClient = lightbulb.di.INJECTED,
        **kwargs
    ):
        """Handle migration confirmation"""
        
        # Get migration data
        migration_data = await mongo.button_store.find_one({"_id": action_id})
        if not migration_data:
            await ctx.respond(
                components=[Container(
                    accent_color=DARK_MAGENTA_ACCENT,
                    components=[
                        Text(content="❌ Migration data expired. Please try again."),
                        Media(items=[MediaItem(media="assets/Red_Footer.png")])
                    ]
                )]
            )
            return
        
        analysis = migration_data["analysis"]
        
        # Perform migration
        update_results = {
            "closed_success": 0,
            "open_success": 0,
            "errors": 0
        }
        
        # Update records to closed
        if analysis["records_to_close"]:
            result = await mongo.new_recruits.update_many(
                {"_id": {"$in": analysis["records_to_close"]}},
                {"$set": {"ticket_open": False}}
            )
            update_results["closed_success"] = result.modified_count
        
        # Update records to open
        if analysis["records_to_open"]:
            result = await mongo.new_recruits.update_many(
                {"_id": {"$in": analysis["records_to_open"]}},
                {"$set": {"ticket_open": True}}
            )
            update_results["open_success"] = result.modified_count
        
        # Clean up migration data
        await mongo.button_store.delete_one({"_id": action_id})
        
        # Create success message
        success_text = (
            f"## ✅ Migration Complete!\n\n"
            f"**Records updated to CLOSED:** {update_results['closed_success']}\n"
            f"**Records updated to OPEN:** {update_results['open_success']}\n"
            f"**Total records updated:** {update_results['closed_success'] + update_results['open_success']}\n\n"
            f"All recruit records now have the ticket_open field."
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


    @register_action("cancel_migration", no_return=True)
    @lightbulb.di.with_di
    async def handle_cancel_migration(
        ctx: lightbulb.components.MenuContext,
        action_id: str,
        mongo: MongoClient = lightbulb.di.INJECTED,
        **kwargs
    ):
        """Handle migration cancellation"""
        
        # Clean up migration data
        await mongo.button_store.delete_one({"_id": action_id})
        
        components = [
            Container(
                accent_color=DARK_MAGENTA_ACCENT,
                components=[
                    Text(content="## ❌ Migration Cancelled"),
                    Text(content="No changes were made to the database."),
                    Media(items=[MediaItem(media="assets/Red_Footer.png")])
                ]
            )
        ]

        await ctx.respond(components=components)