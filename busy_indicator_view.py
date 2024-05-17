from __future__ import annotations
from collections import defaultdict
from functools import partial
import time
import threading

import sublime
import sublime_plugin

from .lint import events, util


from typing import Callable, DefaultDict, Optional, TypedDict, TypeVar
from typing_extensions import ParamSpec
P = ParamSpec('P')
T = TypeVar('T')

FileName = str
LinterName = str


class State_(TypedDict):
    active_view: Optional[sublime.View]
    running: DefaultDict[FileName, dict[LinterName, float]]


INITIAL_DELAY = 2
CYCLE_TIME = 200
TIMEOUT = 20
STATUS_BUSY_KEY = "sublime_linter_status_busy"

State = {
    'active_view': None,
    'running': defaultdict(dict),
}  # type: State_


def plugin_loaded():
    active_view = sublime.active_window().active_view()
    if active_view and util.is_lintable(active_view):
        State.update({
            'active_view': active_view
        })


def plugin_unloaded():
    events.off(on_begin_linting)
    events.off(on_finished_linting)
    for window in sublime.windows():
        for view in window.views():
            view.erase_status(STATUS_BUSY_KEY)


@events.on(events.LINT_START)
def on_begin_linting(filename, linter_name):
    # type: (FileName, LinterName) -> None
    State['running'][filename][linter_name] = time.time()

    active_view = State['active_view']
    if active_view and util.canonical_filename(active_view) == filename:
        sublime.set_timeout_async(
            throttled_on_args(draw, active_view, filename),
            INITIAL_DELAY * 1000
        )


@events.on(events.LINT_END)
def on_finished_linting(filename, linter_name):
    # type: (FileName, LinterName) -> None
    State['running'][filename].pop(linter_name, None)
    if not State['running'][filename]:
        State['running'].pop(filename, None)

    active_view = State['active_view']
    if active_view and util.canonical_filename(active_view) == filename:
        draw(active_view, filename)


class UpdateState(sublime_plugin.EventListener):
    def on_activated(self, active_view):
        # type: (sublime.View) -> None
        if not util.is_lintable(active_view):
            return

        State.update({
            'active_view': active_view
        })

        draw(active_view, util.canonical_filename(active_view))


indicators = [
    'Linting.  ',
    'Linting.. ',
    'Linting. .',
    'Linting ..',
    'Linting  .',
]


def draw(view, filename):
    # type: (sublime.View, FileName) -> None
    start_time = min(State['running'].get(filename, {}).values(), default=None)
    now = time.time()
    if start_time and (INITIAL_DELAY <= (now - start_time) < TIMEOUT):
        num = len(indicators)
        text = indicators[int((now - start_time) * 1000 / CYCLE_TIME) % num]
        view.set_status(STATUS_BUSY_KEY, text)
        sublime.set_timeout_async(throttled_on_args(draw, view, filename), CYCLE_TIME)
    else:
        view.erase_status(STATUS_BUSY_KEY)


THROTTLER_TOKENS = {}
THROTTLER_LOCK = threading.Lock()


def throttled_on_args(fn, *args, **kwargs):
    # type: (Callable[P, T], P.args, P.kwargs) -> Callable[[], None]
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
