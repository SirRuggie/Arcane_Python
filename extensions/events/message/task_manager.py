import asyncio
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any

import hikari
import lightbulb
import pendulum
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

from hikari.impl import (
    ContainerComponentBuilder as Container,
    TextDisplayComponentBuilder as Text,
    SeparatorComponentBuilder as Separator,
    MediaGalleryComponentBuilder as Media,
    MediaGalleryItemBuilder as MediaItem,
    InteractiveButtonBuilder as Button,
    MessageActionRowBuilder as ActionRow,
)

from utils.mongo import MongoClient
from utils.constants import DARK_MAGENTA_ACCENT, GREEN_ACCENT, BLUE_ACCENT, MAGENTA_ACCENT
from extensions.components import register_action

loader = lightbulb.Loader()

@loader.listener(hikari.StartedEvent)
@lightbulb.di.with_di
async def restore_reminders_on_startup(
    event: hikari.StartedEvent,
    bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    mongo: MongoClient = lightbulb.di.INJECTED,
) -> None:
    """Restore all pending reminders from MongoDB on bot startup"""
    try:
        print("[Task Manager] Restoring reminders from MongoDB...")

        # Get current time for comparison
        now = pendulum.now(DEFAULT_TIMEZONE)
        restored_count = 0
        expired_count = 0

        # Find all users with reminders
        users_with_reminders = mongo.user_tasks.find(
            {"reminders": {"$exists": True, "$ne": []}}
        )

        async for user_data in users_with_reminders:
            user_id = int(user_data["user_id"])
            reminders = user_data.get("reminders", [])

            # Track which reminders to keep (not expired)
            valid_reminders = []

            for reminder in reminders:
                try:
                    reminder_time = pendulum.parse(reminder["reminder_time"])
                    reminder_id = reminder["reminder_id"]
                    task_id = reminder["task_id"]

                    if reminder_time > now:
                        # Reminder is still in the future - restore it

                        # Find the task details
                        task = next(
                            (t for t in user_data.get("tasks", []) if t["task_id"] == task_id),
                            None
                        )

                        if task and not task.get("completed", False):
                            # Create the reminder function
                            async def send_reminder_closure(user_id=user_id, task_id=task_id, reminder_id=reminder_id):
                                try:
                                    user = await bot.rest.fetch_user(user_id)
                                    dm_channel = await bot.rest.create_dm_channel(user_id)

                                    current_data = await mongo.user_tasks.find_one({"user_id": str(user_id)})
                                    if current_data:
                                        current_task = next((t for t in current_data.get("tasks", []) if t["task_id"] == task_id), None)
                                        if current_task and not current_task.get("completed", False):
                                            components = [
                                                Container(
                                                    accent_color=BLUE_ACCENT,
                                                    components=[
                                                        Text(content="## 🔔 Task Reminder"),
                                                        Separator(divider=True),
                                                        Text(content=f"**Task #{task_id}:** {current_task['description']}"),
                                                        Text(content=f"\nThis task is still pending completion!"),
                                                        Separator(divider=True),
                                                        ActionRow(
                                                            components=[
                                                                Button(
                                                                    style=hikari.ButtonStyle.SUCCESS,
                                                                    label="Mark Complete",
                                                                    custom_id=f"complete_from_reminder:{user_id}_{task_id}",
                                                                    emoji="✅"
                                                                ),
                                                                Button(
                                                                    style=hikari.ButtonStyle.SECONDARY,
                                                                    label="Snooze 1h",
                                                                    custom_id=f"snooze_reminder:{user_id}_{task_id}_1h",
                                                                    emoji="⏰"
                                                                )
                                                            ]
                                                        ),
                                                        Text(content=f"-# You set this reminder • Task created {current_task['created_at'][:10]}"),
                                                        Media(items=[MediaItem(media="assets/Blue_Footer.png")])
                                                    ]
                                                )
                                            ]

                                            await bot.rest.create_message(
                                                channel=dm_channel.id,
                                                components=components,
                                                user_mentions=True
                                            )

                                            # Also ping user in task channel (create separate components with mention)
                                            channel_components = [
                                                Container(
                                                    accent_color=BLUE_ACCENT,
                                                    components=[
                                                        Text(content=f"{user.mention}"),
                                                        Text(content="## 🔔 Task Reminder"),
                                                        Separator(divider=True),
                                                        Text(content=f"**Task #{task_id}:** {current_task['description']}"),
                                                        Text(content=f"\nThis task is still pending completion!"),
                                                        Separator(divider=True),
                                                        ActionRow(
                                                            components=[
                                                                Button(
                                                                    style=hikari.ButtonStyle.SECONDARY,
                                                                    label="Dismiss",
                                                                    custom_id="dismiss_channel_reminder",
                                                                    emoji="✖️"
                                                                )
                                                            ]
                                                        ),
                                                        Text(content=f"-# You set this reminder • Task created {current_task['created_at'][:10]}"),
                                                        Media(items=[MediaItem(media="assets/Blue_Footer.png")])
                                                    ]
                                                )
                                            ]

                                            await bot.rest.create_message(
                                                channel=TASK_CHANNEL_ID,
                                                components=channel_components,
                                                user_mentions=True
                                            )

                                    # Remove reminder from active list
                                    if reminder_id in active_reminders:
                                        del active_reminders[reminder_id]

                                except Exception as e:
                                    print(f"[Task Manager] Failed to send restored reminder: {e}")

                            # Schedule the reminder
                            reminder_datetime = reminder_time.in_tz(DEFAULT_TIMEZONE).naive()
                            scheduler.add_job(
                                send_reminder_closure,
                                trigger=DateTrigger(run_date=reminder_datetime, timezone=DEFAULT_TIMEZONE),
                                id=reminder_id,
                                replace_existing=True
                            )

                            # Add to active reminders
                            active_reminders[reminder_id] = {
                                "user_id": user_id,
                                "task_id": task_id,
                                "reminder_time": reminder["reminder_time"],
                                "description": task["description"]
                            }

                            valid_reminders.append(reminder)
                            restored_count += 1
                            print(f"[Task Manager] Restored reminder for user {user_id}, task {task_id}")
                        else:
                            # Task completed or not found - remove reminder
                            expired_count += 1
                    else:
                        # Reminder is in the past - remove it
                        expired_count += 1

                except Exception as e:
                    print(f"[Task Manager] Error processing reminder: {e}")
                    expired_count += 1

            # Update user's reminders to remove expired ones
            if len(valid_reminders) != len(reminders):
                await mongo.user_tasks.update_one(
                    {"user_id": str(user_id)},
                    {"$set": {"reminders": valid_reminders}}
                )

        print(f"[Task Manager] Reminder restoration complete: {restored_count} restored, {expired_count} expired/cleaned")

    except Exception as e:
        print(f"[Task Manager] Error during reminder restoration: {e}")

# Configuration
REQUIRED_ROLE_ID = 1060318031575793694
TASK_CHANNEL_ID = 1349392747336958102
AUTO_DELETE_DELAY = 60  # seconds
MAX_TASK_DESCRIPTION_LENGTH = 500
MAX_TASKS_PER_USER = 50
DEFAULT_TIMEZONE = "America/New_York"

# Track pending edit operations
edit_sessions: Dict[int, Dict[str, Any]] = {}

# Track auto-delete tasks
delete_tasks: Dict[int, asyncio.Task] = {}

# Initialize scheduler
scheduler = AsyncIOScheduler(timezone=DEFAULT_TIMEZONE)
scheduler.start()

# Store active reminders
active_reminders: Dict[str, Any] = {}


def create_task_embed(
        title: str,
        description: str,
        color: int = BLUE_ACCENT,
        footer: Optional[str] = None
) -> List[Container]:
    """Create a Components v2 embed for task responses."""
    components = [
        Container(
            accent_color=color,
            components=[
                           Text(content=f"## {title}"),
                           Separator(divider=True),
                           Text(content=description),
                           Media(items=[MediaItem(media="assets/Blue_Footer.png")]),
                       ] + ([Text(content=f"-# {footer}")] if footer else [])
        )
    ]
    return components


def format_task_list(tasks: List[Dict[str, Any]], assigned_info: Optional[Dict[int, str]] = None) -> str:
    """
    Format tasks for display with assignment information.

    Args:
        tasks: List of tasks to format
        assigned_info: Optional dict mapping task_id to assignee/assigner name
    """
    if not tasks:
        return "_No tasks in your list._"

    formatted_tasks = []
    # Sort: completed tasks first, then by task_id
    for task in sorted(tasks, key=lambda t: (not t['completed'], t['task_id'])):
        task_text = task['description']
        task_id = task['task_id']

        # Build task line
        if task['completed']:
            task_line = f"`{task_id}` • ✅ ~~{task_text}~~"
        else:
            task_line = f"`{task_id}` • {task_text}"

        # Add assignment info if provided
        if assigned_info and task_id in assigned_info:
            task_line += f" {assigned_info[task_id]}"

        formatted_tasks.append(task_line)

    return "\n".join(formatted_tasks)


