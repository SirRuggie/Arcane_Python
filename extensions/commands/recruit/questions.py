import lightbulb
import asyncio
import hikari
import re
from aiohttp.web_routedef import delete
from hikari import GatewayBot
from hikari.api import LinkButtonBuilder
from hikari.impl import (
    MessageActionRowBuilder as ActionRow,
    TextSelectMenuBuilder as TextSelectMenu,
    SelectOptionBuilder as SelectOption,
    ContainerComponentBuilder as Container,
    SectionComponentBuilder as Section,
    InteractiveButtonBuilder as Button,
    TextDisplayComponentBuilder as Text,
    SeparatorComponentBuilder as Separator,
    ThumbnailComponentBuilder as Thumbnail,
    MediaGalleryComponentBuilder as Media,
    MediaGalleryItemBuilder as MediaItem,
    LinkButtonBuilder as LinkButton
)

from extensions.commands.recruit import recruit
from extensions.commands.fwa.helpers import get_fwa_base_object
from utils.constants import (
    DARK_MAGENTA_ACCENT,
    GOLD_ACCENT,
    BLUE_ACCENT,
    GREEN_ACCENT,
    FWA_WAR_BASE,
    FWA_ACTIVE_WAR_BASE,
)
from utils.emoji import emojis
from utils.mongo import MongoClient
from extensions.components import register_action

@recruit.register()
class RecruitQuestions(
    lightbulb.SlashCommand,
    name="questions",
    description="Select a new recruit to send them recruit questions"
):
    user = lightbulb.user(
        "discord-user",
        "select a new recruit",
    )

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context, mongo: MongoClient) -> None:
        await ctx.defer(ephemeral=True)
        data = {
            "_id": str(ctx.interaction.id),
            "user_id" : self.user.id
        }
        await mongo.button_store.insert_one(data)
        components = await recruit_questions_page(action_id=str(ctx.interaction.id), **data)
        await ctx.respond(components=components, ephemeral=True)


