import sublime
import sublime_plugin

import time

from .lint import events, util


MYPY = False
if MYPY:
    from typing import Dict, Optional
    from mypy_extensions import TypedDict

    Filename = str
    LinterName = str
    State_ = TypedDict('State_', {
        'active_view': Optional[sublime.View],
        'running': Dict[sublime.BufferId, float],
    })


INITIAL_DELAY = 2
CYCLE_TIME = 200
TIMEOUT = 20
STATUS_BUSY_KEY = "sublime_linter_status_busy"

State = {
    'active_view': None,
    'running': {}
}  # type: State_


def plugin_loaded():
    active_view = sublime.active_window().active_view()
    if util.is_lintable(active_view):
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
def on_begin_linting(buffer_id):
    # type: (sublime.BufferId) -> None
    State['running'][buffer_id] = time.time()

    active_view = State['active_view']
    if active_view and active_view.buffer_id() == buffer_id:
        sublime.set_timeout_async(
            lambda: draw(active_view),  # type: ignore  # mypy bug
            INITIAL_DELAY * 1000
        )


@events.on(events.LINT_END)
def on_finished_linting(buffer_id, **kwargs):
    # type: (sublime.BufferId, object) -> None
    State['running'].pop(buffer_id, None)

    active_view = State['active_view']
    if active_view and active_view.buffer_id() == buffer_id:
        draw(active_view)


class UpdateState(sublime_plugin.EventListener):
    def on_activated(self, active_view):
        # type: (sublime.View) -> None
        if not util.is_lintable(active_view):
            return

        State.update({
            'active_view': active_view
        })

        draw(active_view)


indicators = [
    'Linting.  ',
    'Linting.. ',
    'Linting. .',
    'Linting ..',
    'Linting  .',
]


def draw(view):
    # type: (sublime.View) -> None
    buffer_id = view.buffer_id()
    start_time = State['running'].get(buffer_id, None)
    now = time.time()
    if start_time and (INITIAL_DELAY <= (now - start_time) < TIMEOUT):
        num = len(indicators)
        text = indicators[int((now - start_time) * 1000 / CYCLE_TIME) % num]
        view.set_status(STATUS_BUSY_KEY, text)
        sublime.set_timeout_async(lambda: draw(view), CYCLE_TIME)
    else:
        view.erase_status(STATUS_BUSY_KEY)