async def get_or_create_user_profile(
        mongo: MongoClient,
        bot: hikari.GatewayBot,
        user_id: int,
        guild_id: Optional[int] = None
) -> Dict[str, Any]:
    """Get or create user profile with server display name as default."""
    profile = await mongo.user_profiles.find_one({"user_id": str(user_id)})

    if not profile:
        # Fetch display name (server nickname if available, otherwise Discord username)
        try:
            if guild_id:
                # Try to get server nickname first
                member = await bot.rest.fetch_member(guild_id, user_id)
                display_name = member.nickname if member.nickname else member.username
            else:
                # Fall back to Discord username
                user = await bot.rest.fetch_user(user_id)
                display_name = user.username
        except:
            display_name = "User"

        # Create default profile
        profile = {
            "user_id": str(user_id),
            "display_name": display_name,
            "timezone": DEFAULT_TIMEZONE,
            "notification_preferences": {},
            "theme_color": MAGENTA_ACCENT
        }

        await mongo.user_profiles.insert_one(profile)

    return profile


async def get_user_display_name(
        mongo: MongoClient,
        bot: hikari.GatewayBot,
        user_id: int,
        guild_id: Optional[int] = None
) -> str:
    """Get user's display name from profile."""
    profile = await get_or_create_user_profile(mongo, bot, user_id, guild_id)
    return profile.get("display_name", "User")


async def get_user_timezone(
        mongo: MongoClient,
        bot: hikari.GatewayBot,
        user_id: int,
        guild_id: Optional[int] = None
) -> str:
    """Get user's timezone preference."""
    profile = await get_or_create_user_profile(mongo, bot, user_id, guild_id)
    return profile.get("timezone", DEFAULT_TIMEZONE)


def parse_time_component(time_str: str) -> Optional[tuple[int, int]]:
    """
    Parse a time string into (hour, minute) tuple in 24-hour format.
    Handles: "9pm", "9:20pm", "9:45am", "21:00", etc.
    Returns None if parsing fails.
    """
    time_str = time_str.strip().lower()
    # Add space before am/pm if not present
    time_str = re.sub(r'(\d)([ap]m)', r'\1 \2', time_str)

    # Pattern: optional hour:minute, optional am/pm
    # Makes colon+minutes OPTIONAL: (?::(\d{2}))?
    time_match = re.match(r'^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$', time_str)

    if not time_match:
        return None

    hour = int(time_match.group(1))
    minute = int(time_match.group(2)) if time_match.group(2) else 0
    period = time_match.group(3)

    # Convert to 24-hour format
    if period == 'pm' and hour != 12:
        hour += 12
    elif period == 'am' and hour == 12:
        hour = 0

    # Validate
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return None

    return (hour, minute)


def parse_reminder_time(time_str: str, user_timezone: str = DEFAULT_TIMEZONE) -> Optional[pendulum.DateTime]:
    """Parse various time formats into a datetime object."""
    time_str = time_str.strip().lower()

    # Get current time in user's timezone
    now = pendulum.now(user_timezone)

    # Pattern for relative times (e.g., 5m, 1h, 2d)
    relative_pattern = r'^(\d+)\s*([mhd])$'
    match = re.match(relative_pattern, time_str)

    if match:
        amount = int(match.group(1))
        unit = match.group(2)

        if unit == 'm':
            return now.add(minutes=amount)
        elif unit == 'h':
            return now.add(hours=amount)
        elif unit == 'd':
            return now.add(days=amount)

    # Handle "tomorrow" alone
    if time_str == "tomorrow":
        return now.add(days=1).replace(hour=9, minute=0, second=0, microsecond=0)

    # Handle "today at [time]"
    if time_str.startswith("today at "):
        time_part = time_str.replace("today at ", "")
        parsed = parse_time_component(time_part)
        if parsed:
            hour, minute = parsed
            result = now.set(hour=hour, minute=minute, second=0, microsecond=0)
            # If time has passed, schedule for tomorrow
            if result < now:
                result = result.add(days=1)
            return result


    # Handle "tomorrow at [time]"
    if time_str.startswith("tomorrow at "):
        time_part = time_str.replace("tomorrow at ", "")
        parsed = parse_time_component(time_part)
        if parsed:
            hour, minute = parsed
            return now.add(days=1).set(hour=hour, minute=minute, second=0, microsecond=0)

    # Handle date patterns: "dec 25th at 4pm", "december 25 at 6:15pm", "jan 1st at 9pm"
    # Strip ordinal suffixes (st, nd, rd, th)
    date_pattern = r'^(\w+)\s+(\d{1,2})(?:st|nd|rd|th)?\s+at\s+(.+)$'
    date_match = re.match(date_pattern, time_str)

    if date_match:
        month_str, day_str, time_part = date_match.groups()

        # Parse the time component
        parsed_time = parse_time_component(time_part)
        if not parsed_time:
            return None

        hour, minute = parsed_time
        day = int(day_str)

        # Try to parse month
        try:
            # pendulum can parse month names
            month_map = {
                'jan': 1, 'january': 1,
                'feb': 2, 'february': 2,
                'mar': 3, 'march': 3,
                'apr': 4, 'april': 4,
                'may': 5,
                'jun': 6, 'june': 6,
                'jul': 7, 'july': 7,
                'aug': 8, 'august': 8,
                'sep': 9, 'sept': 9, 'september': 9,
                'oct': 10, 'october': 10,
                'nov': 11, 'november': 11,
                'dec': 12, 'december': 12,
            }

            month = month_map.get(month_str.lower())
            if not month:
                return None

            # Create date for current or next year
            target_date = now.set(month=month, day=day, hour=hour, minute=minute, second=0, microsecond=0)

            # If the date is in the past, use next year
            if target_date < now:
                target_date = target_date.add(years=1)

            return target_date
        except Exception:
            return None

    # Try parsing as absolute time (no prefix)
    # This handles: "9pm", "9:20pm", "21:00"
    parsed = parse_time_component(time_str)
    if parsed:
        hour, minute = parsed
        result = now.set(hour=hour, minute=minute, second=0, microsecond=0)
        # If time has already passed today, schedule for tomorrow
        if result < now:
            result = result.add(days=1)
        return result

    # Final fallback: try pendulum's natural language parser
    try:
        parsed = pendulum.parse(time_str, tz=user_timezone)
        return parsed
    except Exception:
        pass

    return None


async def schedule_message_deletion(
        bot: hikari.GatewayBot,
        message: hikari.Message,
        delay: int = AUTO_DELETE_DELAY
) -> None:
    """Schedule a message for deletion after a delay."""
    try:
        await asyncio.sleep(delay)
        await bot.rest.delete_message(message.channel_id, message.id)
    except hikari.NotFoundError:
        pass
    except Exception:
        pass
    finally:
        if message.id in delete_tasks:
            del delete_tasks[message.id]


async def send_auto_delete_response(
        bot: hikari.GatewayBot,
        channel_id: int,
        components: List[Container]
) -> hikari.Message:
    """Send a response that auto-deletes after configured delay."""
    message = await bot.rest.create_message(
        channel=channel_id,
        components=components
    )

    delete_task = asyncio.create_task(
        schedule_message_deletion(bot, message)
    )
    delete_tasks[message.id] = delete_task

    return message


