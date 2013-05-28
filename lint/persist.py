from collections import defaultdict
from queue import Queue, Empty
import threading
import traceback
import time
import sublime

from .util import merge_user_settings

class Daemon:
    running = False
    callback = None
    q = Queue()
    last_run = {}

    def __init__(self):
        self.settings = {}
        self.sub_settings = None

    def reinit(self):
        if not self.settings:
            if self.sub_settings:
                self.sub_settings.clear_on_change('lint-persist-settings')

            self.sub_settings = sublime.load_settings('SublimeLint.sublime-settings')
            self.sub_settings.add_on_change('lint-persist-settings', self.update_settings)
            self.update_settings()

    def update_settings(self):
        settings = merge_user_settings(self.sub_settings)
        self.settings.clear()
        self.settings.update(settings)

        # reattach settings objects to linters
        import sys
        linter = sys.modules.get('lint.linter')
        if linter and hasattr(linter, 'persist'):
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
                    item = self.q.get(True, 0.1)
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
                        self.printf('SublimeLint daemon detected a reload')
                else:
                    self.printf('SublimeLint: Unknown message sent to daemon:', item)
            except:
                self.printf('Error in SublimeLint daemon:')
                self.printf('-'*20)
                self.printf(traceback.format_exc())
                self.printf('-'*20)

    def hit(self, view):
        self.q.put((view.id(), time.time()))

    def delay(self):
        self.q.put(0.01)

    def printf(self, *args):
        if not self.settings.get('debug'):
            return

        for arg in args:
            print('SublimeLint:', arg, end=' ')
        print()

if not 'already' in globals():
    queue = Daemon()
    debug = queue.printf
    settings = queue.settings

    errors = {}
    languages = {}
    linters = {}
    views = {}
    edits = defaultdict(list)
    modules = None
    already = True

def reinit():
    queue.reinit()

def edit(vid, edit):
    callbacks = edits.pop(vid, [])
    for c in callbacks:
        c(edit)

def add_language(sub, name, attrs):
    if name:
        plugins = settings.get('plugins', {})
        sub.lint_settings = plugins.get(name, {})
        sub.name = name
        languages[name] = sub
