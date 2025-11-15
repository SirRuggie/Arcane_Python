"""
Staff Dashboard Action Handlers
Handles all button clicks, dropdowns, and modal submissions
"""

import lightbulb
import hikari
from datetime import datetime, timezone
from hikari.impl import (
    ContainerComponentBuilder as Container,
    TextDisplayComponentBuilder as Text,
    SeparatorComponentBuilder as Separator,
    MediaGalleryComponentBuilder as Media,
    MediaGalleryItemBuilder as MediaItem,
    SelectMenuBuilder as SelectMenu,
    TextSelectMenuBuilder as TextSelectMenu,
    InteractiveButtonBuilder as Button,
    MessageActionRowBuilder as ActionRow,
)

from extensions.components import register_action
from utils.constants import BLUE_ACCENT, GREEN_ACCENT, GOLD_ACCENT, DARK_MAGENTA_ACCENT, validate_user_has_role
from utils.mongo import MongoClient
from .utils import (
    is_leadership,
    get_all_staff_logs,
    get_staff_log,
    create_staff_log_thread,
    update_forum_log,
    generate_next_case_id,
    format_discord_timestamp
)
from .embeds import build_main_dashboard, build_staff_record_view, build_filter_view, build_user_selection_for_creation, build_team_position_selection, build_staff_select_menu, build_update_position_selection, build_add_position_selection, build_remove_position_selection, build_which_position_to_update_selection, build_case_type_selection, build_remove_case_selection, build_view_cases_menu, build_all_cases_view, build_user_cases_view, build_edit_dates_selection, build_admin_change_selection
from .modals import (
    build_create_log_modal,
    build_position_modal,
    build_admin_reason_modal,
    build_case_modal,
    build_status_modal,
    build_delete_confirmation_modal,
    build_edit_hire_date_modal,
    build_edit_join_date_modal,
    build_edit_position_date_modal
)

# Only Family Lead role can delete staff records
FAMILY_LEAD_ROLE_ID: int = 1345174718944383027

print("[Staff Dashboard Handlers] Module loaded - registering actions...")


# ========== HELPER FUNCTIONS ==========

def build_error_message(message: str) -> list:
    """Helper to wrap error message in Components v2 container"""
    return [
        Container(
            accent_color=DARK_MAGENTA_ACCENT,
            components=[
                Text(content="## ❌ Error"),
                Separator(divider=True),
                Text(content=message),
                Media(items=[MediaItem(media="assets/Red_Footer.png")])
            ]
        )
    ]


def build_success_message(title: str, details: list[str], footer_text: str = None) -> list:
    """Helper to wrap success message in Components v2 container"""
    components_list = [
        Text(content=f"## ✅ {title}"),
        Separator(divider=True),
    ]

    for detail in details:
        components_list.append(Text(content=detail))

    if footer_text:
        components_list.append(Separator(divider=False, spacing=hikari.SpacingType.SMALL))
        components_list.append(Text(content=f"-# {footer_text}"))

    components_list.append(Media(items=[MediaItem(media="assets/Green_Footer.png")]))

    return [
        Container(
            accent_color=GREEN_ACCENT,
            components=components_list
        )
    ]


# ========== USER SELECTION ==========

@register_action("staff_dash_select_user", no_return=True, ephemeral=True, opens_modal=True)
@lightbulb.di.with_di
async def handle_user_select(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    mongo: MongoClient = lightbulb.di.INJECTED,
    bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    **kwargs
):
    """Handle user selection from dropdown - behavior depends on context"""
    # Check if we're in team selection flow
    in_team_flow = action_id.startswith("team_") if action_id else False

    # Only defer for team flow (which updates existing message)
    if in_team_flow:
        await ctx.interaction.create_initial_response(hikari.ResponseType.DEFERRED_MESSAGE_UPDATE)

    # Permission check
    if not is_leadership(ctx.member):
        if in_team_flow:
            await ctx.interaction.edit_initial_response(
                components=build_error_message("❌ Only leadership can view staff logs.")
            )
        else:
            await ctx.respond("❌ Only leadership can view staff logs.", flags=hikari.MessageFlag.EPHEMERAL)
        return

    # Get selected user from TEXT_SELECT_MENU
    if not ctx.interaction.values:
        if in_team_flow:
            await ctx.interaction.edit_initial_response(
                components=build_error_message("❌ No user selected.")
            )
        else:
            await ctx.respond("❌ No user selected.", flags=hikari.MessageFlag.EPHEMERAL)
        return

    selected_user_id = ctx.interaction.values[0]  # user_id string from select menu

    # Fetch user object
    try:
        user = await bot.rest.fetch_user(int(selected_user_id))
    except hikari.NotFoundError:
        if in_team_flow:
            await ctx.interaction.edit_initial_response(
                components=build_error_message("❌ User not found.")
            )
        else:
            await ctx.respond("❌ User not found.", flags=hikari.MessageFlag.EPHEMERAL)
        return

    # Fetch staff log
    log = await get_staff_log(mongo, str(selected_user_id))

    if not log:
        if in_team_flow:
            await ctx.interaction.edit_initial_response(
                components=build_error_message(f"No staff log found for {user.mention}.\n\nUse the **Create New Staff Log** button to create one.")
            )
        else:
            await ctx.respond(
                f"❌ No staff log found for {user.mention}.\n\nUse the **Create New Staff Log** button to create one.",
                flags=hikari.MessageFlag.EPHEMERAL
            )
        return

    # Build staff record view
    components = build_staff_record_view(log, user, ctx.guild_id, from_team_flow=in_team_flow)

    if in_team_flow:
        # UPDATE existing message (team flow navigation)
        await ctx.interaction.edit_initial_response(components=components)
        print(f"[Staff Dashboard] Viewing log for {user.username} (team flow)")
    else:
        # CREATE new ephemeral message (main dashboard behavior)
        await ctx.respond(components=components, flags=hikari.MessageFlag.EPHEMERAL)
        print(f"[Staff Dashboard] Viewing log for {user.username} (new ephemeral)")

        # Auto-refresh the main dashboard to reset dropdown
        all_logs_refresh = await get_all_staff_logs(mongo)
        stats = {
            'active': sum(1 for log in all_logs_refresh if log.get('employment_status') == 'Active'),
            'on_leave': sum(1 for log in all_logs_refresh if log.get('employment_status') == 'On Leave'),
            'inactive': sum(1 for log in all_logs_refresh if log.get('employment_status') in ['Inactive', 'Terminated', 'Staff Banned'])
        }
        dashboard_components = build_main_dashboard(ctx.guild_id, stats, all_logs_refresh)
        await ctx.interaction.edit_message(ctx.interaction.message, components=dashboard_components)


@register_action("staff_dash_view_record", ephemeral=True, no_return=True, defer_update=True)
@lightbulb.di.with_di
async def handle_view_record(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    mongo: MongoClient = lightbulb.di.INJECTED,
    bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    **kwargs
):
    """Handle viewing a staff record (used by Back buttons)"""
    user_id = action_id  # Format: user_id

    # Fetch staff log
    log = await get_staff_log(mongo, user_id)
    if not log:
        await ctx.respond("❌ Staff log not found.", ephemeral=True)
        return

    # Fetch user object
    try:
        user = await bot.rest.fetch_user(int(user_id))
    except hikari.NotFoundError:
        await ctx.respond("❌ User not found.", ephemeral=True)
        return

    # Build and show staff record view
    components = build_staff_record_view(log, user, ctx.guild_id)
    await ctx.interaction.edit_initial_response(components=components)
    print(f"[Staff Dashboard] Returned to record view for {user.username}")


# ========== CREATE NEW LOG ==========

