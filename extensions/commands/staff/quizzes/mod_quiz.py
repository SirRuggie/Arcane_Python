"""
Staff Moderation Quiz - Interactive quiz to ensure staff understand moderation guidelines
"""

import lightbulb
import hikari
import uuid
from datetime import datetime, timezone

from hikari.impl import (
    MessageActionRowBuilder as ActionRow,
    ContainerComponentBuilder as Container,
    SectionComponentBuilder as Section,
    InteractiveButtonBuilder as Button,
    TextDisplayComponentBuilder as Text,
    SeparatorComponentBuilder as Separator,
    MediaGalleryComponentBuilder as Media,
    MediaGalleryItemBuilder as MediaItem,
)

from extensions.commands.staff import staff
from utils.constants import GOLD_ACCENT, GREEN_ACCENT, DARK_MAGENTA_ACCENT
from utils.mongo import MongoClient
from extensions.components import register_action

# Authorized role IDs that can run this quiz
AUTHORIZED_ROLES = [
    1345174718944383027, #Family Lead
    1345184544822657095,  # Discord Chairman
    1345189412291477575 # Discord Manager
]

# Standard Mode Quiz Questions (15 questions)
QUIZ_QUESTIONS = [
    # Staff Commands (2 questions)
    {
        "category": "Staff Commands",
        "question": "What command shows a user's list of warnings?",
        "options": {
            "A": "/warnings",
            "B": "/check-warns",
            "C": "/warns",
            "D": "/view-warnings"
        },
        "correct": "C"
    },
    {
        "category": "Staff Commands",
        "question": "What command do you use to issue a formal warning to a user?",
        "options": {
            "A": "/warning",
            "B": "/strike",
            "C": "/warn",
            "D": "/punish"
        },
        "correct": "C"
    },

    # VSTKB Approach (3 questions)
    {
        "category": "VSTKB Approach",
        "question": "What is the FIRST step in the VSTKB moderation approach?",
        "options": {
            "A": "Strike with /warn command",
            "B": "Verbal Warning",
            "C": "Timeout",
            "D": "Ban"
        },
        "correct": "B"
    },
    {
        "category": "VSTKB Approach",
        "question": "What does the 'B' in VSTKB stand for?",
        "options": {
            "A": "Block",
            "B": "Ban",
            "C": "Banish",
            "D": "Blacklist"
        },
        "correct": "B"
    },
    {
        "category": "VSTKB Approach",
        "question": "Which of these warrants skipping VSTKB and going straight to an immediate ban?",
        "options": {
            "A": "Excessive emoji spam",
            "B": "Speaking a foreign language",
            "C": "Blatantly racist or homophobic language",
            "D": "CAPS lock abuse"
        },
        "correct": "C"
    },

    # Server Rules Enforcement (4 questions)
    {
        "category": "Server Rules",
        "question": "What is Rule 1 about?",
        "options": {
            "A": "Spamming and Trolling",
            "B": "Unsolicited Advertising",
            "C": "Bullying and Harassment",
            "D": "English Only"
        },
        "correct": "B"
    },
    {
        "category": "Server Rules",
        "question": "Rule 3 (Bullying and Harassment) has a zero-tolerance policy. What action should be taken?",
        "options": {
            "A": "Give verbal warning first",
            "B": "Use /warn command",
            "C": "Quarantine user immediately with w!q and report in mod evidence",
            "D": "Timeout for 24 hours"
        },
        "correct": "C"
    },
    {
        "category": "Server Rules",
        "question": "What is Rule 5 about?",
        "options": {
            "A": "No mini-modding",
            "B": "English Only",
            "C": "Appropriate Topics",
            "D": "No impersonation"
        },
        "correct": "B"
    },
    {
        "category": "Server Rules",
        "question": "If a user speaks a foreign language, what should you do FIRST?",
        "options": {
            "A": "Use /warn command immediately",
            "B": "Quarantine them with w!q",
            "C": "Give a verbal warning and request they speak English",
            "D": "Timeout them for 10 minutes"
        },
        "correct": "C"
    },

    # Staff Hierarchy (2 questions)
    {
        "category": "Staff Hierarchy",
        "question": "Who has FINAL authority on Discord moderation issues?",
        "options": {
            "A": "Discord Manager",
            "B": "Moderator",
            "C": "Discord Chairman",
            "D": "Family Lead"
        },
        "correct": "C"
    },
    {
        "category": "Staff Hierarchy",
        "question": "What should you do if you are uncertain about how to handle a situation?",
        "options": {
            "A": "Make your best guess and act quickly",
            "B": "Seek advice from upper staff",
            "C": "Ask other moderators in general chat",
            "D": "Let someone else handle it"
        },
        "correct": "B"
    },

    # Staff Expectations & Guidelines (2 questions)
    {
        "category": "Staff Expectations",
        "question": "Where must ALL infractions be documented, no matter how small?",
        "options": {
            "A": "<#1110520243622772786>",
            "B": "<#1071490639679721472>",
            "C": "<#1058568239526977566>",
            "D": "Direct message to leadership"
        },
        "correct": "C"
    },
    {
        "category": "Staff Expectations",
        "question": "What should staff do before being away for an extended period?",
        "options": {
            "A": "Nothing, just leave",
            "B": "Post in general chat",
            "C": "Inform their department Chairman",
            "D": "Submit a formal written request"
        },
        "correct": "C"
    },

    # Staff Warning System (2 questions)
    {
        "category": "Staff Warning System",
        "question": "What happens if a staff member receives Warning 2?",
        "options": {
            "A": "Just a normal warning, no action",
            "B": "Temporarily suspended from staff team with roles removed for X days",
            "C": "Demoted one rank below current position",
            "D": "Immediately removed from staff team"
        },
        "correct": "B"
    },
    {
        "category": "Staff Warning System",
        "question": "If you use Wick improperly, what happens?",
        "options": {
            "A": "Nothing, it's just a reminder",
            "B": "Verbal warning from leadership",
            "C": "You receive a staff warning",
            "D": "You lose moderator permissions"
        },
        "correct": "C"
    },
]

