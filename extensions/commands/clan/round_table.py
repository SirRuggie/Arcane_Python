# extensions/commands/clan/round_table.py
"""Clan round table management - add/remove right hand leader role"""

import hikari
import lightbulb
from typing import Literal

from extensions.commands.clan import loader, clan
from extensions.components import register_action
from utils.constants import DARK_MAGENTA_ACCENT, GREEN_ACCENT

from hikari.impl import (
    ContainerComponentBuilder as Container,
    TextDisplayComponentBuilder as Text,
    SeparatorComponentBuilder as Separator,
)

# Configuration
ROUND_TABLE_ROLE_ID = 1344477131891277946  # Right Hand Leader role
ROUND_TABLE_CHANNEL_ID = 1345241853624061952  # Round table welcome channel


@clan.register()
class RoundTableCommand(
    lightbulb.SlashCommand,
    name="round-table",
    description="Manage clan right hand leader (round table) role",
):
    # Discord user parameter
    discord_user = lightbulb.user(
        "discord-user",
        "The user to add or remove from the round table",
    )

    # Action parameter with choices
    action = lightbulb.string(
        "action",
        "Add or remove the user from the round table",
        choices=[
            lightbulb.Choice(name="Add", value="add"),
            lightbulb.Choice(name="Remove", value="remove")
        ]
    )

    @lightbulb.invoke
    @lightbulb.di.with_di
    async def invoke(
            self,
            ctx: lightbulb.Context,
            bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    ) -> None:
        # Defer response to prevent timeout
        await ctx.defer(ephemeral=True)

        # Get the selected user and action
        target_user = self.discord_user
        action = self.action

        # Get the member object to check/modify roles
        try:
            member = await bot.rest.fetch_member(ctx.guild_id, target_user.id)
        except hikari.NotFoundError:
            await ctx.respond(
                "❌ User not found in this server!",
                ephemeral=True
            )
            return

        # Check if user already has the role
        has_role = ROUND_TABLE_ROLE_ID in member.role_ids

        # Determine the action result
        if action == "add":
            if has_role:
                # User already has the role
                await ctx.respond(
                    components=create_already_has_role_response(member, ctx.member),
                    ephemeral=True
                )
                return

            # Add the role
            try:
                await member.add_role(ROUND_TABLE_ROLE_ID, reason=f"Added to round table by {ctx.member}")

                # Send welcome message to the round table channel
                welcome_message = (
                    f"{member.mention}, welcome to the Round Table. {ctx.member.mention} insists you're the "
                    f'"missing link" their clan can\'t live without. We\'ve already set your expectations to '
                    f'"legendary," so no pressure when you single-handedly "do work" and rescue them all. '
                    f"We'll be right here, popcorn in hand, waiting for your first world-changing move or at "
                    f'least something that doesn\'t make us ask "why is this person here?" Welcome aboard; '
                    f"now go wow us (or at least make us laugh)."
                )

                try:
                    await bot.rest.create_message(
                        channel=ROUND_TABLE_CHANNEL_ID,
                        content=welcome_message,
                        user_mentions=True
                    )
                except Exception as e:
                    print(f"Failed to send welcome message: {e}")

                await ctx.respond(
                    components=create_role_added_response(member, ctx.member),
                    ephemeral=True
                )
            except hikari.ForbiddenError:
                await ctx.respond(
                    "❌ I don't have permission to manage that role!",
                    ephemeral=True
                )
            except Exception as e:
                await ctx.respond(
                    f"❌ Failed to add role: {str(e)}",
                    ephemeral=True
                )

        else:  # action == "remove"
            if not has_role:
                # User doesn't have the role
                await ctx.respond(
                    components=create_doesnt_have_role_response(member, ctx.member),
                    ephemeral=True
                )
                return

            # Remove the role
            try:
                await member.remove_role(ROUND_TABLE_ROLE_ID, reason=f"Removed from round table by {ctx.member}")
                await ctx.respond(
                    components=create_role_removed_response(member, ctx.member),
                    ephemeral=True
                )
            except hikari.ForbiddenError:
                await ctx.respond(
                    "❌ I don't have permission to manage that role!",
                    ephemeral=True
                )
            except Exception as e:
                await ctx.respond(
                    f"❌ Failed to remove role: {str(e)}",
                    ephemeral=True
                )


def create_role_added_response(member: hikari.Member, executor: hikari.Member) -> list[Container]:
    """Create response for successful role addition"""
    return [
        Container(
            accent_color=GREEN_ACCENT,
            components=[
                Text(content="## ✅ Right Hand Leader Role Added"),
                Separator(divider=True),
                Text(content=(
                    f"**User:** {member.mention}\n"
                    f"**Role:** <@&{ROUND_TABLE_ROLE_ID}>\n"
                    f"**Status:** Successfully added to the round table!\n"
                    f"**Welcome:** A welcome message has been sent to <#{ROUND_TABLE_CHANNEL_ID}>"
                )),
                Separator(divider=True),
                Text(content=f"-# Added by {executor.mention}")
            ]
        )
    ]


def create_role_removed_response(member: hikari.Member, executor: hikari.Member) -> list[Container]:
    """Create response for successful role removal"""
    return [
        Container(
            accent_color=DARK_MAGENTA_ACCENT,
            components=[
                Text(content="## ✅ Right Hand Leader Role Removed"),
                Separator(divider=True),
                Text(content=(
                    f"**User:** {member.mention}\n"
                    f"**Role:** <@&{ROUND_TABLE_ROLE_ID}>\n"
                    f"**Status:** Successfully removed from the round table!"
                )),
                Separator(divider=True),
                Text(content=f"-# Removed by {executor.mention}")
            ]
        )
    ]


def create_already_has_role_response(member: hikari.Member, executor: hikari.Member) -> list[Container]:
    """Create response when user already has the role"""
    return [
        Container(
            accent_color=DARK_MAGENTA_ACCENT,
            components=[
                Text(content="## ℹ️ User Already Has Role"),
                Separator(divider=True),
                Text(content=(
                    f"**User:** {member.mention}\n"
                    f"**Role:** <@&{ROUND_TABLE_ROLE_ID}>\n"
                    f"**Status:** This user is already a member of the round table!"
                )),
                Separator(divider=True),
                Text(content=f"-# Checked by {executor.mention}")
            ]
        )
    ]


def create_doesnt_have_role_response(member: hikari.Member, executor: hikari.Member) -> list[Container]:
    """Create response when user doesn't have the role"""
    return [
        Container(
            accent_color=DARK_MAGENTA_ACCENT,
            components=[
                Text(content="## ℹ️ User Doesn't Have Role"),
                Separator(divider=True),
                Text(content=(
                    f"**User:** {member.mention}\n"
                    f"**Role:** <@&{ROUND_TABLE_ROLE_ID}>\n"
                    f"**Status:** This user is not currently a member of the round table!"
                )),
                Separator(divider=True),
                Text(content=f"-# Checked by {executor.mention}")
            ]
        )
    ]
