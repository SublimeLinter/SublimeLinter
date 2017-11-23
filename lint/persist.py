#
# persist.py
# Part of SublimeLinter3, a code checking framework for Sublime Text 3
#
# Written by Ryan Hileman and Aparajita Fishman
#
# Project: https://github.com/SublimeLinter/SublimeLinter3
# License: MIT
#

"""This module provides persistent global storage for other modules."""

from collections import defaultdict
import os
import re
import sys

from . import util
from .settings import Settings
from .const import PLUGIN_NAME


# Get the name of the plugin directory, which is the parent of this file's directory
PLUGIN_DIRECTORY = os.path.basename(os.path.dirname(os.path.dirname(__file__)))

LINT_MODES = (
    ('background', 'Lint whenever the text is modified'),
    ('load_save', 'Lint only when a file is loaded or saved'),
    ('save only', 'Lint only when a file is saved'),
    ('manual', 'Lint only when requested')
)

SYNTAX_RE = re.compile(r'(?i)/([^/]+)\.(?:tmLanguage|sublime-syntax)$')


if 'plugin_is_loaded' not in globals():
    settings = Settings()

    scheme = None

    # A mapping between view ids and errors, which are line:(col, message) dicts
    errors = {}

    warn_err_count = {}

    # A mapping between view ids and HighlightSets
    highlights = {}

    #
    region_store = None

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

    # Info about the gutter mark icons
    gutter_marks = {'warning': 'Default', 'error': 'Default', 'colorize': True}

    # Whether sys.path has been imported from the system.
    sys_path_imported = False

    # Set to true when the plugin is loaded at startup
    plugin_is_loaded = False

    linter_styles = {}

    highlight_styles = {}

    has_gutter_theme = settings.get('gutter_theme') != 'None'


def get_syntax(view):
    """Return the view's syntax or the syntax it is mapped to in the "syntax_map" setting."""
    view_syntax = view.settings().get('syntax', '')
    mapped_syntax = ''

    if view_syntax:
        match = SYNTAX_RE.search(view_syntax)

        if match:
            view_syntax = match.group(1).lower()
            mapped_syntax = settings.get(
                'syntax_map', {}).get(view_syntax, '').lower()
        else:
            view_syntax = ''

    return mapped_syntax or view_syntax


def edit(vid, edit):
    """Perform an operation on a view with the given edit object."""
    callbacks = edits.pop(vid, [])

    for c in callbacks:
        c(edit)


def debug_mode():
    """Return whether the "debug" setting is True."""
    return settings.get('debug')


def debug(*args):
    """Print args to the console if the "debug" setting is True."""
    if settings.get('debug'):
        printf(*args)


def import_sys_path():
    """Import system python 3 sys.path into our sys.path."""
    global sys_path_imported

    if plugin_is_loaded and not sys_path_imported:
        # Make sure the system python 3 paths are available to plugins.
        # We do this here to ensure it is only done once.
        sys.path.extend(util.get_python_paths())
        sys_path_imported = True


def register_linter(linter_class, name, attrs):
    """Add a linter class to our mapping of class names <-> linter classes."""
    if name:
        name = name.lower()
        linter_classes[name] = linter_class

        # By setting the lint_settings to None, they will be set the next
        # time linter_class.settings() is called.
        linter_class.lint_settings = None

        # The sublime plugin API is not available until plugin_loaded is executed
        if plugin_is_loaded:
            settings.load(force=True)

            # If a linter is reloaded, we have to reassign that linter to all views
            from . import linter

            # If the linter had previously been loaded, just reassign that linter
            if name in linter_classes:
                linter_name = name
            else:
                linter_name = None

            for view in views.values():
                linter.Linter.assign(view, linter_name=linter_name)

            printf('{} linter reloaded'.format(name))

        else:
            printf('{} linter loaded'.format(name))


def printf(*args):
    """Print args to the console, prefixed by the plugin name."""
    print(PLUGIN_NAME + ': ', end='')

    for arg in args:
        print(arg, end=' ')

    print()