# Hard Mode Quiz Questions (50 questions)
HARD_MODE_QUESTIONS = [
    # High Court Structure (7 questions)
    {
        "category": "High Court Structure",
        "question": "Which role is the ultimate authority in Kings Alliance?",
        "options": {
            "A": "Family Lead",
            "B": "Owner",
            "C": "Hand of the King",
            "D": "High Steward"
        },
        "correct": "B"
    },
    {
        "category": "High Court Structure",
        "question": "Who leads and manages the Clans and Community?",
        "options": {
            "A": "Owner",
            "B": "High Steward",
            "C": "Family Lead",
            "D": "Discord Chairman"
        },
        "correct": "C"
    },
    {
        "category": "High Court Structure",
        "question": "What is the role of the Hand of the King?",
        "options": {
            "A": "Manages Discord moderation",
            "B": "Chief advisor and second-in-command to the Family Lead",
            "C": "Oversees recruitment",
            "D": "Handles community events"
        },
        "correct": "B"
    },
    {
        "category": "High Court Structure",
        "question": "What is required to remove a High Court member (e.g., a Chairman)?",
        "options": {
            "A": "Majority vote from all staff",
            "B": "Owner decision only",
            "C": "Unanimous vote from Owner, Family Lead, Hand of the King, and High Steward",
            "D": "Two-thirds vote from High Court"
        },
        "correct": "C"
    },
    {
        "category": "High Court Structure",
        "question": "Which Chairman oversees Discord moderation and server structure?",
        "options": {
            "A": "Community Chairman",
            "B": "Development Chairman",
            "C": "Discord Chairman",
            "D": "Recruitment Chairman"
        },
        "correct": "C"
    },
    {
        "category": "High Court Structure",
        "question": "What is the purpose of the Legacy Council?",
        "options": {
            "A": "Active management of all sections",
            "B": "Former top-level leaders who provide advice and feedback",
            "C": "Training new staff members",
            "D": "Handling disciplinary actions"
        },
        "correct": "B"
    },
    {
        "category": "High Court Structure",
        "question": "Can a Chairman be overruled on decisions within their own section?",
        "options": {
            "A": "Yes, by any High Court member",
            "B": "Yes, by majority vote of staff",
            "C": "No, the Chairman has FINAL SAY in their domain",
            "D": "Only by the Owner"
        },
        "correct": "C"
    },

    # Round Table Composition (5 questions)
    {
        "category": "Round Table",
        "question": "Which of these is a core member of the Round Table?",
        "options": {
            "A": "Trial Moderator",
            "B": "Discord Manager",
            "C": "Legacy Council Member",
            "D": "Owner"
        },
        "correct": "B"
    },
    {
        "category": "Round Table",
        "question": "Who represents clans in the Round Table?",
        "options": {
            "A": "Only Clan Leaders",
            "B": "Recruitment Staff",
            "C": "Clan Leaders and their nominated Second-in-Command",
            "D": "Community Staff"
        },
        "correct": "C"
    },
    {
        "category": "Round Table",
        "question": "Which staff role is part of the Round Table?",
        "options": {
            "A": "All Moderators",
            "B": "Trial Moderators only",
            "C": "Only Discord Chairman",
            "D": "Recruitment Staff"
        },
        "correct": "D"
    },
    {
        "category": "Round Table",
        "question": "What is the Recruitment Lead's role in the Round Table?",
        "options": {
            "A": "Observer only",
            "B": "Oversees recruitment efforts and recruitment staff",
            "C": "Handles community events",
            "D": "Manages Discord structure"
        },
        "correct": "B"
    },
    {
        "category": "Round Table",
        "question": "Which future role will oversee esports operations when activated?",
        "options": {
            "A": "Development Chairman",
            "B": "Community Manager",
            "C": "Esports Manager",
            "D": "Recruitment Manager"
        },
        "correct": "C"
    },

    # Staff Commands & Procedures (7 questions)
    {
        "category": "Commands & Procedures",
        "question": "What command should you use to put a user in time-out?",
        "options": {
            "A": "/timeout",
            "B": "/mute",
            "C": "/silence",
            "D": "/quiet"
        },
        "correct": "B"
    },
    {
        "category": "Commands & Procedures",
        "question": "Before using Wick for serious disruptions, what should you do first?",
        "options": {
            "A": "Use Wick immediately",
            "B": "Consider verbal warning and /warn command first",
            "C": "Ban the user",
            "D": "Timeout for 24 hours"
        },
        "correct": "B"
    },
    {
        "category": "Commands & Procedures",
        "question": "If you use Wick improperly, what happens?",
        "options": {
            "A": "Nothing, it's just a warning",
            "B": "You receive a verbal warning",
            "C": "You receive a staff warning",
            "D": "You lose moderator permissions"
        },
        "correct": "C"
    },
    {
        "category": "Commands & Procedures",
        "question": "What command shows a user's list of warnings?",
        "options": {
            "A": "/warnings",
            "B": "/check-warns",
            "C": "/warns",
            "D": "/view-warnings"
        },
        "correct": "C"
    },
    {
        "category": "Commands & Procedures",
        "question": "When quarantining a user with w!q, what MUST you do to make it valid?",
        "options": {
            "A": "Report it in #mod-evidence immediately",
            "B": "DM the Discord Chairman",
            "C": "Post in general staff chat",
            "D": "Wait 24 hours before reporting"
        },
        "correct": "A"
    },
    {
        "category": "Commands & Procedures",
        "question": "What should you check before banning someone?",
        "options": {
            "A": "Their join date",
            "B": "The No Ban List",
            "C": "Their message history",
            "D": "Other staff opinions"
        },
        "correct": "B"
    },
    {
        "category": "Commands & Procedures",
        "question": "Which command is used to let a banned user back into the server?",
        "options": {
            "A": "/unban",
            "B": "/removeban",
            "C": "/pardon",
            "D": "/restore"
        },
        "correct": "A"
    },

    # Complex VSTKB Scenarios (8 questions)
    {
        "category": "VSTKB Scenarios",
        "question": "A user is spamming emojis. Wick deletes the messages. The user continues. What's your next step?",
        "options": {
            "A": "Immediately use /warn",
            "B": "Give a verbal warning",
            "C": "Timeout for 10 minutes",
            "D": "Use /kick"
        },
        "correct": "B"
    },
    {
        "category": "VSTKB Scenarios",
        "question": "You gave a user a verbal warning for spam. They ignore it and continue. What do you do?",
        "options": {
            "A": "Give another verbal warning",
            "B": "Use /warn command and provide evidence in #mod-evidence",
            "C": "Timeout immediately",
            "D": "Kick them"
        },
        "correct": "B"
    },
    {
        "category": "VSTKB Scenarios",
        "question": "A user has 2 prior warnings for spam. They spam again. Following VSTKB, what's next?",
        "options": {
            "A": "Another verbal warning",
            "B": "Another /warn",
            "C": "Timeout",
            "D": "Kick"
        },
        "correct": "C"
    },
    {
        "category": "VSTKB Scenarios",
        "question": "A new user posts a Discord server link. Bots delete it. What should you do?",
        "options": {
            "A": "Ban them immediately",
            "B": "Delete the link (if not deleted) and give verbal warning",
            "C": "Use /warn immediately",
            "D": "Ignore it since bots handled it"
        },
        "correct": "B"
    },
    {
        "category": "VSTKB Scenarios",
        "question": "A user posts 'kys' (kill yourself). What action do you take?",
        "options": {
            "A": "Verbal warning",
            "B": "/warn command",
            "C": "Timeout",
            "D": "Immediate ban (promotion of self-harm)"
        },
        "correct": "D"
    },
    {
        "category": "VSTKB Scenarios",
        "question": "A user posts a mildly suggestive joke (not explicit). They have no prior warnings. What do you do?",
        "options": {
            "A": "Ignore it",
            "B": "Verbal warning and delete the message",
            "C": "Immediate ban",
            "D": "Quarantine with w!q"
        },
        "correct": "B"
    },
    {
        "category": "VSTKB Scenarios",
        "question": "A user is arguing with another member, using mild profanity. No slurs. What's the appropriate response?",
        "options": {
            "A": "Immediate quarantine",
            "B": "Verbal warning to both to de-escalate",
            "C": "Ban both users",
            "D": "Let them work it out"
        },
        "correct": "B"
    },
    {
        "category": "VSTKB Scenarios",
        "question": "A respected veteran member makes a borderline inappropriate comment. How should you handle it compared to a new member?",
        "options": {
            "A": "Give them a pass since they're a veteran",
            "B": "Apply the same rules - verbal warning",
            "C": "Ban them for setting a bad example",
            "D": "Ignore it completely"
        },
        "correct": "B"
    },

    # Grading System Application (8 questions)
    {
        "category": "Grading System",
        "question": "A user posts sexual topics (not explicit). What grade applies?",
        "options": {
            "A": "Grade 1",
            "B": "Grade 2",
            "C": "Grade 3",
            "D": "Immediate ban"
        },
        "correct": "A"
    },
    {
        "category": "Grading System",
        "question": "What is the enforcement action for Grade 1?",
        "options": {
            "A": "Formal warning with /warn",
            "B": "Quarantine with w!q",
            "C": "Take photo evidence, post in #mod-evidence, give verbal warning",
            "D": "Immediate ban"
        },
        "correct": "C"
    },
    {
        "category": "Grading System",
        "question": "A user posts a suggestive video. What grade applies?",
        "options": {
            "A": "Grade 1",
            "B": "Grade 2",
            "C": "Grade 3",
            "D": "No action needed"
        },
        "correct": "B"
    },
    {
        "category": "Grading System",
        "question": "What is the enforcement action for Grade 2?",
        "options": {
            "A": "Verbal warning only",
            "B": "Take evidence, post in #mod-evidence, use /warn command",
            "C": "Quarantine and ping leadership",
            "D": "Immediate timeout"
        },
        "correct": "B"
    },
    {
        "category": "Grading System",
        "question": "A user posts rape-related content. What grade applies?",
        "options": {
            "A": "Grade 1",
            "B": "Grade 2",
            "C": "Grade 3",
            "D": "Grade 4"
        },
        "correct": "C"
    },
    {
        "category": "Grading System",
        "question": "What is the enforcement action for Grade 3?",
        "options": {
            "A": "Verbal warning",
            "B": "Formal warning with /warn",
            "C": "Quarantine with w!q, report in #mod-evidence, ping Discord Chairman or above",
            "D": "Immediate ban without evidence"
        },
        "correct": "C"
    },
    {
        "category": "Grading System",
        "question": "Which of these is Grade 3?",
        "options": {
            "A": "Suggestive videos",
            "B": "Sexual topics",
            "C": "Gore and nudity",
            "D": "Mild profanity"
        },
        "correct": "C"
    },
    {
        "category": "Grading System",
        "question": "If you quarantine someone for Grade 3, what makes the quarantine valid?",
        "options": {
            "A": "Just using w!q is enough",
            "B": "You must report it in #mod-evidence, otherwise upper staff will deem it invalid and you get a staff warning",
            "C": "You must DM the user first",
            "D": "You must wait 24 hours"
        },
        "correct": "B"
    },

    # Multi-Rule Violations (6 questions)
    {
        "category": "Multi-Rule Violations",
        "question": "A user is spamming (Rule 2) AND advertising their Discord (Rule 1). What do you do?",
        "options": {
            "A": "Only address the spam",
            "B": "Only address the advertising",
            "C": "Give verbal warning covering BOTH violations",
            "D": "Ban immediately"
        },
        "correct": "C"
    },
    {
        "category": "Multi-Rule Violations",
        "question": "A user speaks Spanish (Rule 5) while also posting suggestive content (Rule 4, Grade 1). Which do you prioritize?",
        "options": {
            "A": "Language violation first",
            "B": "Inappropriate content first (higher severity)",
            "C": "Address both equally in one warning",
            "D": "Ignore the language, focus on content"
        },
        "correct": "B"
    },
    {
        "category": "Multi-Rule Violations",
        "question": "Two users are arguing. One uses a racial slur (Rule 3), the other is spamming insults (Rule 2). Who do you handle first?",
        "options": {
            "A": "The spammer",
            "B": "The user with the racial slur (immediate ban)",
            "C": "Both at the same time",
            "D": "Whoever started it"
        },
        "correct": "B"
    },
    {
        "category": "Multi-Rule Violations",
        "question": "A user posts an advertisement link (Rule 1) with excessive CAPS (Rule 2). Bots delete it. What's next?",
        "options": {
            "A": "Nothing, bots handled it",
            "B": "Verbal warning for advertising",
            "C": "Verbal warning for both violations",
            "D": "Immediate /warn"
        },
        "correct": "C"
    },
    {
        "category": "Multi-Rule Violations",
        "question": "A user is trolling (Rule 2) by pretending to be a staff member (Rule 7 - Impersonation). What should you do?",
        "options": {
            "A": "Verbal warning for trolling",
            "B": "Address impersonation as the more serious issue",
            "C": "Ignore both",
            "D": "Timeout immediately"
        },
        "correct": "B"
    },
    {
        "category": "Multi-Rule Violations",
        "question": "When documenting multiple rule violations in #mod-evidence, what should you include?",
        "options": {
            "A": "Only the most serious violation",
            "B": "All violations with evidence for each",
            "C": "Just mention there were multiple violations",
            "D": "No documentation needed for minor violations"
        },
        "correct": "B"
    },

    # Staff Warning System (4 questions)
    {
        "category": "Staff Warnings",
        "question": "What is the consequence of Warning 1 for staff?",
        "options": {
            "A": "Temporary suspension",
            "B": "Demotion",
            "C": "Just a warning, no action",
            "D": "Removal from staff"
        },
        "correct": "C"
    },
    {
        "category": "Staff Warnings",
        "question": "What happens with Warning 3?",
        "options": {
            "A": "Just a warning",
            "B": "Temporary suspension",
            "C": "Demotion one rank below current position (or removal depending on severity)",
            "D": "Activity watch"
        },
        "correct": "C"
    },
    {
        "category": "Staff Warnings",
        "question": "If you believe you were unfairly warned, who should you contact?",
        "options": {
            "A": "Discord Chairman",
            "B": "Family Lead, Hand of the King, or High Steward",
            "C": "Any High Court member",
            "D": "Other staff members"
        },
        "correct": "B"
    },
    {
        "category": "Staff Warnings",
        "question": "How do you report another staff member for rule violations?",
        "options": {
            "A": "Post in #general-staff-chat",
            "B": "DM Discord Chairman or above with specific format (Name, Offender, Date, Description, Proof)",
            "C": "Report in #mod-evidence",
            "D": "Create a ticket"
        },
        "correct": "B"
    },

    # Edge Cases & Judgment Calls (5 questions)
    {
        "category": "Edge Cases",
        "question": "A user speaks Spanish after verbal warning but claims they are asking for urgent help. What do you do?",
        "options": {
            "A": "Use /warn immediately for ignoring warning",
            "B": "Help them in English, then remind them politely of Rule 5",
            "C": "Quarantine with w!q",
            "D": "Ignore and let someone else handle it"
        },
        "correct": "B"
    },
    {
        "category": "Edge Cases",
        "question": "A user posts a link that looks sketchy. How can you tell if it's dangerous?",
        "options": {
            "A": "Click on it to see",
            "B": "Check for misspellings, extra letters, and use link verification sites",
            "C": "Ask the user if it's safe",
            "D": "Always assume all links are safe"
        },
        "correct": "B"
    },
    {
        "category": "Edge Cases",
        "question": "A user with no violations asks 'What happens if I post NSFW?' What should you do?",
        "options": {
            "A": "Ban them for considering it",
            "B": "Explain the rules and consequences politely",
            "C": "Give a verbal warning",
            "D": "Ignore the question"
        },
        "correct": "B"
    },
    {
        "category": "Edge Cases",
        "question": "You see another moderator give a questionable warning. What should you do?",
        "options": {
            "A": "Call them out publicly",
            "B": "Provide feedback respectfully in #staff-feedback channel",
            "C": "Ignore it",
            "D": "Report them immediately for a staff warning"
        },
        "correct": "B"
    },
    {
        "category": "Edge Cases",
        "question": "A user is on the No Ban List and violates rules. What do you do?",
        "options": {
            "A": "Ban them anyway",
            "B": "Get approval before banning from upper leadership",
            "C": "Give them unlimited warnings",
            "D": "Ignore their violations"
        },
        "correct": "B"
    },

    # Additional Questions to reach 50 total
    # Discord Resources & Guidelines (3 questions)
    {
        "category": "Discord Resources",
        "question": "Which of these is an official Discord resource staff should know?",
        "options": {
            "A": "discord.com/moderation",
            "B": "discord.com/staff-guide",
            "C": "discord.com/rules",
            "D": "discord.com/help-center"
        },
        "correct": "A"
    },
    {
        "category": "Discord Resources",
        "question": "What are the three Discord resources listed in the staff guide?",
        "options": {
            "A": "Moderation, Terms, Guidelines",
            "B": "Rules, Guidelines, Support",
            "C": "Terms, Privacy, Safety",
            "D": "Help, Terms, Community"
        },
        "correct": "A"
    },
    {
        "category": "Discord Resources",
        "question": "Why is it important to follow Discord TOS as a staff member?",
        "options": {
            "A": "It's optional",
            "B": "To represent Arcane Alliance properly and avoid harmful associations",
            "C": "Only leaders need to follow it",
            "D": "It only applies to regular members"
        },
        "correct": "B"
    },

    # Staff Expectations Deep Dive (3 questions)
    {
        "category": "Staff Expectations",
        "question": "What does it mean to be an Arcane Ambassador?",
        "options": {
            "A": "Just following rules",
            "B": "Someone who shares the vision and represents Arcane Alliance positively",
            "C": "Having the most warnings",
            "D": "Being the most active"
        },
        "correct": "B"
    },
    {
        "category": "Staff Expectations",
        "question": "How often are activity checks conducted?",
        "options": {
            "A": "Daily",
            "B": "Monthly",
            "C": "Weekly",
            "D": "Annually"
        },
        "correct": "C"
    },
    {
        "category": "Staff Expectations",
        "question": "Do you need to report short breaks under 48 hours?",
        "options": {
            "A": "Yes, always required",
            "B": "No, but it's appreciated",
            "C": "Only if over 24 hours",
            "D": "Never report any breaks"
        },
        "correct": "B"
    },
]


