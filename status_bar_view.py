import sublime
import sublime_plugin

from .lint import persist
from .lint.const import STATUS_KEY, WARNING, ERROR
from .lint import events


State = {
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


@events.on(events.FINISHED_LINTING)
def on_finished_linting(buffer_id):
    active_view = State['active_view']
    if active_view.buffer_id() == buffer_id:
        State.update({
            'we_count': get_we_count(buffer_id)
        })

        draw(**State)


class UpdateState(sublime_plugin.EventListener):
    def on_activated_async(self, active_view):
        bid = active_view.buffer_id()

        current_pos = get_current_pos(active_view)
        we_count = get_we_count(bid)

        State.update({
            'active_view': active_view,
            'we_count': we_count,
            'current_pos': current_pos
        })
        draw(**State)

    def on_selection_modified_async(self, _primary_view_):
        active_view = State['active_view']
        current_pos = get_current_pos(active_view)
        if current_pos != State['current_pos']:
            State.update({
                'current_pos': current_pos
            })
            draw(**State)


def get_current_messages(current_pos, errors):
    line, col = current_pos
    return [
        e["msg"] for e in errors
        if e["line"] == line and e["start"] <= col <= e["end"]
    ]


def draw(active_view, we_count, current_pos, **kwargs):

    if not we_count:
        active_view.erase_status(STATUS_KEY)
        return
    status = "W: {} E: {}".format(*we_count)

    bid = active_view.buffer_id()
    errors = persist.raw_errors[bid]
    msgs = get_current_messages(current_pos, errors)

    if msgs:
        status += " - {}".format("; ".join(msgs))

    if status != active_view.get_status(STATUS_KEY):
        active_view.set_status(STATUS_KEY, status)


def get_we_count(bid):
    warnings, errors = 0, 0
    for error in persist.raw_errors[bid]:
        error_type = error['error_type']
        if error_type == WARNING:
            warnings += 1
        elif error_type == ERROR:
            errors += 1
    return (warnings, errors)


def get_current_pos(view):
    try:
        return view.rowcol(view.sel()[0].begin())
    except (AttributeError, IndexError):
        return -1, -1
