# extensions/commands/help.py
"""
Integrated help command with AI support using Anthropic Claude.
Lists all bot commands and provides an AI assistant for questions.
"""

import os
import asyncio
import aiohttp
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone

import hikari
import lightbulb

from hikari.impl import (
    MessageActionRowBuilder as ActionRow,
    TextSelectMenuBuilder as TextSelectMenu,
    SelectOptionBuilder as SelectOption,
    ContainerComponentBuilder as Container,
    SectionComponentBuilder as Section,
    InteractiveButtonBuilder as Button,
    TextDisplayComponentBuilder as Text,
    SeparatorComponentBuilder as Separator,
    MediaGalleryComponentBuilder as Media,
    MediaGalleryItemBuilder as MediaItem,
    ModalActionRowBuilder as ModalActionRow,
)

from extensions.components import register_action
from utils.constants import BLUE_ACCENT, GREEN_ACCENT, DARK_MAGENTA_ACCENT, GOLD_ACCENT
from utils.mongo import MongoClient
from utils.emoji import emojis

loader = lightbulb.Loader()

# AI Configuration
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
AI_MODEL = "claude-3-haiku-20240307"
MAX_TOKENS = 1500

# Help categories
HELP_CATEGORIES = {
    "clan": {
        "name": "Clan Management",
        "emoji": "🏰",
        "description": "Commands to manage your clans and data"
    },
    "recruit": {
        "name": "Recruitment",
        "emoji": "👥",
        "description": "Complete recruitment system with bidding and questionnaires"
    },
    "fwa": {
        "name": "FWA Tools",
        "emoji": "⚔️",
        "description": "Farm War Alliance bases, weights, and strategies"
    },
    "new_clan": {
        "name": "Adding a New Clan",
        "emoji": "🆕",
        "description": "Step-by-step guide to add a new clan to the family"
    },
    "polls": {
        "name": "Polls",
        "emoji": "🗳️",
        "description": "Create and manage interactive polls"
    },
    "general": {
        "name": "General",
        "emoji": "📋",
        "description": "Other helpful commands and features"
    }
}

