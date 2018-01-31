"""This module provides persistent global storage for other modules."""

from collections import defaultdict
import logging

from .settings import Settings
from . import logging as sl_logging


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

    # Every time a view is modified, this is updated with a mapping between a view id
    # and the time of the modification. This is checked at various stages of the linting
    # process. If a view has been modified since the original modification, the
    # linting process stops.
    last_hit_times = {}

    edits = defaultdict(list)

    # Whether sys.path has been imported from the system.
    sys_path_imported = False

    # Set to true when the plugin is loaded at startup
    plugin_is_loaded = False


def edit(vid, edit):
    """Perform an operation on a view with the given edit object."""
    callbacks = edits.pop(vid, [])

    for c in callbacks:
        c(edit)


# Backwards compatibility
def debug_mode():
    """Return whether the "debug" setting is True."""
    return sl_logging.base_logger.isEnabledFor(logging.DEBUG)


# Backwards compatibility
debug = sl_logging.debug
