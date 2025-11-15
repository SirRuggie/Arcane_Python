"""
Recruitment Staff Quiz - Interactive quiz to ensure staff understand recruitment guidelines
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
    1039311270614142977,  # Role 1
    1345883351139225752,  # Role 2
    1345184776172343318,  # Role 3
    1060318031575793694,  # Role 4
]

# Quiz questions bank
QUIZ_QUESTIONS = [
    # Recruit Process (4 questions)
    {
        "category": "Recruit Process",
        "question": "Where do potential recruits first appear after joining the server?",
        "options": {
            "A": "<#1058426473377185792>",
            "B": "<#1020458939852271626>",
            "C": "<#1378084731874185357>",
            "D": "<#1344107352651071498>"
        },
        "correct": "A"
    },
    {
        "category": "Recruit Process",
        "question": "How many recruiters can interact with each applicant?",
        "options": {
            "A": "Unlimited",
            "B": "Two",
            "C": "One",
            "D": "Depends on TH level"
        },
        "correct": "C"
    },
    {
        "category": "Recruit Process",
        "question": "What are the two ways a recruit can complete their interview?",
        "options": {
            "A": "Text or Voice",
            "B": "Automated Interview or Staff Interview",
            "C": "Ticket or DM",
            "D": "Forum or Reddit"
        },
        "correct": "B"
    },
    {
        "category": "Recruit Process",
        "question": "What must a recruit provide when opening a ticket?",
        "options": {
            "A": "Screenshot of their base.",
            "B": "Their player tag only.",
            "C": "Alt acct details",
            "D": "A and C"
        },
        "correct": "D"
    },

    # Bidding System (4 questions)
    {
        "category": "Bidding System",
        "question": "Who can start a bidding round?",
        "options": {
            "A": "Any recruiter",
            "B": "Recruitment Leadership only",
            "C": "Clan Leaders",
            "D": "Mentors"
        },
        "correct": "B"
    },
    {
        "category": "Bidding System",
        "question": "How long does the bidding window last?",
        "options": {
            "A": "10 minutes",
            "B": "15 minutes",
            "C": "20 minutes",
            "D": "25 minutes"
        },
        "correct": "B"
    },
    {
        "category": "Bidding System",
        "question": "Who skips the bidding process entirely?",
        "options": {
            "A": "TH16 players",
            "B": "FWA recruits",
            "C": "Zen clan recruits",
            "D": "TH14 and below"
        },
        "correct": "B"
    },
    {
        "category": "Bidding System",
        "question": "Which statement is correct about TH13 and below recruits and bidding?",
        "options": {
            "A": "They participate in bidding",
            "B": "They skip bidding (no bidding needed)",
            "C": "They have extended bidding windows",
            "D": "They require leadership approval"
        },
        "correct": "B"
    },

    # Staff Roles & Hierarchy (4 questions)
    {
        "category": "Staff Roles & Hierarchy",
        "question": "Where should staff and leaders talk privately about a recruit?",
        "options": {
            "A": "In general staff chat",
            "B": "In DMs between staff",
            "C": "In the ticket's private thread",
            "D": "In the recruitment channel"
        },
        "correct": "C"
    },
    {
        "category": "Staff Roles & Hierarchy",
        "question": "Who has the final authority on recruitment issues?",
        "options": {
            "A": "Recruitment Lead",
            "B": "Recruitment Chairman",
            "C": "Clan Leader",
            "D": "Mentor"
        },
        "correct": "B"
    },
    {
        "category": "Staff Roles & Hierarchy",
        "question": "If you are interviewing a recruit but realize you don't have time to complete their interview, what should you do?",
        "options": {
            "A": "Rush through the interview quickly",
            "B": "Let them wait until you're available",
            "C": "Ping Recruitment Leadership and request reassignment",
            "D": "Close their ticket"
        },
        "correct": "C"
    },
    {
        "category": "Staff Roles & Hierarchy",
        "question": "Where should staff with seniority provide corrections and feedback?",
        "options": {
            "A": "Publicly in chat",
            "B": "In <#1070040793642958889>, respectfully and constructively",
            "C": "Privately via DM",
            "D": "In the general channel"
        },
        "correct": "B"
    },

    # Rules & Common Sense (1 question)
    {
        "category": "Rules & Common Sense",
        "question": "If a recruiter claims to have invited a candidate, what should you ask for?",
        "options": {
            "A": "Their clan name",
            "B": "Screenshot proof",
            "C": "Recruit's tag",
            "D": "Confirmation from staff"
        },
        "correct": "B"
    },
    {
        "category": "Clan Types",
        "question": "What is Zen?",
        "options": {
            "A": "Competitive war clan",
            "B": "Casual clan where heroes can be down for war",
            "C": "FWA alternative",
            "D": "TH13+ only clan"
        },
        "correct": "B"
    },
    {
        "category": "Clan Types",
        "question": "What is FWA?",
        "options": {
            "A": "Competitive war league",
            "B": "Maximizing loot with fixed bases for casual players to quickly upgrade",
            "C": "Farming without wars",
            "D": "Free-for-all war system"
        },
        "correct": "B"
    },
]

# Hard Mode quiz questions (50 questions for advanced testing)
HARD_MODE_QUESTIONS = [
    # Candidate Entry Process (8 questions)
    {
        "category": "Candidate Entry",
        "question": "Where do potential recruits first appear after joining the server?",
        "options": {
            "A": "<#1058426473377185792>",
            "B": "<#1020458939852271626>",
            "C": "<#1378084731874185357>",
            "D": "<#1344107352651071498>"
        },
        "correct": "A"
    },
    {
        "category": "Candidate Entry",
        "question": "In which channel do recruits open a ticket?",
        "options": {
            "A": "<#1058426473377185792>",
            "B": "<#1020458939852271626>",
            "C": "<#1378084731874185357>",
            "D": "Any recruitment channel"
        },
        "correct": "B"
    },
    {
        "category": "Candidate Entry",
        "question": "What must a recruit provide when opening a ticket?",
        "options": {
            "A": "Screenshot of their base.",
            "B": "Their player tag only.",
            "C": "Alt acct details",
            "D": "A and C"
        },
        "correct": "D"
    },
    {
        "category": "Candidate Entry",
        "question": "What are the two interview path options for recruits?",
        "options": {
            "A": "Forum or DM",
            "B": "Text or Voice",
            "C": "Bot-Driven Interview or Speak with Recruiter",
            "D": "Automated or Manual"
        },
        "correct": "C"
    },
    {
        "category": "Candidate Entry",
        "question": "When does staff jump into an automated interview?",
        "options": {
            "A": "Only at the end",
            "B": "Always at the start",
            "C": "Never - it's fully automated",
            "D": "If needed, recruit requests staff interview, or questions remain unanswered"
        },
        "correct": "D"
    },
    {
        "category": "Candidate Entry",
        "question": "Where is the recruit summary posted after an automated interview?",
        "options": {
            "A": "In the public recruitment channel",
            "B": "In the ticket channel",
            "C": "To the private 'Recruits' thread",
            "D": "In general chat"
        },
        "correct": "C"
    },
    {
        "category": "Candidate Entry",
        "question": "What command does a recruiter use to start a staff interview?",
        "options": {
            "A": "/recruit interview",
            "B": "/start interview",
            "C": "/recruit start",
            "D": "/recruit questions"
        },
        "correct": "D"
    },
    {
        "category": "Candidate Entry",
        "question": "After a \"Speak with Staff\" recruit interview, who should the recruiter ping in the private Recruits thread?",
        "options": {
            "A": "All clan leaders",
            "B": "Recruitment Chairman only",
            "C": "The recruit's TH level roles (@TH# Recruiting) or Zen role for Zen clans",
            "D": "No one - just post the summary"
        },
        "correct": "C"
    },

    # One Recruiter Rule (5 questions)
    {
        "category": "One Recruiter Rule",
        "question": "If you are interviewing a recruit but realize you don't have time to complete their interview, what should you do?",
        "options": {
            "A": "Rush through the interview quickly",
            "B": "Let them wait until you're available",
            "C": "Ping Recruitment Leadership and request reassignment",
            "D": "Close their ticket"
        },
        "correct": "C"
    },
    {
        "category": "One Recruiter Rule",
        "question": "Why is only one recruiter allowed per ticket?",
        "options": {
            "A": "It's just a guideline, not a rule",
            "B": "To save time",
            "C": "To reduce workload",
            "D": "To avoid confusing the candidate"
        },
        "correct": "D"
    },
    {
        "category": "One Recruiter Rule",
        "question": "How many recruiters may interact with each applicant?",
        "options": {
            "A": "Up to three",
            "B": "Two maximum",
            "C": "Only one, under normal circumstances",
            "D": "Unlimited"
        },
        "correct": "C"
    },
    {
        "category": "Clan Types",
        "question": "What is Zen?",
        "options": {
            "A": "Competitive war clan",
            "B": "Casual clan where heroes can be down for war",
            "C": "FWA alternative",
            "D": "TH13+ only clan"
        },
        "correct": "B"
    },
    {
        "category": "Clan Types",
        "question": "What is FWA?",
        "options": {
            "A": "Competitive war league",
            "B": "Maximizing loot with fixed bases for casual players to quickly upgrade",
            "C": "Farming without wars",
            "D": "Free-for-all war system"
        },
        "correct": "B"
    },

    # Bidding System - Basics (9 questions)
    {
        "category": "Bidding System - Basics",
        "question": "What Town Hall levels participate in the bidding process?",
        "options": {
            "A": "TH15 and above",
            "B": "All Town Halls",
            "C": "TH14 and above",
            "D": "TH13 and above"
        },
        "correct": "C"
    },
    {
        "category": "Bidding System - Basics",
        "question": "What happens to TH13 and below recruits regarding bidding?",
        "options": {
            "A": "They wait for special approval",
            "B": "Automatic assignment to lowest clan",
            "C": "They participate in bidding",
            "D": "First come, first served (provided criteria are met)"
        },
        "correct": "D"
    },
    {
        "category": "Bidding System - Basics",
        "question": "How long is the bidding window open?",
        "options": {
            "A": "15 minutes",
            "B": "20 minutes",
            "C": "10 minutes",
            "D": "25 minutes"
        },
        "correct": "A"
    },
    {
        "category": "Clan Types",
        "question": "How do you get Account Weight for FWA?",
        "options": {
            "A": "Request it from FWA Discord server",
            "B": "Use FC or scout base in war",
            "C": "Calculate manually using TH level",
            "D": "Leadership assigns it automatically"
        },
        "correct": "B"
    },
    {
        "category": "Bidding System - Basics",
        "question": "What command initiates the bidding process?",
        "options": {
            "A": "/bidding start",
            "B": "/clan bid",
            "C": "/start bidding",
            "D": "/recruit bidding"
        },
        "correct": "D"
    },
    {
        "category": "Bidding System - Basics",
        "question": "When should bidding be started?",
        "options": {
            "A": "Only for high TH players",
            "B": "Within 24 hours",
            "C": "Immediately after eligible recruit interviews (TH14+, non-FWA)",
            "D": "After leadership review"
        },
        "correct": "C"
    },
    {
        "category": "Bidding System - Basics",
        "question": "How many accounts can be submitted per recruit in bidding?",
        "options": {
            "A": "5 accounts",
            "B": "Unlimited",
            "C": "1 account only",
            "D": "3 accounts"
        },
        "correct": "A"
    },
    {
        "category": "Bidding System - Basics",
        "question": "Who skips the bidding process entirely?",
        "options": {
            "A": "All TH14 and below",
            "B": "TH16 players",
            "C": "Zen clan recruits",
            "D": "FWA recruits"
        },
        "correct": "D"
    },
    {
        "category": "Bidding System - Basics",
        "question": "When are bids revealed to everyone?",
        "options": {
            "A": "Only to leadership",
            "B": "After 24 hours",
            "C": "Immediately when placed",
            "D": "When the timer ends - they are secret until then"
        },
        "correct": "D"
    },

    # Bidding System - Advanced (7 questions)
    {
        "category": "Bidding System - Advanced",
        "question": "What happens if multiple clans tie for the highest bid?",
        "options": {
            "A": "All tied clans split the recruit",
            "B": "Leadership decides",
            "C": "One is chosen at random and others are refunded",
            "D": "First clan to bid wins"
        },
        "correct": "C"
    },
    {
        "category": "Bidding System - Advanced",
        "question": "What happens if only one clan bids on a recruit?",
        "options": {
            "A": "Automatic win with full refund",
            "B": "Bidding extends by 5 minutes",
            "C": "Recruit goes to highest point clan",
            "D": "They pay full price"
        },
        "correct": "A"
    },
    {
        "category": "Bidding System - Advanced",
        "question": "What are clan points used for?",
        "options": {
            "A": "Tracking activity",
            "B": "Ranking clans",
            "C": "Unlocking features",
            "D": "Currency for bidding on recruits"
        },
        "correct": "D"
    },
    {
        "category": "Bidding System - Advanced",
        "question": "Which bid wins when bidding ends?",
        "options": {
            "A": "Leadership's choice",
            "B": "Most recent bid",
            "C": "Highest fitting bid",
            "D": "First bid placed"
        },
        "correct": "C"
    },
    {
        "category": "Bidding System - Advanced",
        "question": "How many bids can each clan submit per account?",
        "options": {
            "A": "Two bids",
            "B": "Three bids",
            "C": "Unlimited",
            "D": "One bid per account"
        },
        "correct": "D"
    },
    {
        "category": "Bidding System - Advanced",
        "question": "When does the bidding timer start?",
        "options": {
            "A": "When /recruit bidding is run",
            "B": "When recruit completes interview",
            "C": "Manually by leadership",
            "D": "When first bid is placed"
        },
        "correct": "A"
    },
    {
        "category": "Point System",
        "question": "Can we approve our own clan points?",
        "options": {
            "A": "Yes, if you have proof",
            "B": "Only if no one else is available",
            "C": "It depends on the point type",
            "D": "No"
        },
        "correct": "D"
    },

    # Invited Candidates (4 questions)
    {
        "category": "Invited Candidates",
        "question": "If a family member or recruiter invites a player to the server, who gets them?",
        "options": {
            "A": "First clan to respond",
            "B": "Goes through normal bidding",
            "C": "Their clan has dibs on them",
            "D": "Highest bidding clan"
        },
        "correct": "C"
    },
    {
        "category": "Invited Candidates",
        "question": "What should you ask if a recruiter claims they invited someone but it wasn't in the ticket?",
        "options": {
            "A": "Check Discord logs",
            "B": "Assume they're lying",
            "C": "Ask the recruit 'Who invited you?'",
            "D": "Ask the clan leader"
        },
        "correct": "C"
    },
    {
        "category": "Invited Candidates",
        "question": "If a recruit says no one invited them, what should you ask the person claiming the invite?",
        "options": {
            "A": "When they invited them",
            "B": "Nothing - take their word",
            "C": "Their reasoning",
            "D": "Screenshot proof containing evidence they invited them"
        },
        "correct": "D"
    },
    {
        "category": "Point System",
        "question": "Who can approve clan points?",
        "options": {
            "A": "Any clan leader",
            "B": "Recruitment Lead and above",
            "C": "Recruitment Chairman only",
            "D": "Any recruiter with proof"
        },
        "correct": "B"
    },

    # Hierarchy & Leadership (6 questions)
    {
        "category": "Hierarchy & Leadership",
        "question": "If there is an argument with recruitment staff, who should you contact?",
        "options": {
            "A": "Directly contact Recruitment Chairman",
            "B": "Contact any available leadership",
            "C": "Follow chain of command: contact your direct senior (Lead → Manager → Chairman)",
            "D": "Handle it yourself"
        },
        "correct": "C"
    },
    {
        "category": "Hierarchy & Leadership",
        "question": "What can the Recruitment Chairman do that Leads cannot?",
        "options": {
            "A": "Promote staff to Recruitment Lead",
            "B": "Hold final decision weight on recruitment matters",
            "C": "Final authority on disputes and escalations",
            "D": "All of the above"
        },
        "correct": "D"
    },
    {
        "category": "Hierarchy & Leadership",
        "question": "Who can start recruit bidding rounds?",
        "options": {
            "A": "Clan leaders",
            "B": "Recruitment Chairman only",
            "C": "Any recruiter",
            "D": "Recruitment Lead and above"
        },
        "correct": "D"
    },
    {
        "category": "Hierarchy & Leadership",
        "question": "Who should train new recruitment staff?",
        "options": {
            "A": "Any experienced recruiter",
            "B": "Clan Leaders",
            "C": "Mentors and Trainers",
            "D": "Recruitment Lead and above"
        },
        "correct": "D"
    },
    {
        "category": "Hierarchy & Leadership",
        "question": "Where should staff and leaders talk privately about a recruit?",
        "options": {
            "A": "In general staff chat",
            "B": "In DMs between staff",
            "C": "In the ticket's private thread",
            "D": "In the recruitment channel"
        },
        "correct": "C"
    },
    {
        "category": "Hierarchy & Leadership",
        "question": "Who handles recruitment disputes and enforces penalties?",
        "options": {
            "A": "Disputes follow chain of command, but Recruitment Lead makes final decision",
            "B": "Vote by all recruiters determines the outcome",
            "C": "Disputes escalate through chain of command, but Recruitment Chairman has final authority",
            "D": "Server Owner must approve all penalties"
        },
        "correct": "C"
    },

    # Point System (7 questions)
    {
        "category": "Point System",
        "question": "How many points does a clan earn for a weekly Reddit post?",
        "options": {
            "A": "+5 points",
            "B": "+10 points",
            "C": "+1 point",
            "D": "+3 points"
        },
        "correct": "A"
    },
    {
        "category": "Point System",
        "question": "How many points for posting once per day in the ClashOfClans recruitment server?",
        "options": {
            "A": "+1 point",
            "B": "+2 points",
            "C": "+5 points",
            "D": "+3 points"
        },
        "correct": "A"
    },
    {
        "category": "Point System",
        "question": "How many points for DM/Reddit comment recruiting (if they join)?",
        "options": {
            "A": "+3 points",
            "B": "+5 points",
            "C": "+1 point (unlimited)",
            "D": "+2 points (max 5 per day)"
        },
        "correct": "C"
    },
    {
        "category": "Point System",
        "question": "How often should you use the 'Recruitment Help' button (/clan recruit-help) to earn a point?",
        "options": {
            "A": "Once only",
            "B": "Every week",
            "C": "Every 2 weeks",
            "D": "Every 30 days"
        },
        "correct": "D"
    },
    {
        "category": "Point System",
        "question": "What command is used to report clan points?",
        "options": {
            "A": "/points report",
            "B": "/submit points",
            "C": "/clan points",
            "D": "/clan recruit points"
        },
        "correct": "D"
    },
    {
        "category": "Point System",
        "question": "What must all recruitment posts (Reddit/Discord) include?",
        "options": {
            "A": "'Kings Alliance' and https://discord.gg/kingsalliance",
            "B": "Player requirements only",
            "C": "Clan level",
            "D": "Clan tag only"
        },
        "correct": "A"
    },
    {
        "category": "Point System",
        "question": "What is forbidden on Reddit that risks a permanent ban?",
        "options": {
            "A": "Giveaways, using alt Reddit accounts, or posting daily",
            "B": "Mentioning Kings Alliance",
            "C": "Posting in r/ClashOfClansRecruit",
            "D": "Using the discord invite link"
        },
        "correct": "A"
    },

    # Common Sense & Rules (4 questions)
    {
        "category": "Common Sense",
        "question": "At what level do clan perks cap (stop increasing)?",
        "options": {
            "A": "Level 20",
            "B": "Level 15",
            "C": "Level 10",
            "D": "Level 5"
        },
        "correct": "C"
    },
    {
        "category": "Common Sense",
        "question": "Which of these is a red flag during a recruit interview?",
        "options": {
            "A": "They refuse to provide a base screenshot",
            "B": "They were banned from multiple clans or demand Co immediately",
            "C": "They ask how many girls are in the clan",
            "D": "All of the above"
        },
        "correct": "D"
    },
    {
        "category": "Common Sense",
        "question": "If a recruit says they want a 'level 20+ clan', what should you tell them?",
        "options": {
            "A": "Level doesn't matter at all",
            "B": "That's not important",
            "C": "We don't have that level",
            "D": "Clan perks cap at level 10, a level 10 and level 30 clan get the same bonuses. Is aiming for level X still a must?"
        },
        "correct": "D"
    },
    {
        "category": "Common Sense",
        "question": "If a recruit says 'I'll join after I collect my rewards', what's the correct response?",
        "options": {
            "A": "Wait until next season",
            "B": "You must join now",
            "C": "Okay, no problem",
            "D": "You're good to join anytime - you keep all Raid Medals, CWL Medals, and Clan Game rewards when switching. The game tracks everything you've earned."
        },
        "correct": "D"
    },
]


@staff.register()
class StaffQuiz(
    lightbulb.SlashCommand,
    name="recruit-quiz",
    description="Administer the recruitment staff quiz to a new recruit"
):
    user = lightbulb.user(
        "recruiter",
        "Select the recruiter to take the quiz"
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
            "user_id": self.user.id,  # The recruit taking the quiz
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
                Text(content=f"## 📝 Recruitment Staff Quiz - {user.mention}"),
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
                        custom_id=f"quiz_answer:{session_id}:A"
                    )
                ),
                Section(
                    components=[Text(content=f"**B)** {question_data['options']['B']}")],
                    accessory=Button(
                        style=hikari.ButtonStyle.SECONDARY,
                        label="B",
                        custom_id=f"quiz_answer:{session_id}:B"
                    )
                ),
                Section(
                    components=[Text(content=f"**C)** {question_data['options']['C']}")],
                    accessory=Button(
                        style=hikari.ButtonStyle.SECONDARY,
                        label="C",
                        custom_id=f"quiz_answer:{session_id}:C"
                    )
                ),
                Section(
                    components=[Text(content=f"**D)** {question_data['options']['D']}")],
                    accessory=Button(
                        style=hikari.ButtonStyle.SECONDARY,
                        label="D",
                        custom_id=f"quiz_answer:{session_id}:D"
                    )
                ),

                Separator(divider=True),
                Text(content="-# Kings Alliance Recruitment Quiz"),
            ]
        )
    ]

    return components


@register_action("quiz_answer", no_return=True)
@lightbulb.di.with_di
async def handle_quiz_answer(
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
            "❌ Quiz session expired. Please start a new quiz with `/staff recruit-quiz`",
            ephemeral=True
        )
        return

    # Verify it's the correct user (only the recruit can click)
    if quiz_state["user_id"] != ctx.user.id:
        # Get the recruit's name for the error message
        recruit = await bot.rest.fetch_user(quiz_state["user_id"])
        await ctx.respond(
            f"❌ Only {recruit.mention} can answer this quiz. Please let them click the buttons!",
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

        # Store result in staff_quiz_results collection
        await mongo.staff_quiz_results.insert_one(result)

        # Show final results after delay
        import asyncio
        await asyncio.sleep(3)

        # Fetch the recruit user for results display
        recruit = await bot.rest.fetch_user(quiz_state["user_id"])
        results_components = await build_results_screen(quiz_state, recruit, bot, difficulty)
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

        # Fetch the recruit user for next question display
        recruit = await bot.rest.fetch_user(quiz_state["user_id"])
        next_question_components = await build_question_display(session_id, quiz_state["current_question"], recruit, difficulty)
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
        message = f"Congratulations {user.mention}! You passed the {mode_text.lower()}recruitment staff quiz with a score of **{score}/{total} ({percentage}%)**!\n\nYou've demonstrated a solid understanding of our recruitment guidelines."
    else:
        accent_color = DARK_MAGENTA_ACCENT
        status_text = f"## ❌ {mode_text}FAILED"
        message = f"Unfortunately {user.mention}, you did not pass the {mode_text.lower()}quiz. You scored **{score}/{total} ({percentage}%)**.\n\nYou need at least **{passing_text}** to pass. Please review the guidelines and try again."

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
            incorrect_text += f"\n\n...and **{remaining} more incorrect answer{'s' if remaining > 1 else ''}**. Please review the recruitment guidelines thoroughly and retake the quiz."

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
