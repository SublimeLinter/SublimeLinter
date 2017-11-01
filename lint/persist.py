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
from copy import deepcopy
import json
import os
import re
import sublime
import sys

from . import util


PLUGIN_NAME = 'SublimeLinter'
SETTINGS_FILE = PLUGIN_NAME + ".sublime-settings"

# Get the name of the plugin directory, which is the parent of this file's directory
PLUGIN_DIRECTORY = os.path.basename(os.path.dirname(os.path.dirname(__file__)))

LINT_MODES = (
    ('background', 'Lint whenever the text is modified'),
    ('load/save', 'Lint only when a file is loaded or saved'),
    ('save only', 'Lint only when a file is saved'),
    ('manual', 'Lint only when requested')
)

SYNTAX_RE = re.compile(r'(?i)/([^/]+)\.(?:tmLanguage|sublime-syntax)$')

DEFAULT_GUTTER_THEME_PATH = 'Packages/SublimeLinter/gutter-themes/Default/Default.gutter-theme'


DYN_PAT = re.compile("sublimelinter\.\w+?\.style_\d{3,}")
AUTO_SCOPE = re.compile("region\.[a-z]+?ish")

class DictDelta:
    '''Returns a list of ḱeys, which are added, deleted or whose values have been altered compared to the dict passed in the previous call.'''

    def __init__(self):
        self.old_dict = None

    def __call__(self, new_dict):
        """Returns list of changed keys."""

        # explicitly check for None, prevent all keys being returned on 1st run
        if self.old_dict is None:
            self.old_dict = new_dict
            return []

        changeset = self.diff_keys(new_dict, self.old_dict)
        self.old_dict = new_dict

        return  changeset

    def diff_keys(self, d1, d2):
        """Diff dicts via set operations and subsequent traversing value comparison.
        """
        changed_keys = []
        d1_keys = set(d1.keys())
        d2_keys = set(d2.keys())

        sym_diff = list(d1_keys ^ d2_keys)
        changed_keys.extend(sym_diff)

        intersec = d1_keys & d2_keys
        for k in intersec:
            if type(d1[k]) is dict:
                changed_keys.extend(self.diff_keys(d1[k], d2[k]))
            elif d1[k] != d2[k]:
                changed_keys.append(k)

        return changed_keys


