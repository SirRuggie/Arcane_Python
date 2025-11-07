# extensions/commands/utilities/__init__.py
import lightbulb

loader = lightbulb.Loader()
utilities = lightbulb.Group("utilities", "Utility commands for server management")

# Import submodules to ensure they're loaded
from . import clone_category
from . import clone_forum
from . import purge_category
from . import process_reddit_post
from . import reboot
from . import add_perms

# Add the group to the loader
loader.command(utilities)

__all__ = ["loader", "utilities"]