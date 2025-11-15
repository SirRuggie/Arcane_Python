import hikari

RED_ACCENT = hikari.Color.from_hex_code("#AA0000")
GOLD_ACCENT = hikari.Color.from_hex_code("FFD700")
BLUE_ACCENT = hikari.Color.from_hex_code("0066FF")
GREEN_ACCENT = hikari.Color.from_hex_code("00B237")
MAGENTA_ACCENT = hikari.Color.from_hex_code("FF00FF")
DARK_MAGENTA_ACCENT = hikari.Color.from_hex_code("#990099")
DARK_GRAY_ACCENT = hikari.Color.from_hex_code("#2F3136")

# Disboard Configuration
DISBOARD_BOT_ID = 302050872383242240
BUMP_CHANNEL_ID = 1435995762508169349
BUMP_ROLE_ID = 999402011034402947
DISBOARD_REVIEW_URL = "https://disboard.org/review/create/640280017770774549"

# Clan Information
CLAN_TYPES = ["Competitive", "Casual", "FWA", "Zen"]
CLAN_STATUS = ["Main", "Zen", "FWA", "Trial"]
TH_LEVELS = [str(i) for i in range(3, 19)]
TH_ATTRIBUTE = ["Max", "Normal", "Rushed", "Non-Rushed"]

# Staff Case Types
STAFF_CASE_TYPES = ["Warning", "Suspension", "Termination", "Staff Ban", "Note"]


# FWA Images
FWA_WAR_BASE = {
    "th9": "https://res.cloudinary.com/dxmtzuomk/image/upload/v1751620708/TH9_WarBase.jpg",
    "th10": "https://res.cloudinary.com/dxmtzuomk/image/upload/v1751620707/TH10_WarBase.jpg",
    "th11": "https://res.cloudinary.com/dxmtzuomk/image/upload/v1751620706/TH11_WarBase.jpg",
    "th12": "https://res.cloudinary.com/dxmtzuomk/image/upload/v1751620705/TH12_WarBase.jpg",
    "th13": "https://res.cloudinary.com/dxmtzuomk/image/upload/v1751620704/TH13_WarBase.jpg",
    "th14": "https://res.cloudinary.com/dxmtzuomk/image/upload/v1751620703/TH14_WarBase.jpg",
    "th15": "https://res.cloudinary.com/dxmtzuomk/image/upload/v1751620703/TH15_WarBase.jpg",
    "th16": "https://res.cloudinary.com/dxmtzuomk/image/upload/v1751620702/TH16_WarBase.jpg",
    "th16_new": "https://res.cloudinary.com/dxmtzuomk/image/upload/v1751620702/TH16_WarBase.jpg",
    "th17": "https://res.cloudinary.com/dxmtzuomk/image/upload/v1751620702/TH17_WarBase.jpg",
    "th17_new": "https://res.cloudinary.com/dxmtzuomk/image/upload/v1751620702/TH17_WarBase.jpg",
}

FWA_ACTIVE_WAR_BASE = {
    "th9": "https://res.cloudinary.com/dxmtzuomk/image/upload/v1751620707/TH9_Active_WarBase.jpg",
    "th10": "https://res.cloudinary.com/dxmtzuomk/image/upload/v1751620707/TH10_Active_WarBase.jpg",
    "th11": "https://res.cloudinary.com/dxmtzuomk/image/upload/v1751620706/TH11_Active_WarBase.jpg",
    "th12": "https://res.cloudinary.com/dxmtzuomk/image/upload/v1751620705/TH12_Active_WarBase.jpg",
    "th13": "https://res.cloudinary.com/dxmtzuomk/image/upload/v1751620705/TH13_Active_WarBase.jpg",
    "th14": "https://res.cloudinary.com/dxmtzuomk/image/upload/v1751620703/TH14_Active_WarBase.jpg",
    "th15": "https://res.cloudinary.com/dxmtzuomk/image/upload/v1751620702/TH15_Active_WarBase.jpg",
    "th16": "https://res.cloudinary.com/dxmtzuomk/image/upload/v1751620702/TH16_Active_WarBase.jpg",
    "th16_new": "https://res.cloudinary.com/dxmtzuomk/image/upload/v1751620702/TH16_Active_WarBase.jpg",
    "th17": "https://res.cloudinary.com/dxmtzuomk/image/upload/v1751620701/TH17_Active_WarBase.jpg",
    "th17_new": "https://res.cloudinary.com/dxmtzuomk/image/upload/v1751620701/TH17_Active_WarBase.jpg",
}

# Staff Roles Hierarchy
# Maps teams to their positions with Discord role IDs
# Role IDs can be added gradually - None means no validation yet
STAFF_ROLES = {
    "Recruitment": {
        "roles": [
            {"name": "Recruitment Chairman", "role_id": 1345184776172343318},
            {"name": "Recruitment Manager", "role_id": 1345883351139225752},
            {"name": "Recruitment Lead", "role_id": 1039311270614142977},
            {"name": "Recruitment Staff", "role_id": 999140213953671188},
            {"name": "Recruitment Liaison", "role_id": 1423008370260185260},
            {"name": "Trial Recruitment Staff", "role_id": 1428423218397450305},
        ]
    },
    "Moderation": {
        "roles": [
            {"name": "Discord Chairman", "role_id": 1345184544822657095},
            {"name": "Discord Manager", "role_id": 1345189412291477575},
            {"name": "Moderator", "role_id": 1022305336515891260},
            {"name": "Trial Moderator", "role_id": 1344513109183823994},
        ]
    },
    "Events": {
        "roles": [
            {"name": "Community Chairman", "role_id": 1345184642608660573},
            {"name": "Community Manager", "role_id": 1345189456038068327},
            {"name": "Community Staff", "role_id": 1003786183391854702},
        ]
    },
    "Development": {
        "roles": [
            {"name": "Development Chairman", "role_id": 1065030453041565696},
            {"name": "Server Developer", "role_id": 1371470242076954706},
        ]
    },
    "eSports": {
        "roles": [
            {"name": "eSports Chairman", "role_id": 1344513276905783377},
        ]
    },
    "Special Roles": {
        "roles": [
            {"name": "Owner", "role_id": 1345174718944383027},
            {"name": "Family Lead", "role_id": 1345174718944383027},
            {"name": "Hand of the King", "role_id": 1350830317937627136},
            {"name": "High Steward", "role_id": 1345183673288228935},
            {"name": "High Court", "role_id": 1344514130228285450},
        ]
    }
}


def get_all_teams() -> list[str]:
    """Get list of all team names"""
    return list(STAFF_ROLES.keys())


def get_positions_for_team(team: str) -> list[str]:
    """Get list of position names for a specific team"""
    if team not in STAFF_ROLES:
        return []
    return [role["name"] for role in STAFF_ROLES[team]["roles"]]


def get_role_id_for_position(team: str, position: str) -> int | None:
    """Get Discord role ID for a team/position combination"""
    if team not in STAFF_ROLES:
        return None
    for role in STAFF_ROLES[team]["roles"]:
        if role["name"] == position:
            return role["role_id"]
    return None


def validate_user_has_role(member: hikari.Member, team: str, position: str) -> bool:
    """Check if user has the Discord role for their assigned position"""
    role_id = get_role_id_for_position(team, position)
    if role_id is None:
        return True  # No role ID set yet, skip validation
    return role_id in member.role_ids