@register_action("primary_questions", no_return=True)
@lightbulb.di.with_di
async def primary_questions(
    user_id: int,
    bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    **kwargs
):

    ctx: lightbulb.components.MenuContext = kwargs.get("ctx")
    choice = ctx.interaction.values[0]
    user = await bot.rest.fetch_member(ctx.guild_id, user_id)
    mention_allowed = {
        # don’t auto-parse @everyone or @here
        "parse": [],
        # only ping this one user
        "users": [user.id],
        # no role pings
        "roles": []
    }
    if choice == "attack_strategies":
        components = [
            Container(
                accent_color=DARK_MAGENTA_ACCENT,
                components=[
                    Text(content=f"## ⚔️ **Attack Strategy Breakdown** · {user.mention}"),
                    Separator(divider=True),
                    Text(content=(
                        "Help us understand your go-to attack strategies!\n\n"
                        f"{emojis.red_arrow_right} **Main Village strategies**\n"
                        f"{emojis.blank}{emojis.white_arrow_right} _e.g. Hybrid, Queen Charge w/ Hydra, Lalo_\n\n"
                        f"{emojis.red_arrow_right} **Clan Capital Attack Strategies**\n"
                        f"{emojis.blank}{emojis.white_arrow_right} _e.g. Super Miners w/ Freeze_\n\n"
                        f"{emojis.red_arrow_right} **Highest Clan Capital Hall level you’ve attacked**\n"
                        f"{emojis.blank}{emojis.white_arrow_right} _e.g. CH 8, CH 9, etc.\n\n_"
                        "*Your detailed breakdown helps us match you to the perfect clan!*"
                    )),
                    Media(
                        items=[
                            MediaItem(media="assets/Red_Footer.png"),
                    ]),
                    Text(content=f"-# Requested by {ctx.member.mention}"),
                ]
            )
        ]

    elif choice == "future_clan_expectations":
        components = [
            Container(
                accent_color=DARK_MAGENTA_ACCENT,
                components=[
                    Text(content=f"## 🔮 **Future Clan Expectations** · {user.mention}"),
                    Separator(divider=True),
                    Text(content=(
                        "Help us tailor your clan experience! Please answer the following:\n\n"
                        f"{emojis.red_arrow_right} **What do you expect from your future clan?**\n"
                        f"{emojis.blank}{emojis.white_arrow_right} _(e.g., Active wars, good communication, strategic support._)\n\n"
                        f"{emojis.red_arrow_right} **Minimum clan level you’re looking for?**\n"
                        f"{emojis.blank}{emojis.white_arrow_right} _e.g. Level 5, Level 10_\n\n"
                        f"{emojis.red_arrow_right}  **Minimum Clan Capital Hall level?**\n"
                        f"{emojis.blank}{emojis.white_arrow_right} _e.g. CH 8 or higher_\n\n"
                        f"{emojis.red_arrow_right} **CWL league preference?**\n"
                        f"{emojis.blank}{emojis.white_arrow_right} _e.g. Crystal league or no preference_\n\n"
                        f"{emojis.red_arrow_right} **Preferred playstyle?**\n"
                        f"{emojis.blank}{emojis.white_arrow_right} Competitive\n"
                        f"{emojis.blank}{emojis.white_arrow_right} Casual\n"
                        f"{emojis.blank}{emojis.white_arrow_right} Zen _Type __What is Zen__ to learn more._\n"
                        f"{emojis.blank}{emojis.white_arrow_right} FWA _Type __What is FWA__ to learn more._\n"
                    )),
                    Media(
                        items=[
                            MediaItem(media="assets/Red_Footer.png"),
                    ]),
                    Text(content=f"-# Requested by {ctx.member.mention}"),
                ]
            )
        ]
    elif choice == "discord_basic_skills":
        components = [
            Container(
                accent_color=DARK_MAGENTA_ACCENT,
                components=[
                    Text(content=f"## 🎓 **Discord Basics Check** · {user.mention}"),
                    Separator(divider=True),
                    Text(
                        content=(
                            "Hey there! Before we proceed, let's confirm you’re comfy with our core Discord features:\n\n"
                            "1️⃣ **React** to this message with any emoji of your choice.\n"
                            "2️⃣ **Mention** your recruiter in this thread (e.g. <@1386722406051217569>).\n\n"
                            "*These steps help us make sure you can react and ping others; key skills for smooth clan comms!*"
                        )
                    ),
                    Media(
                        items=[
                            MediaItem(media="https://c.tenor.com/oEkj7apTtT4AAAAC/tenor.gif"),
                        ]),
                    Text(content=f"-# Requested by {ctx.member.mention}"),
                ]
            ),
        ]
    elif choice == "discord_basic_skills_2":
        components = [
            Container(
                accent_color=DARK_MAGENTA_ACCENT,
                components=[
                    Text(content=f"## 🎯 **Master Discord Communication** · {user.mention}"),
                    Separator(divider=True),
                    Text(
                        content=(
                            "In **Kings**, we rely heavily on two key Discord skills:\n\n"
                            "🔔 **Mentions** (pings) – call out a member or a role to grab attention.\n"
                            "👍 **Reactions** – respond quickly with an emoji to acknowledge messages.\n\n"
                            "*These are the fastest ways to keep our clan chat flowing!*"
                        )
                    ),

                    Media(
                        items=[
                            MediaItem(media="assets/Red_Footer.png"),
                        ]),

                    Text(content=f"-# Requested by {ctx.member.mention}"),
                ]
            ),
        ]
    elif choice == "age_bracket_&_timezone":
        components = [
            Container(
                accent_color=DARK_MAGENTA_ACCENT,
                components=[
                    Text(content=f"## ⏳ **What's Your Age Bracket?** · {user.mention}"),
                    Separator(divider=True),
                    Text(content="**What age bracket do you fall into?**\n\n"),
                    Section(
                        components=[
                            Text(
                                content=(
                                    f"{emojis.white_arrow_right}"
                                    "**16 & Under** *(Family-Friendly Clan)*"
                                )
                            )
                        ],
                        accessory=Button(
                            style=hikari.ButtonStyle.SECONDARY,
                            label="🧒16 & Under",
                            custom_id=f"age:16_under_{user.id}",
                        ),
                    ),
                    Section(
                        components=[
                            Text(
                                content=(
                                    f"{emojis.white_arrow_right}"
                                    "**17 – 25**"
                                )
                            )
                        ],
                        accessory=Button(
                            style=hikari.ButtonStyle.SECONDARY,
                            label="🧑17 – 25",
                            custom_id=f"age:17_25_{user.id}",
                        ),
                    ),
                    Section(
                        components=[
                            Text(
                                content=(
                                    f"{emojis.white_arrow_right}"
                                    "**Over 25**"
                                )
                            )
                        ],
                        accessory=Button(
                            style=hikari.ButtonStyle.SECONDARY,
                            label="🧓Over 25",
                            custom_id=f"age:over_25_{user.id}",
                        ),
                    ),

                    Text(
                        content="*Don’t worry, we’re not knocking on your door! Just helps us get to know you better. 😄👍*"),
                    Media(
                        items=[
                            MediaItem(media="assets/Red_Footer.png"),
                        ]),
                    Text(content=f"-# Requested by {ctx.member.mention}"),
                ]
            ),

        ]
    elif choice == "leaders_checking_you_out":
        components = [
            Container(
                accent_color=DARK_MAGENTA_ACCENT,
                components=[
                    Text(content=f"## 🔍 **Application Under Review** · {user.mention}"),
                    Separator(divider=True),
                    Text(
                        content=(
                            "Thank you for completing your application! 🎉\n\n"
                            "**⏰ Leaders have 15 minutes to review your ticket.**\n"
                            "**Please allow us 20 minutes and we'll be with you shortly!**\n\n"
                            "We appreciate your patience and can't wait to welcome you aboard!"
                        )
                    ),
                    Media(
                        items=[
                            MediaItem(media="assets/Red_Footer.png"),
                        ]),
                    Text(content=f"-# Requested by {ctx.member.mention}"),
                ]
            )
        ]

        # Send notification to the thread (if it exists)
        try:
            from extensions.events.message.ticket_automation.core.state_manager import StateManager
            from extensions.events.message.ticket_automation.handlers.summary_generator import check_candidate_in_family_clans

            ticket_state = await StateManager.get_ticket_state(str(ctx.channel_id))
            if ticket_state:
                thread_id = ticket_state.get("ticket_info", {}).get("thread_id")
                if thread_id:
                    # Check if candidate is already in family clans
                    matches = await check_candidate_in_family_clans(ctx.channel_id)

                    # Build dynamic message based on results
                    if matches:
                        # Found in family clan(s) - send alert with specific details
                        alert_lines = ["⚠️ **ALERT:** The following account(s) are already in family clans:\n"]
                        for match in matches:
                            alert_lines.append(f"• **{match['player_name']}** (`{match['player_tag']}`) is in **{match['clan_name']}**")
                            if match.get('leader_id') and match.get('leader_role_id'):
                                alert_lines.append(f"  → Contact: <@{match['leader_id']}> and <@&{match['leader_role_id']}>")
                            alert_lines.append("")

                        alert_lines.append("Please coordinate with their current clan leadership before proceeding.\n")
                        alert_lines.append("Run `/recruit bidding` only after resolving these conflicts.")

                        notification_content = "<@&1039311270614142977> **Application review initiated!**\n\n" + "\n".join(alert_lines)
                    else:
                        # Not found in any family clan or API failed - send success/fallback message
                        from utils import bot_data
                        coc_client = bot_data.data.get("coc_client")

                        if coc_client:
                            # API available - they're not in any family clan
                            notification_content = (
                                "<@&1039311270614142977> **Application review initiated!**\n\n"
                                "✅ **Verification Complete:** Candidate is not currently in any family clan.\n\n"
                                "Proceed with `/recruit bidding` for the appropriate user accounts."
                            )
                        else:
                            # API unavailable - fallback to manual check
                            notification_content = (
                                "<@&1039311270614142977> **Application review initiated!**\n\n"
                                "⚠️ **Unable to verify clan membership automatically.**\n"
                                "Please manually check if the candidate is already in a family clan.\n\n"
                                "Run `/recruit bidding` after manual verification."
                            )

                    await bot.rest.create_message(
                        channel=int(thread_id),
                        content=notification_content,
                        role_mentions=True
                    )
        except Exception as e:
            print(f"[Questions] Error sending thread notification: {e}")
    await bot.rest.create_message(
        components=components,
        channel=ctx.channel_id,
        user_mentions = [user.id],
        role_mentions = True,
    )
    await asyncio.sleep(20)

    action_id = ctx.interaction.custom_id.split(":", 1)[1]
    new_components = await recruit_questions_page(
        action_id=action_id,
        user_id=user_id,
        ctx=ctx,
    )
    try:
        await ctx.interaction.delete_initial_response()
    except hikari.errors.NotFoundError:
        pass  # Interaction expired or already deleted, continue anyway
    await ctx.respond(
        components=new_components,
        ephemeral=True,
    )
    ## If I decide to edit instead of deleting and resending
    #await ctx.interaction.edit_initial_response(components=new_components)

