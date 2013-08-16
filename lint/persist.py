# persist.py
# Part of SublimeLinter, a code checking framework for Sublime Text 3
#
# Project: https://github.com/SublimeLinter/sublimelinter
# License: MIT

from collections import defaultdict
from queue import Queue, Empty
import threading
import traceback
import time
import sublime

from .util import merge_user_settings

plugin_name = 'SublimeLinter'

class Daemon:
    running = False
    callback = None
    q = Queue()
    last_run = {}

    def __init__(self):
        self.settings = {}
        self.sub_settings = None

    def load_settings(self):
        print('load_settings')
        if not self.settings:
            if self.sub_settings:
                self.sub_settings.clear_on_change('lint-persist-settings')

            self.sub_settings = sublime.load_settings('SublimeLinter.sublime-settings')
            self.sub_settings.add_on_change('lint-persist-settings', self.update_settings)
            self.update_settings()

    def update_settings(self):
        print('update_settings')
        settings = merge_user_settings(self.sub_settings)
        self.settings.clear()
        self.settings.update(settings)

        # Reattach settings objects to linters
        from . import linter
        linter.Linter.reload()

    def start(self, callback):
        self.callback = callback

        if self.running:
            self.q.put('reload')
            return
        else:
            self.running = True
            threading.Thread(target=self.loop).start()

    def reenter(self, view_id):
        self.callback(view_id)

    def loop(self):
        views = {}

        while True:
            try:
                try:
                    item = self.q.get(block=True, timeout=0.1)
                except Empty:
                    for view_id, ts in views.copy().items():
                        if ts < time.time() - 0.1:
                            self.last_run[view_id] = time.time()
                            del views[view_id]
                            self.reenter(view_id)

                    continue

                if isinstance(item, tuple):
                    view_id, ts = item

                    if view_id in self.last_run and ts < self.last_run[view_id]:
                        continue

                    views[view_id] = ts

                elif isinstance(item, (int, float)):
                    time.sleep(item)

                elif isinstance(item, str):
                    if item == 'reload':
                        self.printf('SublimeLinter daemon detected a reload')
                else:
                    self.printf('SublimeLinter: Unknown message sent to daemon:', item)
            except:
                self.printf('Error in SublimeLinter daemon:')
                self.printf('-' * 20)
                self.printf(traceback.format_exc())
                self.printf('-' * 20)

    def hit(self, view):
        self.q.put((view.id(), time.time()))

    def delay(self):
        self.q.put(0.01)

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

    # Set to true when the plugin is loaded at startup
    plugin_is_loaded = False

def load_settings():
    queue.load_settings()

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
            load_settings()

            # If a linter is reloaded, we have to reassign linters to all views
            from . import linter

            for view in views.values():
                linter.Linter.assign(view, reassign=True)

            debug('{} linter reloaded'.format(name))
