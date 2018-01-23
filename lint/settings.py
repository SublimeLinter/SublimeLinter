import os
from glob import glob

import sublime
from . import util
from jsonschema.validators import validate
from jsonschema.exceptions import ValidationError


class Settings:
    """This class provides global access to and management of plugin settings."""

    def __init__(self):
        self._storage = {}

    def load(self):
        """Load the plugin settings."""
        self.observe()
        self.on_update()
        self.update_gutter_icons()

    @property
    def settings(self):
        return sublime.load_settings("SublimeLinter.sublime-settings")

    def has(self, name):
        """Return whether the given setting exists."""
        return self.settings.has(name)

    def get(self, name, default=None):
        """Return a plugin setting, defaulting to default if not found."""
        return self.settings.get(name, default)

    def has_changed(self, name):
        current_value = self.get(name)
        try:
            old_value = self._storage[name]
        except KeyError:
            return False
        else:
            return (old_value != current_value)
        finally:
            self._storage[name] = current_value

    def observe(self):
        """Observe changes."""
        settings = sublime.load_settings("SublimeLinter.sublime-settings")
        settings.clear_on_change('sublimelinter-persist-settings')
        settings.add_on_change('sublimelinter-persist-settings', self.on_update)

    def on_update(self):
        """
        Update state when the user settings change.

        The settings before the change are compared with the new settings.
        Depending on what changes, views will either be redrawn or relinted.

        """
        if not validate_settings():
            return

        # Reparse settings for style rules
        if self.has_changed('styles'):
            from . import style
            style.StyleParser()()

        # If the syntax map changed, reassign linters to all views
        from .linter import Linter

        if self.has_changed('syntax_map'):
            Linter.clear_all()
            util.apply_to_all_views(
                lambda view: Linter.assign(view, reset=True)
            )

        if self.has_changed('gutter_theme'):
            self.update_gutter_icons()

        from ..sublime_linter import SublimeLinter
        SublimeLinter.lint_all_views()

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


def get_settings_objects():
    for name in sublime.find_resources("SublimeLinter.sublime-settings"):
        try:
            yield name, util.load_json(name, from_sl_dir=False)
        except IOError as ie:
            util.printf("Settings file not found: {}".format(name))
        except ValueError as ve:
            util.printf("Settings file corrupt: {}".format(name))


def validate_settings():
    status_msg = "SublimeLinter - Settings invalid. Details in console."
    schema_file = "resources/settings-schema.json"
    schema = util.load_json(schema_file, from_sl_dir=True)

    good = True
    for name, settings in get_settings_objects():
        try:
            validate(settings, schema)
        except ValidationError as ve:
            ve_msg = ve.message.split("\n")[0]  # reduce verbosity
            util.printf("Settings in '{}' invalid:\n{}".format(name, ve_msg))
            sublime.active_window().status_message(status_msg)
            good = False

    return good
