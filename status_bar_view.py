import sublime
import sublime_plugin

from .lint import persist
from .lint import events


STATUS_COUNTER_KEY = "sublime_linter_status_counter"
STATUS_MSG_KEY = "sublime_linter_status_messages"

State = {
    'active_view': None,
    'current_pos': -1
}


def plugin_loaded():
    State.update({
        'active_view': sublime.active_window().active_view()
    })


def plugin_unloaded():
    events.off(on_lint_result)
    for window in sublime.windows():
        for view in window.views():
            view.erase_status(STATUS_COUNTER_KEY)
            view.erase_status(STATUS_MSG_KEY)


@events.on(events.LINT_RESULT)
def on_lint_result(buffer_id, **kwargs):
    active_view = State['active_view']
    if active_view and active_view.buffer_id() == buffer_id:
        draw(**State)


class UpdateState(sublime_plugin.EventListener):
    # Fires once per view with the actual view, not necessary the primary
    def on_activated_async(self, active_view):
        State.update({
            'active_view': active_view,
            'current_pos': get_current_pos(active_view)
        })
        draw(**State)

    # Fires multiple times for each view into the same buffer, but
    # the argument is unfortunately always the same view, the primary.
    # Activating a view via mouse click fires this also, twice per view.
    def on_selection_modified_async(self, view):
        active_view = State['active_view']
        # Do not race between `plugin_loaded` and this event handler
        if active_view is None:
            return

        if view.buffer_id() != active_view.buffer_id():
            return

        current_pos = get_current_pos(active_view)
        if current_pos != State['current_pos']:
            State.update({
                'current_pos': current_pos
            })
            draw(**State)


def draw(active_view, current_pos, **kwargs):
    message = messages_under_cursor(active_view, current_pos)
    if not message:
        active_view.erase_status(STATUS_MSG_KEY)
    elif message != active_view.get_status(STATUS_MSG_KEY):
        active_view.set_status(STATUS_MSG_KEY, message)


def messages_under_cursor(view, current_pos):
    message_template = persist.settings.get('statusbar.messages_template')
    if message_template != "":
        msgs = (
            message_template.format(
                linter=error["linter"],
                type=error["error_type"],
                message=error["msg"],
                code=error["code"]
            )
            for error in get_errors_under_cursor(view.buffer_id(), current_pos)
        )
        return "; ".join(msgs)
    else:
        return ""


def get_errors_under_cursor(bid, cursor):
    return (
        error for error in persist.errors.get(bid, [])
        if error['region'].contains(cursor)
    )


def get_current_pos(view):
    try:
        return view.sel()[0].begin()
    except (AttributeError, IndexError):
        return -1
