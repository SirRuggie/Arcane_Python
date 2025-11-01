# CLAUDE.md - Arcane Python Bot Documentation

## Project Overview

Arcane_Python is a sophisticated Discord bot specifically designed for **Clash of Clans clan management**. It serves the **Kings Alliance**, providing comprehensive tools for:

- **Clan Management**: Dashboards, member tracking, recruitment processing
- **FWA (Friendly War Alliance) Integration**: War strategies, weight calculations, automated war management
- **Recruitment Automation**: Ticket systems, candidate processing, automated questionnaires
- **Reddit Monitoring**: Automated post tracking and notifications
- **Interactive Features**: Polls, counting games, comprehensive task management
- **Manual Ticket Management**: Backup ticket creation and management system
- **Moderation Tools**: Thread management, content moderation

## ⚠️ GIT COMMIT RULES - READ BEFORE EVERY COMMIT ⚠️

**CRITICAL: Check this BEFORE committing - These rules are at the TOP so you NEVER miss them!**

### Commit Prefix Decision Tree:

**1. Is this a NEW command/feature that didn't exist before?**
   - ✅ YES → Use `feat:`
   - Example: `feat: add utilities add-perms command for role permission management`
   - Example: `feat: add clan recruitment bidding system`

**2. Is this fixing a bug in EXISTING code that was already committed?**
   - ✅ YES → Use `fix:`
   - Example: `fix: resolve AttributeError in clan dashboard role selection`
   - Example: `fix: correct TH level ordering in FWA bases dropdown`

**3. Is this a minor update, refactor, or maintenance?**
   - ✅ YES → Use `chore:`
   - Example: `chore: update disboard reminder interval to 6 hours`
   - Example: `chore: clean up debug logging in ticket system`

### WRONG Examples (Learn from mistakes):
- ❌ `fix: resolve component deferral error and improve permission display in add-perms command`
  - **WRONG** because add-perms was a NEW command (never existed before), not a bug in existing code
  - **CORRECT** would be: `feat: add utilities add-perms command with grouped permission display`

- ❌ `feat: fix the clan dashboard bug`
  - **WRONG** because fixing existing code = fix, not feat
  - **CORRECT** would be: `fix: resolve role selection error in clan dashboard`

### Commit Message Format:
- `feat:` - **NEW** features, commands, or major additions that didn't exist before
- `fix:` - Bug fixes in **EXISTING** code that was already committed
- `chore:` - Maintenance, updates, minor changes to existing code

### Important Rules:
- Keep messages to **ONE LINE**
- Use present tense ("add" not "added", "fix" not "fixed")
- Be descriptive but concise
- **NEVER mention AI, Claude, "Generated with", or any AI assistance in commits**

### Git Workflow:
```bash
git add <files>
git commit -m "prefix: description"
git push
```

## Technology Stack

**Core Framework:**
- **Python 3.13.5** - Main language
- **hikari** - Discord API wrapper (modern, fast)
- **hikari-lightbulb** - Command framework for slash/prefix commands with dependency injection

**Database:**
- **MongoDB** - Primary database using `pymongo` driver
- **Custom AsyncMongoClient** - Async wrapper for MongoDB operations

**External APIs:**
- **coc.py** - Clash of Clans API integration
- **asyncpraw** - Reddit API (async)
- **cloudinary** - Media upload and management

**Utilities:**
- **APScheduler** - Background task scheduling
- **python-dotenv** - Environment variable management
- **pendulum** - Advanced datetime handling
- **Pillow** - Image processing
- **requests/aiohttp** - HTTP clients

## Project Structure

```
Arcane_Python/
├── main.py                    # Bot entry point
├── requirements.txt           # Dependencies with detailed comments
├── .env.example              # Environment template
├── README.md                 # Basic project info
├── assets/                   # Image assets (footer images, etc.)
├── _archive/                 # Archived/old files
├── extensions/               # Bot functionality modules
│   ├── commands/            # Slash commands by category
│   │   ├── clan/           # Clan management commands
│   │   ├── fwa/            # FWA-specific tools
│   │   ├── moderation/     # Moderation commands
│   │   ├── recruit/        # Recruitment system
│   │   ├── ticket/         # Manual ticket management
│   │   ├── utilities/      # General purpose commands
│   │   ├── counting/       # Counting game features
│   │   └── poll/           # Interactive polls
│   ├── tasks/              # Background/scheduled tasks
│   ├── events/             # Discord event handlers
│   ├── context_menus/      # Right-click menu commands
│   └── factories/          # Component factories
└── utils/                  # Utility modules
    ├── mongo.py           # Database connection and collections
    ├── constants.py       # Bot constants (colors, IDs, etc.)
    ├── emoji.py          # Custom emoji definitions
    └── ticket_state.py   # Ticket system state management
```