@register_action("staff_dash_create_new", no_return=True, ephemeral=True)
@lightbulb.di.with_di
async def handle_create_new(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    """Handle 'Create New Log' button - shows user selection view"""
    # Permission check
    if not is_leadership(ctx.member):
        await ctx.respond("❌ Only leadership can create staff logs.", ephemeral=True)
        return

    # Capture dashboard message ID for later refresh
    dashboard_msg_id = str(ctx.interaction.message.id)

    # Show user selection view with dashboard message ID
    components = build_user_selection_for_creation(ctx.guild_id, dashboard_msg_id)

    # Create NEW ephemeral message (not edit)
    await ctx.respond(components=components, ephemeral=True)
    print(f"[Staff Dashboard] Create new - showing user selection (dashboard msg: {dashboard_msg_id})")


@register_action("staff_dash_select_for_creation", ephemeral=True, no_return=True, defer_update=True)
@lightbulb.di.with_di
async def handle_select_for_creation(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    mongo: MongoClient = lightbulb.di.INJECTED,
    bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    **kwargs
):
    """Handle user selection for creating new staff log - show team/position selection"""
    # Parse dashboard message ID from action_id
    dashboard_msg_id = action_id  # Format: dashboard_msg_id

    # Permission check
    if not is_leadership(ctx.member):
        await ctx.respond("❌ Only leadership can create staff logs.", ephemeral=True)
        return

    # Get selected user
    if not ctx.interaction.resolved or not ctx.interaction.resolved.users:
        await ctx.respond("❌ No user selected.", ephemeral=True)
        return

    selected_user_id = list(ctx.interaction.resolved.users.keys())[0]
    user = ctx.interaction.resolved.users[selected_user_id]

    # Check if log already exists
    existing_log = await get_staff_log(mongo, str(selected_user_id))
    if existing_log:
        await ctx.respond(
            f"❌ **Staff log already exists** for {user.mention}!\n\n"
            f"Use the main dashboard to view and edit their existing log.",
            ephemeral=True
        )
        return

    # Show team/position selection view with dashboard message ID
    components = build_team_position_selection(ctx.guild_id, user, dashboard_msg_id=dashboard_msg_id)
    await ctx.interaction.edit_initial_response(components=components)
    print(f"[Staff Dashboard] Showing team/position selection for {user.username}")


@register_action("staff_dash_team_select", ephemeral=True, no_return=True, defer_update=True)
@lightbulb.di.with_di
async def handle_team_select(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    **kwargs
):
    """Handle team selection - update position dropdown"""
    # Parse action_id: Format could be user_id or user_id:dashboard_msg_id
    parts = action_id.split(':')
    user_id = parts[0]
    dashboard_msg_id = parts[1] if len(parts) > 1 else None

    # Get selected team
    if not ctx.interaction.values:
        return

    selected_team = ctx.interaction.values[0]

    # Fetch user
    try:
        user = await bot.rest.fetch_user(int(user_id))
    except hikari.NotFoundError:
        await ctx.respond("❌ User not found.", ephemeral=True)
        return

    # Rebuild view with new team selected
    components = build_team_position_selection(ctx.guild_id, user, selected_team=selected_team, dashboard_msg_id=dashboard_msg_id)
    await ctx.interaction.edit_initial_response(components=components)
    print(f"[Staff Dashboard] Team selected: {selected_team}")


@register_action("staff_dash_position_select", ephemeral=True, no_return=True, defer_update=True)
@lightbulb.di.with_di
async def handle_position_select(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    **kwargs
):
    """Handle position selection - update Continue button with team and position data"""
    # Parse action_id format: user_id:selected_team or user_id:selected_team:dashboard_msg_id
    parts = action_id.split(':')
    user_id = parts[0]
    selected_team = parts[1] if len(parts) > 1 else None
    dashboard_msg_id = parts[2] if len(parts) > 2 else None

    # Get selected position from interaction values
    selected_position = ctx.interaction.values[0]

    if not selected_team or not selected_position:
        await ctx.respond("❌ Missing team or position data.", ephemeral=True)
        return

    # Fetch user
    try:
        user = await bot.rest.fetch_user(int(user_id))
    except hikari.NotFoundError:
        await ctx.respond("❌ User not found.", ephemeral=True)
        return

    # Rebuild view with Continue button now containing team:position in custom_id
    components = build_team_position_selection(
        ctx.guild_id,
        user,
        selected_team=selected_team,
        selected_position=selected_position,
        dashboard_msg_id=dashboard_msg_id
    )

    await ctx.interaction.edit_initial_response(components=components)
    print(f"[Staff Dashboard] Position selected: {selected_team} - {selected_position}")


@register_action("staff_dash_continue_creation", no_return=True, opens_modal=True, ephemeral=True)
async def handle_continue_creation(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    **kwargs
):
    """Handle Continue button - open hire date modal with team/position data"""
    # Parse action_id format: user_id:team:position or user_id:team:position:dashboard_msg_id
    parts = action_id.split(':')

    if len(parts) < 3:
        await ctx.respond(
            "❌ Please select both a **team** and **position** before continuing.",
            ephemeral=True
        )
        return

    user_id = parts[0]
    team = parts[1]
    position = parts[2]
    dashboard_msg_id = parts[3] if len(parts) > 3 else None

    # Pass team/position/dashboard_msg_id through modal custom_id
    modal = build_create_log_modal(user_id, team, position, dashboard_msg_id)
    await ctx.interaction.create_modal_response(
        title=modal.title,
        custom_id=modal.custom_id,
        components=modal.components
    )
    print(f"[Staff Dashboard] Continue creation - Team: {team}, Position: {position}")


@register_action("staff_dash_create_submit", no_return=True, is_modal=True, ephemeral=True)
@lightbulb.di.with_di
async def handle_create_submit(
    action_id: str,
    ctx: lightbulb.components.ModalContext,
    bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    """Process staff log creation from modal"""
    # Defer immediately to prevent timeout
    await ctx.interaction.create_initial_response(
        hikari.ResponseType.DEFERRED_MESSAGE_UPDATE
    )

    # Parse action_id format: user_id:team:position or user_id:team:position:dashboard_msg_id
    parts = action_id.split(':')
    if len(parts) < 3:
        await ctx.interaction.edit_initial_response(
            components=build_error_message("Invalid data format. Please start over.")
        )
        return

    user_id = parts[0]
    team = parts[1]
    position = parts[2]
    dashboard_msg_id = parts[3] if len(parts) > 3 else None

    # Get hire date from modal
    hire_date_str = ctx.interaction.components[0].components[0].value

    # Parse hire date
    try:
        hire_date = datetime.strptime(hire_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        await ctx.interaction.edit_initial_response(
            components=build_error_message("Invalid hire date format. Use YYYY-MM-DD")
        )
        return

    # Fetch user and member objects
    try:
        user = await bot.rest.fetch_user(int(user_id))
        member = await bot.rest.fetch_member(ctx.guild_id, int(user_id))
    except hikari.NotFoundError:
        await ctx.interaction.edit_initial_response(
            components=build_error_message("User not found in this server.")
        )
        return

    # Validate role match (warn but allow)
    has_role = validate_user_has_role(member, team, position)
    role_warning = ""
    if not has_role:
        role_warning = "\n\n⚠️ **Warning**: User does not have the Discord role for this position."

    # Create staff log thread and database entry
    try:
        log = await create_staff_log_thread(
            bot=bot,
            mongo=mongo,
            user=user,
            member=member,
            hire_date=hire_date,
            team=team,
            position=position,
            created_by=ctx.user
        )

        details = [
            f"**User:** {user.mention}",
            f"**Team:** {team}",
            f"**Position:** {position}",
            f"**Hire Date:** {hire_date_str}",
        ]
        if role_warning:
            details.append(f"\n⚠️ **Warning:** User does not have the Discord role for this position.")
        details.append(f"\n**Forum thread:** <#{log['forum_thread_id']}>")

        await ctx.interaction.edit_initial_response(
            components=build_success_message("Staff Log Created Successfully", details)
        )
        print(f"[Staff Dashboard] Created new staff log for {user.username}")

        # Auto-refresh the main dashboard to show new staff member
        if dashboard_msg_id:
            try:
                all_logs_refresh = await get_all_staff_logs(mongo)
                stats = {
                    'active': sum(1 for log in all_logs_refresh if log.get('employment_status') == 'Active'),
                    'on_leave': sum(1 for log in all_logs_refresh if log.get('employment_status') == 'On Leave'),
                    'inactive': sum(1 for log in all_logs_refresh if log.get('employment_status') in ['Inactive', 'Terminated', 'Staff Banned'])
                }
                dashboard_components = build_main_dashboard(ctx.guild_id, stats, all_logs_refresh)

                # Fetch and edit the original dashboard message
                dashboard_message = await bot.rest.fetch_message(ctx.channel_id, int(dashboard_msg_id))
                await bot.rest.edit_message(ctx.channel_id, dashboard_message, components=dashboard_components)
                print(f"[Staff Dashboard] Successfully refreshed main dashboard (msg: {dashboard_msg_id})")
            except Exception as refresh_error:
                print(f"[Staff Dashboard] Failed to refresh dashboard: {refresh_error}")
        else:
            print(f"[Staff Dashboard] No dashboard message ID - skipping auto-refresh")

    except Exception as e:
        print(f"[Staff Dashboard] Error creating staff log: {e}")
        await ctx.interaction.edit_initial_response(
            components=build_error_message(f"Error creating staff log: {str(e)}")
        )


@register_action("staff_dash_create_manual", no_return=True, opens_modal=True, ephemeral=True)
@lightbulb.di.with_di
async def handle_create_manual(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    **kwargs
):
    """Show modal for manual user ID entry"""
    modal = (
        hikari.impl.InteractionModalBuilder(
            title="Create Staff Log - Enter User ID",
            custom_id="staff_dash_create_with_id",
        )
        .add_component(
            hikari.impl.InteractionActionRowBuilder()
            .add_component(
                hikari.impl.TextInputBuilder(
                    custom_id="user_id",
                    label="Discord User ID",
                    style=hikari.TextInputStyle.SHORT,
                    placeholder="123456789012345678",
                    required=True,
                )
            )
        )
        .add_component(
            hikari.impl.InteractionActionRowBuilder()
            .add_component(
                hikari.impl.TextInputBuilder(
                    custom_id="hire_date",
                    label="Hire Date (YYYY-MM-DD)",
                    style=hikari.TextInputStyle.SHORT,
                    placeholder="2024-01-15",
                    required=True,
                )
            )
        )
        .add_component(
            hikari.impl.InteractionActionRowBuilder()
            .add_component(
                hikari.impl.TextInputBuilder(
                    custom_id="team",
                    label="Initial Team",
                    style=hikari.TextInputStyle.SHORT,
                    placeholder="Moderation",
                    required=True,
                )
            )
        )
        .add_component(
            hikari.impl.InteractionActionRowBuilder()
            .add_component(
                hikari.impl.TextInputBuilder(
                    custom_id="position",
                    label="Initial Position",
                    style=hikari.TextInputStyle.SHORT,
                    placeholder="Trial Moderator",
                    required=True,
                )
            )
        )
    )

    await ctx.interaction.create_modal_response(
        title=modal.title,
        custom_id=modal.custom_id,
        components=modal.components
    )


@register_action("staff_dash_create_with_id", no_return=True, ephemeral=True)
@lightbulb.di.with_di
async def handle_create_submit(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    mongo: MongoClient = lightbulb.di.INJECTED,
    bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    **kwargs
):
    """Process staff log creation from modal"""
    # Get values from modal
    user_id_str = ctx.interaction.components[0].components[0].value
    hire_date_str = ctx.interaction.components[1].components[0].value
    team = ctx.interaction.components[2].components[0].value
    position = ctx.interaction.components[3].components[0].value

    # Validate user ID
    try:
        user_id = int(user_id_str)
        user = await bot.rest.fetch_user(user_id)
        member = await bot.rest.fetch_member(ctx.guild_id, user_id)
    except (ValueError, hikari.NotFoundError):
        await ctx.respond("❌ Invalid user ID or user not found in server.", ephemeral=True)
        return

    # Check if log already exists
    existing_log = await get_staff_log(mongo, str(user_id))
    if existing_log:
        await ctx.respond(f"❌ {user.mention} already has a staff log.", ephemeral=True)
        return

    # Parse hire date
    try:
        hire_date = datetime.strptime(hire_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        await ctx.respond("❌ Invalid hire date format. Use YYYY-MM-DD (e.g., 2024-01-15)", ephemeral=True)
        return

    # Create staff log thread
    try:
        await create_staff_log_thread(
            bot=bot,
            mongo=mongo,
            user=user,
            member=member,
            hire_date=hire_date,
            team=team,
            position=position,
            created_by=ctx.user
        )

        await ctx.respond(
            f"✅ **Staff log created for {user.mention}!**\n\n"
            f"Team: {team}\nPosition: {position}\n\n"
            "Use the dashboard to view and manage their log.",
            ephemeral=True
        )
        print(f"[Staff Dashboard] Created new staff log for {user.username} via manual ID entry")

    except Exception as e:
        await ctx.respond(f"❌ Error creating staff log: {str(e)}", ephemeral=True)
        print(f"[Staff Dashboard] Error creating log: {e}")


# ========== UPDATE POSITION ==========

@register_action("staff_dash_position", ephemeral=True, no_return=True, defer_update=True)
@lightbulb.di.with_di
async def handle_position_button(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    """Handle 'Update Position' button - check position count and route accordingly"""
    user_id = action_id  # Format: user_id

    # Get current log
    log = await get_staff_log(mongo, user_id)
    if not log:
        await ctx.respond("❌ Staff log not found.", ephemeral=True)
        return

    # Check position count
    additional_positions = log.get('additional_positions', [])
    total_positions = 1 + len(additional_positions)

    if total_positions == 1:
        # Only one position - go directly to team/position selection with "primary" identifier
        components = build_update_position_selection(ctx.guild_id, user_id, log, position_identifier="primary")
        print(f"[Staff Dashboard] Opened Update Position view for user {user_id} (single position)")
    else:
        # Multiple positions - show "which position to update?" selection
        components = build_which_position_to_update_selection(ctx.guild_id, user_id, log)
        print(f"[Staff Dashboard] Opened Which Position selection for user {user_id} ({total_positions} positions)")

    await ctx.interaction.edit_initial_response(components=components)


@register_action("staff_dash_which_position_select", ephemeral=True, no_return=True, defer_update=True)
@lightbulb.di.with_di
async def handle_which_position_select(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    """Handle which position to update selection - opens team/position selection"""
    user_id = action_id

    # Get selected position identifier
    if not ctx.interaction.values:
        return

    position_identifier = ctx.interaction.values[0]  # "primary" or "secondary_0", "secondary_1", etc.

    # Get staff log
    log = await get_staff_log(mongo, user_id)
    if not log:
        await ctx.respond("❌ Staff log not found.", ephemeral=True)
        return

    # Open team/position selection with position_identifier
    components = build_update_position_selection(ctx.guild_id, user_id, log, position_identifier=position_identifier)
    await ctx.interaction.edit_initial_response(components=components)
    print(f"[Staff Dashboard] Position selected for update: {position_identifier}")


@register_action("staff_dash_update_team_select", ephemeral=True, no_return=True, defer_update=True)
@lightbulb.di.with_di
async def handle_update_team_select(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    """Handle team selection in update position flow - update position dropdown"""
    # Parse action_id format: user_id:position_identifier
    parts = action_id.split(':', 1)
    user_id = parts[0]
    position_identifier = parts[1] if len(parts) > 1 else "primary"

    # Get selected team
    if not ctx.interaction.values:
        return

    selected_team = ctx.interaction.values[0]

    # Get staff log
    log = await get_staff_log(mongo, user_id)
    if not log:
        await ctx.respond("❌ Staff log not found.", ephemeral=True)
        return

    # Rebuild view with new team selected
    components = build_update_position_selection(ctx.guild_id, user_id, log, position_identifier=position_identifier, selected_team=selected_team)
    await ctx.interaction.edit_initial_response(components=components)
    print(f"[Staff Dashboard] Update Position - Team selected: {selected_team}")


@register_action("staff_dash_update_position_select", ephemeral=True, no_return=True, defer_update=True)
@lightbulb.di.with_di
async def handle_update_position_select(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    """Handle position selection in update position flow - enable Update button"""
    # Parse action_id format: user_id:position_identifier:selected_team
    parts = action_id.split(':', 2)
    user_id = parts[0]
    position_identifier = parts[1] if len(parts) > 1 else "primary"
    selected_team = parts[2] if len(parts) > 2 else None

    # Get selected position from interaction values
    selected_position = ctx.interaction.values[0]

    if not selected_team or not selected_position:
        await ctx.respond("❌ Missing team or position data.", ephemeral=True)
        return

    # Get staff log
    log = await get_staff_log(mongo, user_id)
    if not log:
        await ctx.respond("❌ Staff log not found.", ephemeral=True)
        return

    # Rebuild view with Update button enabled
    components = build_update_position_selection(
        ctx.guild_id,
        user_id,
        log,
        position_identifier=position_identifier,
        selected_team=selected_team,
        selected_position=selected_position
    )

    await ctx.interaction.edit_initial_response(components=components)
    print(f"[Staff Dashboard] Update Position - Position selected: {selected_team} - {selected_position}")


@register_action("staff_dash_update_position_confirm", no_return=True, opens_modal=True, ephemeral=True)
async def handle_update_position_confirm(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    **kwargs
):
    """Handle Update Position button - open modal for notes"""
    # Parse action_id format: user_id:position_identifier:team:position
    parts = action_id.split(':', 3)

    if len(parts) < 4:
        await ctx.respond("❌ Missing position data.", ephemeral=True)
        return

    user_id = parts[0]
    position_identifier = parts[1]
    new_team = parts[2]
    new_position = parts[3]

    # Create modal for notes
    modal = (
        hikari.impl.InteractionModalBuilder(
            title="Update Staff Position",
            custom_id=f"staff_dash_update_position_submit:{user_id}:{position_identifier}:{new_team}:{new_position}",
        )
        .add_component(
            hikari.impl.MessageActionRowBuilder()
            .add_component(
                hikari.impl.TextInputBuilder(
                    custom_id="notes",
                    label="Reason/Notes (optional)",
                    style=hikari.TextInputStyle.PARAGRAPH,
                    placeholder="Promotion, transfer, demotion, etc.",
                    required=False,
                )
            )
        )
    )

    await ctx.interaction.create_modal_response(
        title=modal.title,
        custom_id=modal.custom_id,
        components=modal.components
    )


@register_action("staff_dash_update_position_submit", ephemeral=True, is_modal=True, no_return=True)
@lightbulb.di.with_di
async def handle_update_position_submit(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    mongo: MongoClient = lightbulb.di.INJECTED,
    bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    **kwargs
):
    """Process position update from notes modal"""
    # Defer immediately to prevent timeout
    await ctx.interaction.create_initial_response(
        hikari.ResponseType.DEFERRED_MESSAGE_UPDATE
    )

    # Parse action_id format: user_id:position_identifier:team:position
    parts = action_id.split(':', 3)

    if len(parts) < 4:
        await ctx.interaction.edit_initial_response(
            components=build_error_message("Missing position data.")
        )
        return

    user_id = parts[0]
    position_identifier = parts[1]
    new_team = parts[2]
    new_position = parts[3]

    # Get notes from modal
    notes = ctx.interaction.components[0].components[0].value if ctx.interaction.components[0].components[0].value else ""

    # Fetch current log to get OLD position values before updating
    log = await get_staff_log(mongo, user_id)
    if not log:
        await ctx.interaction.edit_initial_response(
            components=build_error_message("Staff log not found.")
        )
        return

    # Check employment status for auto-reactivation
    current_status = log.get('employment_status', 'Active')
    should_reactivate = False

    if current_status in ["Terminated", "Staff Banned"]:
        if current_status == "Staff Banned":
            # Only specific user can add positions to Staff Banned members
            authorized_user_id = 505227988229554179
            if ctx.user.id != authorized_user_id:
                await ctx.interaction.edit_initial_response(
                    components=build_error_message("❌ Only authorized leadership can add positions to Staff Banned members.")
                )
                print(f"[Staff Dashboard] Blocked {ctx.user} from adding position to Staff Banned member {user_id}")
                return
            print(f"[Staff Dashboard] Authorized user {ctx.user} adding position to Staff Banned member - will reactivate")
            should_reactivate = True
        else:  # Terminated
            print(f"[Staff Dashboard] Adding position to Terminated member - will reactivate to Active")
            should_reactivate = True

    # If reactivating, update status first
    if should_reactivate:
        await mongo.staff_logs.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "employment_status": "Active",
                    "metadata.last_updated": datetime.now(timezone.utc)
                }
            }
        )
        print(f"[Staff Dashboard] Status updated from {current_status} to Active for user {user_id}")

    # Fetch member for role validation
    try:
        member = await bot.rest.fetch_member(ctx.guild_id, int(user_id))
    except hikari.NotFoundError:
        member = None

    # Validate role match (warn but allow)
    has_role = validate_user_has_role(member, new_team, new_position) if member else True

    # DEBUG LOGGING
    print(f"[Staff Dashboard DEBUG] Role validation (Update Position):")
    print(f"  - Member: {member}")
    print(f"  - Team: {new_team}")
    print(f"  - Position: {new_position}")
    print(f"  - Has role: {has_role}")
    if member:
        from utils.constants import get_role_id_for_position
        role_id = get_role_id_for_position(new_team, new_position)
        print(f"  - Expected role ID: {role_id}")
        print(f"  - Member's role IDs: {member.role_ids}")

    # Update database based on position_identifier
    if position_identifier == "primary":
        # Get old primary position values
        old_team = log.get('current_team', 'Unknown')
        old_position = log.get('current_position', 'Unknown')

        # Update primary position
        await mongo.staff_logs.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "current_team": new_team,
                    "current_position": new_position,
                    "metadata.last_updated": datetime.now(timezone.utc)
                },
                "$push": {
                    "position_history": {
                        "action": "updated",
                        "old_team": old_team,
                        "old_position": old_position,
                        "team": new_team,
                        "position": new_position,
                        "date": datetime.now(timezone.utc),
                        "changed_by_id": str(ctx.user.id),
                        "changed_by_name": str(ctx.user),
                        "notes": notes
                    }
                }
            }
        )
        print(f"[Staff Dashboard] Primary position updated for user {user_id}: {old_team} - {old_position} → {new_team} - {new_position}")
    else:
        # Update secondary position
        # Parse "secondary_0", "secondary_1", etc.
        idx = int(position_identifier.split('_')[1])

        # Get old secondary position values
        additional_positions = log.get('additional_positions', [])
        if idx >= len(additional_positions):
            await ctx.interaction.edit_initial_response(
                components=build_error_message("Invalid position index.")
            )
            return

        old_team = additional_positions[idx].get('team', 'Unknown')
        old_position = additional_positions[idx].get('position', 'Unknown')

        # Update the specific secondary position in the array
        await mongo.staff_logs.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    f"additional_positions.{idx}.team": new_team,
                    f"additional_positions.{idx}.position": new_position,
                    f"additional_positions.{idx}.assigned_date": datetime.now(timezone.utc),
                    f"additional_positions.{idx}.assigned_by_id": str(ctx.user.id),
                    f"additional_positions.{idx}.assigned_by_name": str(ctx.user),
                    f"additional_positions.{idx}.notes": notes,
                    "metadata.last_updated": datetime.now(timezone.utc)
                },
                "$push": {
                    "position_history": {
                        "action": "updated",
                        "old_team": old_team,
                        "old_position": old_position,
                        "team": new_team,
                        "position": new_position,
                        "date": datetime.now(timezone.utc),
                        "changed_by_id": str(ctx.user.id),
                        "changed_by_name": str(ctx.user),
                        "notes": notes
                    }
                }
            }
        )
        print(f"[Staff Dashboard] Secondary position {idx} updated for user {user_id}: {old_team} - {old_position} → {new_team} - {new_position}")

    # Update forum log
    await update_forum_log(bot, mongo, user_id, ctx.guild_id)

    # Get updated log and return to record view
    log = await get_staff_log(mongo, user_id)
    user = await bot.rest.fetch_user(int(user_id))
    components = build_staff_record_view(log, user, ctx.guild_id)

    await ctx.interaction.edit_initial_response(components=components)
    print(f"[Staff Dashboard] Position updated: {new_team} - {new_position}")

    # Send separate ephemeral warning if role doesn't match
    if not has_role:
        await bot.rest.execute_webhook(
            webhook=ctx.interaction.application_id,
            token=ctx.interaction.token,
            content=f"⚠️ **Warning**: <@{user_id}> does not currently have the **{new_position}** role for this position.",
            flags=hikari.MessageFlag.EPHEMERAL
        )


