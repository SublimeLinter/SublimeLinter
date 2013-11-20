#
# persist.py
# Part of SublimeLinter3, a code checking framework for Sublime Text 3
#
# Written by Ryan Hileman and Aparajita Fishman
#
# Project: https://github.com/SublimeLinter/SublimeLinter3
# License: MIT
#

from collections import defaultdict
from copy import deepcopy
import json
import os
from queue import Queue, Empty
import re
import threading
import traceback
import time
import sublime
import sys

from . import util

PLUGIN_NAME = 'SublimeLinter'

# Get the name of the plugin directory, which is the parent of this file's directory
PLUGIN_DIRECTORY = os.path.basename(os.path.dirname(os.path.dirname(__file__)))

LINT_MODES = (
    ('background', 'Lint whenever the text is modified'),
    ('load/save', 'Lint only when a file is loaded or saved'),
    ('save only', 'Lint only when a file is saved'),
    ('manual', 'Lint only when requested')
)

SYNTAX_RE = re.compile(r'/([^/]+)\.tmLanguage$')


class Daemon:
    MIN_DELAY = 0.1
    running = False
    callback = None
    q = Queue()
    last_runs = {}

    def __init__(self):
        self.settings = {}
        self.previous_settings = {}
        self.sub_settings = None
        self.on_settings_updated = None

    def load_settings(self, force=False):
        if force or not self.settings:
            self.observe_settings()
            self.settings_updated()
            self.observe_prefs()

    def change_setting(self, setting, value):
        self.copy_settings()
        self.settings[setting] = value

    def copy_settings(self):
        self.previous_settings = deepcopy(self.settings)

    def observe_prefs(self, observer=None):
        prefs = sublime.load_settings('Preferences.sublime-settings')
        prefs.clear_on_change('sublimelinter-pref-settings')
        prefs.add_on_change('sublimelinter-pref-settings', observer or util.generate_color_scheme)

    def observe_settings(self, observer=None):
        self.sub_settings = sublime.load_settings('SublimeLinter.sublime-settings')
        self.sub_settings.clear_on_change('sublimelinter-persist-settings')
        self.sub_settings.add_on_change('sublimelinter-persist-settings',
                                        observer or self.settings_updated)

    def on_settings_updated_call(self, callback):
        self.on_settings_updated = callback

    def settings_updated(self):
        settings = util.merge_user_settings(self.sub_settings)
        self.settings.clear()
        self.settings.update(settings)
        need_relint = False

        # Clear the path-related caches if the paths list has changed
        if self.previous_settings.get('paths') != self.settings.get('paths'):
            need_relint = True
            util.create_environment.cache_clear()
            util.which.cache_clear()

        # Add python paths if they changed
        if self.previous_settings.get('python_paths') != self.settings.get('python_paths'):
            need_relint = True
            python_paths = self.settings.get('python_paths', {}).get(sublime.platform(), [])

            for path in python_paths:
                if path not in sys.path:
                    sys.path.append(path)

        # If the syntax map changed, reassign linters to all views
        from .linter import Linter

        if self.previous_settings.get('syntax_map') != self.settings.get('syntax_map'):
            need_relint = True
            Linter.clear_all()
            util.apply_to_all_views(lambda view: Linter.assign(view, reassign=True))

        # If any of the linter settings changed, relint
        if (not need_relint and self.previous_settings.get('linters') != self.settings.get('linters')):
            need_relint = True

        # Update the gutter marks if the theme changed
        if self.previous_settings.get('gutter_theme') != self.settings.get('gutter_theme'):
            self.update_gutter_marks()

        if need_relint:
            Linter.reload()

        if self.on_settings_updated:
            self.on_settings_updated(need_relint)

    def update_user_settings(self, view=None):
        load_settings()

        # Fill in default linter settings
        linters = settings.pop('linters', {})

        for name, linter in languages.items():
            if name.startswith('embedded'):
                continue

            default = linter.settings().copy()
            default.update(linters.pop(name, {}))

            if '@disable' not in default:
                default['@disable'] = False

            linters[name] = default

        settings['linters'] = linters

        filename = '{}.sublime-settings'.format(PLUGIN_NAME)
        user_prefs_path = os.path.join(sublime.packages_path(), 'User', filename)

        if view is None:
            # See if any open views are the user prefs
            for window in sublime.windows():
                view = window.find_open_file(user_prefs_path)

                if view is not None:
                    break

        if view is not None:
            def replace(edit):
                if not view.is_dirty():
                    j = json.dumps({'user': settings}, indent=4, sort_keys=True)
                    j = j.replace(' \n', '\n')
                    view.replace(edit, sublime.Region(0, view.size()), j)

            edits[view.id()].append(replace)
            view.run_command('sublimelinter_edit')
            view.run_command('save')
        else:
            user_settings = sublime.load_settings('SublimeLinter.sublime-settings')
            user_settings.set('user', settings)
            sublime.save_settings('SublimeLinter.sublime-settings')

    def update_gutter_marks(self):
        theme = settings.get('gutter_theme', 'Default')

        if theme.lower() == 'none':
            gutter_marks['warning'] = gutter_marks['error'] = ''
            return

        theme_path = None

        # User themes override built in themes, check them first
        paths = (
            ('User', 'SublimeLinter-gutter-themes', theme),
            (PLUGIN_DIRECTORY, 'gutter-themes', theme),
            (PLUGIN_DIRECTORY, 'gutter-themes', 'Default')
        )

        for path in paths:
            sub_path = os.path.join(*path)
            full_path = os.path.join(sublime.packages_path(), sub_path)

            if os.path.isdir(full_path):
                theme_path = sub_path
                break

        if theme_path:
            if theme != 'Default' and os.path.basename(theme_path) == 'Default':
                printf('cannot find the gutter theme \'{}\', using the default'.format(theme))

            for error_type in ('warning', 'error'):
                path = os.path.join(theme_path, '{}.png'.format(error_type))
                gutter_marks[error_type] = util.package_relative_path(path)

            path = os.path.join(sublime.packages_path(), theme_path, 'colorize')
            gutter_marks['colorize'] = os.path.exists(path)
        else:
            sublime.error_message(
                'SublimeLinter: cannot find the gutter theme "{}",'
                ' and the default is also not available. '
                'No gutter marks will display.'.format(theme)
            )
            gutter_marks['warning'] = gutter_marks['error'] = ''

    def start(self, callback):
        self.callback = callback

        if self.running:
            self.q.put('reload')
            return
        else:
            self.running = True
            threading.Thread(target=self.loop).start()

    def reenter(self, view_id, timestamp):
        self.callback(view_id, timestamp)

    def loop(self):
        last_runs = {}

        while True:
            try:
                try:
                    item = self.q.get(block=True, timeout=self.MIN_DELAY)
                except Empty:
                    for view_id, timestamp in last_runs.copy().items():
                        # If more than the minimum delay has elapsed since the last run,
                        # update the view.
                        if time.monotonic() > timestamp:
                            self.last_runs[view_id] = time.monotonic()
                            del last_runs[view_id]
                            self.reenter(view_id, timestamp)

                    continue

                if isinstance(item, tuple):
                    view_id, timestamp = item

                    if view_id in self.last_runs and timestamp < self.last_runs[view_id]:
                        continue

                    last_runs[view_id] = timestamp

                elif isinstance(item, (int, float)):
                    time.sleep(item)

                elif isinstance(item, str):
                    if item == 'reload':
                        self.printf('daemon detected a reload')
                        self.last_runs.clear()
                        last_runs.clear()
                else:
                    self.printf('unknown message sent to daemon:', item)
            except:
                self.printf('error in SublimeLinter daemon:')
                self.printf('-' * 20)
                self.printf(traceback.format_exc())
                self.printf('-' * 20)

    def hit(self, view):
        timestamp = time.monotonic()
        delay = self.get_delay(view)
        self.q.put((view.id(), timestamp + delay))
        return timestamp

    def delay(self, milliseconds=100):
        self.q.put(milliseconds / 1000.0)

    def get_delay(self, view):
        delay = (util.get_view_rc_settings(view) or {}).get("delay")

        if delay is None:
            delay = self.settings.get("delay", self.MIN_DELAY)

        return delay

    def debug(self, *args):
        if self.settings.get('debug'):
            self.printf(*args)

    def printf(self, *args):
        print(PLUGIN_NAME + ': ', end='')

        for arg in args:
            print(arg, end=' ')

        print()