# Predefined command list (since dynamic discovery might be complex)
COMMAND_LIST = {
    "clan": [
        ("/clan dashboard", "Open the comprehensive Clan Management Dashboard with interactive buttons for clan points, FWA data, member management, and statistics"),
        ("/clan info-hub", "Access the clan information hub with category buttons for Main, Feeder, Zen, FWA, and Trial clans"),
        ("/clan recruit-points", "Report recruitment activities to earn clan points - track Discord posts, DMs, helping members, and other contributions"),
        ("/clan round-table", "Manage clan round table (right-hand leader) roles and permissions for clan leadership"),
    ],
    "recruit": [
        ("📖 Recruitment Guide", "Complete recruitment documentation located at the top of <#1435996160950009917> - includes command tutorials, staff hierarchy, blind bidding guide, and essential recruitment details"),
        ("/clan list", "Send clan assignment to a new recruit with welcome message and clan details - select a recruit and assign them to a clan"),
        ("/recruit questions", "Send comprehensive recruitment questionnaire to new recruits - includes FWA base questions, attack strategies, age brackets, and expectations (15-20 minute review time)"),
        ("/recruit bidding", "Start a competitive 15-minute bidding auction for available recruits - clan leaders bid points to win candidates"),
        ("/recruit welcome", "Send a personalized clan welcome message to new members - only available to clan leaders"),
        ("/recruit deny", "Send a professional denial message to applicants with a clear reason for the decision"),
    ],
    "fwa": [
        ("/fwa bases", "Browse and display FWA base layouts by Town Hall level - select a user and their TH level to view bases"),
        ("/fwa chocolate", "Look up players or clans on the FWA Chocolate website for verification and war data"),
        ("/fwa links", "Quick access to essential FWA links - verification forms, war weight entry, and important resources"),
        ("/fwa war-plans", "Generate strategic war plan messages for different war scenarios and outcomes"),
        ("/fwa weight", "Calculate war weight from storage values - automatically converts storage to war weight (×5 multiplier)"),
        ("/fwa lazycwl-snapshot", "Take a snapshot of FWA clan players during CWL to track who needs to return for sync wars - captures current roster for monitoring"),
        ("/fwa lazycwl-ping", "Ping missing players to return to their FWA home clans for sync wars - automated reminders with Discord mentions (Train⇨Join⇨Attack⇨Return 15-30min)"),
        ("/fwa lazycwl-status", "View all active LazyCWL snapshots with player counts, Discord coverage, and creation dates - see what clans are being tracked"),
        ("/fwa lazycwl-roster", "Display complete player roster from any active snapshot - shows all players with TH levels, tags, and Discord link status"),
        ("/fwa lazycwl-autopings-start", "Start automated periodic pinging (every 30min/1hr/2hr) for missing players - runs for up to 7 days or until snapshot reset"),
        ("/fwa lazycwl-autopings-stop", "Stop automated periodic pinging for a snapshot - disables the auto-ping system"),
        ("/fwa lazycwl-autopings-status", "View status of all active auto-pings with countdown timers, intervals, and ping counts"),
        ("/fwa lazycwl-remove-player", "Remove player(s) from a snapshot to stop auto-pinging them - useful when players leave permanently"),
        ("/fwa lazycwl-reset", "Deactivate all active LazyCWL snapshots after wars complete - clears all tracking for the next CWL season"),
    ],
    "new_clan": [
        ("📺 Video Tutorials", "Watch these YouTube tutorials for visual guidance:\n• Clan Dashboard Tutorial: https://youtu.be/ULh7TX008wE\n• Setup ClashKing Logs: https://youtu.be/6p8ILBh07yc"),

        ("Step 1: Add Clan to Dashboard", "Use Clan Dashboard in <#1345587617223151758> → Click 'Update Clan Information' → 'Add a Clan'\n• Enter the clan tag from Clash of Clans\n• Choose your role setup option:\n  - ✅ **Auto-create roles**: Bot creates clan role + leadership role automatically\n  - 📋 **Select existing**: Choose from Discord's existing roles\n  - ⏭️ **Skip for now**: Set up roles later in the edit menu"),

        ("Step 2: Clone Category Structure", "Use `/utilities clone-category` command:\n• Select an existing clan category (e.g., Silent Hill)\n• Choose your new clan from the dropdown\n• This copies all channels with proper permissions"),

        ("Step 3: Complete Setup", "Return to Clan Dashboard in <#1345587617223151758> → 'Update Clan Information' → 'Edit a Clan':\n• Update channel IDs with the newly cloned channels\n• Set announcement, chat, and leadership channels\n• Configure any clan-specific settings like logo and profile"),

        ("⚠️ Important Notes", "• The bot handles role creation automatically if you choose auto-create\n• Clone from a similar clan type (FWA, Trial, etc.)\n• Double-check all channel assignments after cloning\n• Test permissions and functionality before going live"),
    ],
    "polls": [
        ("/poll create", "Create interactive polls with multiple choice options and real-time voting"),
        ("/poll view", "View detailed results and statistics for any poll"),
        ("/poll active", "List all currently active polls in the server"),
    ],
    "general": [
        ("/help", "Show this comprehensive help menu with AI assistant - you're using it right now!"),
        ("/say", "Send a message as the bot (staff only) - useful for announcements and official communications"),
        ("/den-den-mushi", "Broadcast important messages through the Den Den Mushi transponder snail system"),
        ("/howto link", "Learn how to properly link your Clash of Clans account to Discord"),
        ("/color-roles", "Choose your display color from available role options"),
    ]
}


