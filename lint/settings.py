import logging

import sublime
from . import util
from jsonschema import validate, FormatChecker, ValidationError


logger = logging.getLogger(__name__)


class Settings:
    """This class provides global access to and management of plugin settings."""

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

    def unobserve(self):
        settings = sublime.load_settings("SublimeLinter.sublime-settings")
        settings.clear_on_change('sublimelinter-persist-settings')

    def on_update(self):
        """
        Update state when the user settings change.

        The settings before the change are compared with the new settings.
        Depending on what changes, views will either be redrawn or relinted.

        """
        if not validate_global_settings():
            return

        gutter_theme_changed = self.has_changed('gutter_theme')
        if gutter_theme_changed:
            from . import style
            style.read_gutter_theme()

        if (
            self.has_changed('linters') or
            self.has_changed('no_column_highlights_line')
        ):
            sublime.run_command(
                'sublime_linter_config_changed', {'hint': 'relint'})

        elif (
            gutter_theme_changed or
            self.has_changed('highlights.demote_while_editing') or
            self.has_changed('show_marks_in_minimap') or
            self.has_changed('styles')
        ):
            sublime.run_command(
                'sublime_linter_config_changed', {'hint': 'redraw'})


def get_settings_objects():
    for name in sublime.find_resources("SublimeLinter.sublime-settings"):
        try:
            yield name, util.load_json(name, from_sl_dir=False)
        except (IOError, ValueError):
            pass


def validate_global_settings():
    return validate_settings(get_settings_objects())


def validate_settings(filename_settings_pairs, flat=False):
    status_msg = "SublimeLinter - Settings invalid!"
    schema_file = "resources/settings-schema.json"
    schema = util.load_json(schema_file, from_sl_dir=True)
    window = sublime.active_window()
    good = True

    for name, settings in filename_settings_pairs:
        if settings:
            try:
                validate(settings, schema, format_checker=FormatChecker())
            except ValidationError as error:
                good = False
                if flat:
                    path_to_err = '"{}": '.format(
                        'SublimeLinter.' + '.'.join(error.path)
                    )
                else:
                    path_to_err = (' > '.join(
                        repr(part)
                        for part in error.path
                        if not isinstance(part, int)  # drop array indices
                    ) + ': ') if error.path else ''

                logger.warning("Invalid settings in '{}'".format(name))
                util.show_message(
                    "Invalid settings in '{}':\n"
                    '{}{}'.format(name, path_to_err, error.message)
                )
                window.status_message(status_msg)

    if good:
        util.clear_message()

    return good


def validate_project_settings(filename):
    try:
        with open(filename, 'r') as fh:
            contents = fh.read()
    except IOError:
        return True  # Very optimistic

    try:
        obj = sublime.decode_value(contents)
    except ValueError:
        return False

    if 'SublimeLinter' in obj:
        print_deprecation_message(obj.get('SublimeLinter', {}))
        return False

    settings = obj.get('settings', {})
    if not settings:
        util.clear_message()
        return True

    sl_settings = {
        key: value
        for key, value in settings.items()
        if key.startswith('SublimeLinter.')
    }
    if not sl_settings:
        util.clear_message()
        return True

    invalid_top_level_keys = [
        key
        for key in sl_settings
        if not key.startswith('SublimeLinter.linters.')
    ]
    if invalid_top_level_keys:
        logger.error(
            "Invalid settings in '{}':\n"
            "Only 'SublimeLinter.linters.*' keys are allowed. "
            "Got {}.".format(
                filename,
                ', '.join(map(repr, invalid_top_level_keys))
            )
        )
        return False

    invalid_deep_keys = [
        key
        for key in sl_settings
        if len(key.rstrip('.').split('.')) < 4
    ]
    if invalid_deep_keys:
        logger.error(
            "Invalid settings in '{}':\n"
            "{} {} too short.".format(
                filename,
                ', '.join(map(repr, invalid_deep_keys)),
                'are' if len(invalid_deep_keys) > 1 else 'is'
            )
        )
        return False

    deep_settings = {}
    for key, value in sl_settings.items():
        _, *parts = key.split('.')
        edge = deep_settings
        for part in parts[:-1]:
            edge = edge.setdefault(part, {})

        edge[parts[-1]] = value

    return validate_settings([(filename, deep_settings)], flat=True)


def print_deprecation_message(settings):
    import json

    message = """
    Project settings for SublimeLinter have a new, flat format following
    Sublime Text conventions. The old format has been deprecated, use this instead:

    {}
    """

    new_settings = {}
    for linter_name, linter_settings in settings.get('linters', {}).items():
        for key, value in linter_settings.items():
            new_settings['.'.join(('SublimeLinter', 'linters', linter_name, key))] = value

    if not new_settings:
        # User has an empty SublimeLinter obj in their project file. So we
        # make up an example
        new_settings['SublimeLinter.linters.eslint.disable'] = True

    formatted_settings = json.dumps(
        {'settings': new_settings}, sort_keys=True, indent=4
    )[1:-1]
    util.show_message(
        message.format(formatted_settings)
    )
