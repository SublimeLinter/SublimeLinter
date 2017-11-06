import os
import json
import sys

import sublime
from .const import SETTINGS_FILE, PLUGIN_NAME
from . import util


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
        self.update_gutter_marks()

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

        from . import persist

        # TODO: or force_xml_scheme
        if not self.changeset:
            return

        if "force_xml_scheme" in self.changeset:
            persist.printf("Scheme mode changed regenerating style definitions.")

            from . import persist
            persist.scheme.generate()

        if "styles" in self.changeset:
            persist.printf("Style definitions changed. Regenerating.")
            persist.scheme.generate()

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

        # TODO: change whether this optimal:
        Linter.reload()  # always reload
        from ..sublime_linter import SublimeLinter
        SublimeLinter.lint_all_views()

        # TODO: what does this do?
        # if self.previous_settings and self.on_update_callback:
        #     self.on_update_callback(need_relint)

        self.changeset.clear()

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

        from .persist import linter_classes, edits

        for name, linter in linter_classes.items():
            default = linter.settings().copy()
            default.update(linters.pop(name, {}))

            for key, value in (('@disable', False), ('args', []), ('excludes', [])):
                if key not in default:
                    default[key] = value

            linters[name] = default

        settings['linters'] = linters

        # TODO: centralise paths as constants
        user_prefs_path = os.path.join(sublime.packages_path(), 'User', SETTINGS_FILE)
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
            with open(user_prefs_path, "w") as f:
                j = json.dumps(settings, indent=4, sort_keys=True)
                f.write(j)


    def on_prefs_update(self):
        """Perform maintenance when the ST prefs are updated."""
        from .persist import scheme
        scheme.generate()

    def update_gutter_marks(self):
        """Update the gutter mark info based on the the current "gutter_theme" setting."""

        from . import persist

        theme_path = self.settings.get('gutter_theme', persist.DEFAULT_GUTTER_THEME_PATH)

        theme = os.path.splitext(os.path.basename(theme_path))[0]

        if theme_path.lower() == 'none':
            persist.gutter_marks['warning'] = persist.gutter_marks['error'] = ''
            return

        info = None

        for path in (theme_path, persist.DEFAULT_GUTTER_THEME_PATH):
            try:
                info = sublime.load_resource(path)
                break
            except IOError:
                pass

        if info:
            if theme != 'Default' and os.path.basename(path) == 'Default.gutter-theme':
                persist.printf('cannot find the gutter theme \'{}\', using the default'.format(theme))

            path = os.path.dirname(path)

            for error_type in ('warning', 'error'):
                icon_path = '{}/{}.png'.format(path, error_type)
                persist.gutter_marks[error_type] = icon_path

            try:
                info = json.loads(info)
                colorize = info.get('colorize', False)
            except ValueError:
                colorize = False

            persist.gutter_marks['colorize'] = colorize
        else:
            sublime.error_message(
                'SublimeLinter: cannot find the gutter theme "{}",'
                ' and the default is also not available. '
                'No gutter marks will display.'.format(theme)
            )
            persist.gutter_marks['warning'] = persist.gutter_marks['error'] = ''
