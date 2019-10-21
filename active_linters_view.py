from collections import defaultdict

import sublime
import sublime_plugin

from .lint import events, persist, util
from .lint.const import WARNING, ERROR


if False:
    from typing import DefaultDict, Dict, Set
    from mypy_extensions import TypedDict

    Filename = str
    LinterName = str
    State_ = TypedDict('State_', {
        'assigned_linters_per_file': DefaultDict[Filename, Set[LinterName]],
        'failed_linters_per_file': DefaultDict[Filename, Set[LinterName]],
        'problems_per_file': DefaultDict[Filename, Dict[LinterName, str]]
    })


STATUS_ACTIVE_KEY = 'sublime_linter_status_active'

State = {
    'assigned_linters_per_file': defaultdict(set),
    'failed_linters_per_file': defaultdict(set),
    'problems_per_file': defaultdict(dict)
}  # type: State_


def plugin_unloaded():
    events.off(redraw_file)

    for window in sublime.windows():
        for view in window.views():
            view.erase_status(STATUS_ACTIVE_KEY)


@events.on(events.LINT_RESULT)
def redraw_file(filename, linter_name, errors, **kwargs):
    problems = State['problems_per_file'][filename]
    if linter_name in State['failed_linters_per_file'][filename]:
        problems[linter_name] = '(erred)'
    elif linter_name in State['assigned_linters_per_file'][filename] or errors:
        if linter_name not in State['assigned_linters_per_file'][filename]:
            State['assigned_linters_per_file'][filename].add(linter_name)

        we_count = count_problems(errors)
        if we_count == (0, 0):
            problems[linter_name] = '(ok)'
        else:
            tpl = persist.settings.get('statusbar.counters_template')
            problems[linter_name] = tpl.format(*we_count)
    else:
        problems.pop(linter_name, None)

    sublime.set_timeout(lambda: redraw_file_(filename, problems))


def redraw_file_(filename, problems):
    for view in views_into_file(filename):
        draw(view, problems)


def views_into_file(filename):
    return (
        view
        for window in sublime.windows()
        for view in window.views()
        if util.get_filename(view) == filename
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
    def run(self, filename, linter_names):
        State['assigned_linters_per_file'][filename] = set(linter_names)
        State['failed_linters_per_file'][filename] = set()


class sublime_linter_unassigned(sublime_plugin.WindowCommand):
    def run(self, filename, linter_name):
        State['assigned_linters_per_file'][filename].discard(linter_name)
        State['failed_linters_per_file'][filename].discard(linter_name)


class sublime_linter_failed(sublime_plugin.WindowCommand):
    def run(self, filename, linter_name):
        State['failed_linters_per_file'][filename].add(linter_name)


class UpdateState(sublime_plugin.EventListener):
    def on_load_async(self, view):
        filename = util.get_filename(view)
        draw(view, State['problems_per_file'][filename])

    on_clone_async = on_load_async


def draw(view, problems):
    if persist.settings.get('statusbar.show_active_linters'):
        message = ', '.join(
            '{}{}'.format(linter_name, summary)
            for linter_name, summary in sorted(problems.items())
        )
        view.set_status(STATUS_ACTIVE_KEY, message)
    else:
        view.erase_status(STATUS_ACTIVE_KEY)