@staff.register()
class ModQuiz(
    lightbulb.SlashCommand,
    name="mod-quiz",
    description="Administer the staff moderation quiz to a staff member"
):
    user = lightbulb.user(
        "staff-member",
        "Select the staff member to take the quiz"
    )

    difficulty = lightbulb.string(
        "difficulty",
        "Quiz difficulty level",
        choices=[
            lightbulb.Choice(name="Standard", value="Standard"),
            lightbulb.Choice(name="Hard Mode", value="Hard Mode")
        ],
        default="Standard"
    )

    @lightbulb.invoke
    @lightbulb.di.with_di
    async def invoke(
        self,
        ctx: lightbulb.Context,
        mongo: MongoClient = lightbulb.di.INJECTED
    ) -> None:
        await ctx.defer()

        # Role check - only authorized staff can run the command
        if not any(role_id in ctx.member.role_ids for role_id in AUTHORIZED_ROLES):
            await ctx.respond(
                "❌ **Access Denied**\n\nYou do not have permission to administer this quiz.",
                flags=hikari.MessageFlag.EPHEMERAL
            )
            return

        # Create unique session ID for this quiz attempt
        session_id = str(uuid.uuid4())

        # Select question set based on difficulty
        questions = HARD_MODE_QUESTIONS if self.difficulty == "Hard Mode" else QUIZ_QUESTIONS

        # Initialize quiz state in MongoDB
        quiz_state = {
            "_id": session_id,
            "user_id": self.user.id,  # The staff member taking the quiz
            "admin_id": ctx.user.id,  # The staff member administering it
            "current_question": 0,
            "answers": [],
            "score": 0,
            "difficulty": self.difficulty,
            "started_at": datetime.now(timezone.utc),
            "total_questions": len(questions)
        }
        await mongo.button_store.insert_one(quiz_state)

        # Show first question (publicly with ping)
        components = await build_question_display(session_id, 0, self.user, self.difficulty)
        await ctx.respond(components=components, user_mentions=True)