@register_action("age", no_return=True)
@lightbulb.di.with_di
async def on_age_button(
    action_id: str,
    bot: GatewayBot = lightbulb.di.INJECTED,
    **kwargs
):
    ctx: lightbulb.components.MenuContext = kwargs["ctx"]
    bracket, user_id = action_id.rsplit("_", 1)
    user_id = int(user_id)
    user = await bot.rest.fetch_member(ctx.guild_id, user_id)

    if int(ctx.user.id) != user_id:
        await ctx.respond(
            f"Sorry {ctx.user.mention}, this button is only for {user.mention} to click. Please let them continue!",
            ephemeral=True
        )
        return

    try:
        await ctx.interaction.delete_initial_response()
    except hikari.errors.NotFoundError:
        pass  # Interaction expired or already deleted, continue anyway

    if bracket == "16_under":
        components = [
            Text(content=f"🎉 **16 & Under Registered!** · {user.mention}"),

            Container(
                accent_color=DARK_MAGENTA_ACCENT,
                components=[
                    Text(
                        content=(
                            "Got it! You're bringing that youthful energy!\n\n"
                            "We'll find you a family-friendly clan that's the perfect fit for you.\n\n"
                        )
                    ),
                    Media(
                        items=[
                            MediaItem(media="https://c.tenor.com/oxxT2JPSQccAAAAC/tenor.gif"),
                        ]
                    ),
                    Text(content=f"-# Requested by {ctx.member.mention}"),
                ],
            )]
        await bot.rest.create_message(
            components=components,
            channel=ctx.channel_id,
            user_mentions = [user.id],
            role_mentions = True,

        )
    elif bracket == "17_25":
        components = [
            Text(content=f"🎮 **17–25 Confirmed** · {user.mention}"),

            Container(
                accent_color=DARK_MAGENTA_ACCENT,
                components=[
                    Text(
                        content=(
                            "Understood! You’re in prime gaming years!\n\n"
                            "Time to conquer the Clash world! 🏆\n\n"
                        )
                    ),
                    Media(
                        items=[
                            MediaItem(media="https://c.tenor.com/twdtlMLE8UIAAAAC/tenor.gif"),
                        ]
                    ),
                    Text(content=f"-# Requested by {ctx.member.mention}"),
                ],
        )]
        await bot.rest.create_message(
            components=components,
            channel=ctx.channel_id,
            user_mentions = [user.id],
            role_mentions = True,
        )
    elif bracket == "over_25":
        components = [
            Text(content=f"🏅 **Over 25 Confirmed** · {user.mention}"),

            Container(
                accent_color=DARK_MAGENTA_ACCENT,
                components=[
                    Text(
                        content=(
                            "Awesome! Experience meets strategy!\n\n"
                            "Welcome to the veteran league of Clashers! 💪\n\n"
                        )
                    ),
                    Media(
                        items=[
                            MediaItem(media="https://c.tenor.com/m6o-4dKGdVAAAAAC/tenor.gif"),
                        ]
                    ),
                    Text(content=f"-# Requested by {ctx.member.mention}"),
                ],
        )]
        await bot.rest.create_message(
            components=components,
            channel=ctx.channel_id,
            user_mentions = [user.id],
            role_mentions = True,
        )
    await asyncio.sleep(10)
    components = [
        Text(content=f"🌐 **Set Your Time Zone** · {user.mention}"),

        Container(
            accent_color=DARK_MAGENTA_ACCENT,
            components=[
                Text(content="To help us match you with the right clan and events, let’s set your timezone.\n\n"),
                Section(
                    components=[
                        Text(
                            content=(
                                f"{emojis.white_arrow_right}"
                                "**Find Your Time Zone**"
                            )
                        )
                    ],
                    accessory=LinkButton(
                        url="https://zones.arilyn.cc/",
                        label="Get My Time Zone 🌐",
                    ),
                ),
                Text(
                    content=(
                        "**Example format:** `America/New_York`\n"
                        "*Please don't just type GMT+1 or EST; use the link to get the correct format.*\n\n"
                        "Then simply type your timezone in chat, quick and easy!"
                    )
                ),
                Media(
                    items=[
                        MediaItem(media="assets/Red_Footer.png"),
                ]),
                Text(content="_Kings Alliance Recruitment – Syncing Schedules, Building Teams!_")
            ],
        )]
    await bot.rest.create_message(
        components=components,
        channel=ctx.channel_id,
        user_mentions = [user.id],
        role_mentions=True,
    )

