import lightbulb
import hikari
import uuid

from hikari.impl import (
    MessageActionRowBuilder as ActionRow,
    TextSelectMenuBuilder as TextSelectMenu,
    SelectOptionBuilder as SelectOption,
    ContainerComponentBuilder as Container,
    SectionComponentBuilder as Section,
    TextDisplayComponentBuilder as Text,
    SeparatorComponentBuilder as Separator,
    MediaGalleryComponentBuilder as Media,
    MediaGalleryItemBuilder as MediaItem,
    ThumbnailComponentBuilder as Thumbnail,
    LinkButtonBuilder as LinkButton,
)

from extensions.components import register_action
from utils.constants import BLUE_ACCENT, GOLD_ACCENT, GREEN_ACCENT, DARK_MAGENTA_ACCENT
from utils.mongo import MongoClient

loader = lightbulb.Loader()

# Define all color roles with their properties
# This structure makes it easy to add, remove, or modify colors
COLOR_ROLES = {
    "yellow": {
        "name": "Yellow",
        "role_id": 1022637567146999878,
        "emoji_id": 1387847401028718644,
        "emoji_name": "Yellow",  # Exact name in dev portal
        "hex": 0xFFD700
    },
    "lightblue": {
        "name": "Light Blue",
        "role_id": 1022640747591254108,
        "emoji_id": 1387847364198531092,
        "emoji_name": "LightBlue",  # No spaces in emoji name
        "hex": 0xADD8E6
    },
    "bubblegumpink": {
        "name": "Bubblegum Pink",
        "role_id": 1022544379170279504,
        "emoji_id": 1387847332237938761,
        "emoji_name": "BubblegumPink",  # No spaces in emoji name
        "hex": 0xFFC0CB
    },
    "pink": {
        "name": "Pink",
        "role_id": 1022639587409010708,
        "emoji_id": 1387847307281563690,
        "emoji_name": "Pink",
        "hex": 0xFF69B4
    },
    "purple": {
        "name": "Purple",
        "role_id": 1022638009981620235,
        "emoji_id": 1387847286314242062,
        "emoji_name": "Purple",
        "hex": 0x800080
    },
    "amethyst": {
        "name": "Amethyst",
        "role_id": 1023785650014650430,
        "emoji_id": 1387847266852929656,
        "emoji_name": "Amethyst",
        "hex": 0x9966CC
    },
    "red": {
        "name": "Red",
        "role_id": 1022635311337050142,
        "emoji_id": 1387847242165256284,
        "emoji_name": "Red",
        "hex": 0xFF0000
    },
    "ruby": {
        "name": "Ruby",
        "role_id": 1023786543497871411,
        "emoji_id": 1387847220904071390,
        "emoji_name": "Ruby",
        "hex": 0xE0115F
    },
    "androidgreen": {
        "name": "Android Green",
        "role_id": 1024028481102823546,
        "emoji_id": 1387847189673410674,
        "emoji_name": "AndroidGreen",  # No spaces in emoji name
        "hex": 0x3DDC84
    },
    "whiteblue": {
        "name": "White Blue",
        "role_id": 1384965010987679775,
        "emoji_id": 1387847165824602343,
        "emoji_name": "WhiteBlue",  # No spaces in emoji name
        "hex": 0xF0F8FF
    },
    "black": {
        "name": "Black",
        "role_id": 1023954793317802074,
        "emoji_id": 1387847144630784080,
        "emoji_name": "Black",
        "hex": 0x000000
    },
    "white": {
        "name": "White",
        "role_id": 1023954710031515719,
        "emoji_id": 1387847122375671839,
        "emoji_name": "White",
        "hex": 0xFFFFFF
    }
}


@loader.command
class ColorCommand(
    lightbulb.SlashCommand,
    name="color-roles",
    description="Choose your display color from the dropdown below",
):
    @lightbulb.invoke
    @lightbulb.di.with_di
    async def invoke(
            self,
            ctx: lightbulb.Context,
            mongo: MongoClient = lightbulb.di.INJECTED,
    ) -> None:
        # Defer immediately to avoid timeout
        await ctx.defer(ephemeral=True)

        # Create action ID and store in MongoDB
        action_id = str(ctx.interaction.id)
        data = {
            "_id": action_id,
            "user_id": ctx.user.id
        }
        await mongo.button_store.insert_one(data)

        # Build the select options from our color roles dictionary
        options = []
        for key, color in COLOR_ROLES.items():
            options.append(
                SelectOption(
                    emoji=color["emoji_id"],
                    label=color["name"],
                    value=key,
                    description=f"Change your colour to {color['name']}"
                )
            )

        # Build components following your project patterns
        components = [
            Container(
                accent_color=DARK_MAGENTA_ACCENT,
                components=[
                    Text(content=(
                        "### 🎨 Choose Your Colour\n"
                        "Select a color from the dropdown below to change your color.\n"
                        "You can only have one color at a time!"
                    )),
                    Separator(divider=True, spacing=hikari.SpacingType.SMALL),
                    ActionRow(
                        components=[
                            TextSelectMenu(
                                custom_id=f"color_select:{action_id}",
                                placeholder="Select a colour...",
                                max_values=1,
                                options=options
                            )
                        ]
                    ),
                    Media(
                        items=[
                            MediaItem(media="assets/Red_Footer.png")
                        ]
                    )
                ]
            )
        ]

        # Respond with the components
        await ctx.respond(components=components, ephemeral=True)