async def build_question_display(session_id: str, question_num: int, user: hikari.User, difficulty: str = "Standard") -> list:
    """Build the question display with answer buttons"""
    # Select correct question set based on difficulty
    questions = HARD_MODE_QUESTIONS if difficulty == "Hard Mode" else QUIZ_QUESTIONS
    question_data = questions[question_num]
    total = len(questions)

    components = [
        Container(
            accent_color=GOLD_ACCENT,
            components=[
                Text(content=f"## 📝 Staff Moderation Quiz - {user.mention}"),
                Text(content=f"**Question {question_num + 1} of {total}**"),
                Separator(divider=True),
                Text(content=f"**Category:** {question_data['category']}\n"),
                Text(content=f"### {question_data['question']}\n"),

                # Answer buttons
                Section(
                    components=[Text(content=f"**A)** {question_data['options']['A']}")],
                    accessory=Button(
                        style=hikari.ButtonStyle.SECONDARY,
                        label="A",
                        custom_id=f"mod_quiz_answer:{session_id}:A"
                    )
                ),
                Section(
                    components=[Text(content=f"**B)** {question_data['options']['B']}")],
                    accessory=Button(
                        style=hikari.ButtonStyle.SECONDARY,
                        label="B",
                        custom_id=f"mod_quiz_answer:{session_id}:B"
                    )
                ),
                Section(
                    components=[Text(content=f"**C)** {question_data['options']['C']}")],
                    accessory=Button(
                        style=hikari.ButtonStyle.SECONDARY,
                        label="C",
                        custom_id=f"mod_quiz_answer:{session_id}:C"
                    )
                ),
                Section(
                    components=[Text(content=f"**D)** {question_data['options']['D']}")],
                    accessory=Button(
                        style=hikari.ButtonStyle.SECONDARY,
                        label="D",
                        custom_id=f"mod_quiz_answer:{session_id}:D"
                    )
                ),

                Separator(divider=True),
                Text(content="-# Kings Alliance Staff Moderation Quiz"),
            ]
        )
    ]

    return components