## Command Categories

### Clan Management (`clan/`)
- **Dashboard System**: Interactive clan administration panels
- **Clan Information Hub**: Member data, statistics, profiles
- **Member Reporting**: Activity tracking and reporting
- **Points Tracking**: Member contribution tracking
- **FWA Data Management**: War alliance data

### Staff Management (`staff/`)
- **Staff Dashboard** (`/staff dashboard`): Comprehensive employment tracking system
  - Forum-based logging with dedicated threads per staff member
  - Position history tracking with transfers and notes
  - Staff case management (warnings, suspensions, terminations, bans, notes)
  - Admin rights change logging
  - Multiple concurrent position support
  - Smart length limiting for long histories
  - Delete functionality with confirmation
  - Leadership-only access control
  - Search and quick lookup features
- **Staff Quizzes**: Quiz systems for staff onboarding

### FWA Tools (`fwa/`)
- **War Weight Calculations**: Automated weight analysis
- **Chocolate Commands**: War strategy tools
- **Base Management**: FWA base distribution and tracking

### Recruitment (`recruit/`)
- **Automated Ticket System**: Complete recruitment workflow
- **Candidate Processing**: Application review and management
- **Question Flows**: Automated questionnaires with timing (15-20 minutes)
- **Bidding System**: Clan bidding for recruits (see detailed documentation below)

### Manual Ticket Management (`ticket/`)
- **Manual Ticket Creation** (`/ticket create`): Create recruitment tickets when ClashKing fails
- **Ticket Closure** (`/ticket close`): Proper cleanup with MongoDB management
- **ClashKing Integration**: Seamless integration with existing automation
- **Persistent State**: MongoDB-first approach for reliability

### Utilities (`utilities/`)
- **Permission Management** (`/utilities add-perms`): Add permissions to roles for categories and all child channels
  - Restricted to specific admin user (hard-coded ID)
  - Multi-step UI with grouped permission selection (Basic, Message, Thread, Voice, Other)
  - Only adds permissions without removing existing ones
  - Preserves all other role overwrites
  - Grouped confirmation display with emoji category headers
- **Category Cloning** (`/utilities clone-category`): Clone category structure with all channels for new clans
- **General Purpose Commands**: Miscellaneous bot utilities
- **DM Screenshot Upload**: Image processing and upload

### Interactive Features
- **Counting (`counting/`)**: Turn-based counting games with validation
- **Polls (`poll/`)**: Interactive voting with live progress tracking
- **Task Management (`events/message/task_manager.py`)**: Personal productivity system
  - Personal task lists with persistent storage
  - Smart reminders with natural language parsing (e.g., "tomorrow at 2pm")
  - Reminder restoration on bot restart
  - Interactive UI with auto-deleting messages
  - Commands: `add task`, `del task`, `complete task`, `edit task`, `remind task`

### Moderation (`moderation/`)
- **Thread Management**: Discord thread automation
- **Content Moderation**: Message and user management

## Database Schema (MongoDB)

**Collections defined in `utils/mongo.py`:**

- `button_store` - UI component state management
- `clan_data` - Clan information and settings
- `clan_recruitment` - Recruitment data and workflows
- `fwa_data` - Friendly War Alliance information
- `fwa_band_data` - FWA band/group data
- `user_tasks` - User task management system
- `bot_config` - Bot configuration settings
- `reddit_monitor` - Reddit monitoring configuration
- `reddit_notifications` - Reddit notification tracking
- `clan_bidding` - Clan bidding system data
- `new_recruits` - New recruit tracking
- `ticket_automation_state` - Automated ticket system state
- `counting_channels` - Counting game channel data
- `discord_polls` - Poll system data and votes
- `staff_logs` - Staff employment history and case tracking

## Development Setup

**Running the Bot:**
```bash
py main.py
```

**Environment Setup:**
1. Copy `.env.example` to `.env`
2. Fill in required tokens:
   - `BOT_TOKEN` - Discord bot token
   - `MONGO_URI` - MongoDB connection string
   - `MONGO_DB_NAME` - Database name
   - `REDDIT_CLIENT_ID/SECRET` - Reddit API credentials

