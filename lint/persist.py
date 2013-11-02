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
import os
from queue import Queue, Empty
import threading
import traceback
import time
import sublime

from .util import merge_user_settings

plugin_name = 'SublimeLinter'

# Get the name of the plugin directory, which is the parent of this file's directory
plugin_directory = os.path.basename(os.path.dirname(os.path.dirname(__file__)))


class Daemon:
    MIN_DELAY = 0.1
    running = False
    callback = None
    q = Queue()
    last_runs = {}

    def __init__(self):
        self.settings = {}
        self.sub_settings = None

    def load_settings(self, force=False):
        if force or not self.settings:
            if self.sub_settings:
                self.sub_settings.clear_on_change('lint-persist-settings')

            self.sub_settings = sublime.load_settings('SublimeLinter.sublime-settings')
            self.sub_settings.add_on_change('lint-persist-settings', self.update_settings)
            self.update_settings()

    def update_settings(self):
        settings = merge_user_settings(self.sub_settings)
        self.settings.clear()
        self.settings.update(settings)

        # Reattach settings objects to linters
        from . import linter
        linter.Linter.reload()

        update_gutter_marks()

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
                        # If more than the minimum delay has elapsed since the last run, update the view
                        if time.monotonic() > timestamp + self.MIN_DELAY:
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
                else:
                    self.printf('unknown message sent to daemon:', item)
            except:
                self.printf('error in SublimeLinter daemon:')
                self.printf('-' * 20)
                self.printf(traceback.format_exc())
                self.printf('-' * 20)

    def hit(self, view):
        timestamp = time.monotonic()
        self.q.put((view.id(), timestamp))
        return timestamp

    def delay(self, milliseconds=100):
        self.q.put(milliseconds / 1000.0)

    def printf(self, *args):
        if not self.settings.get('debug'):
            return

        print(plugin_name + ': ', end='')

        for arg in args:
            print(arg, end=' ')

        print()

if not 'plugin_is_loaded' in globals():
    queue = Daemon()
    debug = queue.printf
    settings = queue.settings

    errors = {}
    languages = {}

    # A mapping between view ids and a set of linter instances
    linters = {}

    # A mapping between view ids and views
    views = {}

    edits = defaultdict(list)

    # Info about the gutter mark icons
    gutter_marks = {'warning': 'dot', 'error': 'dot', 'colorize': True}

    # Set to true when the plugin is loaded at startup
    plugin_is_loaded = False


def load_settings(force=False):
    queue.load_settings(force)


def edit(vid, edit):
    callbacks = edits.pop(vid, [])

    for c in callbacks:
        c(edit)


def register_linter(linter_class, name, attrs):
    '''Add a linter class to our mapping of languages <--> linter classes.'''
    if name:
        linter_settings = settings.get('linters', {})
        linter_class.lint_settings = linter_settings.get(name, {})
        linter_class.name = name
        languages[name] = linter_class

        # The sublime plugin API is not available until plugin_loaded is executed
        if plugin_is_loaded:
            load_settings(force=True)

            # If a linter is reloaded, we have to reassign linters to all views
            from . import linter

            for view in views.values():
                linter.Linter.assign(view, reassign=True)

            printf('{} linter reloaded'.format(name))
        else:
            printf('{} linter loaded'.format(name))


def update_gutter_marks():
    theme = queue.settings.get('gutter_theme', 'Default')
    theme_path = os.path.join(plugin_directory, 'gutter-themes', theme)

    if not os.path.isdir(os.path.join(sublime.packages_path(), theme_path)):
        theme_path = os.path.join('User', 'SublimeLinter-gutter-themes', theme)

    if os.path.isdir(os.path.join(sublime.packages_path(), theme_path)):
        gutter_marks['warning'] = os.path.join('Packages', theme_path, 'warning.png')
        gutter_marks['error'] = os.path.join('Packages', theme_path, 'error.png')
        gutter_marks['colorize'] = os.path.exists(os.path.join(sublime.packages_path(), theme_path, 'colorize'))
    else:
        debug('cannot find the gutter theme \'{}\''.format(theme))
