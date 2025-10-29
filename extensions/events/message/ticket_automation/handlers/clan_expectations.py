# extensions/events/message/ticket_automation/handlers/clan_expectations.py
"""
Handles clan expectations collection with AI-powered summarization.
Users can type multiple responses which are organized by AI.
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
import hikari
import lightbulb

from hikari.impl import (
    MessageActionRowBuilder as ActionRow,
    ContainerComponentBuilder as Container,
    InteractiveButtonBuilder as Button,
    TextDisplayComponentBuilder as Text,
    SeparatorComponentBuilder as Separator,
    MediaGalleryComponentBuilder as Media,
    MediaGalleryItemBuilder as MediaItem,
    SectionComponentBuilder as Section,
)

from extensions.components import register_action
from utils.mongo import MongoClient
from utils.emoji import emojis
from utils.constants import BLUE_ACCENT, GREEN_ACCENT
from ..core.state_manager import StateManager
from ..ai.processors import process_clan_expectations_with_ai

# Global instances
mongo_client: Optional[MongoClient] = None
bot_instance: Optional[hikari.GatewayBot] = None

# Question content - defined once to avoid duplication
QUESTION_TITLE = "## 🏰 **Future Clan Expectations**"
QUESTION_CONTENT = lambda: (
    "Help us tailor your clan experience! Please answer the following:\n\n"
    f"{emojis.red_arrow_right} **What do you expect from your future clan?**\n"
    f"{emojis.blank}{emojis.white_arrow_right} *(e.g., Active wars, good communication, strategic support.)*\n\n"
    f"{emojis.red_arrow_right} **Minimum clan level you're looking for?**\n"
    f"{emojis.blank}{emojis.white_arrow_right} *e.g. Level 5, Level 10*\n\n"
    f"{emojis.red_arrow_right} **Minimum Clan Capital Hall level?**\n"
    f"{emojis.blank}{emojis.white_arrow_right} *e.g. CH 8 or higher*\n\n"
    f"{emojis.red_arrow_right} **CWL league preference?**\n"
    f"{emojis.blank}{emojis.white_arrow_right} *e.g. Crystal league or no preference*\n\n"
    f"{emojis.red_arrow_right} **Preferred playstyle?**\n"
    f"{emojis.blank}{emojis.white_arrow_right} Competitive\n"
    f"{emojis.blank}{emojis.white_arrow_right} Casual\n"
    f"{emojis.blank}{emojis.white_arrow_right} Zen *Type **What is Zen** to learn more.*\n"
    f"{emojis.blank}{emojis.white_arrow_right} FWA *Type **What is FWA** to learn more.*\n"
)


def initialize(mongo: MongoClient, bot: hikari.GatewayBot):
    """Initialize the handler"""
    global mongo_client, bot_instance
    mongo_client = mongo
    bot_instance = bot


def create_clan_expectations_components(
        current_summary: str,
        title: str,
        detailed_content: str,
        show_done_button: bool = True,
        include_user_ping: bool = True,
        channel_id: Optional[int] = None,
        user_id: Optional[int] = None,
        progress: Optional[dict] = None
) -> List[Container]:
    """Create container components for clan expectations messages"""

    # Format summary with emojis
    formatted_summary = current_summary.replace("{red_arrow}", str(emojis.red_arrow_right))
    formatted_summary = formatted_summary.replace("{white_arrow}", str(emojis.white_arrow_right))
    formatted_summary = formatted_summary.replace("{blank}", str(emojis.blank))

    components_list = []

    # Add user mention if requested
    if include_user_ping and user_id:
        components_list.append(Text(content=f"<@{user_id}>"))
        components_list.append(Separator(divider=True))

    # Add title
    components_list.append(Text(content=title))
    
    # Add requirements info box
    components_list.append(Separator(divider=True))
    components_list.append(Text(content=(
        "📋 **Requirements:**\n"
        "• At least one expectation from your future clan\n"
        "• Minimum clan level\n"
        "• Minimum Capital Hall level\n"
        "• CWL league preference\n"
        "• Preferred playstyle"
    )))
    
    # Add progress indicators if we have progress data
    if progress is not None:
        has_expectations = progress.get("has_expectations", False)
        has_clan_level = progress.get("has_clan_level", False)
        has_capital_hall = progress.get("has_capital_hall", False)
        has_cwl_league = progress.get("has_cwl_league", False)
        has_clan_style = progress.get("has_clan_style", False)
        
        progress_text = (
            f"\n**Progress:**\n"
            f"{'✅' if has_expectations else '⬜'} Expectations {'✓' if has_expectations else ''}\n"
            f"{'✅' if has_clan_level else '⬜'} Minimum Clan Level\n"
            f"{'✅' if has_capital_hall else '⬜'} Minimum Capital Hall Level\n"
            f"{'✅' if has_cwl_league else '⬜'} CWL League Preference\n"
            f"{'✅' if has_clan_style else '⬜'} Clan Style Preference"
        )
        components_list.append(Text(content=progress_text))

    if not formatted_summary:
        # Initial message with detailed instructions
        components_list.append(Separator(divider=True))
        components_list.append(Text(content=detailed_content))

        # Add instruction at the bottom
        components_list.append(Text(
            content="\n💡 _Type your preferences below and I'll categorize them automatically! Click Done when finished._"
        ))
    else:
        # Once user starts typing, show their organized summary
        components_list.append(
            Text(
                content="📝 **Share what you're looking for in a clan!**\n\n*Continue typing or click Done when finished.*")
        )

        # Add current summary
        components_list.append(Separator(divider=True))
        components_list.append(Text(content="**📋 Your Clan Expectations:**"))
        components_list.append(Text(content=formatted_summary))

    # Add footer image
    components_list.append(
        Media(items=[MediaItem(media="assets/Blue_Footer.png")])
    )

    # Add Done button if requested
    if show_done_button:
        custom_id = f"clan_expectations_done:{channel_id}_{user_id}" if channel_id and user_id else "clan_expectations_done:done"
        
        # Check if expectations are provided
        has_expectations = progress and progress.get("has_expectations", False)
        
        done_button = Button(
            style=hikari.ButtonStyle.SUCCESS if has_expectations else hikari.ButtonStyle.SECONDARY,
            label="Done" if has_expectations else "Add expectations first",
            custom_id=custom_id,
            is_disabled=not has_expectations
        )
        done_button.set_emoji("✅" if has_expectations else "⏳")

        # Add button in a Section
        components_list.append(
            Section(
                components=[
                    Text(content="Finished sharing your expectations? Click Done to proceed to the next question.")
                ],
                accessory=done_button
            )
        )

    # Create and return container
    return [
        Container(
            accent_color=BLUE_ACCENT,
            components=components_list
        )
    ]


async def send_clan_expectations(channel_id: int, user_id: int) -> None:
    """Send the clan expectations collection question"""

    if not mongo_client or not bot_instance:
        print("[ClanExpectations] Error: Not initialized")
        return

    try:
        # Update state
        await mongo_client.ticket_automation_state.update_one(
            {"_id": str(channel_id)},
            {
                "$set": {
                    "step_data.questionnaire.current_question": "future_clan_expectations",
                    "step_data.questionnaire.awaiting_response": True,
                    "step_data.questionnaire.collecting_expectations": True,
                    "step_data.questionnaire.expectations_started_at": datetime.now(timezone.utc),
                    "step_data.questionnaire.expectations_progress": {
                        "has_expectations": False,
                        "has_clan_level": False,
                        "has_capital_hall": False,
                        "has_cwl_league": False,
                        "has_clan_style": False
                    }
                }
            }
        )

        # Build the question content inline
        title = QUESTION_TITLE
        detailed_content = QUESTION_CONTENT()
        
        # Create components with initial progress state
        initial_progress = {
            "has_expectations": False,
            "has_clan_level": False,
            "has_capital_hall": False,
            "has_cwl_league": False,
            "has_clan_style": False
        }

        # Create components
        components = create_clan_expectations_components(
            current_summary="",  # Empty initially
            title=title,
            detailed_content=detailed_content,
            show_done_button=True,
            include_user_ping=True,
            channel_id=channel_id,
            user_id=user_id,
            progress=initial_progress
        )

        # Send message
        channel = await bot_instance.rest.fetch_channel(channel_id)
        msg = await channel.send(
            components=components,
            user_mentions=True
        )

        # Store message ID
        await StateManager.store_message_id(
            str(channel_id),
            "questionnaire_future_clan_expectations",
            str(msg.id)
        )

        print(f"[ClanExpectations] Sent question to channel {channel_id}, message ID: {msg.id}")

    except Exception as e:
        print(f"[ClanExpectations] Error sending question: {e}")
        import traceback
        traceback.print_exc()


async def process_user_input(channel_id: int, user_id: int, content: str) -> None:
    """Process user input and update the expectations summary"""

    if not mongo_client:
        return

    try:
        # Get current state
        ticket_state = await StateManager.get_ticket_state(str(channel_id))
        if not ticket_state:
            return

        # Get current summary
        current_summary = ticket_state.get("step_data", {}).get("questionnaire", {}).get("expectations_summary", "")

        # Process with AI (using the imported processor like attack_strategies does)
        updated_summary, progress = await process_clan_expectations_with_ai(current_summary, content)

        # Update the summary and progress in state
        await mongo_client.ticket_automation_state.update_one(
            {"_id": str(channel_id)},
            {
                "$set": {
                    "step_data.questionnaire.expectations_summary": updated_summary,
                    "step_data.questionnaire.last_expectations_input": content,
                    "step_data.questionnaire.last_input_at": datetime.now(timezone.utc),
                    "step_data.questionnaire.expectations_progress": progress
                }
            }
        )

        # Get message ID
        message_id = ticket_state.get("messages", {}).get("questionnaire_future_clan_expectations")
        if not message_id:
            print("[ClanExpectations] No message ID found to update")
            return

        # Build title and content again for consistency
        title = QUESTION_TITLE
        detailed_content = QUESTION_CONTENT()

        # Update the message with new summary and progress
        new_components = create_clan_expectations_components(
            current_summary=updated_summary,
            title=title,
            detailed_content=detailed_content,
            show_done_button=True,
            include_user_ping=True,
            channel_id=channel_id,
            user_id=user_id,
            progress=progress
        )

        try:
            await bot_instance.rest.edit_message(
                channel=channel_id,
                message=int(message_id),
                components=new_components,
                user_mentions=True
            )
            print(f"[ClanExpectations] Updated message with new summary")
        except hikari.errors.NotFoundError:
            # Message was deleted, create a new one
            print(f"[ClanExpectations] Original message not found, creating new message")
            new_msg = await bot_instance.rest.create_message(
                channel=channel_id,
                components=new_components,
                user_mentions=True
            )
            # Update message ID in state
            await mongo_client.ticket_automation_state.update_one(
                {"_id": str(channel_id)},
                {"$set": {"messages.questionnaire_future_clan_expectations": str(new_msg.id)}}
            )
            print(f"[ClanExpectations] Created new message with ID: {new_msg.id}")

    except Exception as e:
        print(f"[ClanExpectations] Error processing input: {e}")
        import traceback
        traceback.print_exc()


@register_action("clan_expectations_done", no_return=True)
async def handle_clan_expectations_done(
        ctx: lightbulb.components.MenuContext,
        action_id: str,
        **kwargs
):
    """Handle when user clicks Done on clan expectations"""

    channel_id = ctx.channel_id
    user_id = ctx.user.id

    # Verify this is the correct user
    ticket_state = await mongo_client.ticket_automation_state.find_one({"_id": str(channel_id)})
    if not ticket_state:
        await ctx.respond("❌ Ticket state not found.", ephemeral=True)
        return

    stored_user_id = (
            ticket_state.get("discord_id") or
            ticket_state.get("ticket_info", {}).get("user_id") or
            ticket_state.get("user_id")
    )

    if stored_user_id:
        try:
            stored_user_id = int(stored_user_id)
        except (ValueError, TypeError):
            print(f"[ClanExpectations] Error converting user_id: {stored_user_id}")
            pass

    if not stored_user_id or user_id != stored_user_id:
        await ctx.respond("❌ You cannot interact with this ticket.", ephemeral=True)
        return
    
    # Check if they have provided at least one expectation
    progress = ticket_state.get("step_data", {}).get("questionnaire", {}).get("expectations_progress", {})
    if not progress.get("has_expectations", False):
        await ctx.respond("❌ Please provide at least one expectation from your future clan before continuing.", ephemeral=True)
        return

    # Stop collecting expectations
    await mongo_client.ticket_automation_state.update_one(
        {"_id": str(channel_id)},
        {
            "$set": {
                "step_data.questionnaire.collecting_expectations": False,
                "step_data.questionnaire.awaiting_response": False
            }
        }
    )

    # Get the current expectations summary and progress
    current_summary = ticket_state.get("step_data", {}).get("questionnaire", {}).get("expectations_summary", "")
    current_progress = ticket_state.get("step_data", {}).get("questionnaire", {}).get("expectations_progress", {
        "has_expectations": False,
        "has_clan_level": False,
        "has_capital_hall": False,
        "has_cwl_league": False,
        "has_clan_style": False
    })

    # Format summary with emojis for display
    formatted_summary = current_summary.replace("{red_arrow}", str(emojis.red_arrow_right))
    formatted_summary = formatted_summary.replace("{white_arrow}", str(emojis.white_arrow_right))
    formatted_summary = formatted_summary.replace("{blank}", str(emojis.blank))

    # Build content again
    title = QUESTION_TITLE
    detailed_content = QUESTION_CONTENT()

    # Create final components without Done button and without ping
    final_components = create_clan_expectations_components(
        current_summary=current_summary,  # Pass original summary (formatting happens inside function)
        title=title,
        detailed_content=detailed_content,
        show_done_button=False,
        include_user_ping=False,  # No ping on final version
        progress=current_progress
    )

    # Update the message to remove the Done button
    await ctx.interaction.edit_initial_response(components=final_components)

    # Wait and move to next question
    await asyncio.sleep(2)

    # Move to next question
    from ..core import questionnaire_manager
    next_question = "discord_basic_skills"  # Next question after clan expectations
    if next_question:
        await questionnaire_manager.send_question(channel_id, user_id, next_question)

    print(f"[ClanExpectations] User {user_id} completed clan expectations")