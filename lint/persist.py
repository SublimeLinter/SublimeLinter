"""This module provides persistent global storage for other modules."""

from collections import defaultdict

from .util import printf
from .settings import Settings


api_ready = False

settings = Settings()

# A mapping between buffer ids and errors,
# Dict[buffer_id, [error]]
errors = defaultdict(list)

# A mapping between linter class names and linter classes
linter_classes = {}

# A mapping between buffer ids and a set of linter instances
view_linters = {}


def debug_mode():
    """Return whether the "debug" setting is True."""
    return settings.get('debug', False)


def debug(*args):
    """Print args to the console if the "debug" setting is True."""
    if debug_mode():
        printf(*args)