**Dependencies:**
```bash
pip install -r requirements.txt
```

## Clan Bidding System - Complete Documentation

### Overview
The bidding system allows clans to compete for new recruits by placing point-based bids. The system uses **placeholder points** in MongoDB to "hold" bid amounts during the auction, then converts them to actual point deductions when a winner is determined.

### Key Components

**Files:**
- `extensions/commands/recruit/bidding.py` - Main bidding logic and auction handling
- `extensions/events/channel/ticket_close_monitor.py` - Processes ticket closure and finalizes recruitment

**MongoDB Collections:**
- `clans` - Contains `points` (actual available points) and `placeholder_points` (held for active bids)
- `clan_bidding` - Tracks active auctions with `bids[]`, `is_finalized`, `winner`, `amount`
- `new_recruits` - Tracks recruit status with `activeBid` flag

**Important Constants:**
- `LOG_CHANNEL_ID = 1381395856317747302` - Feed channel for bid logs (in bidding.py)
- `RECRUITMENT_LOG_CHANNEL = 1345589195695194113` - Feed channel for recruitment logs (in ticket_close_monitor.py)

### Point System Logic

#### Placeholder Points Concept
- **Purpose**: Hold points during bidding without actually deducting them
- **How it works**:
  - When clan bids X points → `placeholder_points += X`
  - Available points = `points - placeholder_points`
  - When auction ends → Convert placeholder to actual deduction (winner) or release hold (losers)

#### MongoDB Operations

**During Bidding** (placing a bid):
```python
# Add to placeholder_points (holds the bid amount)
await mongo.clans.update_one(
    {"tag": clan_tag},
    {"$inc": {"placeholder_points": bid_amount}}
)
```

**When Winner Determined** (single atomic operation):
```python
# Winner: Deduct actual points AND release placeholder
await mongo.clans.update_one(
    {"tag": winner_tag},
    {
        "$inc": {
            "points": -winning_amount,           # Deduct actual points (payment)
            "placeholder_points": -winning_amount  # Release the hold
        }
    }
)

# Losers: Silently release placeholder (no actual deduction)
await safe_adjust_placeholder_points(mongo, loser_tag, -bid_amount)
```

**CRITICAL**: Never deduct points AND adjust placeholder separately - this causes **double deduction bug**!

### Bidding Flow

#### 1. Bid Placement
- Clan places bid through UI
- System checks available points: `points - placeholder_points >= bid_amount`
- If valid: `placeholder_points += bid_amount`
- Bid stored in `clan_bidding` collection

#### 2. Auction Timer
- Default: 2 hours after first bid
- Timer can be extended by new bids
- When timer expires → Determines winner automatically

#### 3. Winner Determination

**Scenario A: Multiple Bids**
- Location: `bidding.py` - `handle_multiple_bids()` (lines ~1416-1541)
- Highest bid wins (random tiebreaker if tied)
- Winner: Deduct actual points + release placeholder (atomic operation)
- Losers: Release placeholder only (silent, no messages)
- Sets `is_finalized = True` in MongoDB
- Sends success message to LOG_CHANNEL_ID
- Sends announcement in ticket thread with winner ping

**Scenario B: Single Bid (No Competition)**
- Location: `bidding.py` - `handle_single_bid()` (lines ~1342-1413)
- Winner gets recruit for FREE (placeholder released, no actual deduction)
- Sets `is_finalized = True` in MongoDB
- Sends log message to LOG_CHANNEL_ID
- Sends announcement in ticket thread

#### 4. Ticket Closure & Finalization

**Location**: `ticket_close_monitor.py` - `process_with_bids_recruitment()` (lines ~380-650)

**Case 1: Recruit Joins Winning Clan (SUCCESS)**
- Check `is_finalized` flag:
  - **If finalized** (timer completed): Points already deducted, do nothing
  - **If NOT finalized** (ticket closed early): Deduct points + release placeholder now
- Send success message to RECRUITMENT_LOG_CHANNEL (lines 496-539)
- Shows: Winner name, bid amount, remaining points, player details
- NO messages for losing clans (they never paid)

**Case 2: Recruit Joins Different Clan or No Clan (FAILURE)**
- Check `is_finalized` flag:
  - **If finalized**: Refund actual points to winner (they already paid)
  - **If NOT finalized**: Just release placeholder (they never paid)
- Send failure/refund message to RECRUITMENT_LOG_CHANNEL (lines 574-612)
- Shows: Winner name, refund amount, where recruit actually went
- Release placeholder for ALL losing bidders (silent)

