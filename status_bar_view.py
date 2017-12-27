import sublime
import sublime_plugin

from .lint import persist, util
from .lint.const import STATUS_KEY
from . import events


State = {
    'running': {},
    'we_count': {},
    'active_view': None,
    'errors_on_pos': {}
}


def plugin_loaded():
    State.update({
        'active_view': sublime.active_window().active_view()
    })


def plugin_unloaded():
    events.off(on_finished_linting)


@events.on(events.FINISHED_LINTING)
def on_finished_linting(vid):
    print('****** on_finished_linting received', vid)
    State['running'].pop(vid, None)
    State.update({
        'we_count': get_we_count(vid)
    })

    draw(**State)


class UpdateState(sublime_plugin.EventListener):
    def on_activated_async(self, view):
        active_view = util.get_focused_view(view)
        vid = active_view.id() if active_view else None
        State.update({
            'active_view': util.get_focused_view(active_view),
            'we_count': get_we_count(vid)
        })
        draw(**State)

    def on_selection_modified_async(self, view):
        active_view = State['active_view']
        vid = active_view.id() if active_view else None
        current_pos = get_current_pos(active_view)
        errors_on_pos = persist.errors.get_region_dict(vid, *current_pos)
        State.update({
            'errors_on_pos': errors_on_pos
        })
        draw(**State)


def draw(active_view, we_count, errors_on_pos, **kwargs):
    if not active_view:
        return

    if not we_count:
        active_view.erase_status(STATUS_KEY)
        return

    status = "W: {warning} E: {error}".format(**we_count)

    msgs = []
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


