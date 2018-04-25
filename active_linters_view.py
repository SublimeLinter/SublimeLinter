from collections import defaultdict

import sublime
import sublime_plugin

from .lint import events, persist
from .lint.const import WARNING, ERROR


STATUS_ACTIVE_KEY = 'sublime_linter_status_active'

State = {
    'assigned_linters_per_bid': defaultdict(set),
    'failed_linters_per_bid': defaultdict(set),
    'problems_per_bid': defaultdict(dict),
    'needs_redraw': set()
}


def plugin_unloaded():
    events.off(redraw_bid)

    for window in sublime.windows():
        for view in window.views():
            view.erase_status(STATUS_ACTIVE_KEY)


@events.on(events.LINT_RESULT)
def redraw_bid(buffer_id, linter_name, errors, **kwargs):
    problems = State['problems_per_bid'][buffer_id]
    if linter_name in State['failed_linters_per_bid'][buffer_id]:
        problems[linter_name] = '(erred)'
    elif linter_name in State['assigned_linters_per_bid'][buffer_id]:
        we_count = count_problems(errors)
        if we_count == (0, 0):
            problems[linter_name] = '(ok)'
        else:
            tpl = persist.settings.get('statusbar.counters_template')
            problems[linter_name] = tpl.format(*we_count)
    else:
        problems.pop(linter_name, None)

    for view in views_into_buffer(buffer_id):
        draw(view, problems)


def views_into_buffer(bid):
    return (
        view
        for window in sublime.windows()
        for view in window.views()
        if view.buffer_id() == bid
    )


def count_problems(errors):
    w, e = 0, 0
    for error in errors:
        error_type = error['error_type']
        if error_type == WARNING:
            w += 1
        elif error_type == ERROR:
            e += 1
    return (w, e)


class sublime_linter_assigned(sublime_plugin.WindowCommand):
    def run(self, bid, linter_names):
        State['assigned_linters_per_bid'][bid] = set(linter_names)
        State['failed_linters_per_bid'][bid] = set()


class sublime_linter_failed(sublime_plugin.WindowCommand):
    def run(self, bid, linter_name):
        State['failed_linters_per_bid'][bid].add(linter_name)


class UpdateState(sublime_plugin.EventListener):
    # Fires once per view with the actual view, not necessary the primary
    def on_activated_async(self, active_view):
        draw(active_view, State['problems_per_bid'][active_view.buffer_id()])


def draw(view, problems):
    if persist.settings.get('statusbar.show_active_linters'):
        message = ', '.join(
            '{}{}'.format(linter_name, summary)
            for linter_name, summary in sorted(problems.items())
        )
        view.set_status(STATUS_ACTIVE_KEY, message)
    else:
        view.erase_status(STATUS_ACTIVE_KEY)