async def update_task_list_message(
        bot: hikari.GatewayBot,
        mongo: MongoClient,
        user_id: int,
        tasks: List[Dict[str, Any]],
        guild_id: Optional[int] = None
) -> Optional[int]:
    """Update or create the task list message in the designated channel with 3-section layout."""
    user_data = await mongo.user_tasks.find_one({"user_id": str(user_id)})
    message_id = user_data.get("task_list_message_id") if user_data else None

    # Get user's display name
    display_name = await get_user_display_name(mongo, bot, user_id, guild_id)

    # Get tasks assigned TO this user
    assigned_to_me = await get_assigned_tasks(mongo, user_id)

    # Get tasks assigned BY this user
    my_assignments = await get_tasks_assigned_by_user(mongo, user_id)

    # Build components list
    all_components = []

    # SECTION 1: My Tasks (tasks I own)
    my_tasks = [t for t in tasks if not t.get("assigned_to")]  # Unassigned owned tasks
    my_tasks_with_assignments = [t for t in tasks if t.get("assigned_to")]  # Assigned owned tasks

    if my_tasks or my_tasks_with_assignments:
        # Build assignment info for owned tasks
        assignment_info = {}
        for task in my_tasks_with_assignments:
            assignee_id = int(task["assigned_to"])
            assignee_name = await get_user_display_name(mongo, bot, assignee_id, guild_id)
            assignment_info[task["task_id"]] = f"→ `{assignee_name}`"

        # Combine and format
        all_my_tasks = my_tasks + my_tasks_with_assignments
        my_tasks_content = format_task_list(all_my_tasks, assignment_info)
        my_completed = sum(1 for t in all_my_tasks if t['completed'])

        all_components.append(
            Container(
                accent_color=MAGENTA_ACCENT,
                components=[
                    Text(content=f"# {display_name}'s Tasks"),
                    Text(content="## 📝 My Tasks"),
                    Separator(divider=True),
                    Text(content=my_tasks_content),
                    Separator(divider=True),
                    Text(content=f"-# {len(all_my_tasks)} total • {my_completed} completed"),
                ]
            )
        )

    # SECTION 2: Assigned to Me
    if assigned_to_me:
        # Build assignment info showing who assigned each task
        assignment_info = {}
        for task in assigned_to_me:
            assigner_id = int(task.get("assigned_by", task.get("owner_id")))
            assigner_name = await get_user_display_name(mongo, bot, assigner_id, guild_id)
            assignment_info[task["task_id"]] = f"← `{assigner_name}`"

        assigned_content = format_task_list(assigned_to_me, assignment_info)
        assigned_completed = sum(1 for t in assigned_to_me if t['completed'])

        # If user has no owned tasks, add their name header to this section
        section_components = []
        if not (my_tasks or my_tasks_with_assignments):
            section_components.append(Text(content=f"# {display_name}'s Tasks"))

        section_components.extend([
            Text(content="## 📥 Assigned to Me"),
            Separator(divider=True),
            Text(content=assigned_content),
            Separator(divider=True),
            Text(content=f"-# {len(assigned_to_me)} total • {assigned_completed} completed"),
        ])

        all_components.append(
            Container(
                accent_color=BLUE_ACCENT,
                components=section_components
            )
        )

    # Add footer
    if all_components:
        all_components[-1].components.append(
            Media(items=[MediaItem(media="assets/Purple_Footer.png")])
        )
    else:
        # No tasks at all
        all_components = [
            Container(
                accent_color=MAGENTA_ACCENT,
                components=[
                    Text(content=f"# {display_name}'s Tasks"),
                    Separator(divider=True),
                    Text(content="_No tasks in your list._"),
                    Media(items=[MediaItem(media="assets/Purple_Footer.png")]),
                ]
            )
        ]

    try:
        if message_id:
            await bot.rest.edit_message(
                channel=TASK_CHANNEL_ID,
                message=message_id,
                components=all_components
            )
            return message_id
    except (hikari.NotFoundError, hikari.ForbiddenError):
        pass

    try:
        message = await bot.rest.create_message(
            channel=TASK_CHANNEL_ID,
            components=all_components
        )

        await mongo.user_tasks.update_one(
            {"user_id": str(user_id)},
            {"$set": {"task_list_message_id": message.id}},
            upsert=True
        )

        return message.id
    except Exception:
        return None


async def get_user_tasks(mongo: MongoClient, user_id: int) -> List[Dict[str, Any]]:
    """Get all tasks for a user."""
    user_data = await mongo.user_tasks.find_one({"user_id": str(user_id)})
    return user_data.get("tasks", []) if user_data else []


