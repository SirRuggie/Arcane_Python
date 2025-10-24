"""
Staff Dashboard Modals
Modal builders for data entry
"""

import hikari


def build_create_log_modal(selected_user_id: str, team: str, position: str, dashboard_msg_id: str = None) -> hikari.impl.InteractionModalBuilder:
    """
    Modal for creating new staff log
    User and team/position are already selected, just need hire date
    Team, position, and dashboard_msg_id are encoded in custom_id for retrieval
    """
    custom_id = f"staff_dash_create_submit:{selected_user_id}:{team}:{position}:{dashboard_msg_id}" if dashboard_msg_id else f"staff_dash_create_submit:{selected_user_id}:{team}:{position}"

    return (
        hikari.impl.InteractionModalBuilder(
            title="Create New Staff Log",
            custom_id=custom_id,
        )
        .add_component(
            hikari.impl.MessageActionRowBuilder()
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
    )


def build_position_modal(user_id: str, current_team: str, current_position: str) -> hikari.impl.InteractionModalBuilder:
    """
    Modal for updating staff position
    """
    return (
        hikari.impl.InteractionModalBuilder(
            title="Update Staff Position",
            custom_id=f"staff_dash_position_submit:{user_id}",
        )
        .add_component(
            hikari.impl.MessageActionRowBuilder()
            .add_component(
                hikari.impl.TextInputBuilder(
                    custom_id="team",
                    label="New Team",
                    style=hikari.TextInputStyle.SHORT,
                    value=current_team,
                    required=True,
                )
            )
        )
        .add_component(
            hikari.impl.MessageActionRowBuilder()
            .add_component(
                hikari.impl.TextInputBuilder(
                    custom_id="position",
                    label="New Position",
                    style=hikari.TextInputStyle.SHORT,
                    value=current_position,
                    required=True,
                )
            )
        )
        .add_component(
            hikari.impl.MessageActionRowBuilder()
            .add_component(
                hikari.impl.TextInputBuilder(
                    custom_id="notes",
                    label="Reason/Notes (optional)",
                    style=hikari.TextInputStyle.PARAGRAPH,
                    required=False,
                )
            )
        )
    )


def build_admin_reason_modal(user_id: str, action: str) -> hikari.impl.InteractionModalBuilder:
    """
    Modal for tracking admin changes (reason only, action determined by button)
    action: "Add" or "Remove"
    """
    title = f"{action} Admin Privileges"
    placeholder_text = f"Reason for {action.lower()}ing admin privileges..."

    return (
        hikari.impl.InteractionModalBuilder(
            title=title,
            custom_id=f"staff_dash_admin_submit:{user_id}:{action}",
        )
        .add_component(
            hikari.impl.MessageActionRowBuilder()
            .add_component(
                hikari.impl.TextInputBuilder(
                    custom_id="reason",
                    label="Reason",
                    style=hikari.TextInputStyle.PARAGRAPH,
                    placeholder=placeholder_text,
                    required=True,
                )
            )
        )
    )


def build_case_modal(user_id: str, case_type: str, action_id: str) -> hikari.impl.InteractionModalBuilder:
    """
    Modal for adding staff case (reason only, case type selected previously)
    """
    return (
        hikari.impl.InteractionModalBuilder(
            title=f"Add {case_type}",
            custom_id=f"staff_dash_case_submit:{action_id}",
        )
        .add_component(
            hikari.impl.MessageActionRowBuilder()
            .add_component(
                hikari.impl.TextInputBuilder(
                    custom_id="reason",
                    label="Reason",
                    style=hikari.TextInputStyle.PARAGRAPH,
                    placeholder=f"Detailed reason for this {case_type.lower()}...",
                    required=True,
                )
            )
        )
    )


def build_status_modal(user_id: str, current_status: str) -> hikari.impl.InteractionModalBuilder:
    """
    Modal for changing employment status
    """
    return (
        hikari.impl.InteractionModalBuilder(
            title="Change Employment Status",
            custom_id=f"staff_dash_status_submit:{user_id}",
        )
        .add_component(
            hikari.impl.MessageActionRowBuilder()
            .add_component(
                hikari.impl.TextInputBuilder(
                    custom_id="status",
                    label="New Status",
                    style=hikari.TextInputStyle.SHORT,
                    placeholder="Active, On Leave, Inactive, Terminated",
                    value=current_status,
                    required=True,
                )
            )
        )
    )


def build_edit_modal(user_id: str, hire_date_str: str, join_date_str: str) -> hikari.impl.InteractionModalBuilder:
    """
    Modal for editing basic info
    """
    return (
        hikari.impl.InteractionModalBuilder(
            title="Edit Staff Info",
            custom_id=f"staff_dash_edit_submit:{user_id}",
        )
        .add_component(
            hikari.impl.MessageActionRowBuilder()
            .add_component(
                hikari.impl.TextInputBuilder(
                    custom_id="hire_date",
                    label="Hire Date (YYYY-MM-DD)",
                    style=hikari.TextInputStyle.SHORT,
                    value=hire_date_str,
                    required=True,
                )
            )
        )
        .add_component(
            hikari.impl.MessageActionRowBuilder()
            .add_component(
                hikari.impl.TextInputBuilder(
                    custom_id="join_date",
                    label="Server Join Date (YYYY-MM-DD)",
                    style=hikari.TextInputStyle.SHORT,
                    value=join_date_str,
                    required=True,
                )
            )
        )
    )


def build_delete_confirmation_modal(user_id: str) -> hikari.impl.InteractionModalBuilder:
    """
    Modal for confirming staff log deletion
    Requires user to type DELETE to confirm
    """
    return (
        hikari.impl.InteractionModalBuilder(
            title="⚠️ Delete Staff Log - Confirmation",
            custom_id=f"staff_dash_delete_confirm:{user_id}",
        )
        .add_component(
            hikari.impl.MessageActionRowBuilder()
            .add_component(
                hikari.impl.TextInputBuilder(
                    custom_id="confirmation",
                    label="Type DELETE to confirm",
                    style=hikari.TextInputStyle.SHORT,
                    placeholder="DELETE",
                    required=True,
                    max_length=10
                )
            )
        )
    )


def build_edit_hire_date_modal(user_id: str, current_hire_date_str: str) -> hikari.impl.InteractionModalBuilder:
    """
    Modal for editing hire date only
    """
    return (
        hikari.impl.InteractionModalBuilder(
            title="Edit Hire Date",
            custom_id=f"staff_dash_edit_hire_date_submit:{user_id}",
        )
        .add_component(
            hikari.impl.MessageActionRowBuilder()
            .add_component(
                hikari.impl.TextInputBuilder(
                    custom_id="hire_date",
                    label="Hire Date (YYYY-MM-DD)",
                    style=hikari.TextInputStyle.SHORT,
                    value=current_hire_date_str,
                    placeholder="2024-01-15",
                    required=True,
                )
            )
        )
    )


def build_edit_join_date_modal(user_id: str, current_join_date_str: str) -> hikari.impl.InteractionModalBuilder:
    """
    Modal for editing join date only
    """
    return (
        hikari.impl.InteractionModalBuilder(
            title="Edit Server Join Date",
            custom_id=f"staff_dash_edit_join_date_submit:{user_id}",
        )
        .add_component(
            hikari.impl.MessageActionRowBuilder()
            .add_component(
                hikari.impl.TextInputBuilder(
                    custom_id="join_date",
                    label="Server Join Date (YYYY-MM-DD)",
                    style=hikari.TextInputStyle.SHORT,
                    value=current_join_date_str,
                    placeholder="2024-01-15",
                    required=True,
                )
            )
        )
    )


def build_edit_position_date_modal(user_id: str, position_identifier: str, current_date_str: str, position_display: str) -> hikari.impl.InteractionModalBuilder:
    """
    Modal for editing a position's assigned date
    position_identifier: "primary" or "secondary_X"
    current_date_str: Current date in YYYY-MM-DD format
    position_display: Display name like "Community - Moderator"
    """
    return (
        hikari.impl.InteractionModalBuilder(
            title=f"Edit Date: {position_display[:40]}",  # Truncate if too long
            custom_id=f"staff_dash_edit_position_date_submit:{user_id}:{position_identifier}",
        )
        .add_component(
            hikari.impl.MessageActionRowBuilder()
            .add_component(
                hikari.impl.TextInputBuilder(
                    custom_id="position_date",
                    label="Position Assigned Date (YYYY-MM-DD)",
                    style=hikari.TextInputStyle.SHORT,
                    value=current_date_str,
                    placeholder="2024-01-15",
                    required=True,
                )
            )
        )
    )