# ========== ADD POSITION (for multiple roles) ==========

@register_action("staff_dash_add_position", ephemeral=True, no_return=True, defer_update=True)
@lightbulb.di.with_di
async def handle_add_position_button(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    """Handle 'Add Position' button - shows dropdown selection view"""
    user_id = action_id  # Format: user_id

    # Get current log
    log = await get_staff_log(mongo, user_id)
    if not log:
        await ctx.respond("❌ Staff log not found.", ephemeral=True)
        return

    # Build dropdown selection view
    components = build_add_position_selection(ctx.guild_id, user_id, log)

    await ctx.interaction.edit_initial_response(components=components)
    print(f"[Staff Dashboard] Opened Add Position view for user {user_id}")


@register_action("staff_dash_add_team_select", ephemeral=True, no_return=True, defer_update=True)
@lightbulb.di.with_di
async def handle_add_team_select(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    """Handle team selection in add position flow - update position dropdown"""
    user_id = action_id  # Format: user_id

    # Get selected team
    if not ctx.interaction.values:
        return

    selected_team = ctx.interaction.values[0]

    # Get staff log
    log = await get_staff_log(mongo, user_id)
    if not log:
        await ctx.respond("❌ Staff log not found.", ephemeral=True)
        return

    # Rebuild view with new team selected
    components = build_add_position_selection(ctx.guild_id, user_id, log, selected_team=selected_team)
    await ctx.interaction.edit_initial_response(components=components)
    print(f"[Staff Dashboard] Add Position - Team selected: {selected_team}")


@register_action("staff_dash_add_position_select", ephemeral=True, no_return=True, defer_update=True)
@lightbulb.di.with_di
async def handle_add_position_select(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    """Handle position selection in add position flow - enable Add button"""
    # Parse action_id format: user_id:selected_team
    parts = action_id.split(':', 1)
    user_id = parts[0]
    selected_team = parts[1] if len(parts) > 1 else None

    # Get selected position from interaction values
    selected_position = ctx.interaction.values[0]

    if not selected_team or not selected_position:
        await ctx.respond("❌ Missing team or position data.", ephemeral=True)
        return

    # Get staff log
    log = await get_staff_log(mongo, user_id)
    if not log:
        await ctx.respond("❌ Staff log not found.", ephemeral=True)
        return

    # Rebuild view with Add button enabled
    components = build_add_position_selection(
        ctx.guild_id,
        user_id,
        log,
        selected_team=selected_team,
        selected_position=selected_position
    )

    await ctx.interaction.edit_initial_response(components=components)
    print(f"[Staff Dashboard] Add Position - Position selected: {selected_team} - {selected_position}")


@register_action("staff_dash_add_position_confirm", no_return=True, opens_modal=True, ephemeral=True)
async def handle_add_position_confirm(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    **kwargs
):
    """Handle Add Position button - open modal for notes"""
    # Parse action_id format: user_id:team:position
    parts = action_id.split(':', 2)

    if len(parts) < 3:
        await ctx.respond("❌ Missing team or position data.", ephemeral=True)
        return

    user_id = parts[0]
    new_team = parts[1]
    new_position = parts[2]

    # Create modal for notes
    modal = (
        hikari.impl.InteractionModalBuilder(
            title="Add Staff Position",
            custom_id=f"staff_dash_add_position_submit:{user_id}:{new_team}:{new_position}",
        )
        .add_component(
            hikari.impl.MessageActionRowBuilder()
            .add_component(
                hikari.impl.TextInputBuilder(
                    custom_id="notes",
                    label="Reason/Notes (optional)",
                    style=hikari.TextInputStyle.PARAGRAPH,
                    placeholder="Cross-team assignment, additional responsibilities, etc.",
                    required=False,
                )
            )
        )
    )

    await ctx.interaction.create_modal_response(
        title=modal.title,
        custom_id=modal.custom_id,
        components=modal.components
    )


@register_action("staff_dash_add_position_submit", ephemeral=True, is_modal=True, no_return=True)
@lightbulb.di.with_di
async def handle_add_position_submit(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    mongo: MongoClient = lightbulb.di.INJECTED,
    bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    **kwargs
):
    """Process adding additional position - uses $push to add to array"""
    # Defer immediately to prevent timeout
    await ctx.interaction.create_initial_response(
        hikari.ResponseType.DEFERRED_MESSAGE_UPDATE
    )

    # Parse action_id format: user_id:team:position
    parts = action_id.split(':', 2)

    if len(parts) < 3:
        await ctx.interaction.edit_initial_response(
            components=build_error_message("Missing team or position data.")
        )
        return

    user_id = parts[0]
    new_team = parts[1]
    new_position = parts[2]

    # Get notes from modal
    notes = ctx.interaction.components[0].components[0].value if ctx.interaction.components[0].components[0].value else ""

    # Fetch current log to check employment status
    log = await get_staff_log(mongo, user_id)
    if not log:
        await ctx.interaction.edit_initial_response(
            components=build_error_message("Staff log not found.")
        )
        return

    # Check employment status for auto-reactivation
    current_status = log.get('employment_status', 'Active')
    should_reactivate = False

    if current_status in ["Terminated", "Staff Banned"]:
        if current_status == "Staff Banned":
            # Only specific user can add positions to Staff Banned members
            authorized_user_id = 505227988229554179
            if ctx.user.id != authorized_user_id:
                await ctx.interaction.edit_initial_response(
                    components=build_error_message("❌ Only authorized leadership can add positions to Staff Banned members.")
                )
                print(f"[Staff Dashboard] Blocked {ctx.user} from adding position to Staff Banned member {user_id}")
                return
            print(f"[Staff Dashboard] Authorized user {ctx.user} adding position to Staff Banned member - will reactivate")
            should_reactivate = True
        else:  # Terminated
            print(f"[Staff Dashboard] Adding position to Terminated member - will reactivate to Active")
            should_reactivate = True

    # If reactivating, update status first
    if should_reactivate:
        await mongo.staff_logs.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "employment_status": "Active",
                    "metadata.last_updated": datetime.now(timezone.utc)
                }
            }
        )
        print(f"[Staff Dashboard] Status updated from {current_status} to Active for user {user_id}")

    # Fetch member for role validation
    try:
        member = await bot.rest.fetch_member(ctx.guild_id, int(user_id))
    except hikari.NotFoundError:
        member = None

    # Validate role match (warn but allow)
    has_role = validate_user_has_role(member, new_team, new_position) if member else True

    # DEBUG LOGGING
    print(f"[Staff Dashboard DEBUG] Role validation (Add Position):")
    print(f"  - Member: {member}")
    print(f"  - Team: {new_team}")
    print(f"  - Position: {new_position}")
    print(f"  - Has role: {has_role}")
    if member:
        from utils.constants import get_role_id_for_position
        role_id = get_role_id_for_position(new_team, new_position)
        print(f"  - Expected role ID: {role_id}")
        print(f"  - Member's role IDs: {member.role_ids}")

    # Check if primary position is empty - if so, set as primary instead of adding as additional
    current_team = log.get('current_team', '')
    current_position = log.get('current_position', '')

    if not current_team or not current_position:
        # Primary position is empty - set this as the primary position
        await mongo.staff_logs.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "current_team": new_team,
                    "current_position": new_position,
                    "metadata.last_updated": datetime.now(timezone.utc)
                },
                "$push": {
                    "position_history": {
                        "action": "assigned",
                        "team": new_team,
                        "position": new_position,
                        "date": datetime.now(timezone.utc),
                        "changed_by_id": str(ctx.user.id),
                        "changed_by_name": str(ctx.user),
                        "notes": notes
                    }
                }
            }
        )
        print(f"[Staff Dashboard] Set as primary position (no primary exists): {new_team} - {new_position}")
    else:
        # Primary position exists - add to additional_positions array
        await mongo.staff_logs.update_one(
            {"user_id": user_id},
            {
                "$push": {
                    "additional_positions": {
                        "team": new_team,
                        "position": new_position,
                        "assigned_date": datetime.now(timezone.utc),
                        "assigned_by_id": str(ctx.user.id),
                        "assigned_by_name": str(ctx.user),
                        "notes": notes
                    },
                    "position_history": {
                        "action": "added",
                        "team": new_team,
                        "position": new_position,
                        "date": datetime.now(timezone.utc),
                        "changed_by_id": str(ctx.user.id),
                        "changed_by_name": str(ctx.user),
                        "notes": notes
                    }
                },
                "$set": {
                    "metadata.last_updated": datetime.now(timezone.utc)
                }
            }
        )
        print(f"[Staff Dashboard] Added as additional position: {new_team} - {new_position}")

    # Update forum log
    await update_forum_log(bot, mongo, user_id, ctx.guild_id)

    # Get updated log and return to record view
    log = await get_staff_log(mongo, user_id)
    user = await bot.rest.fetch_user(int(user_id))
    components = build_staff_record_view(log, user, ctx.guild_id)

    await ctx.interaction.edit_initial_response(components=components)
    print(f"[Staff Dashboard] Position added for {user.username}: {new_team} - {new_position}")

    # Send separate ephemeral warning if role doesn't match
    if not has_role:
        await bot.rest.execute_webhook(
            webhook=ctx.interaction.application_id,
            token=ctx.interaction.token,
            content=f"⚠️ **Warning**: <@{user_id}> does not currently have the **{new_position}** role for this position.",
            flags=hikari.MessageFlag.EPHEMERAL
        )