class Settings:
    """This class provides global access to and management of plugin settings."""

    def __init__(self):
        """Initialize a new instance."""
        self.settings = {}
        self.changeset = []
        self.plugin_settings = None
        self.on_update_callback = None
        self.dict_comparer = DictDelta()

    def load(self, force=False):
        """Load the plugin settings."""
        if force or not self.settings:
            self.observe()
            self.on_update()
            self.observe_prefs()

    def has_setting(self, setting):
        """Return whether the given setting exists."""
        return setting in self.settings

    def get(self, setting, default=None):
        """Return a plugin setting, defaulting to default if not found."""
        return self.settings.get(setting, default)

    def set(self, setting, value, changed=False):
        """
        Set a plugin setting to the given value.

        Clients of this module should always call this method to set a value
        instead of doing settings['foo'] = 'bar'.

        If the caller knows for certain that the value has changed,
        they should pass changed=True.

        """
        self.settings[setting] = value

        if changed:
            self.changeset.add(setting)

    def pop(self, setting, default=None):
        """
        Remove a given setting and return default if it is not in self.settings.

        Clients of this module should always call this method to pop a value
        instead of doing settings.pop('foo').

        """
        return self.settings.pop(setting, default)

    def observe_prefs(self, observer=None):
        """Observe changes to the ST prefs."""
        prefs = sublime.load_settings('Preferences.sublime-settings')
        prefs.clear_on_change('sublimelinter-pref-settings')
        prefs.add_on_change('sublimelinter-pref-settings', observer or self.on_prefs_update)

    def observe(self, observer=None):
        """Observer changes to the plugin settings."""
        self.plugin_settings = sublime.load_settings(SETTINGS_FILE)
        self.plugin_settings.clear_on_change('sublimelinter-persist-settings')
        self.plugin_settings.add_on_change('sublimelinter-persist-settings',
                                           observer or self.on_update)

    def get_merged_settings(self):
        """Returns dict of default and user settings merged."""
        res = sublime.find_resources(SETTINGS_FILE)
        merged_dict = {}
        for r in res:
            s = sublime.load_resource(r)
            d = sublime.decode_value(s)
            merged_dict.update(d)
        return merged_dict

    def on_update_call(self, callback):
        """Set a callback to call when user settings are updated."""
        self.on_update_callback = callback

    def on_update(self):
        """
        Update state when the user settings change.

        The settings before the change are compared with the new settings.
        Depending on what changes, views will either be redrawn or relinted.

        """

        self.settings = self.get_merged_settings()

        self.changeset.extend(self.dict_comparer(self.settings))

        print("self.changeset: ", self.changeset)

        # TODO: or force_xml_scheme
        if not self.changeset:
            return

        if "force_xml_scheme" in self.changeset:
            util.printf("Scheme mode changed regenerating style definitions.")

            from ..sublimelinter import set_scheme
            set_scheme()
            scheme.generate()

        if "styles" in self.changeset:
            util.printf("Style definitions changed. Regenerating.")
            scheme.generate()

        # Clear the path-related caches if the paths list has changed
        if "paths" in self.changeset:
            util.clear_path_caches()

        # Add python paths if they changed
        if "python_paths" in self.changeset:
            python_paths = self.settings.get('python_paths', {}).get(
                sublime.platform(), [])

            for path in python_paths:
                if path not in sys.path:
                    sys.path.append(path)

        # If the syntax map changed, reassign linters to all views
        from .linter import Linter

        if "syntax_map" in self.changeset:
            Linter.clear_all()
            util.apply_to_all_views(lambda view: Linter.assign(view, reset=True))

        if "gutter_theme" in self.changeset:
            self.update_gutter_marks()

        Linter.reload()  # always reload

        # TODO: what does this do?
        # if self.previous_settings and self.on_update_callback:
        #     self.on_update_callback(need_relint)

        self.changeset.clear()

        Linter.reload()


    def save(self, view=None):
        """
        Regenerate and save the user settings.

        User settings are updated with the default settings and the defaults
        from every linter, and if the user settings are currently being edited,
        the view is updated.

        """

        self.load()

        # Fill in default linter settings
        settings = self.settings
        linters = settings.pop('linters', {})

        for name, linter in linter_classes.items():
            default = linter.settings().copy()
            default.update(linters.pop(name, {}))

            for key, value in (('@disable', False), ('args', []), ('excludes', [])):
                if key not in default:
                    default[key] = value

            linters[name] = default

        settings['linters'] = linters

        filename = '{}.sublime-settings'.format(PLUGIN_NAME)
        # TODO: centralise paths as constants
        user_prefs_path = os.path.join(sublime.packages_path(), 'User', filename)
        settings_views = []

        if not view:
            # See if any open views are the user prefs
            for window in sublime.windows():
                for view in window.views():
                    if view.file_name() == user_prefs_path:
                        settings_views.append(view)
        else:
            settings_views = [view]

        if settings_views:
            def replace(edit):
                if not view.is_dirty():
                    j = json.dumps(settings, indent=4, sort_keys=True)
                    j = j.replace(' \n', '\n')
                    view.replace(edit, sublime.Region(0, view.size()), j)

            for view in settings_views:
                edits[view.id()].append(replace)
                view.run_command('sublimelinter_edit')
                view.run_command('save')
        else:
            user_settings = sublime.load_settings('SublimeLinter.sublime-settings')
            user_settings.set('user', settings)
            sublime.save_settings('SublimeLinter.sublime-settings')

    def on_prefs_update(self):
        """Perform maintenance when the ST prefs are updated."""
        scheme.generate()

    def update_gutter_marks(self):
        """Update the gutter mark info based on the the current "gutter_theme" setting."""

        theme_path = self.settings.get('gutter_theme', DEFAULT_GUTTER_THEME_PATH)
        theme = os.path.splitext(os.path.basename(theme_path))[0]

        if theme_path.lower() == 'none':
            gutter_marks['warning'] = gutter_marks['error'] = ''
            return

        info = None

        for path in (theme_path, DEFAULT_GUTTER_THEME_PATH):
            try:
                info = sublime.load_resource(path)
                break
            except IOError:
                pass

        if info:
            if theme != 'Default' and os.path.basename(path) == 'Default.gutter-theme':
                util.printf('cannot find the gutter theme \'{}\', using the default'.format(theme))

            path = os.path.dirname(path)

            for error_type in ('warning', 'error'):
                icon_path = '{}/{}.png'.format(path, error_type)
                gutter_marks[error_type] = icon_path

            try:
                info = json.loads(info)
                colorize = info.get('colorize', False)
            except ValueError:
                colorize = False

            gutter_marks['colorize'] = colorize
        else:
            sublime.error_message(
                'SublimeLinter: cannot find the gutter theme "{}",'
                ' and the default is also not available. '
                'No gutter marks will display.'.format(theme)
            )
            gutter_marks['warning'] = gutter_marks['error'] = ''


if 'plugin_is_loaded' not in globals():
    settings = Settings()

    scheme = None

    # A mapping between view ids and errors, which are line:(col, message) dicts
    errors = {}

    # A mapping between view ids and HighlightSets
    highlights = {}

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
    gutter_marks = {'warning': 'Default', 'error': 'Default'}

    # Whether sys.path has been imported from the system.
    sys_path_imported = False

    # Set to true when the plugin is loaded at startup
    plugin_is_loaded = False

    linter_styles = {}

    has_gutter_theme = settings.get('gutter_theme') != 'None'


def get_syntax(view):
    """Return the view's syntax or the syntax it is mapped to in the "syntax_map" setting."""
    view_syntax = view.settings().get('syntax', '')
    mapped_syntax = ''

    if view_syntax:
        match = SYNTAX_RE.search(view_syntax)

        if match:
            view_syntax = match.group(1).lower()
            mapped_syntax = settings.get('syntax_map', {}).get(view_syntax, '').lower()
        else:
            view_syntax = ''

    return mapped_syntax or view_syntax


def edit(vid, edit):
    """Perform an operation on a view with the given edit object."""
    callbacks = edits.pop(vid, [])

    for c in callbacks:
        c(edit)


def view_did_close(vid):
    """Remove all references to the given view id in persistent storage."""
    if vid in errors:
        del errors[vid]

    if vid in highlights:
        del highlights[vid]

    if vid in view_linters:
        del view_linters[vid]

    if vid in views:
        del views[vid]

    if vid in last_hit_times:
        del last_hit_times[vid]


def debug_mode():
    """Return whether the "debug" setting is True."""
    return settings.get('debug')


def debug(*args):
    """Print args to the console if the "debug" setting is True."""
    if settings.get('debug'):
        util.printf(*args)


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

            util.printf('{} linter reloaded'.format(name))

        else:
            util.printf('{} linter loaded'.format(name))