### FWA Questions Section
@register_action("fwa_questions" ,no_return=True)
@lightbulb.di.with_di
async def fwa_questions(
    user_id: int,
    bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):

    ctx: lightbulb.components.MenuContext = kwargs.get("ctx")
    choice = ctx.interaction.values[0]
    user = await bot.rest.fetch_member(ctx.guild_id, user_id)

    if choice == "get_war_weight":
        components = [
            Container(
                accent_color=GOLD_ACCENT,
                components=[
                    Text(content=f"## ⚖️ **War Weight Check** · {user.mention}"),
                    Separator(divider=True),
                    Text(content=(
                        "We need your **current war weight** to ensure fair matchups. Please:\n\n"
                        f"{emojis.red_arrow_right} **Post** a Friendly Challenge in-game.\n"
                        f"{emojis.red_arrow_right} **Scout** that challenge you posted\n"
                        f"{emojis.red_arrow_right} **Tap** on your Town Hall, then hit **Info**.\n"
                        f"{emojis.red_arrow_right} **Upload** a screenshot of the Town Hall info_hub popup here.\n\n"
                        "*See the example below for reference.*"
                    )),
                    Media(
                        items=[
                            MediaItem(
                                media="https://res.cloudinary.com/dxmtzuomk/image/upload/v1751550804/TH_Weight.png"),
                        ]
                    ),
                    Text(content=f"-# Requested by {ctx.member.mention}"),
                ]
            )
        ]
    elif choice == "heard_of_lazy_cwl":
        components = [
            Container(
                accent_color=GOLD_ACCENT,
                components=[
                    Text(content=f"## 🛋️ **Lazy CWL Overview** · {user.mention}"),
                    Separator(divider=True),
                    Text(content=(
                        "Have you ever heard of **Lazy CWL** before? 🤔\n\n"
                        "**Lazy CWL** is our laid-back twist on Clan War Leagues,\n"
                        "designed for fun, flexibility, and zero stress.\n\n"
                        f"{emojis.white_arrow_right} **Have you played lazy CWL?**\n"
                        f"{emojis.white_arrow_right} **If so, what's your experience or understanding of it?**\n\n"
                    )),
                    Media(
                        items=[
                            MediaItem(media="assets/Gold_Footer.png")
                        ]),
                    Text(content=f"-# Requested by {ctx.member.mention}"),
                ]
            )
        ]
    elif choice == "lazy_cwl_explanation":
        components = [
            Container(
                accent_color=BLUE_ACCENT,
                components=[
                    Text(content=f"## 🛋️ **Lazy CWL Deep Dive** · {user.mention}"),
                    Separator(divider=True),
                    Text(content=(
                        "**What is Lazy CWL?**\n"
                        "We partner with **Warriors United** to run CWL in a laid-back, flexible way,\n"
                        "perfect if you’d otherwise go inactive during league week. \n"
                        "No stress over attacks or donations; just jump in when you can."
                    )),
                    Media(
                        items=[
                            MediaItem(media="assets/Blue_Footer.png")
                        ]),
                ]
            ),
            Container(
                accent_color=BLUE_ACCENT,
                components=[
                    Text(content=(
                        "**How It Works**\n"
                        f"{emojis.red_arrow_right} **Brand-New Clans**\n"
                        f"{emojis.blank}{emojis.white_arrow_right} Created each CWL season. Old clans reused in lower leagues.\n\n"
                        f"{emojis.red_arrow_right} **FWA Season Transition**\n"
                        f"{emojis.blank}{emojis.white_arrow_right} During the last **FWA War**, complete both attacks and **join your assigned CWL Clan** before the war ends.\n"
                        f"{emojis.blank}{emojis.white_arrow_right} Announcements will be posted to guide you.\n\n"
                        f"{emojis.red_arrow_right} **League Search**\n"
                        f"{emojis.blank}{emojis.white_arrow_right} Once everyone is in their assigned CWL Clan, we will start the search.\n"
                        f"{emojis.blank}{emojis.white_arrow_right} After the search begins, **return to your Home FWA Clan**  immediately.\n"
                    )),
                    Media(
                        items=[
                            MediaItem(media="assets/Blue_Footer.png")
                        ]),
                ]
            ),
            Container(
                accent_color=BLUE_ACCENT,
                components=[
                    Text(content=(
                        "**Participation & Rewards**\n"
                        f"{emojis.red_arrow_right} **Bonus Medals**\n"
                        f"{emojis.blank}{emojis.white_arrow_right} Medals are awarded through a lottery system.\n\n"
                        f"{emojis.red_arrow_right} **Participation Requirement**\n"
                        f"{emojis.blank}{emojis.white_arrow_right} Follow Lazy CWL Rules and complete **at least 4+ attacks (60%)**\n"
                    )),
                    Media(
                        items=[
                            MediaItem(media="assets/Blue_Footer.png")
                        ]),
                    Text(content=f"-# Requested by {ctx.member.mention}"),
                ]
            ),
            Container(
                accent_color=BLUE_ACCENT,
                components=[
                    Text(content=(
                        "**How to Sign Up**\n"
                        "If you **WANT to participate** in CWL, signing up is **mandatory!**\n\n"
                        f"{emojis.red_arrow_right} Sign up for **each CWL season** in <#1133030890189094932> or channel name #LazyCwl-Sign-ups , visible after joining the clan.\n\n"
                        f"{emojis.red_arrow_right} **Last-minute signups are strongly discouraged** and may not be accepted. We run several Lazy CWL clans, and proper planning is crucial.\n\n"
                    )),
                    Section(
                        components=[
                            Text(
                                content=(
                                    f"{emojis.white_arrow_right}"
                                    "**More Info**"
                                )
                            )
                        ],
                        accessory=LinkButton(
                            url="https://docs.google.com/document/d/13HrxwaUkenWZ4F1QNCPzdM5n5uXYcLqQYOdQzyQksuA/edit?tab=t.0",
                            label="Deep-Dive Lazy CWL Rules",
                        ),
                    ),
                    Text(content=(
                        "**<a:Alert_01:1043947615429070858>IMPORTANT:**\n"
                        "*Participating in CWL outside of Arcane is **__not allowed if__** you are part of our FWA Operation.*\n\n"
                    )),

                    Media(
                        items=[
                            MediaItem(media="https://c.tenor.com/MMuc_dX1D7AAAAAC/tenor.gif")
                        ]),
                    Text(content=f"-# Requested by {ctx.member.mention}"),
                ]
            )
        ]
    elif choice == "fwa_leaders_reviewing":
        components = [
            Container(
                accent_color=GOLD_ACCENT,
                components=[
                    Text(content=f"## 🔎 **FWA Leadership Review** · {user.mention}"),
                    Separator(divider=True),
                    Text(
                        content=(
                            "Thank you for applying! Our **FWA leadership team** is now reviewing your submission. "
                            "This can take a little time as we adjust rosters and to accommodate your application.\n\n"
                            "We kindly ask that you **do not ping anyone** during this time.\n"
                            "Rest assured, we are aware of your presence and will update you as soon as possible."
                        )
                    ),
                    Media(
                        items=[
                            MediaItem(media="assets/Gold_Footer.png")
                        ]),
                    Text(content=f"-# Requested by {ctx.member.mention}"),
                ]
            )
        ]
    elif choice == "fwa_bases_upon_approval":
        action_id = ctx.interaction.custom_id.split(":", 1)[1]

        fwa = await get_fwa_base_object(mongo)
        components = [
            Container(
                accent_color=BLUE_ACCENT,
                components=[
                    Text(content="## Select FWA Base Town Hall Level"),
                    Text(
                        content="Use the dropdown menu below to assign the appropriate Town Hall level for the recruit."),
                    ActionRow(
                        components=[
                            TextSelectMenu(
                                max_values=1,
                                custom_id=f"th_select:{action_id}",
                                placeholder="Select a Base...",
                                options=[
                                    SelectOption(
                                        emoji=emojis.TH18.partial_emoji,
                                        label="TH18",
                                        value="th18"
                                    ),
                                    SelectOption(
                                        emoji=emojis.TH18.partial_emoji,
                                        label="TH18 New",
                                        value="th18_new"
                                    ),
                                    SelectOption(
                                        emoji=emojis.TH17.partial_emoji,
                                        label="TH17",
                                        value="th17"
                                    ),
                                    SelectOption(
                                        emoji=emojis.TH17.partial_emoji,
                                        label="TH17 New",
                                        value="th17_new"
                                    ),
                                    SelectOption(
                                        emoji=emojis.TH16.partial_emoji,
                                        label="TH16",
                                        value="th16"
                                    ),
                                    SelectOption(
                                        emoji=emojis.TH16.partial_emoji,
                                        label="TH16 New",
                                        value="th16_new"
                                    ),
                                    SelectOption(
                                        emoji=emojis.TH15.partial_emoji,
                                        label="TH15",
                                        value="th15"
                                    ),
                                    SelectOption(
                                        emoji=emojis.TH14.partial_emoji,
                                        label="TH14",
                                        value="th14"
                                    ),
                                    SelectOption(
                                        emoji=emojis.TH13.partial_emoji,
                                        label="TH13",
                                        value="th13"
                                    ),
                                    SelectOption(
                                        emoji=emojis.TH12.partial_emoji,
                                        label="TH12",
                                        value="th12"
                                    ),
                                    SelectOption(
                                        emoji=emojis.TH11.partial_emoji,
                                        label="TH11",
                                        value="th11"
                                    ),
                                    SelectOption(
                                        emoji=emojis.TH10.partial_emoji,
                                        label="TH10",
                                        value="th10"
                                    ),
                                    SelectOption(
                                        emoji=emojis.TH9.partial_emoji,
                                        label="TH9",
                                        value="th9"
                                    ),
                                ],
                            ),
                        ]
                    ),
                    Media(
                        items=[
                            MediaItem(media="assets/Blue_Footer.png")
                        ]),
                    Text(content=f"-# Requested by {ctx.member.mention}"),
                ]
            )
        ]
        await ctx.respond(
            components=components,
            ephemeral=True,
        )

    if choice != "fwa_bases_upon_approval":
        await bot.rest.create_message(
            components=components,
            channel=ctx.channel_id,
            user_mentions = [user.id],
            role_mentions = True,
        )

    await asyncio.sleep(10)
    action_id = ctx.interaction.custom_id.split(":", 1)[1]
    new_components = await recruit_questions_page(
        action_id=action_id,
        user_id=user_id,
        ctx=ctx,
    )
    try:
        await ctx.interaction.delete_initial_response()
    except hikari.errors.NotFoundError:
        pass  # Interaction expired or already deleted, continue anyway
    await ctx.respond(
        components=new_components,
        ephemeral=True,
    )

