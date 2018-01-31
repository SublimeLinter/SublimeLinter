import sublime
from . import util
from jsonschema.validators import validate
from jsonschema.exceptions import ValidationError


class Settings:
    """This class provides global access to and management of plugin settings."""

    # Can be used to check for outdated caches
    change_count = 0

    def __init__(self):
        self._storage = {}

    def load(self):
        """Load the plugin settings."""
        self.observe()
        self.on_update()

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

        self.change_count += 1

        from . import style
        from .linter import Linter

        # Reparse settings for style rules
        # Linter specific settings can include style rules too
        if self.has_changed('styles') or self.has_changed('linters'):
            style.StyleParser()()

        # If the syntax map changed, reassign linters to all views
        if self.has_changed('syntax_map'):
            Linter.clear_all()
            util.apply_to_all_views(
                lambda view: Linter.assign(view, reset=True)
            )

        if self.has_changed('gutter_theme'):
            style.load_gutter_icons()

        from ..sublime_linter import SublimeLinter
        SublimeLinter.lint_all_views()

    def linter_settings(self, linter_name):
        """Return settings for the linter with the specified name."""
        return self.get('linters', {}).get(linter_name, {})


class WindowSettings:

    """Extract settings for SL from a project file."""

    change_count = 0
    _data = None
    _window_map = {}

    def __init__(self, window):
        self.window = window

    def _current_data(self):
        p_data = self.window.project_data()
        if not p_data:
            return {}
        return p_data.get('SublimeLinter', {})

    def check(self):
        """Check whether the underlying data has changed."""
        prev_count = self.change_count
        self.data()
        return self.change_count != prev_count

    def data(self):
        """Fetch the current data and increase `change_count` if it changed."""
        current_data = self._current_data()
        if self._data is None:
            self._data = current_data
        elif self._data != current_data:
            self._data = current_data
            self.change_count += 1
        return self._data

    def linter_settings(self, linter_name):
        """Return settings for the linter with the specified name."""
        return self.data().get('linters', {}).get(linter_name, {})

    @classmethod
    def for_window(cls, window):
        id_ = window.id()
        instance = cls._window_map.get(id_)
        if not instance:
            instance = cls(window)
            cls._window_map[id_] = instance
        return instance


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