### Feed Channel Messages

**When Messages ARE Sent:**

1. **Multi-Bid Win** (LOG_CHANNEL_ID):
   ```
   🏆 **Multi-Bid Win**: [Clan Name] won [Player Name] for X points (Y bids total)
   ```

2. **Single Bid Win** (LOG_CHANNEL_ID):
   ```
   🎯 **Single Bid Win**: [Clan Name] won [Player Name] (no competition, no points deducted)
   ```

3. **Successful Recruitment** (RECRUITMENT_LOG_CHANNEL):
   - Full embed with green accent
   - **For Single Bid**: Shows "Single Bid (No Competition): X points bid" + "Points Deducted: 0 (uncontested recruitment)"
   - **For Multi-Bid**: Shows "Winning Bid: X points" + "Points Deducted: X points"
   - Remaining points after recruitment
   - Player details (Discord ID, name, tag, TH level)
   - 12-day monitoring period notice

4. **Failed Recruitment - Refund** (RECRUITMENT_LOG_CHANNEL):
   - Full embed with red accent
   - Winner clan mentioned with role ping
   - Shows where recruit actually went
   - "✅ Points Refunded: X points returned to [Clan]"

5. **Manual Ticket Close** (RECRUITMENT_LOG_CHANNEL):
   - Refund messages for ALL bidding clans
   - One message per clan

**When Messages are NOT Sent:**
- ❌ Losing clans when winner succeeds (silent placeholder release)
- ❌ Placeholder point releases (not a refund, just releasing a hold)

### Common Issues & Solutions

#### Issue: Double Point Deduction
**Symptom**: Winner clan loses 2X points instead of X
**Cause**: Deducting actual points AND adjusting placeholder separately
**Solution**: Use single atomic `$inc` operation for both:
```python
{"$inc": {"points": -X, "placeholder_points": -X}}
```

#### Issue: "Refund" Messages for Losing Clans
**Symptom**: All clans get refund messages even though losers never paid
**Cause**: Sending feed messages when releasing placeholder points
**Solution**: Only send messages for actual refunds (failure scenarios), not placeholder releases

#### Issue: Winner Gets Free Recruit
**Symptom**: Winner pays 0 points in multi-bid auction
**Cause**: Only releasing placeholder without deducting actual points
**Solution**: Must include `"points": -X` in the atomic update

#### Issue: Points Not Deducted at All
**Symptom**: Winner keeps all their points after winning
**Cause**: Forgot to deduct actual points, only adjusted placeholder
**Solution**: Always check both `points` and `placeholder_points` are updated correctly

### Testing Checklist

**Test Scenario 1: Multi-Bid, Timer Completes, Recruit Joins Winner**
- ✅ Winner pays bid amount once (not double)
- ✅ Winner's placeholder released
- ✅ Losers' placeholders released (silent)
- ✅ Success message in LOG_CHANNEL_ID (auction win)
- ✅ Success message in RECRUITMENT_LOG_CHANNEL (recruitment complete)
- ❌ NO refund messages for anyone

**Test Scenario 2: Single Bid, Timer Completes, Recruit Joins Winner**
- ✅ Winner pays 0 points (free recruit)
- ✅ Winner's placeholder released
- ✅ Success message in LOG_CHANNEL_ID (single bid win)
- ✅ Success message in RECRUITMENT_LOG_CHANNEL (recruitment complete)

**Test Scenario 3: Multi-Bid, Timer Completes, Recruit Joins Different Clan**
- ✅ Winner gets refund (points returned)
- ✅ Losers' placeholders released (silent)
- ✅ Failure/refund message in RECRUITMENT_LOG_CHANNEL for winner only
- ❌ NO messages for losing clans

**Test Scenario 4: Multi-Bid, Ticket Closed Early, Recruit Joins Winner**
- ✅ Winner pays bid amount (deduction happens on ticket close)
- ✅ All placeholders released
- ✅ Success message in RECRUITMENT_LOG_CHANNEL
- ❌ NO refund messages

**Test Scenario 5: Manual Ticket Close (No Recruitment)**
- ✅ ALL clans get placeholders released
- ✅ Refund messages in RECRUITMENT_LOG_CHANNEL for all bidders
- ✅ All clans get their points back

### Key Principles

1. **Placeholder points = holds, not payments**
   - Placeholders reserve points during bidding
   - Only actual `points` field represents real deductions