@register_action("color_select", no_return=True)
@lightbulb.di.with_di
async def on_color_selected(
        action_id: str,
        user_id: int,
        bot: hikari.GatewayBot = lightbulb.di.INJECTED,
        mongo: MongoClient = lightbulb.di.INJECTED,
        **kwargs
):
    """Handle color selection from the dropdown menu"""
    ctx: lightbulb.components.MenuContext = kwargs["ctx"]
    selected_value = ctx.interaction.values[0]

    # Get the selected color from our dictionary
    selected_color = COLOR_ROLES.get(selected_value)
    if not selected_color:
        return

    # Get member and check current roles
    member = ctx.member
    current_roles = set(member.role_ids)

    # Check if user already has the selected color
    has_selected_color = selected_color["role_id"] in current_roles

    # Find all color roles the user currently has
    current_color_roles = []
    for key, color in COLOR_ROLES.items():
        if color["role_id"] in current_roles and key != selected_value:
            current_color_roles.append(color)

    # Build response message based on what actions we're taking
    messages = []

    if has_selected_color:
        # User is clicking the same color they already have - remove it
        await bot.rest.remove_role_from_member(
            guild=ctx.guild_id,
            user=member.id,
            role=selected_color["role_id"]
        )
        messages.append(
            f"<:{selected_color['name']}:{selected_color['emoji_id']}> **{selected_color['name']}** removed!")
        accent_color = DARK_MAGENTA_ACCENT
    else:
        # Remove any existing color roles first
        for color in current_color_roles:
            await bot.rest.remove_role_from_member(
                guild=ctx.guild_id,
                user=member.id,
                role=color["role_id"]
            )
            messages.append(f"<:{color['emoji_name']}:{color['emoji_id']}> **{color['name']}** removed")

        # Add the new color role
        await bot.rest.add_role_to_member(
            guild=ctx.guild_id,
            user=member.id,
            role=selected_color["role_id"]
        )
        messages.append(
            f"<:{selected_color['emoji_name']}:{selected_color['emoji_id']}> **{selected_color['name']}** added!")
        accent_color = selected_color["hex"]

    # Format the response text
    response_text = "\n".join(messages)

    # Create response components
    response_components = [
        Container(
            accent_color=accent_color,
            components=[
                Text(content=(
                    "## ✨ Color Updated\n\n"
                    f"{response_text}"
                )),
                Separator(divider=True, spacing=hikari.SpacingType.SMALL),
                Text(content="_You can dismiss this message or select another color._"),
                Media(
                    items=[
                        MediaItem(media="assets/Red_Footer.png")
                    ]
                ),
            ]
        )
    ]

    # Delete the original interaction
    await ctx.interaction.delete_initial_response()

    # Send update message
    await ctx.respond(components=response_components, ephemeral=True)

    # Recreate the color selector with all options
    options = []
    for key, color in COLOR_ROLES.items():
        options.append(
            SelectOption(
                emoji=color["emoji_id"],
                label=color["name"],
                value=key,
                description=f"Change your colour to {color['name']}"
            )
        )

    new_components = [
        Container(
            accent_color=DARK_MAGENTA_ACCENT,
            components=[
                Text(content=(
                    "### 🎨 Choose Your Color\n"
                    "Select a color from the dropdown below to change your display color.\n"
                    "You can only have one color at a time!"
                )),
                Separator(divider=True, spacing=hikari.SpacingType.SMALL),
                ActionRow(
                    components=[
                        TextSelectMenu(
                            custom_id=f"color_select:{action_id}",
                            placeholder="Select a color...",
                            max_values=1,
                            options=options
                        )
                    ]
                ),
                Media(
                    items=[
                        MediaItem(media="assets/Red_Footer.png")
                    ]
                ),
            ]
        )
    ]

    # Respond with new components
    await ctx.respond(
        components=new_components,
        ephemeral=True
    )