@register_action("th_select" ,no_return=True)
@lightbulb.di.with_di
async def th_select(
    user_id: int,
    bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):

    ctx: lightbulb.components.MenuContext = kwargs.get("ctx")
    choice = ctx.interaction.values[0]
    user = await bot.rest.fetch_member(ctx.guild_id, user_id)
    fwa = await get_fwa_base_object(mongo)

    # Check if FWA data exists
    if not fwa:
        await ctx.respond(
            "❌ **FWA Data Not Found**\n\n"
            "The FWA data is not in the database yet. "
            "Please use the `/clan dashboard` command to add all FWA data first.",
            ephemeral=True
        )
        return

    # Format display name properly for _new variants
    if choice.endswith('_new'):
        base_th = choice.replace('_new', '')
        th_number = base_th.lstrip('th')
        display_name = f"TH{th_number} New"
        friendly_name = f"Town Hall {th_number} New"
    else:
        th_number = choice.lstrip('th')
        display_name = f"TH{th_number}"
        friendly_name = f"Town Hall {th_number}"

    base_link = getattr(fwa.fwa_base_links, choice, None)

    # Get base information for this TH level
    base_info = fwa.base_information.get(choice, "")
    if not base_info:
        base_info = (
            "In order to proceed further, we request that you switch your active war base to the link provided above.\n\n"
            "Once you have made the switch, please send us a screenshot like below to confirm the update."
        )

    # Check if base_link exists
    if not base_link:
        await ctx.respond(
            f"❌ **FWA Base Link Not Found**\n\n"
            f"The FWA base link for {display_name} is not configured in the database. "
            "Please use the `/clan dashboard` command to add all FWA base links.",
            ephemeral=True
        )
        return

    # Check if media URLs exist
    war_base_media = FWA_WAR_BASE.get(choice)
    active_war_base_media = FWA_ACTIVE_WAR_BASE.get(choice)

    if not war_base_media or not active_war_base_media:
        await ctx.respond(
            f"❌ **FWA Base Images Not Found**\n\n"
            f"The FWA base images for {display_name} are not configured. "
            "Please contact an administrator to add the FWA base images.",
            ephemeral=True
        )
        return

    # Get base information for this TH level
    base_info = fwa.base_information.get(choice, "")
    if not base_info:
        base_info = (
            "In order to proceed further, we request that you switch your active war base to the link provided above.\n\n"
            "Once you have made the switch, please send us a screenshot like below to confirm the update."
        )

    components = [
        Text(content=f"{user.mention}"),
        Container(
            accent_color=BLUE_ACCENT,
            components=[
                Text(content=f"## {friendly_name}"),
                Media(
                    items=[
                        MediaItem(media=FWA_WAR_BASE.get(choice, "")),
                    ]
                ),
                ActionRow(
                    components=[
                        LinkButton(
                            url=base_link,
                            label="Click Me!",
                        )
                    ]
                ),
            ]
        ),
        Container(
            accent_color=BLUE_ACCENT,
            components=[
                Text(content=f"### TH{th_number} FWA War Status and Base Layout"),
                Text(content=base_info),
                Media(
                    items=[
                        MediaItem(media=FWA_ACTIVE_WAR_BASE.get(choice, "")),
                    ]
                ),
                Text(content=f"-# Requested by {ctx.member.mention}"),
            ]
        )
    ]
    await bot.rest.create_message(
        components=components,
        channel=ctx.channel_id,
        user_mentions = [user.id],
        role_mentions=True,
    )

