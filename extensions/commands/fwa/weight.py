import lightbulb
import hikari

from extensions.commands.fwa import fwa
from utils.constants import BLUE_ACCENT, GOLD_ACCENT, GREEN_ACCENT, DARK_MAGENTA_ACCENT
from utils.emoji import emojis

from hikari.impl import (
    ContainerComponentBuilder as Container,
    TextDisplayComponentBuilder as Text,
    SeparatorComponentBuilder as Separator,
    MediaGalleryComponentBuilder as Media,
    MediaGalleryItemBuilder as MediaItem,
)

# War weight ranges configuration (TH9 and up only)
WAR_WEIGHT_RANGES = {
    9: {"min": 56000, "max": 70000, "display": "56k - 70k"},
    10: {"min": 71000, "max": 90000, "display": "71k - 90k"},
    11: {"min": 91000, "max": 110000, "display": "91k - 110k"},
    12: {"min": 111000, "max": 120000, "display": "111k - 120k"},
    13: {"min": 121000, "max": 130000, "display": "121k - 130k"},
    14: {"min": 131000, "max": 140000, "display": "131k - 140k"},
    15: {"min": 141000, "max": 150000, "display": "141k - 150k"},
    16: {"min": 151000, "max": 160000, "display": "151k - 160k"},
    17: {"min": 161000, "max": 170000, "display": "161k - 170k"},
}


def determine_town_hall(total_weight: int) -> tuple[int | None, str, int]:
    """
    Determine town hall level from total war weight.
    Returns: (th_level, status, color)
    Status can be: 'exact', 'below', 'above', 'between'
    """
    # Check if below TH9 minimum
    if total_weight < 56000:
        return None, "below", DARK_MAGENTA_ACCENT

    # Check if above TH17 maximum
    if total_weight > 170000:
        return None, "above", DARK_MAGENTA_ACCENT

    # Find exact match
    for th_level, range_data in WAR_WEIGHT_RANGES.items():
        if range_data["min"] <= total_weight <= range_data["max"]:
            return th_level, "exact", GREEN_ACCENT

    # Find between ranges
    for th_level in sorted(WAR_WEIGHT_RANGES.keys()):
        if total_weight < WAR_WEIGHT_RANGES[th_level]["min"]:
            return th_level - 1, "between", GOLD_ACCENT

    return None, "unknown", DARK_MAGENTA_ACCENT


def get_th_emoji(th_level: int) -> str:
    """Get the appropriate TH emoji or fallback."""
    if th_level is None:
        return "❓"

    emoji_attr = f"TH{th_level}"
    if hasattr(emojis, emoji_attr):
        return str(getattr(emojis, emoji_attr))
    return "🏛️"


def calculate_position_in_range(weight: int, th_level: int) -> int:
    """Calculate percentage position within TH range."""
    if th_level not in WAR_WEIGHT_RANGES:
        return 0

    range_data = WAR_WEIGHT_RANGES[th_level]
    range_size = range_data["max"] - range_data["min"]
    position = weight - range_data["min"]
    return int((position / range_size) * 100)


def format_weight_reference_guide(current_weight: int, current_th: int | None) -> str:
    """Format the complete weight reference guide."""
    lines = []

    for th_level, range_data in sorted(WAR_WEIGHT_RANGES.items()):
        emoji = get_th_emoji(th_level)
        display = range_data["display"]

        # Highlight current TH level
        if th_level == current_th:
            lines.append(f"{emoji} **{display} (TH{th_level})** ← You are here")
        else:
            lines.append(f"{emoji} {display} (TH{th_level})")

    return "\n".join(lines)


def get_upgrade_info(weight: int, th_level: int | None) -> str:
    """Get information about upgrading to next TH level."""
    if th_level is None or th_level >= 17:
        return ""

    next_th = th_level + 1
    if next_th in WAR_WEIGHT_RANGES:
        next_min = WAR_WEIGHT_RANGES[next_th]["min"]
        weight_needed = next_min - weight
        if weight_needed > 0:
            return f"• {weight_needed:,} weight away from TH{next_th} range"

    return ""