@register_action("mod_quiz_answer", no_return=True)
@lightbulb.di.with_di
async def handle_mod_quiz_answer(
    action_id: str,
    ctx: lightbulb.components.MenuContext,
    mongo: MongoClient = lightbulb.di.INJECTED,
    bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    **kwargs
):
    """Handle answer button clicks"""
    # Parse action_id: session_id:answer
    parts = action_id.split(":")
    session_id = parts[0]
    selected_answer = parts[1]

    # Get quiz state from MongoDB
    quiz_state = await mongo.button_store.find_one({"_id": session_id})

    if not quiz_state:
        await ctx.respond(
            "❌ Quiz session expired. Please start a new quiz with `/mod-quiz`",
            ephemeral=True
        )
        return

    # Verify it's the correct user (only the staff member can click)
    if quiz_state["user_id"] != ctx.user.id:
        # Get the staff member's name for the error message
        staff_member = await bot.rest.fetch_user(quiz_state["user_id"])
        await ctx.respond(
            f"❌ Only {staff_member.mention} can answer this quiz. Please let them click the buttons!",
            ephemeral=True
        )
        return

    # Get difficulty and select correct question set
    difficulty = quiz_state.get("difficulty", "Standard")
    questions = HARD_MODE_QUESTIONS if difficulty == "Hard Mode" else QUIZ_QUESTIONS

    current_q = quiz_state["current_question"]
    question_data = questions[current_q]
    correct_answer = question_data["correct"]
    is_correct = selected_answer == correct_answer

    # Update quiz state
    quiz_state["answers"].append({
        "question_num": current_q,
        "selected": selected_answer,
        "correct": correct_answer,
        "is_correct": is_correct
    })

    if is_correct:
        quiz_state["score"] += 1

    # Show feedback
    if is_correct:
        feedback_components = [
            Container(
                accent_color=GREEN_ACCENT,
                components=[
                    Text(content="## ✅ Correct!"),
                    Separator(divider=True),
                    Text(content=f"You selected **{selected_answer}** - that's right!\n"),
                    Text(content=f"Current Score: **{quiz_state['score']}/{current_q + 1}**"),
                ]
            )
        ]
    else:
        feedback_components = [
            Container(
                accent_color=DARK_MAGENTA_ACCENT,
                components=[
                    Text(content="## ❌ Incorrect"),
                    Separator(divider=True),
                    Text(content=f"You selected **{selected_answer}**, but the correct answer is **{correct_answer}**.\n"),
                    Text(content=f"{question_data['options'][correct_answer]}\n"),
                    Text(content=f"Current Score: **{quiz_state['score']}/{current_q + 1}**"),
                ]
            )
        ]

    await ctx.interaction.edit_initial_response(components=feedback_components)

    # Move to next question or show results
    quiz_state["current_question"] += 1

    if quiz_state["current_question"] >= len(questions):
        # Quiz complete - show results
        await mongo.button_store.update_one(
            {"_id": session_id},
            {"$set": {
                "completed_at": datetime.now(timezone.utc),
                "final_score": quiz_state["score"],
                "answers": quiz_state["answers"]
            }}
        )

        # Calculate passing score based on difficulty (90%)
        passing_score = 45 if difficulty == "Hard Mode" else 14

        # Store permanent result
        result = {
            "user_id": quiz_state["user_id"],
            "session_id": session_id,
            "score": quiz_state["score"],
            "total": len(questions),
            "difficulty": difficulty,
            "percentage": round((quiz_state["score"] / len(questions)) * 100),
            "passed": quiz_state["score"] >= passing_score,
            "completed_at": datetime.now(timezone.utc),
            "answers": quiz_state["answers"]
        }

        # Store result in staff_mod_quiz_results collection
        await mongo.staff_mod_quiz_results.insert_one(result)

        # Show final results after delay
        import asyncio
        await asyncio.sleep(3)

        # Fetch the staff member user for results display
        staff_member = await bot.rest.fetch_user(quiz_state["user_id"])
        results_components = await build_results_screen(quiz_state, staff_member, bot, difficulty)
        await ctx.interaction.edit_initial_response(components=results_components)

        # Clean up button_store
        await mongo.button_store.delete_one({"_id": session_id})

    else:
        # Update MongoDB and show next question after delay
        await mongo.button_store.update_one(
            {"_id": session_id},
            {"$set": quiz_state}
        )

        import asyncio
        await asyncio.sleep(3)

        # Fetch the staff member user for next question display
        staff_member = await bot.rest.fetch_user(quiz_state["user_id"])
        next_question_components = await build_question_display(session_id, quiz_state["current_question"], staff_member, difficulty)
        await ctx.interaction.edit_initial_response(components=next_question_components)