### Explanation Section
@register_action("explanations", no_return=True)
@lightbulb.di.with_di
async def explanations(
    user_id: int,
    bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    **kwargs
):

    ctx: lightbulb.components.MenuContext = kwargs.get("ctx")
    choice = ctx.interaction.values[0]
    user = await bot.rest.fetch_member(ctx.guild_id, user_id)

    if choice == "what_is_zen":
        components = [
            Container(
                accent_color=GREEN_ACCENT,
                components=[
                    Text(
                        content=f"## <:BabyYoda:1390465217997312234> **Zen War Clans: A Quick Overview** · {user.mention}"),
                    Separator(divider=True),
                    Text(content=(
                        "## Concept\n"
                        "We are a laid-back farm/war clan — **NOT A CAMPING CLAN**.\n"
                        "As Heroes are not required here, we understand that some may not feel confident to attack in war, "
                        "but we encourage everyone to find their Zen and make their war attacks. "
                        "Our ultimate goal? A stress-free, Zen-like experience.\n\n"
                        "## Purpose\n"
                        " Our goal is to cultivate a Zen war environment. "
                        "Here, heroes can be down, ensuring every member has the chance to partake in war attacks, "
                        "freeing the mind from the stress of sitting out due to hero upgrades.\n\n"
                        "## Core Rules\n"
                        "> **NOTE:** Each clan has their own set of unique Zen rules. This is **ONLY** a general rule. "
                        "Once you have been assigned to a clan, refer to your clan’s specific rules.\n"
                        f"{emojis.gold_arrow_right} **No camping Allowed:** This clan is dedicated to warring. Active participation is a must.\n"
                        f"{emojis.gold_arrow_right} **Minimum Participation:** Even with heroes down, every member is required to execute at least one war attack. "
                        "Failure to participate in war earns a strike. Accumulate enough strikes, and you risk replacement."
                    )),
                    Media(
                        items=[
                            MediaItem(media="assets/Green_Footer.png")
                        ]),
                ]
            ),
            Container(
                accent_color=GREEN_ACCENT,
                components=[
                    Text(content=(
                        "## War Strategy\n"
                        "**__First Attack__**\n"
                        f"{emojis.gold_arrow_right} **General Rule:** __Drop 2__ from your position.\n"
                        "*For instance, if you're at the 10th spot, target the 12th base.*\n"
                        "> Strictly adhere to this — neither attack higher nor lower.\n"
                        f"{emojis.gold_arrow_right} **Top 3 & Bottom 3 Players**\n"
                        f"{emojis.blank}{emojis.white_arrow_right} Attack your mirror.\n\n"
                        "**__What if My Target's Already 3-Starred?__**\n"
                        "Looks like my assigned target’s already three starred, switch to cleanup mode!\n\n"
                        "**__Second Attack__**\n"
                        f"{emojis.gold_arrow_right} General Rule: See Clan Specific Rules\n"
                        "A second attack isn’t required, but if it could help us win, we encourage you to support your clan by making that extra effort.\n"
                        "> Don’t be that guy who causes a war loss because you’re lazy... you’ll be on the chopping block!\n\n"
                        f"{emojis.blank}{emojis.white_arrow_right} **Top 3 players:**\n"
                        "> Clean up any of the top 5 bases that need it.\n\n"
                        f"{emojis.blank}{emojis.white_arrow_right} **Everyone Else**\n"
                        "__Option 1: Cleanup__\n"
                        "Use your second attack to **__clean up a base that’s already been hit__** and grab those extra stars ⭐️⭐️⭐️\n\n"
                        "__Option 2: Free-for-All__\n"
                        "**__Wait until 12 hours remain__** then it’s a **free-for-all**. Pick any base you’re confident you can **⭐️⭐️⭐️**"
                    )),
                    Media(
                        items=[
                            MediaItem(media="assets/Green_Footer.png")
                        ]),
                ]
            ),
            Container(
                accent_color=GREEN_ACCENT,
                components=[
                    Text(content=(
                        "## Strike System\n"
                        f"{emojis.gold_arrow_right} Zen Clans expect participation in wars, clan games, raid weekends, and other clan activities to stay active.\n"
                        f"{emojis.gold_arrow_right} Strike rules vary by clan (e.g., 1 or 2 war attacks).\n"
                        f"{emojis.gold_arrow_right} The norm is 4 strikes leading to removal, but check your clan's specific rules.\n"
                    )),
                    Media(
                        items=[
                            MediaItem(media="https://c.tenor.com/58O460v-6nEAAAAC/tenor.gif")
                        ]),
                    Text(content=f"-# Requested by {ctx.member.mention}"),
                ]
            )
        ]
    elif choice == "what_is_fwa":
        components = [
            Container(
                accent_color=BLUE_ACCENT,
                components=[
                    Text(content=f"## <a:FWA:1387882523358527608> **FWA Clans Quick Overview** · {user.mention}"),
                    Separator(divider=True),
                    Text(content=(
                        "## 📌 FWA Clans in Clash of Clans: A Quick Overview\n"
                        f"> Minimum TH for FWA: TH13 {emojis.TH13}\n\n"
                        "FWA, or Farm War Alliance, is a unique concept in Clash of Clans. It's all about maximizing loot and clan XP, rather than focusing solely on winning wars.\n\n"
                        "### **__<a:FWA:1387882523358527608> What are the benefits?__**\n"
                        "**<:Money_Gob:1024851096847519794> Maximized Loot and XP**\n"
                        "FWA clans aim to ensure a steady stream of resources and XP, perfect for upgrading bases, troops, and heroes.\n\n"
                        "**<a:sleep_zzz:1125067436601901188> War Participation with Upgrading Heroes**\n"
                        "Unlike traditional wars, in FWA you can participate even if your heroes are down for upgrades, making continuous progress possible.\n\n"
                        "**<:CoolOP:1024001628979855360> Fair Wars**\n"
                        "War winners are decided via a lottery system, ensuring fair chances and significant loot for both sides.\n\n"
                        "**<:Waiting:1318704702443094150> Is it against the rules?**"
                        "No, as long as FWA clans follow the game rules and don't use any hacks or exploits, they are within the game's terms of service. It's a unique and accepted way of playing the game."
                    )),
                    Media(
                        items=[
                            MediaItem(media="assets/Blue_Footer.png")
                        ]),
                ]
            ),
            Container(
                accent_color=BLUE_ACCENT,
                components=[
                    Text(content=(
                        "## ⚔️ FWA War Plans ⚔️\n"
                        "Below are your two main war plans for FWA. Follow these and all will be good\n"
                        "### 💎 WIN WAR💎\n"
                        "__1st hit:__⭐️⭐️⭐️ star your mirror.\n"
                        "__2nd hit:__⭐️⭐️ BASE #1 or any base above you for loot or wait for 8 hr cleanup call in Discord.\n"
                        "**Goal is 150 Stars!**\n\n"
                        "### ❌ LOSE WAR ❌\n"
                        "__1st hit:__⭐️⭐️star your mirror.\n"
                        "__2nd hit:__⭐️BASE #1 or any base above you for loot or wait for 8 hr cleanup call in Discord.\n"
                        "**Goal is 100 Stars!**\n\n"
                        "War Plans are posted via Discord and Clan Mail. Don't hesitate to ping an __FWA Clan Rep__ in your Clan's Chat Channel with any questions you may have."
                    )),
                    Media(
                        items=[
                            MediaItem(media="assets/Blue_Footer.png")
                        ]),
                ]
            ),
            Container(
                accent_color=BLUE_ACCENT,
                components=[
                    Text(content=(
                        "## 🏰 Default FWA Base 🏰\n"
                        "Below is a picture of a TH13 default FWA War Base. Each TH Level is similar with the major difference being TH12+ where the TH is separate. It's a simple layout that allows you to strategically attack for a certain star count but still maximize the most loot available."
                    )),
                    Media(
                        items=[
                            MediaItem(
                                media="https://res.cloudinary.com/dxmtzuomk/image/upload/v1751616880/Default_FWA_Base.jpg")
                        ]),
                    Text(content=f"-# Requested by {ctx.member.mention}"),
                ]
            )
        ]
    elif choice == "fwa_war_plans":
        components = [
            Container(
                accent_color=DARK_MAGENTA_ACCENT,
                components=[
                    Text(content=f"## ⚔️ **FWA War Plans** ⚔️ · {user.mention}"),
                    Separator(divider=True),
                    Text(content=(
                        "Below are your two main war plans for FWA. Follow these and all will be good.\n\n"
                        "**💎 __WIN WAR__ 💎**\n"
                        "1st hit: ⭐⭐⭐ star your mirror.\n"
                        "2nd hit: ⭐⭐ BASE 1 for loot or any base above you for loot or wait for 8 hr cleanup call in Discord. "
                        "**Goal is 150 Stars!!**\n\n"
                        "**❌ __LOSE WAR__ ❌**\n"
                        "1st hit: ⭐⭐ star your mirror.\n"
                        "2nd hit: ⭐ BASE 1 for loot or wait for 8 hr cleanup call in Discord. The goal is 100 Stars!\n\n"
                        "There are two other plans \"Blacklisted War\" and \"Mismatch War\" but the above two are the most used.\n\n"
                        "War Plans are posted via Discord and Clan Mail. Don't hesitate to ping me in your Clan's Chat Channel "
                        "with any questions you may have.\n\n"
                        "Following the posted war plans is an important part of FWA. Deviation can cause headaches and potentially "
                        "harm to the clan. **Don't be \"that guy\"**...🫡"
                    )),
                    Media(
                        items=[
                            MediaItem(media="assets/Blue_Footer.png")
                        ]),
                ]
            ),
            Container(
                accent_color=DARK_MAGENTA_ACCENT,
                components=[
                    Text(content="## ⚔️ **DAILY FWA EXPECTATIONS** ⚔️"),
                    Separator(divider=True),
                    Text(content=(
                        "✅ **Attack in wars. Every. Single. Time.**\n"
                        "✅ **Follow posted war plans. They're not suggestions—they're the playbook.**\n"
                        "✅ **Check Discord & Clan Mail for instructions.**\n\n"
                        "Wondering what happens if you ghost a war?\n"
                        "👻 **You land on the Naughty List.**\n"
                        "That means we start looking for a replacement. No hard feelings, just FWA business.\n\n"
                        "Let's keep it fun, but let's keep it serious too. 💥"
                    )),
                    Media(
                        items=[
                            MediaItem(media="https://media1.giphy.com/media/v1.Y2lkPTc5MGI3NjExMjg1amo0dmdsa2lpbnB3NzAzOWhsYWkyczRuNGwwdmRiZHpxb3YxNiZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/3o6ZtnrDUtbqynaOys/giphy.gif")
                        ]),
                    Text(content=f"-# Requested by {ctx.member.mention}"),
                ]
            )
        ]
    elif choice == "wu_fwa_partner":
        components = [
            Container(
                accent_color=DARK_MAGENTA_ACCENT,
                components=[
                    Text(content=f"## 🤝 **FWA Partner Invitation** · {user.mention}"),
                    Separator(divider=True),
                    Text(
                        content=(
                            "Instead of keeping you on our FWA wait-list, we'd love to invite you directly to our partner server\n"
                            "**Warriors United**! 🎖️\n\n"
                            "Click the button below to join their Discord, complete the intro, and open an **FWA Entry Ticket**."
                        )),
                    Media(
                        items=[
                            MediaItem(
                                media="https://res.cloudinary.com/dxmtzuomk/image/upload/v1751617812/Warriors_United.gif")
                        ]),
                    ActionRow(
                        components=[
                            LinkButton(
                                url="https://discord.gg/2edDGBStax",
                                label="Click Me",
                            )
                        ]
                    ),
                ]
            ),
        ]
    await bot.rest.create_message(
        components=components,
        channel=ctx.channel_id,
        user_mentions = [user.id],
        role_mentions=True,
    )

    await asyncio.sleep(10)
    action_id = ctx.interaction.custom_id.split(":", 1)[1]
    new_components = await recruit_questions_page(
        action_id=action_id,
        user_id=user_id,
        ctx=ctx,
    )
    try:
        await ctx.interaction.delete_initial_response()
    except hikari.errors.NotFoundError:
        pass  # Interaction expired or already deleted, continue anyway
    await ctx.respond(
        components=new_components,
        ephemeral=True,
    )


