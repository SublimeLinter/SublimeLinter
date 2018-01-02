import sublime
import sublime_plugin

import time
from itertools import cycle

from .lint import persist, util
from .lint.const import STATUS_KEY
from .lint import events


State = {
    'running': {},
    'we_count': {},
    'active_view': None,
    'current_pos': (-1, -1)
}


def plugin_loaded():
    State.update({
        'active_view': sublime.active_window().active_view()
    })


def plugin_unloaded():
    events.off(on_finished_linting)


@events.on(events.BEGIN_LINTING)
def on_begin_linting(vid):
    State['running'][vid] = time.time()

    active_view = State['active_view']
    if active_view and active_view.id() == vid:
        draw(**State)


@events.on(events.FINISHED_LINTING)
def on_finished_linting(vid):
    State['running'].pop(vid, None)

    active_view = State['active_view']
    if active_view and active_view.id() == vid:
        State.update({
            'we_count': get_we_count(vid)
        })

        draw(**State)


class UpdateState(sublime_plugin.EventListener):
    def on_activated_async(self, view):
        active_view = util.get_focused_view(view)
        vid = active_view.id() if active_view else None

        current_pos = get_current_pos(active_view)
        we_count = get_we_count(vid)

        State.update({
            'active_view': active_view,
            'we_count': we_count,
            'current_pos': current_pos
        })

        draw(**State)

    def on_selection_modified_async(self, view):
        active_view = State['active_view']
        current_pos = get_current_pos(active_view)
        if current_pos != State['current_pos']:
            State.update({
                'current_pos': current_pos
            })

            draw(**State)


INITIAL_DELAY = 1
CYCLE_TIME = 700
TIMEOUT = 20


def draw(active_view, we_count, current_pos, running, **kwargs):
    if not active_view:
        return

    vid = active_view.id()
    start_time = running.get(vid, None)
    now = time.time()
    if start_time and (INITIAL_DELAY < (now - start_time) < TIMEOUT):
        cursor = next(phases)
        active_view.set_status(STATUS_KEY, "W: {} E: {}".format(cursor, cursor))
        sublime.set_timeout_async(lambda: draw(**State), CYCLE_TIME)
        return

    if not we_count:
        active_view.erase_status(STATUS_KEY)
        return

    status = "W: {warning} E: {error}".format(**we_count)

    msgs = []
    errors_on_pos = persist.errors.get_region_dict(vid, *current_pos)
    for error_type, dc in errors_on_pos.items():
        for d in dc:
            msgs.append(d["msg"])
    if msgs:
        status += " - {}".format("; ".join(msgs))

    if status != active_view.get_status(STATUS_KEY):
        active_view.set_status(STATUS_KEY, status)


def get_we_count(vid):
    view_errors = persist.errors.get_view_dict(vid) if vid else {}
    return view_errors.get('we_count_view', {})


def get_current_pos(view):
    try:
        return view.rowcol(view.sel()[0].begin())
    except (AttributeError, IndexError):
        return -1, -1


phases = cycle(['.', ' '])
