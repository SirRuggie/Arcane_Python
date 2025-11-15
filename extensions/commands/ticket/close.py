"""Manual ticket closure command for proper cleanup"""

import hikari
import lightbulb
from datetime import datetime, timezone
from typing import Optional

from extensions.commands.ticket import loader, ticket
from utils.mongo import MongoClient
from utils.constants import DARK_MAGENTA_ACCENT, GREEN_ACCENT, GOLD_ACCENT

# Import Components V2
from hikari.impl import (
    ContainerComponentBuilder as Container,
    TextDisplayComponentBuilder as Text,
    SeparatorComponentBuilder as Separator,
    MediaGalleryComponentBuilder as Media,
    MediaGalleryItemBuilder as MediaItem,
)

# Recruitment staff role ID (same as create.py)
RECRUITMENT_STAFF_ROLE = 999140213953671188
RECRUITMENT_LOG_CHANNEL = 1436169870273413169


@ticket.register()
class CloseTicketCommand(
    lightbulb.SlashCommand,
    name="close",
    description="Close a recruitment ticket and clean up all data"
):
    channel = lightbulb.channel(
        "channel",
        "Ticket channel to close (defaults to current channel)",
        channel_types=[hikari.ChannelType.GUILD_TEXT],
        default=None
    )

    @lightbulb.invoke
    @lightbulb.di.with_di
    async def invoke(
        self,
        ctx: lightbulb.Context,
        bot: hikari.GatewayBot = lightbulb.di.INJECTED,
        mongo: MongoClient = lightbulb.di.INJECTED,
    ) -> None:
        # Determine which channel to close
        target_channel = self.channel if self.channel else ctx.channel_id
        channel_id = str(target_channel.id) if hasattr(target_channel, 'id') else str(target_channel)

        print(f"[DEBUG] Ticket close requested for channel: {channel_id}")

        # Defer the response
        await ctx.defer(ephemeral=True)

        try:
            # Check if this is actually a ticket channel
            ticket_state = await mongo.ticket_automation_state.find_one({"_id": channel_id})
            recruits = await mongo.new_recruits.find({
                "ticket_channel_id": channel_id,
                "ticket_open": True
            }).to_list(length=None)

            if not ticket_state and not recruits:
                await ctx.respond(
                    components=[
                        Container(
                            accent_color=DARK_MAGENTA_ACCENT,
                            components=[
                                Text(content="## ❌ Not a Ticket Channel"),
                                Text(content="This doesn't appear to be an active ticket channel."),
                                Media(items=[MediaItem(media="assets/Red_Footer.png")])
                            ]
                        )
                    ],
                    ephemeral=True
                )
                return

            # Get ticket information for logging
            player_tag = None
            player_name = None
            ticket_type = None

            if ticket_state:
                ticket_info = ticket_state.get("ticket_info", {})
                player_info = ticket_state.get("player_info", {})
                player_tag = ticket_info.get("user_tag") or player_info.get("player_tag")
                player_name = player_info.get("player_name")
                ticket_type = ticket_info.get("ticket_type")

            if recruits and not player_tag:
                recruit = recruits[0]
                player_tag = recruit.get("player_tag")
                player_name = recruit.get("player_name")

            print(f"[DEBUG] Closing ticket for player: {player_tag} ({player_name})")

            # 1. Update new_recruits collection
            if recruits:
                now = datetime.now(timezone.utc)
                update_result = await mongo.new_recruits.update_many(
                    {"ticket_channel_id": channel_id},
                    {
                        "$set": {
                            "ticket_open": False,
                            "ticket_closed_at": now,
                            "manually_closed": True,
                            "closed_by": str(ctx.user.id)
                        }
                    }
                )
                print(f"[DEBUG] Updated {update_result.modified_count} recruit records")

            # 2. Handle any active bids
            if player_tag:
                bid_data = await mongo.clan_bidding.find_one({"player_tag": player_tag})
                if bid_data and bid_data.get("bids"):
                    print(f"[DEBUG] Found active bids for {player_tag}, processing refunds...")

                    # Refund all bids and log to recruitment channel
                    for bid in bid_data.get("bids", []):
                        clan_tag = bid.get("clan_tag")
                        bid_amount = bid.get("amount", 0)

                        if clan_tag and bid_amount > 0:
                            await mongo.clans.update_one(
                                {"tag": clan_tag},
                                {"$inc": {"points": bid_amount}}
                            )
                            print(f"[DEBUG] Refunded {bid_amount} points to {clan_tag}")

                            # Get clan details for leadership ping
                            refund_clan = await mongo.clans.find_one({"tag": clan_tag})

                            if refund_clan:
                                log_components = [
                                    Container(
                                        accent_color=GOLD_ACCENT,
                                        components=[
                                            Text(content=(
                                                f"## 💰 Ticket Closed - Bid Refund"
                                            )),
                                            Separator(divider=True),
                                            Text(content=(
                                                f"<@&{refund_clan.get('leader_role_id', 0)}> "
                                                f"Ticket was manually closed. Bid has been refunded.\n\n"
                                                f"• **Clan:** {refund_clan['name']}\n"
                                                f"• **Refund Amount:** {bid_amount} points\n"
                                                f"• **Player:** {player_name or 'Unknown'} (`{player_tag}`)\n"
                                                f"• **Closed By:** <@{ctx.user.id}>"
                                            )),
                                            Media(items=[MediaItem(media="assets/Gold_Footer.png")])
                                        ]
                                    )
                                ]

                                try:
                                    await bot.rest.create_message(
                                        channel=RECRUITMENT_LOG_CHANNEL,
                                        components=log_components,
                                        role_mentions=True
                                    )
                                except Exception as e:
                                    print(f"[ERROR] Failed to send refund log: {e}")

                    # Delete the bidding document
                    await mongo.clan_bidding.delete_one({"player_tag": player_tag})
                    print(f"[DEBUG] Deleted clan_bidding document for {player_tag}")

            # 3. Delete ticket automation state
            if ticket_state:
                await mongo.ticket_automation_state.delete_one({"_id": channel_id})
                print(f"[DEBUG] Deleted ticket_automation_state document")

            # 4. Send confirmation before deleting channel
            success_message = f"✅ **Ticket Closed Successfully**\n\n"
            if player_tag:
                success_message += f"**Player:** {player_name or 'Unknown'} (`{player_tag}`)\n"
            if ticket_type:
                success_message += f"**Type:** {ticket_type}\n"
            success_message += f"**Closed by:** {ctx.user.mention}\n"
            success_message += f"**Channel will be deleted in 5 seconds...**"

            await ctx.respond(
                components=[
                    Container(
                        accent_color=GREEN_ACCENT,
                        components=[
                            Text(content="## ✅ Ticket Closed"),
                            Separator(divider=True),
                            Text(content=success_message),
                            Media(items=[MediaItem(media="assets/Green_Footer.png")])
                        ]
                    )
                ],
                ephemeral=True
            )

            # 5. Wait a moment then delete the channel
            import asyncio
            await asyncio.sleep(5)

            try:
                await bot.rest.delete_channel(target_channel)
                print(f"[SUCCESS] Deleted ticket channel {channel_id}")
            except Exception as e:
                print(f"[ERROR] Failed to delete channel {channel_id}: {e}")

        except Exception as e:
            print(f"[ERROR] Failed to close ticket: {e}")

            await ctx.respond(
                components=[
                    Container(
                        accent_color=DARK_MAGENTA_ACCENT,
                        components=[
                            Text(content="## ❌ Ticket Closure Failed"),
                            Separator(divider=True),
                            Text(content=f"An error occurred while closing the ticket:\n```{str(e)[:500]}```"),
                            Text(content="Please contact an administrator if this issue persists."),
                            Media(items=[MediaItem(media="assets/Red_Footer.png")])
                        ]
                    )
                ],
                ephemeral=True
            )