### HURRY TF UP Section
@register_action("keep_it_moving", no_return=True)
@lightbulb.di.with_di
async def keep_it_moving(
    user_id: int,
    bot: hikari.GatewayBot = lightbulb.di.INJECTED,
    **kwargs
):

    ctx: lightbulb.components.MenuContext = kwargs.get("ctx")
    choice = ctx.interaction.values[0]
    user = await bot.rest.fetch_member(ctx.guild_id, user_id)

    if choice == "waiting_response":
        components = [
            Text(content=f"{user.mention}"),
            Container(
                accent_color=DARK_MAGENTA_ACCENT,
                components=[
                    Text(
                        content=(
                            "At this rate, I’ll finish my snack and a three-course meal. Any day now... 🥪⏳\n"
                        )),
                    Media(
                        items=[
                            MediaItem(
                                media="https://c.tenor.com/E4TulgtK2ssAAAAC/tenor.gif")
                        ]),
                ]
            ),
        ]
    elif choice == "circles":
        components = [
            Text(content=f"{user.mention}"),
            Container(
                accent_color=DARK_MAGENTA_ACCENT,
                components=[
                    Text(
                        content=(
                            "Waiting for your response like: round and round we go… Any time now! 🌀⏳\n"
                        )),
                    Media(
                        items=[
                            MediaItem(
                                media="https://c.tenor.com/NcibGDKTKQAAAAAd/tenor.gif")
                        ]),
                ]
            ),
        ]
    elif choice == "today":
        components = [
            Text(content=f"{user.mention}"),
            Container(
                accent_color=DARK_MAGENTA_ACCENT,
                components=[
                    Text(
                        content=(
                            "Still waiting like it’s the DMV. T-t-t-today junior, the clan’s got places to be! 🕰️🚦\n"
                        )),
                    Media(
                        items=[
                            MediaItem(
                                media="https://c.tenor.com/je0FzJYReA0AAAAd/tenor.gif")
                        ]),
                ]
            ),
        ]
    elif choice == "chop_chop":
        components = [
            Text(content=f"{user.mention}"),
            Container(
                accent_color=DARK_MAGENTA_ACCENT,
                components=[
                    Text(
                        content=(
                            "Dragging this out won’t end well for anyone. Chop-chop, before I start sharpening the knives... 🔪⏳\n"
                        )),
                    Media(
                        items=[
                            MediaItem(
                                media="https://c.tenor.com/Q0fmnnIHcRoAAAAC/tenor.gif")
                        ]),
                ]
            ),
        ]
    await bot.rest.create_message(
        components=components,
        channel=ctx.channel_id,
        user_mentions = [user.id],
        role_mentions=True,
    )

    await asyncio.sleep(10)
    action_id = ctx.interaction.custom_id.split(":", 1)[1]
    new_components = await recruit_questions_page(
        action_id=action_id,
        user_id=user_id,
        ctx=ctx,
    )
    try:
        await ctx.interaction.delete_initial_response()
    except hikari.errors.NotFoundError:
        pass  # Interaction expired or already deleted, continue anyway
    await ctx.respond(
        components=new_components,
        ephemeral=True,
    )

