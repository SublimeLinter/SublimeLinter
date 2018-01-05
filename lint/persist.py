"""This module provides persistent global storage for other modules."""

from collections import defaultdict

import sys

from .util import get_python_paths, printf
from .settings import Settings


if 'plugin_is_loaded' not in globals():
    settings = Settings()

    scheme = None

    # A mapping between view ids and errors, which are line:(col, message) dicts
    errors = None

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


def debug_mode():
    """Return whether the "debug" setting is True."""
    return settings.get('debug', False)


def debug(*args):
    """Print args to the console if the "debug" setting is True."""
    if debug_mode():
        printf(*args)


def import_sys_path():
    """Import system python 3 sys.path into our sys.path."""
    global sys_path_imported

    if plugin_is_loaded and not sys_path_imported:
        # Make sure the system python 3 paths are available to plugins.
        # We do this here to ensure it is only done once.
        sys.path.extend(get_python_paths())
        sys_path_imported = True