2. **Atomic operations prevent double deduction**
   - Always update `points` and `placeholder_points` together in one operation
   - Never deduct points and adjust placeholder in separate operations

3. **Feed messages only for actual events**
   - Success messages when someone wins
   - Refund messages when someone gets actual money back
   - NO messages for silent placeholder releases

4. **is_finalized flag is critical**
   - `True` = Auction timer completed, points already handled
   - `False` = Ticket closed early, need to handle points now

5. **Losers never pay**
   - Losing bidders only had placeholder holds
   - Just release the hold silently when auction ends
   - No refunds needed because they never paid anything


## Code Style Guidelines

**Python Conventions:**
- **Async/await** throughout (hikari is async-first)
- **Type hints** where beneficial
- **Descriptive variable names** 
- **Modular architecture** with extensions
- **Dependency injection** pattern with lightbulb
- **Error handling** with try/catch blocks

**Discord Component Patterns:**
- Use hikari's modern component builders
- Container-based layouts for rich UI
- Interactive buttons and select menus
- Media galleries for images
- Separators and text components for formatting

**Database Patterns:**
- Async MongoDB operations
- State management for complex workflows  
- Document-based data storage
- Collection-specific access patterns

## Important Files to Know

**Core Files:**
- `main.py` - Bot initialization and startup
- `utils/mongo.py` - Database connection and all collection definitions
- `utils/constants.py` - Color constants, IDs, and configuration
- `utils/emoji.py` - Custom emoji mappings

**Key Feature Files:**
- `extensions/commands/recruit/questions.py` - Recruitment questionnaire system
- `extensions/events/message/ticket_automation/` - Automated ticket processing
- `extensions/commands/clan/dashboard.py` - Main clan management interface
- `extensions/commands/fwa/` - FWA war management tools
- `extensions/commands/ticket/create.py` - Manual ticket creation system
- `extensions/commands/ticket/close.py` - Ticket cleanup command
- `extensions/commands/utilities/add_perms.py` - Role permission management with grouped display
- `extensions/commands/utilities/clone_category.py` - Category cloning for new clans
- `extensions/events/message/task_manager.py` - Complete task management system

**Configuration:**
- `.env` - Environment variables (not in repo)
- `.env.example` - Environment template
- `requirements.txt` - All dependencies with explanations

**Documentation:**
- `TASK_SYSTEM_ROADMAP.md` - Future development roadmap for task system enhancements

## Testing & Deployment

**Testing Approach:**
- Standalone test scripts for specific features
- Manual testing in Discord development servers
- No formal test suite (pytest/unittest not used)

**Key Test Files:**
- `test_forum_starter_message.py` - Forum message testing
- `fetch_forum_threads_example.py` - API integration testing

**Deployment:**
- Direct execution with `py main.py`
- No build process required
- Environment variables control behavior
- MongoDB required for persistence

## Architecture Notes

**Design Patterns:**
- **Extension/Plugin Architecture** - Modular command loading
- **Factory Pattern** - UI component creation
- **Repository Pattern** - Database access abstraction  
- **Event-Driven** - Discord event handling
- **Dependency Injection** - Service management with lightbulb

**Key Design Principles:**
- **Async-First** - All operations use async/await
- **Component-Based UI** - Rich Discord interfaces
- **State Management** - Complex workflow tracking
- **Modular Commands** - Organized by feature area
- **Error Resilience** - Graceful failure handling
- **MongoDB-First** - Database operations take precedence for reliability
- **Persistent Systems** - All critical data survives bot restarts

**Component System (extensions/components.py):**
- **Critical Pattern**: Hikari component builders "freeze" their state when instantiated
- **Builder Freeze Issue**: Appending to `Container().components` after instantiation does NOT work
  - ❌ WRONG: `container = Container(components=[...]); container.components.append(...)`
  - ✅ CORRECT: Build complete list first, then pass to Container constructor
- **Modal Handling**: Modal interactions require special deferral pattern
  - Use `ctx.interaction.create_initial_response(DEFERRED_MESSAGE_UPDATE)`
  - Then `ctx.interaction.edit_initial_response(components=...)`
  - Never use `ctx.defer()` or `ctx.edit_initial_response()` on ModalContext
- **Components v2 Restrictions**: Cannot use `content=` parameter with Components v2 messages
  - All responses must be wrapped in Container components
  - Helper functions should wrap text in proper component structure
