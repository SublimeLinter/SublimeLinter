from collections import defaultdict

import sublime
import sublime_plugin


STATUS_ACTIVE_KEY = 'sublime_linter_status_active'

State = {
    'active_linters_per_vid': defaultdict(set)
}


def plugin_unloaded():
    for window in sublime.windows():
        for view in window.views():
            view.erase_status(STATUS_ACTIVE_KEY)


class sublime_linter_activated(sublime_plugin.WindowCommand):
    def run(self, vid, linter_name):
        set_active_status(vid, linter_name, active=True)


class sublime_linter_deactivated(sublime_plugin.WindowCommand):
    def run(self, vid, linter_name):
        set_active_status(vid, linter_name, active=False)


def set_active_status(vid, linter_name, active):
    active_linters = State['active_linters_per_vid'][vid]
    current_state = linter_name in active_linters
    if current_state == active:
        return

    if active:
        active_linters.add(linter_name)
    else:
        active_linters.discard(linter_name)

    view = sublime.View(vid)
    draw(view, active_linters)


def draw(view, active_linters):
    view.set_status(STATUS_ACTIVE_KEY, ', '.join(active_linters))
