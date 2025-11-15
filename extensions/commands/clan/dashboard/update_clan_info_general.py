import typing

import lightbulb
import pymongo
import hikari
import coc
import re
from PIL import Image
from io import BytesIO
import requests

from hikari.impl import (
    MessageActionRowBuilder as ActionRow,
    TextSelectMenuBuilder as TextSelectMenu,
    SelectMenuBuilder as SelectMenu,
    SelectOptionBuilder as SelectOption,
    ContainerComponentBuilder as Container,
    SectionComponentBuilder as Section,
    InteractiveButtonBuilder as Button,
    TextDisplayComponentBuilder as Text,
    SeparatorComponentBuilder as Separator,
    ThumbnailComponentBuilder as Thumbnail,
    MediaGalleryComponentBuilder as Media,
    MediaGalleryItemBuilder as MediaItem,
    ModalActionRowBuilder as ModalActionRow
)
from lightbulb import channel
from lightbulb.components import MenuContext, ModalContext
from utils.emoji import EmojiType
from extensions.autocomplete import clan_types
from utils.constants import DARK_MAGENTA_ACCENT ,CLAN_TYPES ,TH_LEVELS ,CLAN_STATUS ,TH_ATTRIBUTE
from utils.emoji import emojis
from extensions.components import register_action
from utils.mongo import MongoClient
from utils.classes import Clan

# 2) Modal‐submit (handles the data)
import re

@register_action("update_general_info", ephemeral=True)
@lightbulb.di.with_di
async def update_general_info_panel(
        ctx: MenuContext,
        action_id: str,               # clan tag
        mongo: MongoClient = lightbulb.di.INJECTED,
        **kwargs
):
    tag = action_id
    raw = await mongo.clans.find_one({"tag": tag})
    if not raw:
        await ctx.respond("❌ Clan not found!", ephemeral=True)

    db_clan = Clan(data=raw)
    components = [
        Container(
            accent_color=DARK_MAGENTA_ACCENT,
            components=[
                Text(content=f"## ✏️ **Editing {db_clan.name}** (`{db_clan.tag}`)"),
                Separator(divider=True, spacing=hikari.SpacingType.LARGE),
                Text(content=f"{emojis.white_arrow_right}**Clan Type:** {db_clan.type or '⚠️ Missing'}\n"),
                ActionRow(components=[
                    TextSelectMenu(
                        custom_id=f"edit_general:type_{tag}",
                        placeholder="Select the clan type…",
                        min_values=1,
                        max_values=1,
                        options=[
                            SelectOption(label=ctype, value=ctype)
                            for ctype in CLAN_TYPES
                        ],
                    )
                ]),
                Text(content=f"{emojis.white_arrow_right}**Clan Status:** {db_clan.status or '⚠️ Missing'}\n"),
                ActionRow(components=[
                    TextSelectMenu(
                        custom_id=f"edit_general:status_{tag}",
                        placeholder="Select the clan status…",
                        min_values=1,
                        max_values=1,
                        options=[
                            SelectOption(label=ctype, value=ctype)
                            for ctype in CLAN_STATUS
                        ],
                    )
                ]),
                Text
                (content=f"{emojis.white_arrow_right}**TH Requirement:** {db_clan.th_requirements or '⚠️ Missing'}\n"),
                ActionRow(components=[
                    TextSelectMenu(
                        custom_id=f"edit_general:th_requirements_{tag}",
                        placeholder="Select the TH requirement…",
                        min_values=1,
                        max_values=1,
                        options=[
                            SelectOption(label=f"{lvl}", value=lvl)
                            for lvl in reversed(TH_LEVELS)
                        ],
                    )
                ]),
                Text(content=f"{emojis.white_arrow_right}**TH Attribute:** {db_clan.th_attribute or '⚠️ Missing'}\n"),
                ActionRow(components=[
                    TextSelectMenu(
                        custom_id=f"edit_general:th_attribute_{tag}",
                        placeholder="Select the TH Attribute…",
                        min_values=1,
                        max_values=1,
                        options=[
                            SelectOption(label=ctype, value=ctype)
                            for ctype in TH_ATTRIBUTE
                        ],
                    )
                ]),
                Separator(divider=True, spacing=hikari.SpacingType.LARGE),
                ActionRow(components=[
                    Button(
                        style=hikari.ButtonStyle.SECONDARY,
                        custom_id=f"back_to_clan_edit:{tag}",
                        label="← Back to Edit Menu",
                    )
                ]),
                Media(items=[MediaItem(media="assets/Red_Footer.png")]),
            ],
        )
    ]
    return components

@register_action("edit_general", no_return=True, ephemeral=True)
@lightbulb.di.with_di
async def on_edit_general(
        ctx: MenuContext,
        action_id: str,
        mongo: MongoClient = lightbulb.di.INJECTED,
        **kwargs
):
    field, tag = action_id.rsplit("_", 1)
    selected = ctx.interaction.values[0]

    await mongo.clans.update_one({"tag": tag}, {"$set": {field: selected}})

    new_components = await update_general_info_panel(
        ctx=ctx,
        action_id=tag,
        mongo=mongo
    )
    await ctx.interaction.edit_initial_response(components=new_components)

@register_action("back_to_clan_edit", ephemeral=True, no_return=True)
@lightbulb.di.with_di
async def back_to_clan_edit(
    ctx: MenuContext,
    action_id: str,              # the tag
    mongo: MongoClient = lightbulb.di.INJECTED,
    **kwargs
):
    # Dynamically import the original menu
    from extensions.commands.clan.dashboard.update_clan_info import clan_edit_menu

    # Call the undecorated function to get fresh components
    components = await clan_edit_menu.__wrapped__(
        ctx,
        action_id=action_id,
        mongo=mongo,
        tag=action_id,
    )

    # Replace the current view
    await ctx.interaction.edit_initial_response(components=components)
