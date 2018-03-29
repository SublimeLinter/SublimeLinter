from collections import defaultdict

import sublime
import sublime_plugin

from .lint import events


STATUS_ACTIVE_KEY = 'sublime_linter_status_active'

State = {
    'active_linters_per_bid': defaultdict(set),
    'needs_redraw': set()
}


def plugin_unloaded():
    events.off(redraw_bid)

    for window in sublime.windows():
        for view in window.views():
            view.erase_status(STATUS_ACTIVE_KEY)


@events.on(events.LINT_END)
def redraw_bid(buffer_id, **kwargs):
    if buffer_id not in State['needs_redraw']:
        return

    State['needs_redraw'].discard(buffer_id)
    active_linters = State['active_linters_per_bid'][buffer_id]
    for window in sublime.windows():
        for view in window.views():
            if view.buffer_id() == buffer_id:
                draw(view, active_linters)


class sublime_linter_assigned(sublime_plugin.WindowCommand):
    def run(self, bid, linter_names):
        current_state = State['active_linters_per_bid'][bid]
        next_state = set(linter_names)
        if current_state == next_state:
            return

        State['active_linters_per_bid'][bid] = next_state
        State['needs_redraw'].add(bid)


class sublime_linter_deactivated(sublime_plugin.WindowCommand):
    def run(self, bid, linter_name):
        set_active_status(bid, linter_name, active=False)


def set_active_status(bid, linter_name, active):
    active_linters = State['active_linters_per_bid'][bid]
    current_state = linter_name in active_linters
    if current_state == active:
        return

    if active:
        active_linters.add(linter_name)
    else:
        active_linters.discard(linter_name)

    State['needs_redraw'].add(bid)


def draw(view, active_linters):
    view.set_status(STATUS_ACTIVE_KEY, ', '.join(sorted(active_linters)))