async def recruit_questions_page(
    action_id: str,
    user_id: int,
    **kwargs
):
    components = [
        Container(
            accent_color=DARK_MAGENTA_ACCENT,
            components=[
                Text(content=(
                    "An all-in-one toolkit to efficiently recruit candidates into the Kings Alliance.\n\n"
                    f"{emojis.red_arrow_right} Primary Questions: Send tailored candidate questions.\n"
                    f"{emojis.red_arrow_right} Explanations: Summarise FWA, Zen & Alliance essentials.\n"
                    f"{emojis.red_arrow_right} FWA Questions: Send core FWA questions.\n"
                    f"{emojis.red_arrow_right} Keep It Moving: Send quick “hurry up” GIFs.\n\n"
                    "Stay organized, efficient, and aligned with Kings recruitment standards.\n\n"
                )),
                ActionRow(
                    components=[
                        TextSelectMenu(
                            max_values=1,
                            custom_id=f"primary_questions:{action_id}",
                            placeholder="Primary Questions",
                            options=[
                                SelectOption(
                                    emoji=1387846413211402352,
                                    label="Attack Strategies",
                                    value="attack_strategies"),
                                SelectOption(
                                    emoji=1387846432316194837,
                                    label="Future Clan Expectations",
                                    value="future_clan_expectations"),
                                SelectOption(
                                    emoji=1387846461672132649,
                                    label="Discord Basic Skills",
                                    value="discord_basic_skills"),
                                SelectOption(
                                    emoji=1387846482220159168,
                                    label="Discord Basic Skills pt.2",
                                    value="discord_basic_skills_2"),
                                SelectOption(
                                    emoji=1387846506589061220,
                                    label="Age Bracket & Timezone",
                                    value="age_bracket_&_timezone"),
                                SelectOption(
                                    emoji=1387846529229787246,
                                    label="Leaders Checking You Out",
                                    value="leaders_checking_you_out"),
                    ]),
                ]),
                ActionRow(
                    components=[
                        TextSelectMenu(
                            max_values=1,
                            custom_id=f"fwa_questions:{action_id}",
                            placeholder="FWA Questions",
                            options=[
                                SelectOption(
                                    emoji="⚖️",
                                    label="Get War Weight",
                                    value="get_war_weight"
                                ),
                                SelectOption(
                                    emoji=1157399772018249828,
                                    label="Heard of Lazy CWL?",
                                    value="heard_of_lazy_cwl"
                                ),
                                SelectOption(
                                    emoji=1004110859729125466,
                                    label="Lazy CWL Explanation",
                                    value="lazy_cwl_explanation"
                                ),
                                SelectOption(
                                    emoji=1001907873170849792,
                                    label="FWA Leaders Reviewing",
                                    value="fwa_leaders_reviewing"
                                ),
                                SelectOption(
                                    emoji=1387844788853801081,
                                    label="FWA Bases (Upon Approval)",
                                    value="fwa_bases_upon_approval"
                                ),
                            ],
                        ),
                    ]
                ),
                ActionRow(
                    components=[
                        TextSelectMenu(
                            max_values=1,
                            custom_id=f"explanations:{action_id}",
                            placeholder="Explanations",
                            options=[
                                SelectOption(
                                    emoji=1390465217997312234,
                                    label="What is Zen",
                                    value="what_is_zen"
                                ),
                                SelectOption(
                                    emoji=1387882523358527608,
                                    label="What is FWA",
                                    value="what_is_fwa"
                                ),
                                SelectOption(
                                    emoji="⚔️",
                                    label="FWA War Plans",
                                    value="fwa_war_plans"
                                ),
                                SelectOption(
                                    emoji=1390465929632153640,
                                    label="WU FWA Partner",
                                    value="wu_fwa_partner"
                                ),
                            ],
                        ),
                    ]
                ),
                ActionRow(
                    components=[
                        TextSelectMenu(
                            max_values=1,
                            custom_id=f"keep_it_moving:{action_id}",
                            placeholder="Keep It Moving",
                            options=[
                                SelectOption(
                                    emoji=1318704702443094150,
                                    label="Waiting for Response...",
                                    value="waiting_response"
                                ),
                                SelectOption(
                                    emoji=999526289738317834,
                                    label="Going in Circles...",
                                    value="circles"
                                ),
                                SelectOption(
                                    emoji=1231080049332191305,
                                    label="Today Jr...",
                                    value="today"
                                ),
                                SelectOption(
                                    emoji=1390616848730685500,
                                    label="Chop Chop...",
                                    value="chop_chop"
                                ),
                            ],
                        ),
                    ]
                ),
                Text(content="-# Kings Alliance - Where Legends Are Made"),
                Media(
                    items=[
                        MediaItem(media="assets/Red_Footer.png")
                ]),
            ]),
        ]

    return components