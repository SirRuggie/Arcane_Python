"""Add users or roles to a ticket with standard permissions"""

import hikari
import lightbulb
from typing import Optional

from extensions.commands.ticket import loader, ticket
from utils.mongo import MongoClient
from utils.constants import DARK_MAGENTA_ACCENT, GREEN_ACCENT

# Import Components V2
from hikari.impl import (
    ContainerComponentBuilder as Container,
    TextDisplayComponentBuilder as Text,
    SeparatorComponentBuilder as Separator,
    MediaGalleryComponentBuilder as Media,
    MediaGalleryItemBuilder as MediaItem,
)

# Standard ticket permissions
TICKET_PERMISSIONS = (
    hikari.Permissions.VIEW_CHANNEL |
    hikari.Permissions.SEND_MESSAGES |
    hikari.Permissions.READ_MESSAGE_HISTORY |
    hikari.Permissions.ATTACH_FILES |
    hikari.Permissions.EMBED_LINKS
)


@ticket.register()
class AddToTicketCommand(
    lightbulb.SlashCommand,
    name="add",
    description="Add a user or role to this ticket channel with standard permissions",
):
    user = lightbulb.user(
        "user",
        "User to add to the ticket",
        default=None
    )

    role = lightbulb.role(
        "role",
        "Role to add to the ticket",
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
        # Check if at least one option was provided
        if not self.user and not self.role:
            await ctx.respond(
                components=[
                    Container(
                        accent_color=DARK_MAGENTA_ACCENT,
                        components=[
                            Text(content="## ❌ Missing Parameters"),
                            Text(content="You must provide at least one of: **user** or **role**"),
                            Media(items=[MediaItem(media="assets/Red_Footer.png")])
                        ]
                    )
                ],
                ephemeral=True
            )
            return

        # Defer response
        await ctx.defer(ephemeral=True)

        channel_id = str(ctx.channel_id)

        # Verify this is a ticket channel
        ticket_state = await mongo.ticket_automation_state.find_one({"_id": channel_id})
        recruit_data = await mongo.new_recruits.find_one({
            "ticket_channel_id": channel_id,
            "ticket_open": True
        })

        if not ticket_state and not recruit_data:
            await ctx.respond(
                components=[
                    Container(
                        accent_color=DARK_MAGENTA_ACCENT,
                        components=[
                            Text(content="## ❌ Not a Ticket Channel"),
                            Text(content="This command can only be used in an active ticket channel."),
                            Media(items=[MediaItem(media="assets/Red_Footer.png")])
                        ]
                    )
                ],
                ephemeral=True
            )
            return

        added = []
        errors = []

        # Add user if provided
        if self.user:
            try:
                await bot.rest.edit_permission_overwrite(
                    channel=ctx.channel_id,
                    target=self.user,
                    allow=TICKET_PERMISSIONS
                )
                added.append(f"• User: {self.user.mention}")
            except Exception as e:
                errors.append(f"• Failed to add user {self.user.mention}: {str(e)[:100]}")

        # Add role if provided
        if self.role:
            try:
                await bot.rest.edit_permission_overwrite(
                    channel=ctx.channel_id,
                    target=self.role,
                    allow=TICKET_PERMISSIONS
                )
                added.append(f"• Role: {self.role.mention}")
            except Exception as e:
                errors.append(f"• Failed to add role {self.role.mention}: {str(e)[:100]}")

        # Send notification message in the channel for successfully added users/roles
        if added:
            # Build mention list
            mentions = []
            if self.user and f"• User: {self.user.mention}" in added:
                mentions.append(self.user.mention)
            if self.role and f"• Role: {self.role.mention}" in added:
                mentions.append(self.role.mention)

            if mentions:
                mention_text = " ".join(mentions)

                # Send notification message in the ticket channel
                notification_components = [
                    Container(
                        accent_color=0x5865F2,  # Blurple
                        components=[
                            Text(content=f"## 📋 Added to Ticket"),
                            Separator(divider=True),
                            Text(content=(
                                f"{mention_text}\n\n"
                                f"You have been added to this ticket channel.\n"
                                f"Please review the ticket details and provide any necessary assistance."
                            )),
                            Text(content=f"-# Added by {ctx.user.mention}"),
                            Media(items=[MediaItem(media="assets/Blue_Footer.png")])
                        ]
                    )
                ]

                try:
                    await bot.rest.create_message(
                        channel=ctx.channel_id,
                        components=notification_components,
                        user_mentions=True,
                        role_mentions=True
                    )
                except Exception as e:
                    print(f"[ERROR] Failed to send ticket add notification: {e}")

        # Build response
        if errors:
            # Show errors (partial or complete failure)
            error_message = "## ❌ Failed to Add"
            if added:
                error_message = "## ⚠️ Partially Added to Ticket"

            error_components = [
                Container(
                    accent_color=DARK_MAGENTA_ACCENT if not added else 0xFFA500,  # Red for complete failure, Orange for partial
                    components=[
                        Text(content=error_message),
                        Separator(divider=True),
                        Text(content="**Errors:**\n" + "\n".join(errors)),
                        Media(items=[MediaItem(media="assets/Red_Footer.png")])
                    ]
                )
            ]

            await ctx.respond(
                components=error_components,
                ephemeral=True
            )
        else:
            # Success - send minimal ephemeral acknowledgment
            await ctx.respond(
                "✅ Done",
                ephemeral=True
            )
