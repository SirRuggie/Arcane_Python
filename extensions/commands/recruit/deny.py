"""
Recruit deny command - Send denial notification to applicants
"""

import hikari
import lightbulb
from datetime import datetime

from hikari.impl import (
    MessageActionRowBuilder as ActionRow,
    ContainerComponentBuilder as Container,
    InteractiveButtonBuilder as Button,
    TextDisplayComponentBuilder as Text,
    SeparatorComponentBuilder as Separator,
    MediaGalleryComponentBuilder as Media,
    MediaGalleryItemBuilder as MediaItem,
    ModalActionRowBuilder as ModalActionRow,
    SectionComponentBuilder as Section,
    ThumbnailComponentBuilder as Thumbnail,
)

from extensions.commands.recruit import recruit
from extensions.components import register_action
from utils.constants import DARK_MAGENTA_ACCENT

@recruit.register()
class RecruitDeny(
    lightbulb.SlashCommand,
    name="deny",
    description="Deny a recruit application with a reason"
):
    user = lightbulb.user(
        "user",
        "The user whose application to deny"
    )

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        """Show modal for denial reason"""
        # Store user info in a temporary session
        session_key = f"deny_{ctx.user.id}_{int(datetime.now().timestamp())}"
        
        # Create modal for denial reason
        reason_input = ModalActionRow().add_text_input(
            "denial_reason",
            "Denial Reason",
            placeholder="Please provide a clear reason for the denial",
            required=True,
            style=hikari.TextInputStyle.PARAGRAPH,
            min_length=5,
            max_length=1000
        )
        
        await ctx.respond_with_modal(
            title="Application Denial",
            custom_id=f"process_denial:{session_key}:{self.user.id}",
            components=[reason_input]
        )


@register_action("process_denial", no_return=True, is_modal=True)
@lightbulb.di.with_di
async def process_denial(
    ctx: lightbulb.components.ModalContext,
    action_id: str,
    bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    **kwargs
):
    """Process the denial and send notification"""
    # Parse action_id to get user_id (action_id format: "session_key:user_id")
    parts = action_id.split(":")
    if len(parts) < 2:
        await ctx.respond("❌ Error processing denial.", ephemeral=True)
        return
    
    denied_user_id = parts[1]
    
    # Get denial reason from modal
    reason = ""
    for row in ctx.interaction.components:
        for comp in row:
            if comp.custom_id == "denial_reason":
                reason = comp.value.strip()
                break
    
    # Send denial message to the channel
    denial_components = [
        Container(
            accent_color=DARK_MAGENTA_ACCENT,
            components=[
                Section(
                    components=[
                        Text(content=(
                            f"<@{denied_user_id}>, we regret to inform you that currently your application has been denied.\n\n"
                            f"## **Reason:**\n{reason}"
                        ))
                    ],
                    accessory=Thumbnail(media="https://res.cloudinary.com/dxmtzuomk/image/upload/v1753271403/misc_images/Denied.png")
                ),
                Media(items=[MediaItem(media="assets/Red_Footer.png")])
            ]
        )
    ]
    
    # Send the denial notification to the channel
    await bot.rest.create_message(
        channel=ctx.channel_id,
        components=denial_components,
        user_mentions=[int(denied_user_id)]
    )
    
    # Respond to the modal interaction
    await ctx.respond(
        f"✅ Denial notification sent to <@{denied_user_id}>",
        ephemeral=True
    )