async def create_help_menu_components(selected_category: Optional[str] = None) -> list:
    """Create the help menu components with category selector."""
    components = []

    # Header
    components.extend([
        Text(content="# 📚 Bot Help Center"),
        Text(content="Pick a category below OR ask the AI helper for help! 🤖"),
        Text(content="💡 **Tip:** The AI helper can tell you exactly which buttons to click!"),
        Separator(),
    ])

    # Category selector
    select_options = []
    for cat_id, cat_info in HELP_CATEGORIES.items():
        select_options.append(
            SelectOption(
                label=cat_info["name"],
                value=cat_id,
                description=cat_info["description"],
                emoji=cat_info["emoji"],
                is_default=(cat_id == selected_category)
            )
        )

    components.extend([
        ActionRow(
            components=[
                TextSelectMenu(
                    custom_id="help_category_select:menu",
                    placeholder="Pick a category to see commands...",
                    max_values=1,
                    options=select_options
                )
            ]
        ),
        Separator(),
    ])

    # Action buttons
    components.append(
        ActionRow(
            components=[
                Button(
                    style=hikari.ButtonStyle.PRIMARY,
                    custom_id="help_ai_assistant:main",
                    label="Ask the AI Helper",
                    emoji="🤖"
                ),
                Button(
                    style=hikari.ButtonStyle.SECONDARY,
                    custom_id="help_refresh:main",
                    label="Refresh",
                    emoji="🔄"
                ),
            ]
        )
    )

    return [Container(accent_color=BLUE_ACCENT, components=components)]


async def create_category_view(category: str) -> list:
    """Create a view showing commands in a specific category."""
    cat_info = HELP_CATEGORIES.get(category, {"name": "Unknown", "emoji": "❓"})
    commands = COMMAND_LIST.get(category, [])

    components = [
        Text(content=f"# {cat_info['emoji']} {cat_info['name']} Commands"),
        Separator(),
    ]

    # List commands
    for cmd_name, cmd_desc in commands:
        components.append(
            Text(content=f"**{cmd_name}**\n{cmd_desc}")
        )
        components.append(Separator(divider=False, spacing=hikari.SpacingType.SMALL))

    # Back button
    components.extend([
        Separator(),
        ActionRow(
            components=[
                Button(
                    style=hikari.ButtonStyle.SECONDARY,
                    custom_id="help_back:category",
                    label="Back to Categories",
                    emoji="◀️"
                ),
                Button(
                    style=hikari.ButtonStyle.PRIMARY,
                    custom_id="help_ai_assistant:category",
                    label="Ask the AI Helper",
                    emoji="🤖"
                ),
            ]
        )
    ])

    return [Container(accent_color=BLUE_ACCENT, components=components)]