# ========== REMOVE POSITION ==========

@register_action("staff_dash_remove_position", ephemeral=True, no_return=True, defer_update=True)
@lightbulb.di.with_di
async def handle_remove_position_button(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    """Handle 'Remove Position' button - shows position selection view"""
    user_id = action_id

    # Get current log
    log = await get_staff_log(mongo, user_id)
    if not log:
        await ctx.respond("❌ Staff log not found.", ephemeral=True)
        return

    # Build position selection view
    components = build_remove_position_selection(ctx.guild_id, user_id, log)
    await ctx.interaction.edit_initial_response(components=components)
    print(f"[Staff Dashboard] Opened Remove Position view for user {user_id}")


@register_action("staff_dash_select_position_remove", ephemeral=True, no_return=True, opens_modal=True)
async def handle_select_position_remove(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    **kwargs
):
    """Handle position selection for removal - open confirmation modal"""
    user_id = action_id
    selected_value = ctx.interaction.values[0]  # "primary" or "secondary:idx"

    # Build modal asking for reason
    modal = (
        hikari.impl.InteractionModalBuilder(
            title="Confirm Position Removal",
            custom_id=f"staff_dash_remove_position_submit:{user_id}:{selected_value}",
        )
        .add_component(
            hikari.impl.MessageActionRowBuilder()
            .add_component(
                hikari.impl.TextInputBuilder(
                    custom_id="reason",
                    label="Reason for Removal",
                    style=hikari.TextInputStyle.PARAGRAPH,
                    placeholder="Enter reason for removing this position...",
                    required=True,
                    max_length=500,
                )
            )
        )
    )

    await ctx.interaction.create_modal_response(
        title=modal.title,
        custom_id=modal.custom_id,
        components=modal.components
    )


@register_action("staff_dash_remove_position_submit", ephemeral=True, is_modal=True, no_return=True)
@lightbulb.di.with_di
async def handle_remove_position_submit(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    mongo: MongoClient = lightbulb.di.INJECTED,
    bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    **kwargs
):
    """Process position removal from modal"""
    # Defer immediately to prevent timeout
    await ctx.interaction.create_initial_response(
        hikari.ResponseType.DEFERRED_MESSAGE_UPDATE
    )

    # Parse action_id format: user_id:position_type (either "primary" or "secondary:idx")
    parts = action_id.split(':', 2)
    if len(parts) < 2:
        await ctx.interaction.edit_initial_response(
            components=build_error_message("Missing position data.")
        )
        return

    user_id = parts[0]
    position_identifier = parts[1]
    secondary_idx = int(parts[2]) if len(parts) > 2 else None

    # Get reason from modal
    reason = ctx.interaction.components[0].components[0].value

    # Get current log
    log = await get_staff_log(mongo, user_id)
    if not log:
        await ctx.interaction.edit_initial_response(
            components=build_error_message("Staff log not found.")
        )
        return

    current_team = log.get('current_team')
    current_position = log.get('current_position')
    additional_positions = log.get('additional_positions', [])

    # Validate: Must have at least 1 position remaining
    total_positions = 1 + len(additional_positions)
    if total_positions <= 1:
        await ctx.interaction.edit_initial_response(
            components=build_error_message("Cannot remove the last position. Staff must have at least one role.")
        )
        return

    # Perform removal
    if position_identifier == "primary":
        # Removing primary - promote first secondary to primary
        if not additional_positions:
            await ctx.interaction.edit_initial_response(
                components=build_error_message("Cannot remove primary position - no secondary positions to promote.")
            )
            return

        first_secondary = additional_positions[0]
        new_primary_team = first_secondary.get('team')
        new_primary_position = first_secondary.get('position')

        # Update database
        await mongo.staff_logs.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "current_team": new_primary_team,
                    "current_position": new_primary_position,
                    "metadata.last_updated": datetime.now(timezone.utc)
                },
                "$pull": {
                    "additional_positions": {"team": new_primary_team, "position": new_primary_position}
                },
                "$push": {
                    "position_history": {
                        "action": "removed",
                        "team": current_team,
                        "position": current_position,
                        "date": datetime.now(timezone.utc),
                        "changed_by_id": str(ctx.user.id),
                        "changed_by_name": str(ctx.user),
                        "notes": f"Position removed. Reason: {reason}. {new_primary_team} - {new_primary_position} promoted to primary."
                    }
                }
            }
        )

        print(f"[Staff Dashboard] Primary position removed for user {user_id}, promoted {new_primary_team} - {new_primary_position}")

    else:
        # Removing secondary position
        if secondary_idx is None or secondary_idx >= len(additional_positions):
            await ctx.interaction.edit_initial_response(
                components=build_error_message("Invalid secondary position index.")
            )
            return

        removed_position = additional_positions[secondary_idx]
        removed_team = removed_position.get('team')
        removed_pos = removed_position.get('position')

        # Update database
        await mongo.staff_logs.update_one(
            {"user_id": user_id},
            {
                "$pull": {
                    "additional_positions": {"team": removed_team, "position": removed_pos}
                },
                "$set": {
                    "metadata.last_updated": datetime.now(timezone.utc)
                },
                "$push": {
                    "position_history": {
                        "action": "removed",
                        "team": removed_team,
                        "position": removed_pos,
                        "date": datetime.now(timezone.utc),
                        "changed_by_id": str(ctx.user.id),
                        "changed_by_name": str(ctx.user),
                        "notes": f"Secondary position removed. Reason: {reason}"
                    }
                }
            }
        )

        print(f"[Staff Dashboard] Secondary position removed for user {user_id}: {removed_team} - {removed_pos}")

    # Update forum log
    await update_forum_log(bot, mongo, user_id, ctx.guild_id)

    # Get updated log and return to record view
    log = await get_staff_log(mongo, user_id)
    user = await bot.rest.fetch_user(int(user_id))
    components = build_staff_record_view(log, user, ctx.guild_id)

    await ctx.interaction.edit_initial_response(components=components)
    print(f"[Staff Dashboard] Position removal complete for {user.username}")


# ========== EDIT POSITION DATE ==========

