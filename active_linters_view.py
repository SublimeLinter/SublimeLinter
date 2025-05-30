from __future__ import annotations
from collections import defaultdict
from functools import partial
import threading

import sublime
import sublime_plugin

from .lint import events, persist, util


from typing import Callable, Container, Iterator, TypedDict, TypeVar
from typing_extensions import ParamSpec
P = ParamSpec('P')
T = TypeVar('T')
U = TypeVar('U')
FileName = str
LinterName = str


class State_(TypedDict):
    assigned_linters_per_file: defaultdict[FileName, set[LinterName]]
    failed_linters_per_file: defaultdict[FileName, set[LinterName]]
    problems_per_file: defaultdict[FileName, dict[LinterName, str]]
    running: defaultdict[FileName, int]
    expanded_ok: set[FileName]


ATTEMPTED_LINTERS: dict[FileName, Container[LinterName]] = {}
STATUS_ACTIVE_KEY = 'sublime_linter_status_active'
State: State_ = {
    'assigned_linters_per_file': defaultdict(set),
    'failed_linters_per_file': defaultdict(set),
    'problems_per_file': defaultdict(dict),
    'running': defaultdict(int),
    'expanded_ok': set(),
}


def plugin_unloaded():
    events.off(redraw_file)
    events.off(on_begin_linting)
    events.off(on_finished_linting)

    for window in sublime.windows():
        for view in window.views():
            view.erase_status(STATUS_ACTIVE_KEY)


@events.on(events.LINT_START)
def on_begin_linting(filename: FileName, linter_name: LinterName) -> None:
    State['running'][filename] += 1


@events.on(events.LINT_END)
def on_finished_linting(filename: FileName, linter_name: LinterName) -> None:
    if State['running'][filename] <= 1:
        State['running'].pop(filename)
    else:
        State['running'][filename] -= 1


def on_first_activate(view: sublime.View) -> None:
    if not util.is_lintable(view):
        return

    filename = util.canonical_filename(view)
    force_verbose_format(filename)
    draw(view)


def on_attempted_linters_changed(filename: FileName) -> None:
    force_verbose_format(filename)
    redraw_file_(filename)


def force_verbose_format(filename: FileName) -> None:
    State['expanded_ok'].add(filename)
    enqueue_unset_expanded_ok(filename)


def enqueue_unset_expanded_ok(filename: FileName, timeout: int = 3000) -> None:
    sublime.set_timeout(
        throttled_on_args(_unset_expanded_ok, filename),
        timeout
    )


def _unset_expanded_ok(filename: FileName) -> None:
    # Keep expanded if linters are running to minimize redraws
    if State['running'].get(filename, 0) > 0:
        enqueue_unset_expanded_ok(filename)
        return

    State['expanded_ok'].discard(filename)
    redraw_file_(filename)


@events.on(events.LINTER_ASSIGNED)
def on_linter_assigned(filename: FileName, linter_names: set[LinterName]) -> None:
    State['assigned_linters_per_file'][filename] = linter_names
    State['failed_linters_per_file'][filename] = set()
    if attempted_linters_changed(filename, linter_names):
        on_attempted_linters_changed(filename)


class sublime_linter_unassigned(sublime_plugin.WindowCommand):
    def run(self, filename, linter_name):
        State['assigned_linters_per_file'][filename].discard(linter_name)
        State['failed_linters_per_file'][filename].discard(linter_name)


class sublime_linter_failed(sublime_plugin.WindowCommand):
    def run(self, filename, linter_name):
        State['failed_linters_per_file'][filename].add(linter_name)


@events.on(events.LINT_RESULT)
def redraw_file(
    filename: FileName,
    linter_name: LinterName,
    errors: list[persist.LintError],
    **kwargs: object
) -> None:
    problems = State['problems_per_file'][filename]
    if linter_name in State['failed_linters_per_file'][filename]:
        problems[linter_name] = '?'
    elif linter_name in State['assigned_linters_per_file'][filename] or errors:
        if linter_name not in State['assigned_linters_per_file'][filename]:
            State['assigned_linters_per_file'][filename].add(linter_name)

        counts = count_problems(errors)
        if sum(counts.values()) == 0:
            problems[linter_name] = ''
        else:
            sorted_keys = (
                tuple(sorted(counts.keys() - {'w', 'e'}))
                + ('w', 'e')
            )
            parts = ' '.join(
                "{}:{}".format(error_type, counts[error_type])
                for error_type in sorted_keys
                if error_type in counts and counts[error_type] > 0
            )
            problems[linter_name] = '({})'.format(parts)
    else:
        problems.pop(linter_name, None)

    if actual_linters_changed(filename, set(problems.keys())):
        force_verbose_format(filename)

    sublime.set_timeout(lambda: redraw_file_(filename))


def count_problems(errors: list[persist.LintError]) -> dict[str, int]:
    counters: defaultdict[str, int] = defaultdict(int)
    for error in errors:
        error_type = error['error_type']
        counters[error_type[0]] += 1

    return counters


def redraw_file_(filename: FileName) -> None:
    for view in views_into_file(filename):
        draw(view)


def views_into_file(filename: FileName) -> Iterator[sublime.View]:
    return (
        view
        for window in sublime.windows()
        for view in window.views()
        if util.canonical_filename(view) == filename
    )


def draw(view: sublime.View) -> None:
    if persist.settings.get('statusbar.show_active_linters'):
        filename = util.canonical_filename(view)
        problems = State['problems_per_file'][filename]
        expanded_ok = filename in State['expanded_ok']
        if (
            not expanded_ok
            and problems.keys()
            and all(part == '' for part in problems.values())
        ):
            message = 'ok'
            view.set_status(STATUS_ACTIVE_KEY, message)
            return

        message = ' '.join(
            '{}{}'.format(linter_name, summary)
            for linter_name, summary in sorted(problems.items(), key=by_severity)
        )
        view.set_status(STATUS_ACTIVE_KEY, message)
    else:
        view.erase_status(STATUS_ACTIVE_KEY)


def by_severity(item):
    linter_name, summary = item
    if summary == '':
        return (0, linter_name)
    elif summary[0] == '?':
        return (2, linter_name)
    return (1, linter_name)


THROTTLER_TOKENS = {}
THROTTLER_LOCK = threading.Lock()


def throttled_on_args(fn: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> Callable[[], None]:
    key = (fn,) + args
    action = partial(fn, *args, **kwargs)
    with THROTTLER_LOCK:
        THROTTLER_TOKENS[key] = action

    def program():
        with THROTTLER_LOCK:
            # Use `get` bc during hot-reload `THROTTLER_TOKENS` gets emptied
            ok = THROTTLER_TOKENS.get(key) == action
        if ok:
            action()

    return program


ACTIVATED_VIEWS: set[sublime.View] = set()


class OnFirstActivate(sublime_plugin.EventListener):
    def on_activated(self, view: sublime.View) -> None:
        if view in ACTIVATED_VIEWS:
            return

        ACTIVATED_VIEWS.add(view)
        on_first_activate(view)

    def on_close(self, view: sublime.View) -> None:
        ACTIVATED_VIEWS.discard(view)


def distinct_mapping(store: dict[T, U], key: T, val: U) -> bool:
    """Store key/value pair in the `store`; return if the value has changed"""
    previous = store.get(key)
    current = store[key] = val
    return current != previous


actual_linters_changed = partial(distinct_mapping, persist.actual_linters)
attempted_linters_changed = partial(distinct_mapping, ATTEMPTED_LINTERS)