async def renumber_tasks(
        mongo: MongoClient,
        user_id: int,
        tasks: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Renumber tasks to be sequential starting from 1."""
    sorted_tasks = sorted(tasks, key=lambda t: t['task_id'])

    for index, task in enumerate(sorted_tasks, start=1):
        task['task_id'] = index

    next_id = len(sorted_tasks) + 1

    await mongo.user_tasks.update_one(
        {"user_id": str(user_id)},
        {
            "$set": {
                "tasks": sorted_tasks,
                "next_task_id": next_id
            }
        }
    )

    return sorted_tasks


async def add_task(
        mongo: MongoClient,
        user_id: int,
        description: str
) -> Optional[Dict[str, Any]]:
    """Add a new task for a user."""
    user_data = await mongo.user_tasks.find_one({"user_id": str(user_id)})

    if user_data:
        tasks = user_data.get("tasks", [])
    else:
        tasks = []

    if len(tasks) >= MAX_TASKS_PER_USER:
        return None

    next_id = len(tasks) + 1

    new_task = {
        "task_id": next_id,
        "description": description[:MAX_TASK_DESCRIPTION_LENGTH],
        "completed": False,
        "created_at": datetime.utcnow().isoformat(),
        "completed_at": None
    }

    tasks.append(new_task)

    await mongo.user_tasks.update_one(
        {"user_id": str(user_id)},
        {
            "$set": {
                "tasks": tasks,
                "next_task_id": next_id + 1
            }
        },
        upsert=True
    )

    return new_task


async def delete_task(
        mongo: MongoClient,
        user_id: int,
        task_id: int
) -> tuple[bool, Optional[Dict[str, Any]]]:
    """
    Delete a specific task and renumber remaining tasks.
    Returns (success, deleted_task) tuple where deleted_task contains assignment info if any.
    """
    user_data = await mongo.user_tasks.find_one({"user_id": str(user_id)})
    if not user_data:
        return False, None

    tasks = user_data.get("tasks", [])
    deleted_task = None

    # Find and store the task before deletion
    for task in tasks:
        if task["task_id"] == task_id:
            deleted_task = task.copy()
            break

    # Remove the task
    tasks = [t for t in tasks if t["task_id"] != task_id]

    if not deleted_task:
        return False, None

    await renumber_tasks(mongo, user_id, tasks)

    return True, deleted_task


async def complete_task(
        mongo: MongoClient,
        user_id: int,
        task_id: int
) -> tuple[bool, Optional[Dict[str, Any]]]:
    """
    Mark a task as completed.
    Returns (success, task_data) tuple where task_data contains assignment info if any.
    """
    user_data = await mongo.user_tasks.find_one({"user_id": str(user_id)})
    if not user_data:
        return False, None

    tasks = user_data.get("tasks", [])
    completed_task = None

    for task in tasks:
        if task["task_id"] == task_id:
            task["completed"] = True
            task["completed_at"] = datetime.utcnow().isoformat()
            completed_task = task.copy()  # Store the task data
            break

    if not completed_task:
        return False, None

    await mongo.user_tasks.update_one(
        {"user_id": str(user_id)},
        {"$set": {"tasks": tasks}}
    )

    return True, completed_task


async def delete_all_tasks(
        mongo: MongoClient,
        user_id: int
) -> tuple[int, List[Dict[str, Any]]]:
    """
    Delete all tasks for a user.
    Returns (count_deleted, deleted_tasks) tuple.
    """
    user_data = await mongo.user_tasks.find_one({"user_id": str(user_id)})
    if not user_data:
        return 0, []

    tasks = user_data.get("tasks", [])
    task_count = len(tasks)

    await mongo.user_tasks.update_one(
        {"user_id": str(user_id)},
        {"$set": {"tasks": [], "next_task_id": 1}}
    )

    return task_count, tasks


async def delete_completed_tasks(
        mongo: MongoClient,
        user_id: int
) -> tuple[int, List[Dict[str, Any]]]:
    """
    Delete all completed tasks for a user.
    Returns (count_deleted, remaining_tasks) tuple.
    """
    user_data = await mongo.user_tasks.find_one({"user_id": str(user_id)})
    if not user_data:
        return 0, []

    tasks = user_data.get("tasks", [])

    # Separate completed from non-completed tasks
    completed_tasks = [t for t in tasks if t.get("completed", False)]
    remaining_tasks = [t for t in tasks if not t.get("completed", False)]

    count_deleted = len(completed_tasks)

    if count_deleted > 0:
        # Renumber remaining tasks
        remaining_tasks = await renumber_tasks(mongo, user_id, remaining_tasks)

    return count_deleted, remaining_tasks


async def edit_task(
        mongo: MongoClient,
        user_id: int,
        task_id: int,
        new_description: str
) -> tuple[bool, Optional[Dict[str, Any]]]:
    """
    Edit a task's description.
    Returns (success, edited_task) tuple where edited_task contains assignment info if any.
    """
    user_data = await mongo.user_tasks.find_one({"user_id": str(user_id)})
    if not user_data:
        return False, None

    tasks = user_data.get("tasks", [])
    edited_task = None

    for task in tasks:
        if task["task_id"] == task_id:
            task["description"] = new_description[:MAX_TASK_DESCRIPTION_LENGTH]
            edited_task = task.copy()  # Store the edited task data
            break

    if not edited_task:
        return False, None

    await mongo.user_tasks.update_one(
        {"user_id": str(user_id)},
        {"$set": {"tasks": tasks}}
    )

    return True, edited_task


async def assign_task(
        mongo: MongoClient,
        bot: hikari.GatewayBot,
        owner_id: int,
        task_id: int,
        assignee_id: int,
        assignment_note: Optional[str] = None,
        guild_id: Optional[int] = None
) -> tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Assign a task to another user.
    Returns (success, message, task_data) tuple.
    """
    # Get owner's tasks
    owner_data = await mongo.user_tasks.find_one({"user_id": str(owner_id)})
    if not owner_data:
        return False, "You don't have any tasks.", None

    tasks = owner_data.get("tasks", [])
    task = None

    # Find the task
    for t in tasks:
        if t["task_id"] == task_id:
            task = t
            break

    if not task:
        return False, f"Could not find task #{task_id}.", None

    # Check if task is already completed
    if task.get("completed", False):
        return False, "Cannot assign completed tasks.", None

    # Check if assigning to self
    if owner_id == assignee_id:
        return False, "Cannot assign a task to yourself.", None

    # Verify assignee exists
    try:
        assignee_user = await bot.rest.fetch_user(assignee_id)
    except (hikari.NotFoundError, hikari.ForbiddenError):
        return False, "Could not find that user.", None

    # Check if already assigned to this user
    if task.get("assigned_to") == str(assignee_id):
        assignee_name = await get_user_display_name(mongo, bot, assignee_id, guild_id)
        return False, f"Task is already assigned to {assignee_name}.", None

    # Update task with assignment info
    task["assigned_to"] = str(assignee_id)
    task["assigned_by"] = str(owner_id)
    task["assigned_at"] = datetime.utcnow().isoformat()
    if assignment_note:
        task["assignment_note"] = assignment_note[:500]  # Limit note length

    # Save updated tasks
    await mongo.user_tasks.update_one(
        {"user_id": str(owner_id)},
        {"$set": {"tasks": tasks}}
    )

    return True, "Task assigned successfully.", task.copy()


async def unassign_task(
        mongo: MongoClient,
        user_id: int,
        task_id: int
) -> tuple[bool, str]:
    """
    Remove assignment from a task.
    Returns (success, message) tuple.
    """
    # Get user's tasks
    user_data = await mongo.user_tasks.find_one({"user_id": str(user_id)})
    if not user_data:
        return False, "You don't have any tasks."

    tasks = user_data.get("tasks", [])
    task = None

    # Find the task
    for t in tasks:
        if t["task_id"] == task_id:
            task = t
            break

    if not task:
        return False, f"Could not find task #{task_id}."

    # Check if task has an assignment
    if "assigned_to" not in task or not task.get("assigned_to"):
        return False, "This task is not assigned to anyone."

    # Remove assignment fields
    task.pop("assigned_to", None)
    task.pop("assigned_by", None)
    task.pop("assigned_at", None)
    task.pop("assignment_note", None)

    # Save updated tasks
    await mongo.user_tasks.update_one(
        {"user_id": str(user_id)},
        {"$set": {"tasks": tasks}}
    )

    return True, "Task assignment removed."


async def get_assigned_tasks(
        mongo: MongoClient,
        user_id: int
) -> List[Dict[str, Any]]:
    """Get all tasks assigned TO a user (from all task owners)."""
    assigned_tasks = []

    # Query all user_tasks collections where tasks have assigned_to field matching user_id
    async for user_data in mongo.user_tasks.find({}):
        tasks = user_data.get("tasks", [])
        owner_id = user_data.get("user_id")

        for task in tasks:
            if task.get("assigned_to") == str(user_id):
                # Add owner_id to task for reference
                task_copy = task.copy()
                task_copy["owner_id"] = owner_id
                assigned_tasks.append(task_copy)

    return assigned_tasks


async def get_tasks_assigned_by_user(
        mongo: MongoClient,
        user_id: int
) -> List[Dict[str, Any]]:
    """Get all tasks that a user has assigned to others."""
    # Get user's tasks
    user_data = await mongo.user_tasks.find_one({"user_id": str(user_id)})
    if not user_data:
        return []

    tasks = user_data.get("tasks", [])

    # Filter for tasks that have been assigned
    assigned_tasks = [t for t in tasks if t.get("assigned_to")]

    return assigned_tasks


async def find_task_owner(
        mongo: MongoClient,
        user_id: int,
        task_id: int
) -> Optional[tuple[int, Dict[str, Any]]]:
    """
    Find who owns a task (either user themselves or someone who assigned it to them).
    Returns (owner_id, task) if found, None otherwise.

    First checks user's own tasks, then checks tasks assigned to user.
    """
    # Check user's own tasks first
    user_data = await mongo.user_tasks.find_one({"user_id": str(user_id)})
    if user_data:
        for task in user_data.get("tasks", []):
            if task["task_id"] == task_id:
                return (user_id, task)

    # Check if it's a task assigned to this user (owned by someone else)
    async for owner_data in mongo.user_tasks.find({}):
        owner_id_str = owner_data.get("user_id")
        for task in owner_data.get("tasks", []):
            if task.get("assigned_to") == str(user_id) and task["task_id"] == task_id:
                return (int(owner_id_str), task)

    return None


async def send_assignment_dm(
        bot: hikari.GatewayBot,
        mongo: MongoClient,
        assignee_id: int,
        assigner_id: int,
        task: Dict[str, Any],
        assignment_note: Optional[str] = None,
        guild_id: Optional[int] = None
) -> bool:
    """Send a DM notification to the assignee about the new assignment."""
    try:
        # Create DM channel
        dm_channel = await bot.rest.create_dm_channel(assignee_id)

        # Get display names
        assigner_name = await get_user_display_name(mongo, bot, assigner_id, guild_id)

        # Format assignment time using Discord timestamp (auto-adjusts to user's timezone)
        assigned_at = pendulum.parse(task.get("assigned_at", datetime.utcnow().isoformat()))
        assigned_timestamp = int(assigned_at.timestamp())

        # Build components
        components_list = [
            Text(content="# 📬 Task Assigned to You"),
            Separator(divider=True),
            Text(content=f"**Task #{task['task_id']}:** {task['description']}"),
            Text(content=f"**Assigned by:** {assigner_name}"),
            Text(content=f"**Assigned:** <t:{assigned_timestamp}:f> (<t:{assigned_timestamp}:R>)"),
        ]

        # Add note if provided
        if assignment_note:
            components_list.extend([
                Separator(divider=True),
                Text(content="📝 **Note from assigner:**"),
                Text(content=assignment_note),
            ])

        # Add footer with channel link
        components_list.extend([
            Separator(divider=True),
            Text(content=f"**View in:** <#{TASK_CHANNEL_ID}>"),
            Media(items=[MediaItem(media="assets/Blue_Footer.png")]),
        ])

        # Create container
        components = [
            Container(
                accent_color=BLUE_ACCENT,
                components=components_list
            )
        ]

        # Send DM
        await bot.rest.create_message(
            channel=dm_channel,
            components=components
        )

        return True
    except Exception as e:
        print(f"[Task Manager] Failed to send assignment DM: {e}")
        return False


async def create_reminder(
        mongo: MongoClient,
        bot: hikari.GatewayBot,
        user_id: int,
        task_id: int,
        reminder_time: pendulum.DateTime,
        user_timezone: str = DEFAULT_TIMEZONE
) -> bool:
    """Create a reminder for a specific task."""
    user_data = await mongo.user_tasks.find_one({"user_id": str(user_id)})
    if not user_data:
        return False

    task = next((t for t in user_data.get("tasks", []) if t["task_id"] == task_id), None)
    if not task:
        return False

    reminder_datetime = reminder_time.in_tz(user_timezone).naive()
    reminder_id = f"{user_id}_{task_id}_{int(reminder_time.timestamp())}"

    async def send_reminder():
        try:
            user = await bot.rest.fetch_user(user_id)
            dm_channel = await bot.rest.create_dm_channel(user_id)

            current_data = await mongo.user_tasks.find_one({"user_id": str(user_id)})
            if current_data:
                current_task = next((t for t in current_data.get("tasks", []) if t["task_id"] == task_id), None)
                if current_task and not current_task.get("completed", False):
                    components = [
                        Container(
                            accent_color=BLUE_ACCENT,
                            components=[
                                Text(content="## 🔔 Task Reminder"),
                                Separator(divider=True),
                                Text(content=f"**Task #{task_id}:** {current_task['description']}"),
                                Text(content=f"\nThis task is still pending completion!"),
                                Separator(divider=True),
                                ActionRow(
                                    components=[
                                        Button(
                                            style=hikari.ButtonStyle.SUCCESS,
                                            label="Mark Complete",
                                            custom_id=f"complete_from_reminder:{user_id}_{task_id}",
                                            emoji="✅"
                                        ),
                                        Button(
                                            style=hikari.ButtonStyle.SECONDARY,
                                            label="Snooze 1h",
                                            custom_id=f"snooze_reminder:{user_id}_{task_id}_1h",
                                            emoji="⏰"
                                        )
                                    ]
                                ),
                                Text(
                                    content=f"-# You set this reminder • Task created {current_task['created_at'][:10]}"),
                            ]
                        )
                    ]

                    await bot.rest.create_message(
                        channel=dm_channel.id,
                        components=components
                    )

                    # Also ping user in task channel (create separate components with mention)
                    channel_components = [
                        Container(
                            accent_color=BLUE_ACCENT,
                            components=[
                                Text(content=f"{user.mention}"),
                                Text(content="## 🔔 Task Reminder"),
                                Separator(divider=True),
                                Text(content=f"**Task #{task_id}:** {current_task['description']}"),
                                Text(content=f"\nThis task is still pending completion!"),
                                Separator(divider=True),
                                ActionRow(
                                    components=[
                                        Button(
                                            style=hikari.ButtonStyle.SECONDARY,
                                            label="Dismiss",
                                            custom_id="dismiss_channel_reminder",
                                            emoji="✖️"
                                        )
                                    ]
                                ),
                                Text(
                                    content=f"-# You set this reminder • Task created {current_task['created_at'][:10]}"),
                            ]
                        )
                    ]

                    await bot.rest.create_message(
                        channel=TASK_CHANNEL_ID,
                        components=channel_components,
                        user_mentions=True
                    )

            if reminder_id in active_reminders:
                del active_reminders[reminder_id]

        except Exception as e:
            print(f"[Task Manager] Reminder failed: {e}")
            import traceback
            traceback.print_exc()

    scheduler.add_job(
        send_reminder,
        trigger=DateTrigger(run_date=reminder_datetime, timezone=user_timezone),
        id=reminder_id,
        replace_existing=True
    )

    active_reminders[reminder_id] = {
        "user_id": user_id,
        "task_id": task_id,
        "reminder_time": reminder_time.isoformat(),
        "description": task["description"]
    }

    await mongo.user_tasks.update_one(
        {"user_id": str(user_id)},
        {
            "$push": {
                "reminders": {
                    "reminder_id": reminder_id,
                    "task_id": task_id,
                    "reminder_time": reminder_time.isoformat(),
                    "created_at": datetime.utcnow().isoformat()
                }
            }
        }
    )

    return True


@loader.listener(hikari.MessageCreateEvent)
async def on_task_command(
        event: hikari.MessageCreateEvent,
        bot: hikari.GatewayBot = lightbulb.di.INJECTED,
        mongo: MongoClient = lightbulb.di.INJECTED,
) -> None:
    """Handle task management commands."""
    try:
        if event.is_bot or not event.content:
            return

        content = event.content.strip()

        # Check if user is in a pending edit session
        if event.author_id in edit_sessions:
            session = edit_sessions[event.author_id]
            if session["channel_id"] == event.channel_id:
                task_id = session["task_id"]
                owner_id = session["owner_id"]  # Get the stored owner_id
                prompt_message_id = session.get("prompt_message_id")
                del edit_sessions[event.author_id]

                # Delete the prompt message
                if prompt_message_id:
                    try:
                        await bot.rest.delete_message(event.channel_id, prompt_message_id)
                        if prompt_message_id in delete_tasks:
                            delete_tasks[prompt_message_id].cancel()
                            del delete_tasks[prompt_message_id]
                    except:
                        pass

                # Delete the user's response message (the new description they just sent)
                try:
                    await bot.rest.delete_message(event.channel_id, event.message_id)
                except:
                    pass

                success, edited_task = await edit_task(mongo, owner_id, task_id, content)

                if success:
                    # Update owner's task list
                    owner_tasks = await get_user_tasks(mongo, owner_id)
                    await update_task_list_message(bot, mongo, owner_id, owner_tasks, event.guild_id)

                    # If task was assigned and owner != current user, update current user's list too
                    if edited_task and edited_task.get("assigned_to"):
                        assignee_id = int(edited_task["assigned_to"])
                        if assignee_id != owner_id:
                            assignee_tasks = await get_user_tasks(mongo, assignee_id)
                            await update_task_list_message(bot, mongo, assignee_id, assignee_tasks, event.guild_id)

                    components = create_task_embed(
                        "✅ Task Updated",
                        f"Task #{task_id} has been updated successfully!",
                        GREEN_ACCENT,
                        "This message will delete in 60 seconds"
                    )
                else:
                    components = create_task_embed(
                        "❌ Edit Failed",
                        f"Could not find task #{task_id} to edit.",
                        DARK_MAGENTA_ACCENT,
                        "This message will delete in 60 seconds"
                    )

                await send_auto_delete_response(bot, event.channel_id, components)
                return

        # Pattern matching for commands
        add_match = re.match(r'^add task\s+(.+)$', content, re.IGNORECASE)
        del_match = re.match(r'^del task\s+#?(\d+)$', content, re.IGNORECASE)
        complete_match = re.match(r'^complete task\s+#?(\d+)$', content, re.IGNORECASE)
        edit_match = re.match(r'^edit task\s+#?(\d+)$', content, re.IGNORECASE)
        del_all_match = re.match(r'^del all tasks$', content, re.IGNORECASE)
        del_completed_match = re.match(r'^del completed tasks$', content, re.IGNORECASE)
        remind_match = re.match(r'^remind(?:er)?\s+(?:task\s+)?#?(\d+)\s+(.+)$', content, re.IGNORECASE)
        view_match = re.match(r'^view tasks?$', content, re.IGNORECASE)
        help_match = re.match(r'^(?:help tasks?|tasks? help)$', content, re.IGNORECASE)
        set_name_match = re.match(r'^tasks set name\s+(.+)$', content, re.IGNORECASE)
        set_timezone_match = re.match(r'^tasks set timezone\s+(.+)$', content, re.IGNORECASE)
        profile_match = re.match(r'^tasks profile$', content, re.IGNORECASE)
        sync_name_match = re.match(r'^tasks sync name$', content, re.IGNORECASE)
        # NEW: Assignment commands
        assign_match = re.match(r'^assign\s+task\s+#?(\d+)\s+(?:to\s+)?<@(\d+)>(?:\s+with\s+note\s+(.+))?$', content, re.IGNORECASE)
        unassign_match = re.match(r'^unassign\s+task\s+#?(\d+)$', content, re.IGNORECASE)
        view_assigned_match = re.match(r'^view\s+assigned(?:\s+tasks)?$', content, re.IGNORECASE)

        if not any([add_match, del_match, complete_match, edit_match, del_all_match, del_completed_match, remind_match, view_match, help_match, set_name_match, set_timezone_match, profile_match, sync_name_match, assign_match, unassign_match, view_assigned_match]):
            return

        # Check role permission (only in guilds)
        if event.guild_id:
            try:
                member = await bot.rest.fetch_member(event.guild_id, event.author_id)
                if REQUIRED_ROLE_ID not in member.role_ids:
                    components = create_task_embed(
                        "❌ Permission Denied",
                        "You don't have permission to use task commands.\n\n"
                        "**Required:**\n"
                        "• You need the **Admin** role to use this feature\n"
                        "• Contact a server administrator for access",
                        DARK_MAGENTA_ACCENT,
                        "This message will delete in 60 seconds"
                    )
                    await send_auto_delete_response(bot, event.channel_id, components)
                    return
            except Exception:
                return

        # Delete the user's command message
        try:
            await bot.rest.delete_message(event.channel_id, event.message_id)
        except Exception:
            pass  # Continue even if deletion fails

        # Process commands
        if add_match:
            description = add_match.group(1).strip()
            task = await add_task(mongo, event.author_id, description)

            if task:
                tasks = await get_user_tasks(mongo, event.author_id)
                await update_task_list_message(bot, mongo, event.author_id, tasks, event.guild_id)

                components = create_task_embed(
                    "✅ Task Added",
                    f"Added task #{task['task_id']}: {task['description']}",
                    GREEN_ACCENT,
                    "This message will delete in 60 seconds"
                )
            else:
                components = create_task_embed(
                    "❌ Task Limit Reached",
                    f"You've reached the maximum of {MAX_TASKS_PER_USER} tasks.\n\n"
                    f"**To make room:**\n"
                    f"• Complete old tasks with `complete task #[id]`\n"
                    f"• Delete tasks with `del task #[id]`\n"
                    f"• Use `view tasks` to see your list",
                    DARK_MAGENTA_ACCENT,
                    "This message will delete in 60 seconds"
                )

            await send_auto_delete_response(bot, event.channel_id, components)

        elif del_match:
            task_id = int(del_match.group(1))

            # Find who owns this task (user or someone who assigned it to them)
            owner_info = await find_task_owner(mongo, event.author_id, task_id)

            if not owner_info:
                components = create_task_embed(
                    "❌ Task Not Found",
                    f"Could not find task #{task_id}.\n\n"
                    f"**Try this:**\n"
                    f"• Use `view tasks` to see your task list\n"
                    f"• Check the task number is correct",
                    DARK_MAGENTA_ACCENT,
                    "This message will delete in 60 seconds"
                )
            else:
                owner_id, task = owner_info
                success, deleted_task = await delete_task(mongo, owner_id, task_id)

                if success:
                    # Update owner's task list
                    owner_tasks = await get_user_tasks(mongo, owner_id)
                    await update_task_list_message(bot, mongo, owner_id, owner_tasks, event.guild_id)

                    # If task was assigned and owner != current user, update current user's list too
                    if deleted_task and deleted_task.get("assigned_to"):
                        assignee_id = int(deleted_task["assigned_to"])
                        if assignee_id != owner_id:
                            assignee_tasks = await get_user_tasks(mongo, assignee_id)
                            await update_task_list_message(bot, mongo, assignee_id, assignee_tasks, event.guild_id)

                    components = create_task_embed(
                        "✅ Task Deleted",
                        f"Task #{task_id} has been deleted.",
                        GREEN_ACCENT,
                        "This message will delete in 60 seconds"
                    )
                else:
                    components = create_task_embed(
                        "❌ Task Not Found",
                        f"Could not find task #{task_id}.\n\n"
                        f"**Try this:**\n"
                        f"• Use `view tasks` to see your task list\n"
                        f"• Check the task number is correct",
                        DARK_MAGENTA_ACCENT,
                        "This message will delete in 60 seconds"
                    )

            await send_auto_delete_response(bot, event.channel_id, components)

        elif complete_match:
            task_id = int(complete_match.group(1))

            # Find who owns this task (user or someone who assigned it to them)
            owner_info = await find_task_owner(mongo, event.author_id, task_id)

            if not owner_info:
                components = create_task_embed(
                    "❌ Task Not Found",
                    f"Could not find task #{task_id}. It may have been deleted.\n\n"
                    f"**Try this:**\n"
                    f"• Use `view tasks` to see active tasks\n"
                    f"• Verify the task number is correct",
                    DARK_MAGENTA_ACCENT,
                    "This message will delete in 60 seconds"
                )
            else:
                owner_id, task = owner_info
                success, completed_task = await complete_task(mongo, owner_id, task_id)

                if success:
                    # Update owner's task list
                    owner_tasks = await get_user_tasks(mongo, owner_id)
                    await update_task_list_message(bot, mongo, owner_id, owner_tasks, event.guild_id)

                    # If task was assigned and owner != current user, update current user's list too
                    if completed_task and completed_task.get("assigned_to"):
                        assignee_id = int(completed_task["assigned_to"])
                        if assignee_id != owner_id:
                            assignee_tasks = await get_user_tasks(mongo, assignee_id)
                            await update_task_list_message(bot, mongo, assignee_id, assignee_tasks, event.guild_id)

                    components = create_task_embed(
                        "✅ Task Completed",
                        f"Task #{task_id} has been marked as complete!",
                        GREEN_ACCENT,
                        "This message will delete in 60 seconds"
                    )
                else:
                    components = create_task_embed(
                        "❌ Task Not Found",
                        f"Could not find task #{task_id}. It may have been deleted.\n\n"
                        f"**Try this:**\n"
                        f"• Use `view tasks` to see active tasks\n"
                        f"• Verify the task number is correct",
                        DARK_MAGENTA_ACCENT,
                        "This message will delete in 60 seconds"
                    )

            await send_auto_delete_response(bot, event.channel_id, components)

        elif edit_match:
            task_id = int(edit_match.group(1))

            # Find who owns this task (user or someone who assigned it to them)
            owner_info = await find_task_owner(mongo, event.author_id, task_id)

            if owner_info:
                owner_id, task = owner_info

                components = create_task_embed(
                    "✏️ Edit Task",
                    f"Please type the new description for task #{task_id}:",
                    BLUE_ACCENT,
                    "This message will delete in 60 seconds or when you respond"
                )

                prompt_message = await send_auto_delete_response(bot, event.channel_id, components)

                edit_sessions[event.author_id] = {
                    "task_id": task_id,
                    "owner_id": owner_id,  # Store owner_id for later use
                    "channel_id": event.channel_id,
                    "timestamp": datetime.utcnow(),
                    "prompt_message_id": prompt_message.id
                }

                async def cleanup_session():
                    await asyncio.sleep(300)
                    if event.author_id in edit_sessions:
                        if edit_sessions[event.author_id]["task_id"] == task_id:
                            del edit_sessions[event.author_id]

                asyncio.create_task(cleanup_session())
            else:
                components = create_task_embed(
                    "❌ Task Not Found",
                    f"Could not find task #{task_id} to edit.\n\n"
                    f"**Try this:**\n"
                    f"• Use `view tasks` to check task numbers\n"
                    f"• Make sure you own this task",
                    DARK_MAGENTA_ACCENT,
                    "This message will delete in 60 seconds"
                )
                await send_auto_delete_response(bot, event.channel_id, components)

        elif del_all_match:
            count, deleted_tasks = await delete_all_tasks(mongo, event.author_id)

            if count > 0:
                tasks = []
                await update_task_list_message(bot, mongo, event.author_id, tasks, event.guild_id)

                # Update all assignees' task lists since their assigned tasks were deleted
                # Get all tasks that were assigned
                assigned_tasks = [t for t in deleted_tasks if t.get("assigned_to")]

                # Collect unique assignee IDs
                assignee_ids = set()
                for task in assigned_tasks:
                    assignee_ids.add(int(task["assigned_to"]))

                # Update each assignee's task list message
                for assignee_id in assignee_ids:
                    assignee_tasks = await get_user_tasks(mongo, assignee_id)
                    await update_task_list_message(bot, mongo, assignee_id, assignee_tasks, event.guild_id)

                components = create_task_embed(
                    "✅ All Tasks Deleted",
                    f"Deleted {count} task{'s' if count != 1 else ''} from your list.",
                    GREEN_ACCENT,
                    "This message will delete in 60 seconds"
                )
            else:
                components = create_task_embed(
                    "ℹ️ No Tasks",
                    "You don't have any tasks to delete.",
                    BLUE_ACCENT,
                    "This message will delete in 60 seconds"
                )

            await send_auto_delete_response(bot, event.channel_id, components)

        elif del_completed_match:
            count, remaining_tasks = await delete_completed_tasks(mongo, event.author_id)

            if count > 0:
                # Update owner's task list with remaining tasks
                await update_task_list_message(bot, mongo, event.author_id, remaining_tasks, event.guild_id)

                # Update all assignees' task lists so they see the new renumbered task IDs
                # Get all tasks assigned by this user
                assigned_tasks = [t for t in remaining_tasks if t.get("assigned_to")]

                # Collect unique assignee IDs
                assignee_ids = set()
                for task in assigned_tasks:
                    assignee_ids.add(int(task["assigned_to"]))

                # Update each assignee's task list message
                for assignee_id in assignee_ids:
                    assignee_tasks = await get_user_tasks(mongo, assignee_id)
                    await update_task_list_message(bot, mongo, assignee_id, assignee_tasks, event.guild_id)

                components = create_task_embed(
                    "✅ Completed Tasks Deleted",
                    f"Deleted {count} completed task{'s' if count != 1 else ''}.\n"
                    f"{len(remaining_tasks)} pending task{'s' if len(remaining_tasks) != 1 else ''} remaining.",
                    GREEN_ACCENT,
                    "This message will delete in 60 seconds"
                )
            else:
                components = create_task_embed(
                    "ℹ️ No Completed Tasks",
                    "You don't have any completed tasks to delete.",
                    BLUE_ACCENT,
                    "This message will delete in 60 seconds"
                )

            await send_auto_delete_response(bot, event.channel_id, components)

        elif view_match:
            tasks = await get_user_tasks(mongo, event.author_id)
            display_name = await get_user_display_name(mongo, bot, event.author_id, event.guild_id)

            # Get tasks assigned TO this user
            assigned_to_me = await get_assigned_tasks(mongo, event.author_id)

            all_components = []

            # SECTION 1: My Tasks (owned tasks)
            if tasks:
                # Build assignment info for owned tasks that are assigned
                assignment_info = {}
                for task in tasks:
                    if task.get("assigned_to"):
                        assignee_id = int(task["assigned_to"])
                        assignee_name = await get_user_display_name(mongo, bot, assignee_id, event.guild_id)
                        assignment_info[task["task_id"]] = f"→ `{assignee_name}`"

                task_content = format_task_list(tasks, assignment_info)
                completed_count = sum(1 for t in tasks if t['completed'])

                all_components.append(
                    Container(
                        accent_color=MAGENTA_ACCENT,
                        components=[
                            Text(content=f"# {display_name}'s Tasks"),
                            Text(content="## 📝 My Tasks"),
                            Separator(divider=True),
                            Text(content=task_content),
                            Separator(divider=True),
                            Text(content=f"-# {len(tasks)} total • {completed_count} completed"),
                        ]
                    )
                )

            # SECTION 2: Assigned to Me
            if assigned_to_me:
                # Build assignment info showing who assigned each task
                assignment_info = {}
                for task in assigned_to_me:
                    assigner_id = int(task.get("assigned_by", task.get("owner_id")))
                    assigner_name = await get_user_display_name(mongo, bot, assigner_id, event.guild_id)
                    assignment_info[task["task_id"]] = f"← `{assigner_name}`"

                assigned_content = format_task_list(assigned_to_me, assignment_info)
                assigned_completed = sum(1 for t in assigned_to_me if t['completed'])

                # If no owned tasks, add user name header
                section_components = []
                if not tasks:
                    section_components.append(Text(content=f"# {display_name}'s Tasks"))

                section_components.extend([
                    Text(content="## 📥 Assigned to Me"),
                    Separator(divider=True),
                    Text(content=assigned_content),
                    Separator(divider=True),
                    Text(content=f"-# {len(assigned_to_me)} total • {assigned_completed} completed"),
                ])

                all_components.append(
                    Container(
                        accent_color=BLUE_ACCENT,
                        components=section_components
                    )
                )

            # Add footer and auto-delete notice
            if all_components:
                all_components[-1].components.append(
                    Text(content=f"-# This message will delete in {AUTO_DELETE_DELAY} seconds")
                )
                all_components[-1].components.append(
                    Media(items=[MediaItem(media="assets/Purple_Footer.png")])
                )
            else:
                # No tasks at all
                all_components = [
                    Container(
                        accent_color=MAGENTA_ACCENT,
                        components=[
                            Text(content=f"# {display_name}'s Tasks"),
                            Separator(divider=True),
                            Text(content="_No tasks in your list._"),
                            Text(content=f"-# This message will delete in {AUTO_DELETE_DELAY} seconds"),
                            Media(items=[MediaItem(media="assets/Purple_Footer.png")]),
                        ]
                    )
                ]

            await send_auto_delete_response(bot, event.channel_id, all_components)

        elif help_match:
            help_text = (
                "**Available Task Commands:**\n\n"
                "`add task [description]` - Add a new task to your list\n"
                "`view tasks` - View your current tasks (auto-deletes after 60s)\n"
                "`complete task #[id]` - Mark a task as complete\n"
                "`edit task #[id]` - Edit a task's description\n"
                "`del task #[id]` - Delete a specific task\n"
                "`del all tasks` - Delete all your tasks\n"
                "`del completed tasks` - Delete all completed tasks\n"
                "`remind task #[id] [time]` - Set a reminder for a task\n"
                "`help tasks` - Show this help message\n\n"
                "**Task Assignment:**\n"
                "`assign task #[id] @user` - Assign a task to someone\n"
                "`assign task #[id] @user with note [text]` - Assign with a note\n"
                "`unassign task #[id]` - Remove task assignment\n"
                "`view assigned` - View tasks assigned to you\n\n"
                "**Personal Settings:**\n"
                "`tasks set name [name]` - Set your display name for task lists\n"
                "`tasks set timezone [zone]` - Set your timezone (e.g., America/New_York)\n"
                "`tasks sync name` - Sync display name from server nickname\n"
                "`tasks profile` - View your current settings\n\n"
                "**Time Examples for Reminders:**\n"
                "• `5m`, `1h`, `2d` - Relative times\n"
                "• `3:30pm`, `tomorrow at 2pm` - Absolute times\n"
                "• `Dec 25 at 9am` - Specific dates\n\n"
                "**Your tasks automatically sync to the task channel.**"
            )

            components = create_task_embed(
                "📋 Task Commands Help",
                help_text,
                BLUE_ACCENT,
                "This message will delete in 60 seconds"
            )

            await send_auto_delete_response(bot, event.channel_id, components)

        elif remind_match:
            task_id = int(remind_match.group(1))
            time_str = remind_match.group(2).strip()

            reminder_time = parse_reminder_time(time_str)

            if not reminder_time:
                components = create_task_embed(
                    "❌ Invalid Time Format",
                    "I couldn't understand that time. Try:\n"
                    "• Relative: `5m`, `1h`, `2d`\n"
                    "• Absolute: `3:30pm`, `tomorrow at 2pm`\n"
                    "• Date: `Dec 25 at 9am`",
                    DARK_MAGENTA_ACCENT,
                    "This message will delete in 60 seconds"
                )
                await send_auto_delete_response(bot, event.channel_id, components)
                return

            tasks = await get_user_tasks(mongo, event.author_id)
            task_exists = any(t["task_id"] == task_id for t in tasks)

            if not task_exists:
                components = create_task_embed(
                    "❌ Task Not Found",
                    f"Could not find task #{task_id} to set reminder.\n\n"
                    f"**Try this:**\n"
                    f"• Use `view tasks` to see your task list\n"
                    f"• Check the task number is correct",
                    DARK_MAGENTA_ACCENT,
                    "This message will delete in 60 seconds"
                )
                await send_auto_delete_response(bot, event.channel_id, components)
                return

            # Get user's timezone
            user_timezone = await get_user_timezone(mongo, bot, event.author_id, event.guild_id)

            success = await create_reminder(
                mongo, bot, event.author_id, task_id,
                reminder_time, user_timezone
            )

            if success:
                # Convert to Unix timestamp for Discord formatting
                unix_timestamp = int(reminder_time.timestamp())

                # Discord timestamp formats:
                # <t:TIMESTAMP:f> = Full date/time (displays in user's timezone)
                # <t:TIMESTAMP:R> = Relative time (e.g., "in 2 hours")
                components = create_task_embed(
                    "⏰ Reminder Set",
                    f"I'll remind you about task #{task_id} <t:{unix_timestamp}:f> (<t:{unix_timestamp}:R>)!",
                    GREEN_ACCENT,
                    "This message will delete in 60 seconds"
                )
            else:
                components = create_task_embed(
                    "❌ Reminder Failed",
                    "Could not create the reminder. Please try again.",
                    DARK_MAGENTA_ACCENT,
                    "This message will delete in 60 seconds"
                )

            await send_auto_delete_response(bot, event.channel_id, components)

        elif set_name_match:
            new_name = set_name_match.group(1).strip()[:50]  # Limit to 50 characters

            # Update user profile
            await mongo.user_profiles.update_one(
                {"user_id": str(event.author_id)},
                {
                    "$set": {"display_name": new_name}
                },
                upsert=True
            )

            # Update task list message with new name
            tasks = await get_user_tasks(mongo, event.author_id)
            await update_task_list_message(bot, mongo, event.author_id, tasks, event.guild_id)

            components = create_task_embed(
                "✅ Display Name Updated",
                f"Your display name has been set to: **{new_name}**",
                GREEN_ACCENT,
                "This message will delete in 60 seconds"
            )

            await send_auto_delete_response(bot, event.channel_id, components)

        elif set_timezone_match:
            timezone_str = set_timezone_match.group(1).strip()

            # Validate timezone
            try:
                pendulum.timezone(timezone_str)
                valid = True
            except:
                valid = False

            if valid:
                # Update user profile
                await mongo.user_profiles.update_one(
                    {"user_id": str(event.author_id)},
                    {
                        "$set": {"timezone": timezone_str}
                    },
                    upsert=True
                )

                components = create_task_embed(
                    "✅ Timezone Updated",
                    f"Your timezone has been set to: **{timezone_str}**\n\nThis will be used for all your reminders.",
                    GREEN_ACCENT,
                    "This message will delete in 60 seconds"
                )
            else:
                components = create_task_embed(
                    "❌ Invalid Timezone",
                    f"Could not recognize timezone: **{timezone_str}**\n\n"
                    "Common examples:\n"
                    "• `America/New_York`\n"
                    "• `America/Los_Angeles`\n"
                    "• `America/Chicago`\n"
                    "• `Europe/London`\n"
                    "• `UTC`",
                    DARK_MAGENTA_ACCENT,
                    "This message will delete in 60 seconds"
                )

            await send_auto_delete_response(bot, event.channel_id, components)

        elif profile_match:
            profile = await get_or_create_user_profile(mongo, bot, event.author_id, event.guild_id)

            display_name = profile.get("display_name", "User")
            timezone = profile.get("timezone", DEFAULT_TIMEZONE)

            components = [
                Container(
                    accent_color=BLUE_ACCENT,
                    components=[
                        Text(content="## 👤 Your Task Profile"),
                        Separator(divider=True),
                        Text(content=f"**Display Name:** {display_name}"),
                        Text(content=f"**Timezone:** {timezone}"),
                        Separator(divider=True),
                        Text(content="**Change Settings:**\n"
                                     "`tasks set name [name]` - Update display name\n"
                                     "`tasks set timezone [zone]` - Update timezone\n"
                                     "`tasks sync name` - Sync name from server nickname"),
                        Text(content="-# This message will delete in 60 seconds"),
                        Media(items=[MediaItem(media="assets/Blue_Footer.png")]),
                    ]
                )
            ]

            await send_auto_delete_response(bot, event.channel_id, components)

        elif sync_name_match:
            # Sync display name from server nickname
            if event.guild_id:
                try:
                    member = await bot.rest.fetch_member(event.guild_id, event.author_id)
                    new_name = member.nickname if member.nickname else member.username

                    # Update user profile
                    await mongo.user_profiles.update_one(
                        {"user_id": str(event.author_id)},
                        {
                            "$set": {"display_name": new_name}
                        },
                        upsert=True
                    )

                    # Update task list message with new name
                    tasks = await get_user_tasks(mongo, event.author_id)
                    await update_task_list_message(bot, mongo, event.author_id, tasks, event.guild_id)

                    components = create_task_embed(
                        "✅ Display Name Synced",
                        f"Your display name has been synced to: **{new_name}**",
                        GREEN_ACCENT,
                        "This message will delete in 60 seconds"
                    )
                except Exception as e:
                    components = create_task_embed(
                        "❌ Sync Failed",
                        f"Could not sync display name from server: {str(e)}",
                        DARK_MAGENTA_ACCENT,
                        "This message will delete in 60 seconds"
                    )
            else:
                components = create_task_embed(
                    "❌ Not in Server",
                    "This command must be used in a server, not in DMs.",
                    DARK_MAGENTA_ACCENT,
                    "This message will delete in 60 seconds"
                )

            await send_auto_delete_response(bot, event.channel_id, components)

        elif assign_match:
            task_id = int(assign_match.group(1))
            assignee_id = int(assign_match.group(2))
            assignment_note = assign_match.group(3).strip() if assign_match.group(3) else None

            # Assign the task
            success, message, assigned_task = await assign_task(
                mongo, bot, event.author_id, task_id, assignee_id,
                assignment_note, event.guild_id
            )

            if success:
                # Get assignee display name
                assignee_name = await get_user_display_name(mongo, bot, assignee_id, event.guild_id)

                # Update owner's task list
                owner_tasks = await get_user_tasks(mongo, event.author_id)
                await update_task_list_message(bot, mongo, event.author_id, owner_tasks, event.guild_id)

                # Update assignee's task list
                assignee_tasks = await get_user_tasks(mongo, assignee_id)
                await update_task_list_message(bot, mongo, assignee_id, assignee_tasks, event.guild_id)

                # Send DM notification to assignee (fixed parameter order and pass task dict)
                await send_assignment_dm(
                    bot, mongo, assignee_id, event.author_id,
                    assigned_task, assignment_note, event.guild_id
                )

                components = create_task_embed(
                    "✅ Task Assigned",
                    f"Task #{task_id} has been assigned to **{assignee_name}**!",
                    GREEN_ACCENT,
                    "This message will delete in 60 seconds"
                )
            else:
                components = create_task_embed(
                    "❌ Assignment Failed",
                    message,
                    DARK_MAGENTA_ACCENT,
                    "This message will delete in 60 seconds"
                )

            await send_auto_delete_response(bot, event.channel_id, components)

        elif unassign_match:
            task_id = int(unassign_match.group(1))

            # Unassign the task
            success, message = await unassign_task(mongo, bot, event.author_id, task_id, event.guild_id)

            if success:
                # Update owner's task list
                owner_tasks = await get_user_tasks(mongo, event.author_id)
                await update_task_list_message(bot, mongo, event.author_id, owner_tasks, event.guild_id)

                # Note: We don't update assignee's list here because unassign_task already does it

                components = create_task_embed(
                    "✅ Task Unassigned",
                    f"Task #{task_id} has been unassigned.",
                    GREEN_ACCENT,
                    "This message will delete in 60 seconds"
                )
            else:
                components = create_task_embed(
                    "❌ Unassign Failed",
                    message,
                    DARK_MAGENTA_ACCENT,
                    "This message will delete in 60 seconds"
                )

            await send_auto_delete_response(bot, event.channel_id, components)

        elif view_assigned_match:
            # Get tasks assigned TO the user
            assigned_tasks = await get_assigned_tasks(mongo, event.author_id)

            if assigned_tasks:
                # Build formatted list with assigner names
                formatted_lines = []
                for task_data in assigned_tasks:
                    task = task_data["task"]
                    assigner_name = task_data["assigner_name"]
                    task_id = task["task_id"]
                    description = task["description"]

                    if task.get("completed", False):
                        formatted_lines.append(f"`{task_id}` • ✅ ~~{description}~~ ← from {assigner_name}")
                    else:
                        formatted_lines.append(f"`{task_id}` • {description} ← from {assigner_name}")

                task_list_text = "\n".join(formatted_lines)

                components = [
                    Container(
                        accent_color=BLUE_ACCENT,
                        components=[
                            Text(content="## 📥 Tasks Assigned to You"),
                            Separator(divider=True),
                            Text(content=task_list_text),
                            Text(content="-# This message will delete in 60 seconds"),
                            Media(items=[MediaItem(media="assets/Blue_Footer.png")]),
                        ]
                    )
                ]
            else:
                components = create_task_embed(
                    "📥 No Assigned Tasks",
                    "You don't have any tasks assigned to you.",
                    BLUE_ACCENT,
                    "This message will delete in 60 seconds"
                )

            await send_auto_delete_response(bot, event.channel_id, components)

    except Exception:
        pass


@register_action("complete_from_reminder", no_return=True)
@lightbulb.di.with_di
async def handle_complete_from_reminder(
        ctx,
        action_id: str,
        bot: hikari.GatewayBot = lightbulb.di.INJECTED,
        mongo: MongoClient = lightbulb.di.INJECTED,
        **kwargs
) -> None:
    """Handle complete task button from reminder DM."""
    try:
        # Parse action_id: user_id_task_id
        parts = action_id.split("_")
        if len(parts) != 2:
            return

        user_id = int(parts[0])
        task_id = int(parts[1])

        # Verify this is the correct user
        if ctx.user.id != user_id:
            await ctx.respond(
                components=[
                    Container(
                        accent_color=DARK_MAGENTA_ACCENT,
                        components=[
                            Text(content="❌ This reminder is not for you!")
                        ]
                    )
                ],
                edit=True
            )
            return

        # Mark task as complete
        success, completed_task = await complete_task(mongo, user_id, task_id)

        if success:
            # Update owner's task list message
            tasks = await get_user_tasks(mongo, user_id)
            await update_task_list_message(bot, mongo, user_id, tasks)

            # If task was assigned to someone, update their task list too
            if completed_task and completed_task.get("assigned_to"):
                assignee_id = int(completed_task["assigned_to"])
                assignee_tasks = await get_user_tasks(mongo, assignee_id)
                await update_task_list_message(bot, mongo, assignee_id, assignee_tasks)

            # Update the reminder message
            await ctx.respond(
                components=[
                    Container(
                        accent_color=GREEN_ACCENT,
                        components=[
                            Text(content="## ✅ Task Completed!"),
                            Separator(divider=True),
                            Text(content=f"Task #{task_id} has been marked as complete."),
                            Text(content="Great job! 🎉")
                        ]
                    )
                ],
                edit=True
            )
        else:
            await ctx.respond(
                components=[
                    Container(
                        accent_color=DARK_MAGENTA_ACCENT,
                        components=[
                            Text(content="## ❌ Task Not Found"),
                            Text(content="This task may have already been completed or deleted.")
                        ]
                    )
                ],
                edit=True
            )

    except Exception as e:
        try:
            await ctx.respond(
                components=[
                    Container(
                        accent_color=DARK_MAGENTA_ACCENT,
                        components=[
                            Text(content="❌ An error occurred processing your request.")
                        ]
                    )
                ],
                edit=True
            )
        except:
            pass


@register_action("snooze_reminder", no_return=True)
@lightbulb.di.with_di
async def handle_snooze_reminder(
        ctx,
        action_id: str,
        bot: hikari.GatewayBot = lightbulb.di.INJECTED,
        mongo: MongoClient = lightbulb.di.INJECTED,
        **kwargs
) -> None:
    """Handle snooze reminder button from reminder DM."""
    try:
        # Parse action_id: user_id_task_id_duration
        parts = action_id.split("_")
        if len(parts) != 3:
            return

        user_id = int(parts[0])
        task_id = int(parts[1])
        duration = parts[2]  # e.g., "1h"

        # Verify this is the correct user
        if ctx.user.id != user_id:
            await ctx.respond(
                components=[
                    Container(
                        accent_color=DARK_MAGENTA_ACCENT,
                        components=[
                            Text(content="❌ This reminder is not for you!")
                        ]
                    )
                ],
                edit=True
            )
            return

        # Parse snooze duration and create new reminder
        snooze_time = parse_reminder_time(duration)
        if not snooze_time:
            await ctx.respond(
                components=[
                    Container(
                        accent_color=DARK_MAGENTA_ACCENT,
                        components=[
                            Text(content="❌ Invalid snooze duration")
                        ]
                    )
                ],
                edit=True
            )
            return

        # Get user's timezone
        user_timezone = await get_user_timezone(mongo, bot, user_id)

        # Create new reminder
        success = await create_reminder(
            mongo, bot, user_id, task_id,
            snooze_time, user_timezone
        )

        if success:
            # Format snooze time for display
            now = pendulum.now(DEFAULT_TIMEZONE)
            if snooze_time.date() == now.date():
                formatted_time = snooze_time.format("h:mm A")
                time_desc = f"today at {formatted_time}"
            elif snooze_time.date() == now.add(days=1).date():
                formatted_time = snooze_time.format("h:mm A")
                time_desc = f"tomorrow at {formatted_time}"
            else:
                time_desc = snooze_time.format("MMM D [at] h:mm A")

            # Update the reminder message
            await ctx.respond(
                components=[
                    Container(
                        accent_color=BLUE_ACCENT,
                        components=[
                            Text(content="## ⏰ Reminder Snoozed"),
                            Separator(divider=True),
                            Text(content=f"I'll remind you about task #{task_id} {time_desc}."),
                            Text(content="💤 Sleep tight!")
                        ]
                    )
                ],
                edit=True
            )
        else:
            await ctx.respond(
                components=[
                    Container(
                        accent_color=DARK_MAGENTA_ACCENT,
                        components=[
                            Text(content="## ❌ Snooze Failed"),
                            Text(content="Could not create new reminder. The task may no longer exist.")
                        ]
                    )
                ],
                edit=True
            )

    except Exception as e:
        try:
            await ctx.respond(
                components=[
                    Container(
                        accent_color=DARK_MAGENTA_ACCENT,
                        components=[
                            Text(content="❌ An error occurred processing your request.")
                        ]
                    )
                ],
                edit=True
            )
        except:
            pass


@register_action("dismiss_channel_reminder", no_return=True)
@lightbulb.di.with_di
async def handle_dismiss_channel_reminder(
        ctx,
        bot: hikari.GatewayBot = lightbulb.di.INJECTED,
        **kwargs
) -> None:
    """Handle dismiss button - delete the channel reminder message."""
    try:
        await bot.rest.delete_message(ctx.channel_id, ctx.interaction.message.id)
    except Exception as e:
        print(f"[Task Manager] Failed to dismiss channel reminder: {e}")
        import traceback
        traceback.print_exc()


@loader.listener(hikari.StoppingEvent)
async def cleanup_tasks(event: hikari.StoppingEvent) -> None:
    """Cancel all pending delete tasks and shutdown scheduler on bot shutdown."""
    for task in delete_tasks.values():
        task.cancel()
    delete_tasks.clear()
    edit_sessions.clear()

    scheduler.shutdown()