@register_action("staff_dash_select_position_date", ephemeral=True, no_return=True, opens_modal=True)
@lightbulb.di.with_di
async def handle_position_date_select(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    """Handle position selection from dropdown - opens modal with current date"""
    user_id = action_id
    position_identifier = ctx.interaction.values[0]  # "primary" or "secondary_X"

    # Get staff log
    log = await get_staff_log(mongo, user_id)
    if not log:
        await ctx.respond(
            components=build_error_message("Staff log not found."),
            flags=hikari.MessageFlag.EPHEMERAL
        )
        return

    current_team = log.get('current_team')
    current_position = log.get('current_position')
    additional_positions = log.get('additional_positions', [])
    position_history = log.get('position_history', [])

    # Determine which position was selected
    if position_identifier == "primary":
        target_team = current_team
        target_position = current_position
        position_display = f"{target_team} - {target_position}"
    else:
        # Parse "secondary_X"
        idx = int(position_identifier.split('_')[1])
        if idx >= len(additional_positions):
            await ctx.respond(
                components=build_error_message("Invalid position selection."),
                flags=hikari.MessageFlag.EPHEMERAL
            )
            return
        target_team = additional_positions[idx].get('team')
        target_position = additional_positions[idx].get('position')
        position_display = f"{target_team} - {target_position}"

    # Find current date for this position from position_history
    current_date = None
    for entry in reversed(position_history):
        if entry.get('team') == target_team and entry.get('position') == target_position:
            current_date = entry.get('date')
            break

    # Format date as string
    if current_date:
        if isinstance(current_date, str):
            current_date_str = current_date[:10]  # Take YYYY-MM-DD part
        else:
            current_date_str = current_date.strftime('%Y-%m-%d')
    else:
        current_date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    # Build and show modal
    modal = build_edit_position_date_modal(user_id, position_identifier, current_date_str, position_display)
    await ctx.interaction.create_modal_response(
        title=modal.title,
        custom_id=modal.custom_id,
        components=modal.components
    )


@register_action("staff_dash_edit_position_date_submit", ephemeral=True, is_modal=True, no_return=True)
@lightbulb.di.with_di
async def handle_position_date_submit(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    mongo: MongoClient = lightbulb.di.INJECTED,
    bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    **kwargs
):
    """Process position date update from modal"""
    # Defer immediately to prevent timeout
    await ctx.interaction.create_initial_response(
        hikari.ResponseType.DEFERRED_MESSAGE_UPDATE
    )

    # Parse action_id format: user_id:position_identifier
    parts = action_id.split(':', 2)
    if len(parts) < 2:
        await ctx.interaction.edit_initial_response(
            components=build_error_message("Missing position data.")
        )
        return

    user_id = parts[0]
    position_identifier = parts[1]

    # Get new date from modal
    new_date_str = ctx.interaction.components[0].components[0].value.strip()

    # Parse date
    try:
        new_date = datetime.strptime(new_date_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    except ValueError:
        await ctx.interaction.edit_initial_response(
            components=build_error_message("Invalid date format. Please use YYYY-MM-DD.")
        )
        return

    # Get current log
    log = await get_staff_log(mongo, user_id)
    if not log:
        await ctx.interaction.edit_initial_response(
            components=build_error_message("Staff log not found.")
        )
        return

    current_team = log.get('current_team')
    current_position = log.get('current_position')
    additional_positions = log.get('additional_positions', [])
    position_history = log.get('position_history', [])

    # Determine which position to update
    if position_identifier == "primary":
        target_team = current_team
        target_position = current_position
    else:
        # Parse "secondary_X"
        idx = int(position_identifier.split('_')[1])
        if idx >= len(additional_positions):
            await ctx.interaction.edit_initial_response(
                components=build_error_message("Invalid position selection.")
            )
            return
        target_team = additional_positions[idx].get('team')
        target_position = additional_positions[idx].get('position')

    # Find the position_history entry to update (most recent one with matching team+position)
    history_index_to_update = None
    for idx, entry in enumerate(reversed(position_history)):
        if entry.get('team') == target_team and entry.get('position') == target_position:
            # Found the entry - convert to actual index in original array
            history_index_to_update = len(position_history) - 1 - idx
            break

    if history_index_to_update is None:
        await ctx.interaction.edit_initial_response(
            components=build_error_message(f"No history entry found for {target_team} - {target_position}.")
        )
        return

    # Update the date in the position_history entry
    await mongo.staff_logs.update_one(
        {"user_id": user_id},
        {
            "$set": {
                f"position_history.{history_index_to_update}.date": new_date,
                "metadata.last_updated": datetime.now(timezone.utc)
            }
        }
    )

    # If this is the primary position's initial hire date (oldest entry), also update top-level hire_date
    # Check if this is the first (oldest) position_history entry
    if history_index_to_update == 0:
        await mongo.staff_logs.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "hire_date": new_date
                }
            }
        )
        print(f"[Staff Dashboard] Updated hire_date for user {user_id} to {new_date_str}")

    print(f"[Staff Dashboard] Updated position date for {target_team} - {target_position} to {new_date_str}")

    # Update forum log
    await update_forum_log(bot, mongo, user_id, ctx.guild_id)

    # Get updated log and return to record view
    log = await get_staff_log(mongo, user_id)
    user = await bot.rest.fetch_user(int(user_id))
    components = build_staff_record_view(log, user, ctx.guild_id)

    await ctx.interaction.edit_initial_response(components=components)
    print(f"[Staff Dashboard] Position date update complete for {user.username}")


# ========== ADMIN CHANGE ==========

@register_action("staff_dash_admin", no_return=True, defer_update=True, ephemeral=True)
@lightbulb.di.with_di
async def handle_admin_button(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    """Handle 'Admin Change' button - shows Add/Remove selection view"""
    user_id = action_id

    # Get user's log
    log = await get_staff_log(mongo, user_id)
    if not log:
        await ctx.interaction.edit_initial_response(
            components=build_error_message("Staff log not found.")
        )
        return

    # Get user
    user = await bot.rest.fetch_user(int(user_id))

    # Build admin change selection view
    components = build_admin_change_selection(ctx.guild_id, user_id, user.username, log)
    await ctx.interaction.edit_initial_response(components=components)
    print(f"[Staff Dashboard] Admin change selection opened for {user.username}")


@register_action("staff_dash_admin_add", no_return=True, opens_modal=True, ephemeral=True)
@lightbulb.di.with_di
async def handle_admin_add_button(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    **kwargs
):
    """Handle 'Add Admin Privileges' button - opens modal for reason"""
    user_id = action_id

    modal = build_admin_reason_modal(user_id, "Add")
    await ctx.interaction.create_modal_response(
        title=modal.title,
        custom_id=modal.custom_id,
        components=modal.components
    )


@register_action("staff_dash_admin_remove", no_return=True, opens_modal=True, ephemeral=True)
@lightbulb.di.with_di
async def handle_admin_remove_button(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    **kwargs
):
    """Handle 'Remove Admin Privileges' button - opens modal for reason"""
    user_id = action_id

    modal = build_admin_reason_modal(user_id, "Remove")
    await ctx.interaction.create_modal_response(
        title=modal.title,
        custom_id=modal.custom_id,
        components=modal.components
    )


@register_action("staff_dash_admin_submit", ephemeral=True, is_modal=True, no_return=True)
@lightbulb.di.with_di
async def handle_admin_submit(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    mongo: MongoClient = lightbulb.di.INJECTED,
    bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    **kwargs
):
    """Process admin change from modal"""
    # Defer immediately to prevent timeout
    await ctx.interaction.create_initial_response(
        hikari.ResponseType.DEFERRED_MESSAGE_UPDATE
    )

    # Parse action_id: format is "user_id:action"
    parts = action_id.split(":")
    user_id = parts[0]
    action = parts[1]  # "Add" or "Remove"

    # Get reason from modal (only field)
    reason = ctx.interaction.components[0].components[0].value

    # Validate action
    if action not in ["Add", "Remove"]:
        await ctx.interaction.edit_initial_response(
            components=build_error_message("Invalid action")
        )
        return

    # Prepare database updates
    current_time = datetime.now(timezone.utc)
    update_operations = {
        "$set": {
            "metadata.last_updated": current_time
        },
        "$push": {
            "admin_changes": {
                "action": action,
                "date": current_time,
                "reason": reason,
                "changed_by_id": str(ctx.user.id),
                "changed_by_name": str(ctx.user)
            }
        }
    }

    # Update admin_privileges based on action
    if action == "Add":
        update_operations["$set"]["admin_privileges"] = {
            "has_admin": True,
            "granted_date": current_time,
            "granted_by_id": str(ctx.user.id),
            "granted_by_name": str(ctx.user)
        }
    else:  # Remove
        update_operations["$set"]["admin_privileges"] = {
            "has_admin": False,
            "granted_date": None,
            "granted_by_id": None,
            "granted_by_name": None
        }

    # Update database
    await mongo.staff_logs.update_one(
        {"user_id": user_id},
        update_operations
    )

    # Update forum log
    await update_forum_log(bot, mongo, user_id, ctx.guild_id)

    # Get updated log and return to record view
    log = await get_staff_log(mongo, user_id)
    user = await bot.rest.fetch_user(int(user_id))
    components = build_staff_record_view(log, user, ctx.guild_id)

    await ctx.interaction.edit_initial_response(components=components)
    print(f"[Staff Dashboard] Admin change recorded for {user.username}: {action}")


# ========== ADD CASE ==========

@register_action("staff_dash_case", ephemeral=True, no_return=True, defer_update=True)
@lightbulb.di.with_di
async def handle_case_button(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    mongo: MongoClient = lightbulb.di.INJECTED,
    bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    **kwargs
):
    """Handle 'Add Case' button - shows case type selection"""
    user_id = action_id

    # Get staff log to retrieve username
    log = await get_staff_log(mongo, user_id)
    if not log:
        await ctx.respond("❌ Staff log not found.", ephemeral=True)
        return

    # Fetch user to get current username
    try:
        user = await bot.rest.fetch_user(int(user_id))
        username = user.username
    except hikari.NotFoundError:
        username = log.get('username', 'Unknown')

    # Build case type selection view
    components = build_case_type_selection(ctx.guild_id, user_id, username)

    # Update to show case type selection
    await ctx.interaction.edit_initial_response(components=components)


@register_action("staff_dash_select_case_type", no_return=True, opens_modal=True, ephemeral=True)
@lightbulb.di.with_di
async def handle_case_type_select(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    """Handle case type selection - opens modal for reason"""
    user_id = action_id

    # Get selected case type from dropdown
    if not ctx.interaction.values:
        await ctx.respond("❌ No case type selected.", ephemeral=True)
        return

    selected_case_type = ctx.interaction.values[0]

    # Generate unique action_id for button store
    import uuid
    unique_action_id = str(uuid.uuid4())

    # Store case type and user_id in button_store
    await mongo.button_store.insert_one({
        "_id": unique_action_id,
        "user_id": user_id,
        "case_type": selected_case_type
    })

    # Build and open modal with just reason field
    modal = build_case_modal(user_id, selected_case_type, unique_action_id)
    await ctx.interaction.create_modal_response(
        title=modal.title,
        custom_id=modal.custom_id,
        components=modal.components
    )


@register_action("staff_dash_case_submit", ephemeral=True, is_modal=True, no_return=True)
@lightbulb.di.with_di
async def handle_case_submit(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    mongo: MongoClient = lightbulb.di.INJECTED,
    bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    **kwargs
):
    """Process staff case from modal"""
    # Defer immediately to prevent timeout
    await ctx.interaction.create_initial_response(
        hikari.ResponseType.DEFERRED_MESSAGE_UPDATE
    )

    # action_id is now the unique_action_id from button_store
    stored_data = await mongo.button_store.find_one({"_id": action_id})

    if not stored_data:
        await ctx.interaction.edit_initial_response(
            components=build_error_message("Session expired. Please try again.")
        )
        return

    user_id = stored_data.get('user_id')
    case_type = stored_data.get('case_type')

    # Clean up button store
    await mongo.button_store.delete_one({"_id": action_id})

    # Get reason from modal (now only one component)
    reason = ctx.interaction.components[0].components[0].value

    # Get current log to generate case ID
    log = await get_staff_log(mongo, user_id)
    if not log:
        await ctx.interaction.edit_initial_response(
            components=build_error_message("Staff log not found.")
        )
        return

    existing_cases = log.get('staff_cases', [])
    case_id = generate_next_case_id(existing_cases)

    # Update database
    await mongo.staff_logs.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "metadata.last_updated": datetime.now(timezone.utc)
            },
            "$push": {
                "staff_cases": {
                    "case_id": case_id,
                    "type": case_type,
                    "date": datetime.now(timezone.utc),
                    "reason": reason,
                    "issued_by_id": str(ctx.user.id),
                    "issued_by_name": str(ctx.user)
                }
            }
        }
    )

    # Check if case type is Termination or Staff Ban - auto-update status and remove positions
    if case_type in ["Termination", "Staff Ban"]:
        # Determine new status based on case type
        if case_type == "Termination":
            new_status = "Terminated"
        else:  # Staff Ban
            new_status = "Staff Banned"

        # Update employment status
        await mongo.staff_logs.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "employment_status": new_status,
                    "metadata.last_updated": datetime.now(timezone.utc)
                }
            }
        )

        # Get updated log to see all positions (re-fetch after status update)
        log = await get_staff_log(mongo, user_id)

        if log:
            current_team = log.get('current_team')
            current_position = log.get('current_position')
            additional_positions = log.get('additional_positions', [])

            # Build reason based on case type and include case ID
            reason_text = f"Automatically removed due to {case_type} case (#{case_id})"

            # Collect all position removal entries for position_history
            position_removals = []

            # Add primary position removal if exists
            if current_team and current_position:
                position_removals.append({
                    "action": "removed",
                    "team": current_team,
                    "position": current_position,
                    "date": datetime.now(timezone.utc),
                    "changed_by_id": str(ctx.user.id),
                    "changed_by_name": str(ctx.user),
                    "notes": reason_text
                })

            # Add additional position removals
            for pos in additional_positions:
                position_removals.append({
                    "action": "removed",
                    "team": pos.get('team'),
                    "position": pos.get('position'),
                    "date": datetime.now(timezone.utc),
                    "changed_by_id": str(ctx.user.id),
                    "changed_by_name": str(ctx.user),
                    "notes": reason_text
                })

            # Update database - clear positions and add removal entries to history
            if position_removals:
                await mongo.staff_logs.update_one(
                    {"user_id": user_id},
                    {
                        "$set": {
                            "current_team": "",
                            "current_position": "",
                            "additional_positions": [],
                            "metadata.last_updated": datetime.now(timezone.utc)
                        },
                        "$push": {
                            "position_history": {"$each": position_removals}
                        }
                    }
                )

                total_removed = len(position_removals)
                print(f"[Staff Dashboard] Auto-removed {total_removed} position(s) due to {case_type} case #{case_id} for user {user_id}")

        print(f"[Staff Dashboard] Auto-updated status to {new_status} due to {case_type} case #{case_id}")

    # Update forum log
    await update_forum_log(bot, mongo, user_id, ctx.guild_id)

    # Get updated log and return to record view
    log = await get_staff_log(mongo, user_id)
    user = await bot.rest.fetch_user(int(user_id))
    components = build_staff_record_view(log, user, ctx.guild_id)

    await ctx.interaction.edit_initial_response(components=components)
    print(f"[Staff Dashboard] Case #{case_id} added for {user.username}: {case_type}")


