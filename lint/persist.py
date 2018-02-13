"""This module provides persistent global storage for other modules."""

from collections import defaultdict

from .util import printf
from .settings import Settings


if 'plugin_is_loaded' not in globals():
    settings = Settings()

    scheme = None

    # A mapping between buffer ids and errors,
    # Dict[buffer_id, [error]]
    errors = defaultdict(list)

    # A mapping between linter class names and linter classes
    linter_classes = {}

    # A mapping between view ids and a set of linter instances
    view_linters = {}

    # A mapping between view ids and views
    views = {}

    # Set to true when the plugin is loaded at startup
    plugin_is_loaded = False


def debug_mode():
    """Return whether the "debug" setting is True."""
    return settings.get('debug', False)


def debug(*args):
    """Print args to the console if the "debug" setting is True."""
    if debug_mode():
        printf(*args)