async def build_results_screen(quiz_state: dict, user: hikari.User, bot: hikari.GatewayBot, difficulty: str = "Standard") -> list:
    """Build the final results screen"""
    # Select correct question set and passing score based on difficulty
    questions = HARD_MODE_QUESTIONS if difficulty == "Hard Mode" else QUIZ_QUESTIONS
    passing_score = 45 if difficulty == "Hard Mode" else 14  # 90% for both

    score = quiz_state["score"]
    total = len(questions)
    percentage = round((score / total) * 100)
    passed = score >= passing_score

    # Build list of incorrect answers
    incorrect_questions = []
    for answer in quiz_state["answers"]:
        if not answer["is_correct"]:
            q_num = answer["question_num"] + 1
            q_data = questions[answer["question_num"]]
            incorrect_questions.append(
                f"**Q{q_num}:** {q_data['question']}\n"
                f"  • Your answer: {answer['selected']}\n"
                f"  • Correct answer: {answer['correct']} - {q_data['options'][answer['correct']]}"
            )

    # Build mode-specific messages
    mode_text = "HARD MODE " if difficulty == "Hard Mode" else ""
    passing_text = f"{passing_score}/{total} (90%)"

    if passed:
        accent_color = GREEN_ACCENT
        status_text = f"## ✅ {mode_text}PASSED!"
        message = f"Congratulations {user.mention}! You passed the {mode_text.lower()}staff moderation quiz with a score of **{score}/{total} ({percentage}%)**!\n\nYou've demonstrated a solid understanding of our moderation guidelines."
    else:
        accent_color = DARK_MAGENTA_ACCENT
        status_text = f"## ❌ {mode_text}FAILED"
        message = f"Unfortunately {user.mention}, you did not pass the {mode_text.lower()}quiz. You scored **{score}/{total} ({percentage}%)**.\n\nYou need at least **{passing_text}** to pass. Please review the staff guidelines and try again."

    components = [
        Container(
            accent_color=accent_color,
            components=[
                Text(content=status_text),
                Separator(divider=True),
                Text(content=message),
                Text(content=f"\n**Final Score:** {score}/{total} ({percentage}%)"),
                Text(content=f"**Passing Score:** {passing_text}"),
            ]
        )
    ]

    # Show incorrect answers if any (limit to first 10 to avoid Discord character limit)
    if incorrect_questions:
        # Limit to first 10 incorrect answers
        display_count = min(10, len(incorrect_questions))
        incorrect_text = "\n\n".join(incorrect_questions[:display_count])

        # Add note if there are more than 10 incorrect answers
        if len(incorrect_questions) > 10:
            remaining = len(incorrect_questions) - 10
            incorrect_text += f"\n\n...and **{remaining} more incorrect answer{'s' if remaining > 1 else ''}**. Please review the staff guidelines thoroughly and retake the quiz."

        components.append(
            Container(
                accent_color=GOLD_ACCENT,
                components=[
                    Text(content="## 📋 Review Your Mistakes\n"),
                    Text(content=incorrect_text),
                    Separator(divider=True),
                    Text(content="-# Review these questions and retake the quiz to improve your score!"),
                ]
            )
        )

    return components