@fwa.register()
class WeightCommand(
    lightbulb.SlashCommand,
    name="weight",
    description="Calculate war weight from storage value (automatically multiplies by 5)",
):
    weight = lightbulb.integer(
        "storage-weight",
        "Single storage weight value (will be multiplied by 5)",
        min_value=1,
        max_value=100000
    )

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context, bot: hikari.GatewayBot = lightbulb.di.INJECTED) -> None:
        await ctx.defer(ephemeral=True)

        # Calculate total weight (multiply by 5)
        total_weight = self.weight * 5

        # Determine town hall and status
        th_level, status, color = determine_town_hall(total_weight)

        # Build status message
        if status == "below":
            status_msg = "⚠️ **Below TH9 range**\nThis weight is lower than TH9 minimum (56k)."
            th_display = "Below TH9"
        elif status == "above":
            status_msg = "⚠️ **Above TH17 range**\nThis weight exceeds the maximum range."
            th_display = "Above TH17"
        elif status == "between":
            if th_level and th_level < 17:
                next_th = th_level + 1
                status_msg = f"📊 **Between TH{th_level} and TH{next_th}**"
                th_display = f"TH{th_level}-{next_th} Gap"
            else:
                status_msg = "📊 **In transition range**"
                th_display = "Transition"
        else:  # exact
            status_msg = f"✅ **Town Hall {th_level} Confirmed**"
            th_display = f"Town Hall {th_level}"
            if th_level in WAR_WEIGHT_RANGES:
                range_data = WAR_WEIGHT_RANGES[th_level]
                status_msg += f"\nWeight Range: {range_data['min']:,} - {range_data['max']:,}"

        # Build additional info_hub
        additional_info = []

        # Add upgrade info_hub if applicable
        if th_level and status == "exact":
            upgrade_info = get_upgrade_info(total_weight, th_level)
            if upgrade_info:
                additional_info.append(upgrade_info)

            # Add position in range
            position = calculate_position_in_range(total_weight, th_level)
            additional_info.append(f"• {position}% through TH{th_level} weight range")

        # Add FWA suitability with separator
        if total_weight >= 56000:  # Only show FWA info for TH9+
            additional_info.append("")  # Add empty line for separator
            if total_weight < 115000:
                additional_info.append("❌ **War Weight not suitable for FWA Wars.**")
                additional_info.append("**Minimum weight requirement = 115,000.**")
                additional_info.append("**Recommend a Zen Clan.**")
            else:
                additional_info.append("✅ Suitable weight for FWA clan wars")

        # Build the response components
        components = [
            Container(
                accent_color=color,
                components=[
                    Text(content="## ⚖️ **FWA War Weight Calculator**"),
                    Separator(divider=True),
                    Text(content=(
                        f"**Storage Weight:** {self.weight:,}\n"
                        f"**Total War Weight:** {self.weight:,} × 5 = {get_th_emoji(th_level)} **{total_weight:,}**\n\n"
                        f"{status_msg}"
                    )),
                ]
            ),
            Container(
                accent_color=BLUE_ACCENT,
                components=[
                    Text(content="### 📊 **War Weight Reference Guide (TH9+)**"),
                    Text(content=format_weight_reference_guide(total_weight, th_level)),
                ]
            )
        ]

        # Add additional info container if we have any
        if additional_info:
            # Build components for additional info
            additional_components = [Text(content="### 📈 **Additional Information**")]
            
            # Process additional info items
            for info in additional_info:
                if info == "":  # Empty string indicates separator
                    additional_components.append(Separator(divider=True))
                else:
                    additional_components.append(Text(content=info))
            
            additional_components.append(Media(items=[MediaItem(media="assets/Gold_Footer.png")]))
            
            components.append(
                Container(
                    accent_color=GOLD_ACCENT,
                    components=additional_components
                )
            )
        else:
            # Add footer to last container
            components[-1].components.append(
                Media(items=[MediaItem(media="assets/Blue_Footer.png")])
            )

        # Send to channel without replying
        await bot.rest.create_message(
            channel=ctx.channel_id,
            components=components
        )

        # Delete the ephemeral "thinking" message
        await ctx.interaction.delete_initial_response()