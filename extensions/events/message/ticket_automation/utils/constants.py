# extensions/events/message/ticket_automation/utils/constants.py
"""
Constants for ticket automation system.
"""

from utils.emoji import emojis

# Role and Channel IDs
RECRUITMENT_STAFF_ROLE = 999140213953671188
LOG_CHANNEL_ID = 1436169870273413169

# Timing Constants (in seconds)
REMINDER_DELETE_TIMEOUT = 15  # Seconds before auto-deleting reminder messages
REMINDER_TIMEOUT = 30  # Seconds before allowing another reminder to be sent
TIMEZONE_CONFIRMATION_TIMEOUT = 60  # Seconds to wait for Friend Time bot confirmation

# Friend Time Bot Configuration
FRIEND_TIME_BOT_ID = 481439443015942166
FRIEND_TIME_SET_COMMAND_ID = 924862149292085268