if not 'queue' in globals():
    queue = Daemon()
    debug = queue.debug
    printf = queue.printf
    settings = queue.settings
    previous_settings = queue.previous_settings

    # A mapping between view ids and errors, which are line:(col, message) dicts
    errors = {}

    # A mapping between view ids and HighlightSets
    highlights = {}

    # A mapping between language names and linter classes
    languages = {}

    # A mapping between view ids and a set of linter instances
    linters = {}

    # A mapping between view ids and views
    views = {}

    edits = defaultdict(list)

    # Info about the gutter mark icons
    gutter_marks = {'warning': 'Default', 'error': 'Default', 'colorize': True}

    # Set to true when the plugin is loaded at startup
    plugin_is_loaded = False


def load_settings(force=False):
    queue.load_settings(force)


def change_setting(setting, value):
    queue.change_setting(setting, value)


def copy_settings():
    queue.copy_settings()


def on_settings_updated_call(callback):
    queue.on_settings_updated_call(callback)


def update_user_settings(view=None):
    queue.update_user_settings(view=view)


def observe_prefs(observer=None):
    queue.observe_prefs(observer=observer)


def syntax(view):
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
    callbacks = edits.pop(vid, [])

    for c in callbacks:
        c(edit)


def view_did_close(vid):
    if vid in errors:
        del errors[vid]

    if vid in highlights:
        del highlights[vid]

    if vid in linters:
        del linters[vid]

    if vid in views:
        del views[vid]


def register_linter(linter_class, name, attrs):
    """Add a linter class to our mapping of languages <--> linter classes."""
    if name:
        name = name.lower()
        linter_class.name = name
        languages[name] = linter_class

        if not name.startswith('embedded'):
            linter_settings = settings.get('linters', {})
            linter_class.lint_settings = linter_settings.get(name, {})

        # The sublime plugin API is not available until plugin_loaded is executed
        if plugin_is_loaded:
            load_settings(force=True)

            # If a linter is reloaded, we have to reassign linters to all views
            from . import linter

            for view in views.values():
                linter.Linter.assign(view, reassign=True)

            printf('{} linter reloaded'.format(linter_class.__name__))
        else:
            printf('{} linter loaded'.format(linter_class.__name__))
