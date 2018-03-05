import sublime
import sublime_plugin

import time

from .lint import events


INITIAL_DELAY = 2
CYCLE_TIME = 200
TIMEOUT = 20
STATUS_BUSY_KEY = "sublime_linter_status_busy"

State = {
    'active_view': None,
    'running': {}
}


def plugin_loaded():
    State.update({
        'active_view': sublime.active_window().active_view()
    })


def plugin_unloaded():
    events.off(on_begin_linting)
    events.off(on_finished_linting)


@events.on(events.LINT_START)
def on_begin_linting(buffer_id):
    State['running'][buffer_id] = time.time()

    active_view = State['active_view']
    if active_view.buffer_id() == buffer_id:
        sublime.set_timeout_async(lambda: draw(**State), INITIAL_DELAY * 1000)


@events.on(events.LINT_END)
def on_finished_linting(buffer_id, **kwargs):
    State['running'].pop(buffer_id, None)

    active_view = State['active_view']
    if active_view.buffer_id() == buffer_id:
        draw(**State)


class UpdateState(sublime_plugin.EventListener):
    def on_activated_async(self, active_view):
        State.update({
            'active_view': active_view
        })

        draw(**State)


indicators = [
    'Linting.  ',
    'Linting.. ',
    'Linting. .',
    'Linting ..',
    'Linting  .',
]


def draw(active_view, running, **kwargs):
    buffer_id = active_view.buffer_id()
    start_time = running.get(buffer_id, None)
    now = time.time()
    if start_time and (INITIAL_DELAY <= (now - start_time) < TIMEOUT):
        num = len(indicators)
        text = indicators[int((now - start_time) * 1000 / CYCLE_TIME) % num]
        active_view.set_status(STATUS_BUSY_KEY, text)
        sublime.set_timeout_async(lambda: draw(**State), CYCLE_TIME)
    else:
        active_view.erase_status(STATUS_BUSY_KEY)