async def call_claude_api(user_question: str) -> str:
    """Call Claude API for help with bot commands."""

    # Special response for Fayez
    if "fayez" in user_question.lower():
        return "https://c.tenor.com/-lFxNI2gjGwAAAAd/tenor.gif"

    if not ANTHROPIC_API_KEY:
        return "❌ Oops! The AI helper isn't set up yet. Please ask a staff member for help!"

    # Create bot context from command list
    bot_context = "Here are all the bot commands I can help you with:\n\n"
    for category, commands in COMMAND_LIST.items():
        cat_info = HELP_CATEGORIES.get(category, {"name": category.title()})
        bot_context += f"📂 **{cat_info['name']} Commands:**\n"
        for cmd_name, cmd_desc in commands:
            bot_context += f"  • {cmd_name}\n    → {cmd_desc}\n"
        bot_context += "\n"

    system_prompt = f"""You are a friendly Discord bot helper for the Arcane Python bot used by the Kings Alliance Clash of Clans community! You help people use bot commands in simple, easy-to-understand ways with special expertise in the recruitment system.

{bot_context}

Important Rules:
- Use VERY simple words (like you're explaining to a 5th grader)
- Be super specific about WHERE to find things
- Give step-by-step instructions with timing details when relevant
- Use emojis to make it fun and clear 😊
- Focus heavily on recruitment workflows since they're complex

When someone asks "where" or "how" to find something:
1. Tell them the EXACT command name
2. Tell them EXACTLY what to click/select
3. Number your steps (Step 1, Step 2, etc.)
4. Include timing information for recruitment processes

Examples of good answers for RECRUITMENT:
- "Need help with recruitment? Check the complete guide at the top of <#1435996160950009917> - it has command tutorials, staff hierarchy, blind bidding guide, and everything you need!"
- "Want to send recruit questions? Use `/recruit questions` → pick the Discord user → they get a comprehensive questionnaire about FWA bases, attack strategies, age, and expectations → leaders have 15-20 minutes to review!"
- "Start bidding for recruits? Use `/recruit bidding` → select the Discord user → clans bid points in a 15-minute auction → highest bidder wins!"
- "Send welcome messages? Use `/recruit welcome` → pick your clan → select the Discord user → they get your clan's custom welcome message (only clan leaders can do this!)"
- "Deny an application? Use `/recruit deny` → select the user → write a clear reason → they get a professional denial message"

Examples for OTHER COMMANDS:
- "See clan info? Use `/clan info-hub` → click buttons for 'Main', 'Feeder', 'Zen', 'FWA', or 'Trial' clans"
- "Add clan points? Use `/clan dashboard` → click 'Clan Points' → pick your clan → report your recruitment activities"
- "Get FWA bases? Use `/fwa bases` → pick a Discord user → select their Town Hall level → see their base layouts"
- "Calculate war weight? Use `/fwa weight` → enter storage value → automatically multiplied by 5 for war weight"
- "Create polls? Use `/poll create` → fill in your question and options → members can vote with real-time results"

Examples for LAZYCWL TRACKING SYSTEM:
- "Track players during CWL? Use `/fwa lazycwl-snapshot` → pick your FWA clan → bot saves who's in the clan right now → helps track who leaves for CWL wars"
- "Ping missing players? Use `/fwa lazycwl-ping` → pick which clan snapshot → bot checks who's missing → sends reminders to return (Train⇨Join⇨Attack⇨Return 15-30min max!)"
- "See all tracked clans? Use `/fwa lazycwl-status` → shows all active snapshots → see player counts and Discord coverage for each clan"
- "View full roster? Use `/fwa lazycwl-roster` → pick a clan snapshot → see every player with TH level, tag, and Discord link status"
- "Auto-ping missing players? Use `/fwa lazycwl-autopings-start` → pick snapshot → choose interval (30min/1hr/2hr) → bot automatically pings missing players for up to 7 days!"
- "Stop auto-pinging? Use `/fwa lazycwl-autopings-stop` → pick the snapshot → auto-ping system turns off immediately"
- "Check auto-ping status? Use `/fwa lazycwl-autopings-status` → see all active auto-pings → shows time remaining, ping counts, and intervals"
- "Remove player from tracking? Use `/fwa lazycwl-remove-player` → pick snapshot → select players → they stop getting pinged (useful when they leave permanently)"
- "Finish CWL tracking? Use `/fwa lazycwl-reset` → clears all snapshots AND stops all auto-pings → use this after wars end to start fresh next month"
- "LazyCWL Workflow: Snapshot clans FIRST → Players leave for CWL wars → Start auto-ping OR manual ping → Remove players who left permanently → Check roster to see who's linked → Reset after CWL ends"

Examples for ADDING NEW CLANS:
- "Adding a new clan? First watch the YouTube tutorials → Use Clan Dashboard in <#1345587617223151758> → Click 'Add a Clan' → Choose auto-create roles or select existing → Clone channels with `/utilities clone-category` → Finish setup in dashboard"
- "Need help with new clan setup? Check the 'Adding a New Clan' help section → Has video tutorials, step-by-step guide, and all the commands you need → Dashboard handles role creation automatically!"

RECRUITMENT SYSTEM DETAILS to include when relevant:
- Questions take 15-20 minutes for leaders to review
- Bidding auctions last exactly 15 minutes
- Clan recruitment help posts have a 30-day cooldown
- Only clan leaders can send welcome messages
- Bidding uses clan points as currency

NEW CLAN ADDITION PROCESS:
- Add clan to dashboard FIRST in <#1345587617223151758> → Choose role creation option (auto-create, select existing, or skip)
- Clone category structure SECOND using `/utilities clone-category` from existing clan
- Complete setup THIRD by updating channel IDs and settings in dashboard
- Three role options: ✅ Auto-create (bot makes roles), 📋 Select existing (choose from Discord), ⏭️ Skip (set up later)
- Video tutorials available: https://youtu.be/ULh7TX008wE and https://youtu.be/6p8ILBh07yc

Always:
- Break down big words into smaller ones
- Use arrows (→) to show what happens next
- Say which buttons to press or menus to pick
- Include timing for recruitment processes (15-20 min reviews, 15 min bidding)
- Mention role restrictions (clan leaders only for some commands)
- If something has multiple steps, list them as 1, 2, 3...
- End with "Need more help? Just ask!"

Never use big technical words. Instead of "parameters" say "the blanks you fill in". Instead of "comprehensive questionnaire" say "lots of questions".

If they ask about something not in the commands, say: "Hmm, I don't know about that command. 🤔 Here's what I CAN help you with: [list 2-3 related commands they might want]. Want to try one of these instead?"

SPECIAL FOCUS: When users ask about recruitment, always mention the full workflow and timing since it's the most complex system in the bot! For detailed recruitment help, always direct them to the comprehensive guide at the top of <#1435996160950009917> which has command tutorials, staff hierarchy, blind bidding guide, and essential recruitment details.

SPECIAL FOCUS: When users ask about adding new clans, setting up clans, creating clans, or expanding the family, always mention the proper workflow order and direct them to the 'Adding a New Clan' help section for complete step-by-step instructions and video tutorials!

SPECIAL FOCUS: When users ask about LazyCWL, CWL tracking, or tracking players during CWL wars, explain the complete workflow: Take snapshot FIRST → Players leave for CWL → Start auto-ping (automated) OR use manual ping → Remove players who left permanently → Check roster to see Discord links → Reset after CWL ends (this also stops all auto-pings). The 15-30 minute window (Train⇨Join⇨Attack⇨Return) is critical! Auto-ping can run every 30min, 1hr, or 2hr for up to 7 days automatically!

Remember: Make it so easy that anyone can understand, especially the recruitment system! 🌟"""

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }

    payload = {
        "model": AI_MODEL,
        "max_tokens": MAX_TOKENS,
        "messages": [
            {
                "role": "user",
                "content": user_question
            }
        ],
        "system": system_prompt
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(ANTHROPIC_API_URL, headers=headers, json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    return result["content"][0]["text"]
                else:
                    error_text = await response.text()
                    print(f"[Help AI] API error {response.status}: {error_text}")
                    return "❌ Oops! Something went wrong. Try asking your question in a different way!"
    except Exception as e:
        print(f"[Help AI] Error calling Claude API: {e}")
        return "❌ The AI helper is taking a break! Please try again in a moment."


@loader.command
class Help(
    lightbulb.SlashCommand,
    name="help",
    description="Get help with bot commands or ask questions",
):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        await ctx.respond(
            components=await create_help_menu_components(),
            ephemeral=True
        )


@register_action("help_category_select", opens_modal=False, ephemeral=True)
async def handle_category_select(ctx, action_id: str, **kwargs) -> list:
    """Handle category selection from dropdown."""
    # Get selected value from interaction
    selected_category = ctx.interaction.values[0]

    # Return the category view components
    return await create_category_view(selected_category)


@register_action("help_back", no_return=True, ephemeral=True)
async def handle_back_button(ctx, action_id: str, **kwargs) -> None:
    """Handle back button to return to main menu."""
    # The interaction is already deferred by component handler
    await ctx.interaction.edit_initial_response(
        components=await create_help_menu_components()
    )


@register_action("help_refresh", no_return=True, ephemeral=True)
async def handle_refresh(ctx, action_id: str, **kwargs) -> None:
    """Refresh the help menu."""
    # The interaction is already deferred by component handler
    await ctx.interaction.edit_initial_response(
        components=await create_help_menu_components()
    )


@register_action("help_ai_assistant", opens_modal=True, no_return=True)
async def handle_ai_assistant(ctx, action_id: str, **kwargs) -> None:
    """Open modal for AI assistant question."""
    question_input = ModalActionRow().add_text_input(
        "ai_question",  # custom_id (positional)
        "Ask me anything about the bot!",  # label (positional)
        placeholder="Examples: How do I see FWA bases? Where are recruit questions? How do I bid?",
        required=True,
        style=hikari.TextInputStyle.PARAGRAPH,
        min_length=5,
        max_length=500
    )

    await ctx.respond_with_modal(
        title="Ask the Bot Helper",
        custom_id="help_ai_modal:question",
        components=[question_input]
    )


@register_action("help_ai_modal", no_return=True, is_modal=True)
async def handle_ai_modal_submit(ctx: lightbulb.components.ModalContext, action_id: str, **kwargs) -> None:
    """Handle AI assistant modal submission."""
    # Get the question
    question = ""
    for row in ctx.interaction.components:
        for comp in row:
            if comp.custom_id == "ai_question":
                question = comp.value
                break

    if not question:
        await ctx.respond("Please provide a question!", ephemeral=True)
        return

    # Defer while processing
    await ctx.interaction.create_initial_response(
        hikari.ResponseType.DEFERRED_MESSAGE_CREATE,
        flags=hikari.MessageFlag.EPHEMERAL
    )

    # Get AI response
    ai_response = await call_claude_api(question)

    # Check if response is the Fayez GIF
    is_fayez_gif = ai_response == "https://c.tenor.com/-lFxNI2gjGwAAAAd/tenor.gif"

    # Create response components
    if is_fayez_gif:
        # Special handling for Fayez GIF - display as image
        components = [
            Container(
                accent_color=GREEN_ACCENT,
                components=[
                    Text(content="## 🤖 AI Helper Response"),
                    Separator(),
                    Text(content=f"**You asked:**\n{question}"),
                    Separator(),
                    Media(items=[MediaItem(media=ai_response)]),
                    Separator(),
                    ActionRow(
                        components=[
                            Button(
                                style=hikari.ButtonStyle.PRIMARY,
                                custom_id="help_ai_assistant:response",
                                label="Ask Something Else",
                                emoji="💭"
                            ),
                            Button(
                                style=hikari.ButtonStyle.SECONDARY,
                                custom_id="help_ai_back_to_menu:response",
                                label="Back to Help Menu",
                                emoji="📚"
                            ),
                        ]
                    )
                ]
            )
        ]
    else:
        # Normal text response
        components = [
            Container(
                accent_color=GREEN_ACCENT,
                components=[
                    Text(content="## 🤖 AI Helper Response"),
                    Separator(),
                    Text(content=f"**You asked:**\n{question}"),
                    Separator(),
                    Text(content=f"**Here's my answer:**\n{ai_response}"),
                    Separator(),
                    Text(content="💡 **Still confused?** Try asking in a different way!"),
                    Separator(),
                    ActionRow(
                        components=[
                            Button(
                                style=hikari.ButtonStyle.PRIMARY,
                                custom_id="help_ai_assistant:response",
                                label="Ask Something Else",
                                emoji="💭"
                            ),
                            Button(
                                style=hikari.ButtonStyle.SECONDARY,
                                custom_id="help_ai_back_to_menu:response",
                                label="Back to Help Menu",
                                emoji="📚"
                            ),
                        ]
                    )
                ]
            )
        ]

    await ctx.interaction.edit_initial_response(
        content="",
        components=components
    )


@register_action("help_ai_back_to_menu", no_return=True)
async def handle_ai_back_to_menu(ctx, action_id: str, **kwargs) -> None:
    """Handle back to menu from AI response."""
    # The interaction is already deferred by component handler
    await ctx.interaction.edit_initial_response(
        components=await create_help_menu_components()
    )


# Add the command to the loader
loader.command(Help)