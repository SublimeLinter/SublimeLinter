import sublime
import sublime_plugin

from .lint import persist
from .lint import util
from .lint import events
from .panel import panel


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
    vid = active_view.id()

    if active_view.buffer_id() == buffer_id:
        State.update({
            'we_count': persist.errors.get_view_we_count(vid)
        })

        panel.update_panel_selection(**State)


class UpdateState(sublime_plugin.EventListener):
    def on_activated_async(self, active_view):
        vid = active_view.id()

        State.update({
            'active_view': active_view,
            'we_count': persist.errors.get_view_we_count(vid),
            'current_pos': util.get_current_pos(active_view)
        })

        panel.update_panel_selection(**State)

    def on_selection_modified_async(self, _primary_view_):
        active_view = State['active_view']
        current_pos = util.get_current_pos(active_view)
        if current_pos != State['current_pos']:
            State.update({
                'current_pos': current_pos
            })

            panel.update_panel_selection(**State)