- **Registration Flags**:
  - `is_modal=True` - Handler processes modal submissions, uses manual response handling
  - `opens_modal=True` - Handler opens a modal, skips automatic deferral
  - `defer_update=True` - Uses DEFERRED_MESSAGE_UPDATE for component navigation
  - `no_return=True` - Handler manages its own responses, framework doesn't send anything
  - `ephemeral=True` - Response visible only to the user who triggered interaction

## Special Features

**Advanced Discord Integration:**
- **Interactive Dashboards** using Discord's latest UI components
- **Automated Workflows** for recruitment and clan management
- **Real-time Updates** with live data synchronization
- **Rich Media** integration with Cloudinary

**Clash of Clans Integration:**
- **Live Clan Data** via official API
- **War Weight Calculations** for FWA
- **Player Profile Analysis** for recruitment
- **Base Management** and distribution

**External Integrations:**
- **Reddit Monitoring** for clan-related posts
- **Image Processing** for screenshots and media
- **Task Scheduling** for automated operations
- **Multi-platform** data aggregation

**Task Management System:**
- **Personal Task Lists** with persistent MongoDB storage
- **Smart Reminders** with natural language parsing (e.g., "tomorrow at 2pm")
- **Reminder Restoration** automatically restores reminders on bot restart
- **Interactive UI** with auto-deleting messages and buttons
- **Future Roadmap** documented in TASK_SYSTEM_ROADMAP.md

## Working with This Codebase

**When Adding Features:**
1. Choose appropriate `extensions/` subdirectory
2. Follow existing patterns for UI components
3. Use dependency injection for services
4. Add database collections to `utils/mongo.py` if needed
5. Test manually in development server
6. Commit with appropriate prefix (`feat:`, `fix:`, `chore:`)

**When Fixing Bugs:**
1. Identify the affected component/extension
2. Check related database collections and state
3. Test the fix thoroughly
4. Use `fix:` prefix in commit message

**When Making Changes:**
1. Always run the bot locally first
2. Check logs for errors or warnings  
3. Test affected Discord commands/features
4. Commit and push changes promptly
5. Monitor production for any issues

## Recent Feature Additions

**October 2024:**
- **Staff Dashboard System** (`/staff dashboard`) - Comprehensive employment tracking and management
  - Forum-based log system with dedicated thread per staff member
  - Complete employment history tracking (hire date, position changes, status updates)
  - Staff case management (warnings, suspensions, terminations, notes, bans)
  - Admin rights change logging with detailed reasons
  - Multiple position support for staff with concurrent roles
  - Position history with transfer tracking and notes
  - Smart length limiting (shows full history until Discord 4000-char limit reached)
  - Interactive dashboard with emoji-labeled sections (📋 Position Changes, 🔑 Admin Changes, ⚠️ Staff Cases)
  - Case type emojis matching dropdown selection (⚠️ Warning, ⏸️ Suspension, 🔴 Termination, 🚫 Staff Ban, 📝 Note)
  - Leadership-only access with role-based permissions
  - Delete confirmation system requiring "DELETE" text input
  - Real-time forum log updates using Components v2
  - Ephemeral interactions for privacy (only visible to the user)
  - Search functionality for quick staff lookup
  - Modular architecture: handlers.py, embeds.py, modals.py, components.py, utils.py
  - Technical implementation notes in "Architecture Notes - Component System"
- Permission management system (`/utilities add-perms`) for adding permissions to categories and channels
  - Restricted to specific admin user for security
  - Multi-step UI with grouped permission selection (Basic, Message, Thread, Voice, Other)
  - Only adds permissions without removing existing ones
  - Preserves all other role overwrites
  - Grouped confirmation display with emoji category headers and counts
  - Automatically defers component interactions (no manual deferral needed)

**September 2024:**
- Manual ticket creation system for ClashKing failover scenarios
- Enhanced task reminder system with persistent scheduling across reboots
- Time parsing improvements for natural language (e.g., "9:20pm", "tomorrow at 2pm")
- MongoDB-first ticket processing for improved reliability
- Complete ticket lifecycle management with proper cleanup

This bot represents a sophisticated Discord application with deep Clash of Clans integration, modern UI components, complex workflow automation, and comprehensive task management. The architecture is designed for maintainability, extensibility, and robust operation in a live gaming community environment.

## Maintenance Notes

**Documentation Updates:**
- CLAUDE.md should be updated whenever new features are added
- Review monthly to ensure accuracy with current codebase
- Document breaking changes and migration notes
- Keep feature descriptions current and comprehensive