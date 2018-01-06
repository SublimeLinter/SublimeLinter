import sublime
import sublime_plugin

from .lint import persist
from .lint.const import STATUS_KEY
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
            'we_count': get_we_count(active_view.id())
        })

        draw(**State)


class UpdateState(sublime_plugin.EventListener):
    def on_activated_async(self, active_view):
        vid = active_view.id()

        current_pos = get_current_pos(active_view)
        we_count = get_we_count(vid)

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


def draw(active_view, we_count, current_pos, **kwargs):
    vid = active_view.id()

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
