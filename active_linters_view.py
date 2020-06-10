from collections import defaultdict
from functools import partial
import threading

import sublime
import sublime_plugin

from .lint import events, persist, util


MYPY = False
if MYPY:
    from typing import DefaultDict, Dict, Iterator, List, Set
    from mypy_extensions import TypedDict

    FileName = str
    LinterName = str
    State_ = TypedDict('State_', {
        'assigned_linters_per_file': DefaultDict[FileName, Set[LinterName]],
        'failed_linters_per_file': DefaultDict[FileName, Set[LinterName]],
        'problems_per_file': DefaultDict[FileName, Dict[LinterName, str]],
        'running': DefaultDict[FileName, int],
        'expanded_ok': Set[FileName],
    })


STATUS_ACTIVE_KEY = 'sublime_linter_status_active'

State = {
    'assigned_linters_per_file': defaultdict(set),
    'failed_linters_per_file': defaultdict(set),
    'problems_per_file': defaultdict(dict),
    'running': defaultdict(int),
    'expanded_ok': set(),
}  # type: State_


def plugin_unloaded():
    events.off(redraw_file)
    events.off(on_begin_linting)
    events.off(on_finished_linting)
    events.off(on_actual_linters_changed)

    for window in sublime.windows():
        for view in window.views():
            view.erase_status(STATUS_ACTIVE_KEY)


@events.on(events.LINT_START)
def on_begin_linting(filename):
    # type: (FileName) -> None
    State['running'][filename] += 1


@events.on(events.LINT_END)
def on_finished_linting(filename):
    # type: (FileName) -> None
    if State['running'][filename] <= 1:
        State['running'].pop(filename)
    else:
        State['running'][filename] -= 1


def on_first_activate(view):
    # type: (sublime.View) -> None
    if not util.is_lintable(view):
        return

    filename = util.get_filename(view)
    set_expanded_ok(filename)
    draw(view, State['problems_per_file'][filename], expanded_ok=True)


def on_assigned_linters_changed(filename):
    # type: (FileName) -> None
    set_expanded_ok(filename)
    redraw_file_(filename, State['problems_per_file'][filename], expanded_ok=True)


def set_expanded_ok(filename):
    # type: (FileName) -> None
    State['expanded_ok'].add(filename)


def enqueue_unset_expanded_ok(view, timeout=3000):
    # type: (sublime.View, int) -> None
    sublime.set_timeout(
        throttled_on_args(_unset_expanded_ok, view.id()),
        timeout
    )


def _unset_expanded_ok(vid):
    # type: (sublime.ViewId) -> None
    view = sublime.View(vid)
    if not view.is_valid():
        return

    filename = util.get_filename(view)
    # Keep expanded if linters are running to minimize redraws
    if State['running'].get(filename, 0) > 0:
        enqueue_unset_expanded_ok(view)
        return

    State['expanded_ok'].discard(filename)
    draw(view, State['problems_per_file'][filename], expanded_ok=False)


class sublime_linter_assigned(sublime_plugin.WindowCommand):
    def run(self, filename, linter_names):
        # type: (FileName, List[LinterName]) -> None
        State['assigned_linters_per_file'][filename] = set(linter_names)
        State['failed_linters_per_file'][filename] = set()

        if assigned_linters_changed(filename, linter_names):
            on_assigned_linters_changed(filename)


class sublime_linter_unassigned(sublime_plugin.WindowCommand):
    def run(self, filename, linter_name):
        State['assigned_linters_per_file'][filename].discard(linter_name)
        State['failed_linters_per_file'][filename].discard(linter_name)


class sublime_linter_failed(sublime_plugin.WindowCommand):
    def run(self, filename, linter_name):
        State['failed_linters_per_file'][filename].add(linter_name)


@events.on(events.LINT_RESULT)
def redraw_file(filename, linter_name, errors, **kwargs):
    # type: (FileName, LinterName, List[persist.LintError], object) -> None
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

    remember_actual_linters(filename, set(problems.keys()))

    sublime.set_timeout(
        lambda: redraw_file_(
            filename,
            problems,
            # eval on the UI thread!
            expanded_ok=filename in State['expanded_ok']
        )
    )


@events.on('actual_linters_changed')
def on_actual_linters_changed(filename, linter_names):
    set_expanded_ok(filename)


def count_problems(errors):
    # type: (List[persist.LintError]) -> Dict[str, int]
    counters = defaultdict(int)  # type: DefaultDict[str, int]
    for error in errors:
        error_type = error['error_type']
        counters[error_type[0]] += 1

    return counters


def redraw_file_(filename, problems, expanded_ok):
    # type: (FileName, Dict[LinterName, str], bool) -> None
    for view in views_into_file(filename):
        draw(view, problems, expanded_ok)


def views_into_file(filename):
    # type: (FileName) -> Iterator[sublime.View]
    return (
        view
        for window in sublime.windows()
        for view in window.views()
        if util.get_filename(view) == filename
    )


def draw(view, problems, expanded_ok):
    # type: (sublime.View, Dict[LinterName, str], bool) -> None
    if persist.settings.get('statusbar.show_active_linters'):
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
        enqueue_unset_expanded_ok(view)
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


def throttled_on_args(fn, *args, **kwargs):
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


ACTIVATED_VIEWS = set()


class OnFirstActivate(sublime_plugin.EventListener):
    def on_activated(self, view):
        # type: (sublime.View) -> None
        vid = view.id()
        if vid in ACTIVATED_VIEWS:
            return

        ACTIVATED_VIEWS.add(vid)
        on_first_activate(view)

    def on_close(self, view):
        # type: (sublime.View) -> None
        ACTIVATED_VIEWS.discard(view.id())


if MYPY:
    from typing import Container, TypeVar
    T = TypeVar('T')
    U = TypeVar('U')


ASSIGNED_LINTERS = {}  # type: Dict[FileName, Container[LinterName]]


def remember_actual_linters(filename, linter_names):
    # type: (FileName, Set[LinterName])  -> None
    previous = persist.actual_linters.get(filename)
    current = persist.actual_linters[filename] = linter_names
    if current != previous:
        events.broadcast('actual_linters_changed', {
            'filename': filename,
            'linter_names': linter_names
        })


def assigned_linters_changed(filename, linter_names):
    # type: (FileName, Container[LinterName])  -> bool
    return not distinct_mapping(ASSIGNED_LINTERS, filename, linter_names)


def distinct_mapping(store, key, val):
    # type: (Dict[T, U], T, U) -> bool
    previous = store.get(key)
    current = store[key] = val
    return current == previous
