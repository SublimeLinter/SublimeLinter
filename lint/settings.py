import os
from glob import glob

import sublime
from . import util
from jsonschema.validators import validate
from jsonschema.exceptions import ValidationError


class DictDelta:
    """Return a list of ḱeys, which are added, deleted.

    Or whose values have been altered compared to the dict passed in the previous call.
    """

    def __init__(self):
        self.old_dict = None

    def __call__(self, new_dict):
        """Return list of changed keys."""
        # explicitly check for None, prevent all keys being returned on 1st run
        if self.old_dict is None:
            self.old_dict = new_dict
            return []

        changeset = self.diff_keys(new_dict, self.old_dict)
        self.old_dict = new_dict

        return changeset

    def diff_keys(self, d1, d2):
        """Diff dicts via set operations and subsequent traversing value comparison."""
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
        self.settings = {}
        self.changeset = []
        self.plugin_settings = None
        self.dict_comparer = DictDelta()

    def load(self):
        """Load the plugin settings."""
        self.observe()
        self.on_update()
        self.observe_prefs()
        self.update_gutter_icons()

    def has(self, setting):
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
            self.changeset.append(setting)

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
        prefs.add_on_change('sublimelinter-pref-settings', observer)

    def observe(self, observer=None):
        """Observer changes to the plugin settings."""
        self.plugin_settings = sublime.load_settings("SublimeLinter.sublime-settings")
        self.plugin_settings.clear_on_change('sublimelinter-persist-settings')
        self.plugin_settings.add_on_change('sublimelinter-persist-settings',
                                           observer or self.on_update)

    def get_view_settings(self):
        """Return dict of default and user settings merged."""
        res = sublime.find_resources("SublimeLinter.sublime-settings")
        merged_dict = {}
        for r in res:
            try:
                s = sublime.load_resource(r)
                d = sublime.decode_value(s)
            except IOError as ie:
                util.printf("Settings file not found: {}".format(r))
            except ValueError as ve:
                util.printf("Settings file corrupt: {}".format(r))
            else:
                merged_dict.update(d)
        return merged_dict

    def on_update(self):
        """
        Update state when the user settings change.

        The settings before the change are compared with the new settings.
        Depending on what changes, views will either be redrawn or relinted.

        """
        self.settings = self.get_view_settings()
        if not self.settings_valid():
            return

        self.changeset.extend(self.dict_comparer(self.settings))

        if not self.changeset:
            return

        # Reparse settings for style rules
        if "styles" in self.changeset:
            from . import style
            style.StyleParser()()

        # Clear the path-related caches if the paths list has changed
        if "paths" in self.changeset:
            util.clear_path_caches()

        # If the syntax map changed, reassign linters to all views
        from .linter import Linter

        if "syntax_map" in self.changeset:
            Linter.clear_all()
            util.apply_to_all_views(
                lambda view: Linter.assign(view, reset=True)
            )

        if "gutter_theme" in self.changeset:
            self.update_gutter_icons()

        Linter.reload()  # always reload
        from ..sublime_linter import SublimeLinter
        SublimeLinter.lint_all_views()

        self.changeset.clear()

    def update_gutter_icons(self):
        """Update the gutter mark info based on the the current "gutter_theme" setting."""
        new_gutter_dict = {"icons": {}}

        theme_path = self.settings.get('gutter_theme')

        theme_file = os.path.basename(theme_path)

        if not theme_file.endswith(".gutter-theme"):
            theme_file += ".gutter-theme"

        theme_files = sublime.find_resources(theme_file)

        if theme_files:
            theme_file = theme_files[0]
            opts = util.load_json(theme_file)
            if not opts:
                colorize = False
            else:
                colorize = opts.get("colorize", False)
        else:
            colorize = False

        new_gutter_dict["colorize"] = colorize
        dir_path, _ = os.path.split(theme_file)
        pck_path = sublime.packages_path().split("/Packages")[0]
        abs_dir = os.path.join(pck_path, dir_path)

        png_files = glob(os.path.join(abs_dir, "*.png"))
        for png in png_files:
            png_file = os.path.basename(png)
            name, ext = os.path.splitext(png_file)

            new_gutter_dict["icons"][name] = os.path.join(dir_path, png_file)

        from . import style

        style.GUTTER_ICONS = new_gutter_dict

    def settings_valid(self):
        """
        Validate merged settings against json schema.

        If invalid, display message in status bar and console.
        """
        status_msg = "SublimeLinter - Settings invalid. Details in console."
        schema_file = "resources/settings-schema.json"
        schema = util.load_json(schema_file, from_sl_dir=True)

        try:
            validate(self.settings, schema)
        except ValidationError as ve:
            ve_msg = ve.message.split("\n")[0]  # reduce verbosity
            util.printf("Settings invalid:\n{}".format(ve_msg))
            sublime.active_window().status_message(status_msg)
            return False
        else:
            return True