# ========== REMOVE CASE ==========

@register_action("staff_dash_remove_case", ephemeral=True, no_return=True, defer_update=True)
@lightbulb.di.with_di
async def handle_remove_case_button(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    """Handle 'Remove Case' button - shows case selection view"""
    user_id = action_id

    # Get current log
    log = await get_staff_log(mongo, user_id)
    if not log:
        await ctx.respond("❌ Staff log not found.", ephemeral=True)
        return

    # Build case selection view
    components = build_remove_case_selection(ctx.guild_id, user_id, log)
    await ctx.interaction.edit_initial_response(components=components)
    print(f"[Staff Dashboard] Opened Remove Case view for user {user_id}")


@register_action("staff_dash_select_case_remove", ephemeral=True, no_return=True, defer_update=True)
@lightbulb.di.with_di
async def handle_select_case_remove(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    mongo: MongoClient = lightbulb.di.INJECTED,
    bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    **kwargs
):
    """Handle case selection for removal - remove the selected case"""
    user_id = action_id
    selected_case_id = ctx.interaction.values[0]

    # Get current log
    log = await get_staff_log(mongo, user_id)
    if not log:
        await ctx.respond("❌ Staff log not found.", ephemeral=True)
        return

    # Remove the case from the database
    await mongo.staff_logs.update_one(
        {"user_id": user_id},
        {
            "$pull": {
                "staff_cases": {"case_id": selected_case_id}
            },
            "$set": {
                "metadata.last_updated": datetime.now(timezone.utc)
            }
        }
    )

    # Update forum log
    await update_forum_log(bot, mongo, user_id, ctx.guild_id)

    # Get updated log and return to record view
    log = await get_staff_log(mongo, user_id)
    user = await bot.rest.fetch_user(int(user_id))
    components = build_staff_record_view(log, user, ctx.guild_id)

    await ctx.interaction.edit_initial_response(components=components)
    print(f"[Staff Dashboard] Case {selected_case_id} removed for user {user_id}")


# ========== VIEW CASES ==========

@register_action("staff_dash_view_cases", ephemeral=True, no_return=True, defer_update=True)
@lightbulb.di.with_di
async def handle_view_cases_button(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    """Handle 'View Cases' button - shows all cases for this user"""
    user_id = action_id

    # Get user's log
    log = await get_staff_log(mongo, user_id)
    if not log:
        await ctx.interaction.edit_initial_response(
            components=build_error_message("Staff log not found.")
        )
        return

    # Build user cases view
    components = build_user_cases_view(ctx.guild_id, user_id, log)
    await ctx.interaction.edit_initial_response(components=components)
    print(f"[Staff Dashboard] Showing cases for user {user_id}")


@register_action("staff_dash_view_all_cases", ephemeral=True, no_return=True, defer_update=True)
@lightbulb.di.with_di
async def handle_view_all_cases(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    """Handle 'View All Cases' button - shows all cases across all staff"""
    # Get all staff logs
    all_logs = await get_all_staff_logs(mongo)

    # Build all cases view
    components = build_all_cases_view(ctx.guild_id, all_logs)
    await ctx.interaction.edit_initial_response(components=components)
    print(f"[Staff Dashboard] Viewing all cases")


@register_action("staff_dash_search_case_id", no_return=True, opens_modal=True, ephemeral=True)
async def handle_search_case_id_button(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    **kwargs
):
    """Handle 'Search by Case ID' button - opens modal for ID input"""
    # Create modal for case ID search
    modal = (
        hikari.impl.InteractionModalBuilder(
            title="Search Case by ID",
            custom_id=f"staff_dash_search_case_submit",
        )
        .add_component(
            hikari.impl.MessageActionRowBuilder()
            .add_component(
                hikari.impl.TextInputBuilder(
                    custom_id="case_id",
                    label="Case ID",
                    style=hikari.TextInputStyle.SHORT,
                    placeholder="e.g., SC-A7B3K",
                    required=True,
                    max_length=20
                )
            )
        )
    )

    await ctx.interaction.create_modal_response(
        title=modal.title,
        custom_id=modal.custom_id,
        components=modal.components
    )


@register_action("staff_dash_search_case_submit", ephemeral=True, is_modal=True, no_return=True)
@lightbulb.di.with_di
async def handle_search_case_submit(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    """Process case ID search from modal"""
    # Defer immediately to prevent timeout
    await ctx.interaction.create_initial_response(
        hikari.ResponseType.DEFERRED_MESSAGE_UPDATE
    )

    # Get case ID from modal
    search_case_id = ctx.interaction.components[0].components[0].value.strip().upper()

    # Search for the case across all staff logs
    all_logs = await get_all_staff_logs(mongo)

    found_case = None
    found_username = None

    for log in all_logs:
        staff_cases = log.get('staff_cases', [])
        for case in staff_cases:
            if case.get('case_id') == search_case_id:
                found_case = case
                found_username = log.get('username', 'Unknown')
                break
        if found_case:
            break

    # Build result display
    if found_case:
        case_type = found_case.get('type', 'Unknown')
        reason = found_case.get('reason', 'No reason provided')
        date_str = format_discord_timestamp(found_case.get('date'), "D")
        issued_by = found_case.get('issued_by_name', 'Unknown')

        result_text = f"**[{search_case_id}]** {case_type}\n\n"
        result_text += f"**Staff Member:** {found_username}\n"
        result_text += f"**Issued by:** {issued_by}\n"
        result_text += f"**Date:** {date_str}\n\n"
        result_text += f"**Reason:**\n{reason}"

        components = [
            Container(
                accent_color=BLUE_ACCENT,
                components=[
                    Text(content="## 🔍 Case Search Result"),
                    Separator(divider=True),

                    Text(content=result_text),

                    Separator(divider=True),

                    ActionRow(components=[
                        Button(
                            style=hikari.ButtonStyle.SECONDARY,
                            label="Close",
                            custom_id="staff_dash_back",
                            emoji="✖️"
                        )
                    ]),

                    Media(items=[MediaItem(media="assets/Blue_Footer.png")])
                ]
            )
        ]
    else:
        components = [
            Container(
                accent_color=DARK_MAGENTA_ACCENT,
                components=[
                    Text(content="## 🔍 Case Search Result"),
                    Separator(divider=True),

                    Text(content=f"❌ **Case Not Found**"),
                    Text(content=f"No case found with ID: **{search_case_id}**"),

                    Separator(divider=True),

                    ActionRow(components=[
                        Button(
                            style=hikari.ButtonStyle.SECONDARY,
                            label="Close",
                            custom_id="staff_dash_back",
                            emoji="✖️"
                        )
                    ]),

                    Media(items=[MediaItem(media="assets/Blue_Footer.png")])
                ]
            )
        ]

    await ctx.interaction.edit_initial_response(components=components)
    print(f"[Staff Dashboard] Searched for case ID: {search_case_id}, Found: {found_case is not None}")


# ========== CHANGE STATUS ==========

@register_action("staff_dash_status_select", no_return=True, ephemeral=True, defer_update=True)
@lightbulb.di.with_di
async def handle_status_select(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    mongo: MongoClient = lightbulb.di.INJECTED,
    bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    **kwargs
):
    """Process status change from dropdown selection"""
    user_id = action_id

    # Get selected value from dropdown
    if not ctx.interaction.values:
        await ctx.interaction.edit_initial_response(
            components=build_error_message("❌ No status selected.")
        )
        return

    new_status = ctx.interaction.values[0]

    # Update database
    await mongo.staff_logs.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "employment_status": new_status,
                "metadata.last_updated": datetime.now(timezone.utc)
            }
        }
    )

    # Check if new status is Terminated or Staff Banned - auto-remove all positions
    if new_status in ["Terminated", "Staff Banned"]:
        # Get current log to see all positions
        log = await get_staff_log(mongo, user_id)

        if log:
            current_team = log.get('current_team')
            current_position = log.get('current_position')
            additional_positions = log.get('additional_positions', [])

            # Build reason based on status
            reason = f"Automatically removed due to {new_status}"

            # Collect all position removal entries for position_history
            position_removals = []

            # Add primary position removal if exists
            if current_team and current_position:
                position_removals.append({
                    "action": "removed",
                    "team": current_team,
                    "position": current_position,
                    "date": datetime.now(timezone.utc),
                    "changed_by_id": str(ctx.user.id),
                    "changed_by_name": str(ctx.user),
                    "notes": reason
                })

            # Add additional position removals
            for pos in additional_positions:
                position_removals.append({
                    "action": "removed",
                    "team": pos.get('team'),
                    "position": pos.get('position'),
                    "date": datetime.now(timezone.utc),
                    "changed_by_id": str(ctx.user.id),
                    "changed_by_name": str(ctx.user),
                    "notes": reason
                })

            # Update database - clear positions and add removal entries to history
            if position_removals:
                await mongo.staff_logs.update_one(
                    {"user_id": user_id},
                    {
                        "$set": {
                            "current_team": "",
                            "current_position": "",
                            "additional_positions": [],
                            "metadata.last_updated": datetime.now(timezone.utc)
                        },
                        "$push": {
                            "position_history": {"$each": position_removals}
                        }
                    }
                )

                total_removed = len(position_removals)
                print(f"[Staff Dashboard] Auto-removed {total_removed} position(s) due to {new_status} for user {user_id}")

    # Update forum log
    await update_forum_log(bot, mongo, user_id, ctx.guild_id)

    # Get updated log and return to record view
    log = await get_staff_log(mongo, user_id)
    user = await bot.rest.fetch_user(int(user_id))
    components = build_staff_record_view(log, user, ctx.guild_id)

    await ctx.interaction.edit_initial_response(components=components)
    print(f"[Staff Dashboard] Status updated for {user.username}: {new_status}")


# ========== EDIT INFO ==========

@register_action("staff_dash_edit_dates", ephemeral=True, no_return=True, defer_update=True)
@lightbulb.di.with_di
async def handle_edit_dates_button(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    """Handle 'Edit Dates' button - shows date selection view"""
    user_id = action_id

    # Get staff log
    log = await get_staff_log(mongo, user_id)
    if not log:
        await ctx.interaction.edit_initial_response(
            components=build_error_message("Staff log not found.")
        )
        return

    # Build date selection view
    components = build_edit_dates_selection(ctx.guild_id, user_id, log)
    await ctx.interaction.edit_initial_response(components=components)
    print(f"[Staff Dashboard] Edit dates menu opened for user {user_id}")


@register_action("staff_dash_edit_hire_date", no_return=True, opens_modal=True, ephemeral=True)
@lightbulb.di.with_di
async def handle_edit_hire_date_button(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    """Handle 'Edit Hire Date' button - opens modal with hire date field"""
    user_id = action_id

    # Get current log
    log = await get_staff_log(mongo, user_id)
    if not log:
        await ctx.respond(
            components=build_error_message("Staff log not found."),
            flags=hikari.MessageFlag.EPHEMERAL
        )
        return

    # Format hire date for modal
    hire_date = log.get('hire_date')
    hire_date_str = hire_date.strftime("%Y-%m-%d") if hire_date else ""

    modal = build_edit_hire_date_modal(user_id, hire_date_str)
    await ctx.interaction.create_modal_response(
        title=modal.title,
        custom_id=modal.custom_id,
        components=modal.components
    )


@register_action("staff_dash_edit_join_date", no_return=True, opens_modal=True, ephemeral=True)
@lightbulb.di.with_di
async def handle_edit_join_date_button(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    """Handle 'Edit Join Date' button - opens modal with join date field"""
    user_id = action_id

    # Get current log
    log = await get_staff_log(mongo, user_id)
    if not log:
        await ctx.respond(
            components=build_error_message("Staff log not found."),
            flags=hikari.MessageFlag.EPHEMERAL
        )
        return

    # Format join date for modal
    join_date = log.get('join_date')
    join_date_str = join_date.strftime("%Y-%m-%d") if join_date else ""

    modal = build_edit_join_date_modal(user_id, join_date_str)
    await ctx.interaction.create_modal_response(
        title=modal.title,
        custom_id=modal.custom_id,
        components=modal.components
    )


@register_action("staff_dash_edit_hire_date_submit", ephemeral=True, is_modal=True, no_return=True)
@lightbulb.di.with_di
async def handle_edit_hire_date_submit(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    mongo: MongoClient = lightbulb.di.INJECTED,
    bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    **kwargs
):
    """Process hire date edit from modal"""
    # Defer immediately to prevent timeout
    await ctx.interaction.create_initial_response(
        hikari.ResponseType.DEFERRED_MESSAGE_UPDATE
    )

    user_id = action_id

    # Get value from modal
    hire_date_str = ctx.interaction.components[0].components[0].value.strip()

    # Parse date
    try:
        hire_date = datetime.strptime(hire_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        await ctx.interaction.edit_initial_response(
            components=build_error_message("Invalid date format. Use YYYY-MM-DD")
        )
        return

    # Update database
    await mongo.staff_logs.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "hire_date": hire_date,
                "metadata.last_updated": datetime.now(timezone.utc)
            }
        }
    )

    # Update forum log
    await update_forum_log(bot, mongo, user_id, ctx.guild_id)

    # Get updated log and return to record view
    log = await get_staff_log(mongo, user_id)
    user = await bot.rest.fetch_user(int(user_id))
    components = build_staff_record_view(log, user, ctx.guild_id)

    await ctx.interaction.edit_initial_response(components=components)
    print(f"[Staff Dashboard] Hire date updated for {user.username} to {hire_date_str}")


@register_action("staff_dash_edit_join_date_submit", ephemeral=True, is_modal=True, no_return=True)
@lightbulb.di.with_di
async def handle_edit_join_date_submit(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    mongo: MongoClient = lightbulb.di.INJECTED,
    bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    **kwargs
):
    """Process join date edit from modal"""
    # Defer immediately to prevent timeout
    await ctx.interaction.create_initial_response(
        hikari.ResponseType.DEFERRED_MESSAGE_UPDATE
    )

    user_id = action_id

    # Get value from modal
    join_date_str = ctx.interaction.components[0].components[0].value.strip()

    # Parse date
    try:
        join_date = datetime.strptime(join_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        await ctx.interaction.edit_initial_response(
            components=build_error_message("Invalid date format. Use YYYY-MM-DD")
        )
        return

    # Update database
    await mongo.staff_logs.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "join_date": join_date,
                "metadata.last_updated": datetime.now(timezone.utc)
            }
        }
    )

    # Update forum log
    await update_forum_log(bot, mongo, user_id, ctx.guild_id)

    # Get updated log and return to record view
    log = await get_staff_log(mongo, user_id)
    user = await bot.rest.fetch_user(int(user_id))
    components = build_staff_record_view(log, user, ctx.guild_id)

    await ctx.interaction.edit_initial_response(components=components)
    print(f"[Staff Dashboard] Join date updated for {user.username} to {join_date_str}")


# ========== BACK TO DASHBOARD ==========

@register_action("staff_dash_back", ephemeral=True, no_return=True)
@lightbulb.di.with_di
async def handle_back(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    **kwargs
):
    """Handle 'Close' button - closes the ephemeral message"""
    # Just delete the ephemeral message (main dashboard is public and always visible)
    await ctx.interaction.delete_initial_response()
    print("[Staff Dashboard] Closed ephemeral message")


@register_action("staff_dash_refresh", no_return=True, ephemeral=True)
@lightbulb.di.with_di
async def handle_refresh(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    """Handle 'Refresh Dashboard' button - rebuilds dashboard in the same message with fresh dropdown"""
    import time

    # Get all staff logs
    all_logs = await get_all_staff_logs(mongo)

    # Calculate stats
    stats = {
        'active': sum(1 for log in all_logs if log.get('employment_status') == 'Active'),
        'on_leave': sum(1 for log in all_logs if log.get('employment_status') == 'On Leave'),
        'inactive': sum(1 for log in all_logs if log.get('employment_status') in ['Inactive', 'Terminated', 'Staff Banned'])
    }

    # Rebuild main dashboard with fresh unique_id to reset dropdown
    components = build_main_dashboard(ctx.guild_id, stats, all_logs)

    # Update the public dashboard message
    await ctx.interaction.edit_message(ctx.interaction.message, components=components)

    # Send ephemeral confirmation
    await ctx.respond("✅ Dashboard refreshed!", ephemeral=True)
    print("[Staff Dashboard] Dashboard refreshed - dropdown reset")


# ========== FILTER HANDLERS ==========

@register_action("staff_dash_filter_team", no_return=True, ephemeral=True)
@lightbulb.di.with_di
async def handle_filter_team(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    """Handle 'Filter by Team' button - shows selection for teams"""
    # Get all logs
    all_logs = await get_all_staff_logs(mongo)

    if not all_logs:
        await ctx.respond("❌ No staff logs found.", ephemeral=True)
        return

    # Get unique teams
    teams = set()
    for log in all_logs:
        team = log.get('current_team')
        if team:
            teams.add(team)

    teams = sorted(list(teams))

    if not teams:
        await ctx.respond("❌ No teams found in staff records.", ephemeral=True)
        return

    # For now, show all staff grouped by team
    # Build grouped view
    import time
    unique_id = str(int(time.time() * 1000))

    team_sections = []
    for team in teams:
        team_staff = [log for log in all_logs if log.get('current_team') == team]
        staff_list = [f"• <@{log.get('user_id')}> - {log.get('current_position', 'N/A')}" for log in team_staff]
        staff_text = "\n".join(staff_list)

        team_sections.append(Text(content=f"**{team}** ({len(team_staff)} members)"))
        team_sections.append(Text(content=staff_text))
        team_sections.append(Separator(divider=False, spacing=hikari.SpacingType.SMALL))

    components = [
        Container(
            accent_color=BLUE_ACCENT,
            components=[
                Text(content="## 👥 Staff by Team"),
                Separator(divider=True),
                *team_sections,
                Separator(divider=True),
                Text(content="Select a staff member to view their record:"),
                Separator(divider=False, spacing=hikari.SpacingType.SMALL),
                ActionRow(components=[
                    build_staff_select_menu(all_logs, unique_id)
                ]),
                Separator(divider=True),
                ActionRow(components=[
                    Button(
                        style=hikari.ButtonStyle.SECONDARY,
                        label="Close",
                        custom_id="staff_dash_back",
                        emoji="✖️"
                    )
                ]),
                Media(items=[MediaItem(media="assets/Blue_Footer.png")])
            ]
        )
    ]

    # Create NEW ephemeral message (not edit)
    await ctx.respond(components=components, ephemeral=True)
    print(f"[Staff Dashboard] Filter by Team - {len(teams)} teams found")


@register_action("staff_dash_filter_status", no_return=True, ephemeral=True)
@lightbulb.di.with_di
async def handle_filter_status(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    """Handle 'Filter by Status' button - shows selection for status types"""
    # Get all logs
    all_logs = await get_all_staff_logs(mongo)

    if not all_logs:
        await ctx.respond("❌ No staff logs found.", ephemeral=True)
        return

    # Group by status
    status_groups = {
        "Active": [log for log in all_logs if log.get('employment_status') == 'Active'],
        "On Leave": [log for log in all_logs if log.get('employment_status') == 'On Leave'],
        "Inactive": [log for log in all_logs if log.get('employment_status') == 'Inactive'],
        "Terminated": [log for log in all_logs if log.get('employment_status') == 'Terminated'],
        "Staff Banned": [log for log in all_logs if log.get('employment_status') == 'Staff Banned']
    }

    # Build grouped view
    import time
    unique_id = str(int(time.time() * 1000))

    status_emojis = {
        "Active": "✅",
        "On Leave": "🏖️",
        "Inactive": "💤",
        "Terminated": "❌",
        "Staff Banned": "🚫"
    }

    status_sections = []
    for status, staff_list in status_groups.items():
        if staff_list:
            emoji = status_emojis.get(status, "•")
            staff_mentions = [f"• <@{log.get('user_id')}> - {log.get('current_team', 'N/A')}: {log.get('current_position', 'N/A')}" for log in staff_list]
            staff_text = "\n".join(staff_mentions)

            status_sections.append(Text(content=f"**{emoji} {status}** ({len(staff_list)} members)"))
            status_sections.append(Text(content=staff_text))
            status_sections.append(Separator(divider=False, spacing=hikari.SpacingType.SMALL))

    components = [
        Container(
            accent_color=BLUE_ACCENT,
            components=[
                Text(content="## 📊 Staff by Status"),
                Separator(divider=True),
                *status_sections,
                Separator(divider=True),
                Text(content="Select a staff member to view their record:"),
                Separator(divider=False, spacing=hikari.SpacingType.SMALL),
                ActionRow(components=[
                    build_staff_select_menu(all_logs, unique_id)
                ]),
                Separator(divider=True),
                ActionRow(components=[
                    Button(
                        style=hikari.ButtonStyle.SECONDARY,
                        label="Close",
                        custom_id="staff_dash_back",
                        emoji="✖️"
                    )
                ]),
                Media(items=[MediaItem(media="assets/Blue_Footer.png")])
            ]
        )
    ]

    # Create NEW ephemeral message (not edit)
    await ctx.respond(components=components, ephemeral=True)
    print(f"[Staff Dashboard] Filter by Status - {sum(len(v) for v in status_groups.values())} staff shown")


@register_action("staff_dash_filter_role", no_return=True, ephemeral=True)
@lightbulb.di.with_di
async def handle_filter_role(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    """Handle 'By Team' button - shows team selection dropdown"""
    from utils.constants import STAFF_ROLES

    # Get all logs
    all_logs = await get_all_staff_logs(mongo)

    if not all_logs:
        await ctx.respond("❌ No staff logs found.", ephemeral=True)
        return

    # Build team selection dropdown
    team_options = []
    for team_name in STAFF_ROLES.keys():
        team_options.append(
            hikari.impl.SelectOptionBuilder(
                label=team_name,
                value=team_name,
                description=f"View {team_name} team hierarchy"
            )
        )

    components = [
        Container(
            accent_color=BLUE_ACCENT,
            components=[
                Text(content="## 👥 Select Team to View"),
                Separator(divider=True),
                Text(content="Choose a team to see their positions and staff members:"),
                Separator(divider=False, spacing=hikari.SpacingType.SMALL),
                ActionRow(components=[
                    TextSelectMenu(
                        custom_id="staff_dash_select_team",
                        placeholder="Select a team...",
                        options=team_options,
                        min_values=1,
                        max_values=1
                    )
                ]),
                Separator(divider=True),
                ActionRow(components=[
                    Button(
                        style=hikari.ButtonStyle.SECONDARY,
                        label="Close",
                        custom_id="staff_dash_back",
                        emoji="✖️"
                    )
                ]),
                Media(items=[MediaItem(media="assets/Blue_Footer.png")])
            ]
        )
    ]

    await ctx.respond(components=components, ephemeral=True)
    print(f"[Staff Dashboard] Team selection view shown")


@register_action("staff_dash_return_team_selection", no_return=True, ephemeral=True, defer_update=True)
@lightbulb.di.with_di
async def handle_return_team_selection(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    """Handle 'Back to Team Selection' button - returns to team selection dropdown"""
    from utils.constants import STAFF_ROLES

    # Get all logs
    all_logs = await get_all_staff_logs(mongo)

    if not all_logs:
        await ctx.interaction.edit_initial_response(
            components=build_error_message("No staff logs found.")
        )
        return

    # Build team selection dropdown
    team_options = []
    for team_name in STAFF_ROLES.keys():
        team_options.append(
            hikari.impl.SelectOptionBuilder(
                label=team_name,
                value=team_name,
                description=f"View {team_name} team hierarchy"
            )
        )

    components = [
        Container(
            accent_color=BLUE_ACCENT,
            components=[
                Text(content="## 👥 Select Team to View"),
                Separator(divider=True),
                Text(content="Choose a team to see their positions and staff members:"),
                Separator(divider=False, spacing=hikari.SpacingType.SMALL),
                ActionRow(components=[
                    TextSelectMenu(
                        custom_id="staff_dash_select_team",
                        placeholder="Select a team...",
                        options=team_options,
                        min_values=1,
                        max_values=1
                    )
                ]),
                Separator(divider=True),
                ActionRow(components=[
                    Button(
                        style=hikari.ButtonStyle.SECONDARY,
                        label="Close",
                        custom_id="staff_dash_back",
                        emoji="✖️"
                    )
                ]),
                Media(items=[MediaItem(media="assets/Blue_Footer.png")])
            ]
        )
    ]

    await ctx.interaction.edit_initial_response(components=components)
    print(f"[Staff Dashboard] Returned to team selection")


@register_action("staff_dash_select_team", no_return=True, ephemeral=True, defer_update=True)
@lightbulb.di.with_di
async def handle_team_selected(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    """Handle team selection - shows staff hierarchy for selected team"""
    from utils.constants import STAFF_ROLES

    # Get selected team
    if not ctx.interaction.values:
        await ctx.respond("❌ No team selected.", ephemeral=True)
        return

    selected_team = ctx.interaction.values[0]

    # Get all logs
    all_logs = await get_all_staff_logs(mongo)

    if not all_logs:
        await ctx.interaction.edit_initial_response(
            components=build_error_message("No staff logs found.")
        )
        return

    # Build hierarchy for ONLY the selected team
    import time
    unique_id = f"team_{int(time.time() * 1000)}"  # Prefix with "team_" to track context

    role_sections = []
    team_data = STAFF_ROLES.get(selected_team)

    if not team_data:
        await ctx.interaction.edit_initial_response(
            components=build_error_message(f"Team '{selected_team}' not found in configuration.")
        )
        return

    team_positions = {}  # position_name: list of (log, is_primary)

    # For each position in the selected team
    for role_info in team_data["roles"]:
        position_name = role_info["name"]
        staff_in_position = []

        # Find all staff who hold this position
        for log in all_logs:
            # Check if it's their primary position
            if log.get('current_team') == selected_team and log.get('current_position') == position_name:
                staff_in_position.append((log, True))  # True = primary
            # Check if it's in their additional positions
            else:
                additional_positions = log.get('additional_positions', [])
                for add_pos in additional_positions:
                    if add_pos.get('team') == selected_team and add_pos.get('position') == position_name:
                        staff_in_position.append((log, False))  # False = additional
                        break

        # Only add if there are staff in this position
        if staff_in_position:
            team_positions[position_name] = staff_in_position

    # Build the team section
    # Team header
    role_sections.append(Text(content=f"### 📋 {selected_team} Team"))
    role_sections.append(Separator(divider=False, spacing=hikari.SpacingType.SMALL))

    if not team_positions:
        role_sections.append(Text(content="*No staff members found in this team.*"))
    else:
        # Add each position within this team
        for position_name, staff_list in team_positions.items():
            member_count = len(staff_list)
            role_sections.append(Text(content=f"**🎯 {position_name}** ({member_count} member{'s' if member_count != 1 else ''})"))

            # Build staff mentions with indicators
            staff_lines = []
            for log, is_primary in staff_list:
                user_id = log.get('user_id')
                if is_primary:
                    staff_lines.append(f"   • <@{user_id}> (Primary)")
                else:
                    primary_team = log.get('current_team', 'Unknown')
                    primary_pos = log.get('current_position', 'Unknown')
                    staff_lines.append(f"   • <@{user_id}> (Additional - Primary: {primary_pos})")

            staff_text = "\n".join(staff_lines)
            role_sections.append(Text(content=staff_text))
            role_sections.append(Separator(divider=False, spacing=hikari.SpacingType.SMALL))

    components = [
        Container(
            accent_color=BLUE_ACCENT,
            components=[
                Text(content=f"## 📋 {selected_team} Team Hierarchy"),
                Separator(divider=True),
                *role_sections,
                Separator(divider=True),
                Text(content="Select a staff member to view their record:"),
                Separator(divider=False, spacing=hikari.SpacingType.SMALL),
                ActionRow(components=[
                    build_staff_select_menu(all_logs, unique_id)
                ]),
                Separator(divider=True),
                ActionRow(components=[
                    Button(
                        style=hikari.ButtonStyle.SECONDARY,
                        label="Back",
                        custom_id="staff_dash_return_team_selection",
                        emoji="◀️"
                    )
                ]),
                Media(items=[MediaItem(media="assets/Blue_Footer.png")])
            ]
        )
    ]

    # Update existing message
    await ctx.interaction.edit_initial_response(components=components)
    print(f"[Staff Dashboard] Showing {selected_team} team hierarchy")


@register_action("staff_dash_filter_recent", no_return=True, ephemeral=True)
@lightbulb.di.with_di
async def handle_filter_recent(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    """Handle 'Recent Changes' button - shows staff with recent updates"""
    from datetime import timedelta

    # Get all logs
    all_logs = await get_all_staff_logs(mongo)

    if not all_logs:
        await ctx.respond("❌ No staff logs found.", ephemeral=True)
        return

    # Filter logs updated in last 7 days
    now = datetime.now(timezone.utc)
    seven_days_ago = now - timedelta(days=7)

    recent_logs = []
    for log in all_logs:
        last_updated = log.get('metadata', {}).get('last_updated')
        if last_updated:
            # Ensure timezone-aware for comparison
            if last_updated.tzinfo is None:
                last_updated = last_updated.replace(tzinfo=timezone.utc)
            if last_updated >= seven_days_ago:
                recent_logs.append(log)

    # Sort by most recent first
    recent_logs.sort(key=lambda x: x.get('metadata', {}).get('last_updated', now), reverse=True)

    # Build view
    import time
    unique_id = str(int(time.time() * 1000))

    if recent_logs:
        staff_lines = []
        for log in recent_logs[:15]:  # Show max 15
            user_id = log.get('user_id')
            username = log.get('username', 'Unknown')
            last_updated = log.get('metadata', {}).get('last_updated')
            team = log.get('current_team', 'N/A')
            position = log.get('current_position', 'N/A')

            staff_lines.append(f"• <@{user_id}> - {team}: {position}")
            staff_lines.append(f"  Updated: {format_discord_timestamp(last_updated, 'F')}")

        staff_text = "\n".join(staff_lines)

        if len(recent_logs) > 15:
            staff_text += f"\n\n-# ... and {len(recent_logs) - 15} more"
    else:
        staff_text = "-# No staff records updated in the last 7 days"

    components = [
        Container(
            accent_color=BLUE_ACCENT,
            components=[
                Text(content="## 🕒 Recent Changes (Last 7 Days)"),
                Separator(divider=True),
                Text(content=f"**Showing {len(recent_logs)} of {len(all_logs)} staff members**"),
                Separator(divider=False, spacing=hikari.SpacingType.SMALL),
                Text(content=staff_text),
                Separator(divider=True),
                Text(content="Select a staff member to view their record:"),
                Separator(divider=False, spacing=hikari.SpacingType.SMALL),
                ActionRow(components=[
                    build_staff_select_menu(recent_logs, unique_id)
                ]),
                Separator(divider=True),
                ActionRow(components=[
                    Button(
                        style=hikari.ButtonStyle.SECONDARY,
                        label="Close",
                        custom_id="staff_dash_back",
                        emoji="✖️"
                    )
                ]),
                Media(items=[MediaItem(media="assets/Blue_Footer.png")])
            ]
        )
    ]

    # Create NEW ephemeral message (not edit)
    await ctx.respond(components=components, ephemeral=True)
    print(f"[Staff Dashboard] Filter by Recent - {len(recent_logs)} recent updates found")


# ========== DELETE STAFF LOG ==========

@register_action("staff_dash_delete_log", opens_modal=True, no_return=True)
async def handle_delete_log_button(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    **kwargs
):
    """Show confirmation modal for deleting staff log"""
    user_id = action_id

    # Authorization check - only Family Lead can delete staff records
    if not ctx.member or FAMILY_LEAD_ROLE_ID not in ctx.member.role_ids:
        await ctx.respond(
            "❌ Only Family Lead can delete staff records.",
            flags=hikari.MessageFlag.EPHEMERAL
        )
        print(f"[Staff Dashboard] Blocked {ctx.user} from deleting staff record for user {user_id}")
        return

    # Create confirmation modal
    modal = build_delete_confirmation_modal(user_id)
    await ctx.interaction.create_modal_response(
        title=modal.title,
        custom_id=modal.custom_id,
        components=modal.components
    )
    print(f"[Staff Dashboard] Showing delete confirmation modal for user {user_id}")


@register_action("staff_dash_delete_confirm", ephemeral=True, is_modal=True, no_return=True)
@lightbulb.di.with_di
async def handle_delete_confirm_submit(
    action_id: str,
    ctx: lightbulb.components.ModalContext,
    mongo: MongoClient = lightbulb.di.INJECTED,
    bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    **kwargs
):
    """Process staff log deletion after confirmation"""
    # Defer immediately
    await ctx.interaction.create_initial_response(
        hikari.ResponseType.DEFERRED_MESSAGE_UPDATE
    )

    user_id = action_id

    # Authorization check - only Family Lead can delete staff records
    if not ctx.member or FAMILY_LEAD_ROLE_ID not in ctx.member.role_ids:
        await ctx.interaction.edit_initial_response(
            components=[
                Container(
                    accent_color=DARK_MAGENTA_ACCENT,
                    components=[
                        Text(content="## ❌ Unauthorized"),
                        Separator(divider=True),
                        Text(content="Only Family Lead can delete staff records."),
                        Media(items=[MediaItem(media="assets/Red_Footer.png")])
                    ]
                )
            ]
        )
        print(f"[Staff Dashboard] Blocked {ctx.user} from confirming deletion of staff record for user {user_id}")
        return

    # Get confirmation text
    confirmation = ctx.interaction.components[0].components[0].value.strip().upper()

    if confirmation != "DELETE":
        await ctx.interaction.edit_initial_response(
            components=[
                Container(
                    accent_color=DARK_MAGENTA_ACCENT,
                    components=[
                        Text(content="## ❌ Deletion Cancelled"),
                        Separator(divider=True),
                        Text(content="Confirmation text did not match."),
                        Text(content="Please type **DELETE** exactly to confirm deletion."),
                        Media(items=[MediaItem(media="assets/Red_Footer.png")])
                    ]
                )
            ]
        )
        print(f"[Staff Dashboard] Delete cancelled - confirmation mismatch for user {user_id}")
        return

    # Get log before deleting
    log = await mongo.staff_logs.find_one({"user_id": user_id})
    if not log:
        await ctx.interaction.edit_initial_response(
            components=[
                Container(
                    accent_color=DARK_MAGENTA_ACCENT,
                    components=[
                        Text(content="## ❌ Staff Log Not Found"),
                        Separator(divider=True),
                        Text(content="This log may have already been deleted."),
                        Media(items=[MediaItem(media="assets/Red_Footer.png")])
                    ]
                )
            ]
        )
        print(f"[Staff Dashboard] Delete failed - log not found for user {user_id}")
        return

    username = log.get('username', 'Unknown')
    forum_thread_id = log.get('forum_thread_id')

    # Delete from MongoDB
    await mongo.staff_logs.delete_one({"user_id": user_id})
    print(f"[Staff Dashboard] Deleted MongoDB document for {username} ({user_id})")

    # Delete forum thread
    forum_deleted = False
    try:
        await bot.rest.delete_channel(int(forum_thread_id))
        forum_deleted = True
        print(f"[Staff Dashboard] Deleted forum thread {forum_thread_id} for {username}")
    except Exception as e:
        print(f"[Staff Dashboard] Error deleting forum thread {forum_thread_id}: {e}")

    # Build success message as Components v2
    forum_status = 'Removed' if forum_deleted else 'Failed to remove (may need manual deletion)'

    success_components = [
        Container(
            accent_color=GREEN_ACCENT,
            components=[
                Text(content="## ✅ Staff Log Deleted Successfully"),
                Separator(divider=True),
                Text(content=f"**Staff Member:** {username}"),
                Text(content=f"**Database:** Removed"),
                Text(content=f"**Forum Thread:** {forum_status}"),
                Media(items=[MediaItem(media="assets/Green_Footer.png")])
            ]
        )
    ]

    # Show success
    await ctx.interaction.edit_initial_response(components=success_components)
    print(f"[Staff Dashboard] Completed deletion for {username} ({user_id})")
