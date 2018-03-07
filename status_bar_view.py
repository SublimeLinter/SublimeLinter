import sublime
import sublime_plugin

from collections import defaultdict

from .lint import persist
from .lint.const import WARNING, ERROR
from .lint import events


STATUS_COUNTER_KEY = "sublime_linter_status_counter"
STATUS_MSG_KEY = "sublime_linter_status_messages"

State = {
    'we_count': {},
    'active_view': None,
    'current_pos': (-1, -1),
    'errors_per_line': defaultdict(list)
}


def plugin_loaded():
    State.update({
        'active_view': sublime.active_window().active_view()
    })


def plugin_unloaded():
    events.off(on_lint_result)


@events.on(events.LINT_RESULT)
def on_lint_result(buffer_id, **kwargs):
    active_view = State['active_view']
    if active_view.buffer_id() == buffer_id:
        State.update({
            'we_count': get_we_count(buffer_id),
            'errors_per_line': errors_per_line(persist.errors[buffer_id]),
        })

        draw(**State)


class UpdateState(sublime_plugin.EventListener):
    # Fires once per view with the actual view, not necessary the primary
    def on_activated_async(self, active_view):
        bid = active_view.buffer_id()

        State.update({
            'active_view': active_view,
            'we_count': get_we_count(bid),
            'errors_per_line': errors_per_line(persist.errors[bid]),
            'current_pos': get_current_pos(active_view)
        })
        draw(**State)

    # Triggers multiple times for each view into the same buffer.
    # But the argument is always the same view, the primary.
    # Activate view via mouse click fires this also, twice per view.
    def on_selection_modified_async(self, view):
        active_view = State['active_view']
        # It is possible that views (e.g. panels) update in the background.
        # So we check here and return early.
        if active_view.buffer_id() != view.buffer_id():
            return

        current_pos = get_current_pos(active_view)
        if current_pos != State['current_pos']:
            State.update({
                'current_pos': current_pos
            })
            draw(**State)


def draw(active_view, we_count, current_pos, errors_per_line, **kwargs):
    counter_template = persist.settings.get('statusbar.counters_template')
    if we_count:
        counter = counter_template.format(warning=we_count[0], error=we_count[1])
        if counter != active_view.get_status(STATUS_COUNTER_KEY):
            active_view.set_status(STATUS_COUNTER_KEY, counter)
    else:
        active_view.erase_status(STATUS_COUNTER_KEY)

    msgs = messages_under_cursor(errors_per_line, current_pos)
    message_template = persist.settings.get('statusbar.messages_template')
    if msgs:
        message = message_template.format(messages="; ".join(msgs))
        if message != active_view.get_status(STATUS_MSG_KEY):
            active_view.set_status(STATUS_MSG_KEY, message)
    else:
        active_view.erase_status(STATUS_MSG_KEY)


def messages_under_cursor(errors, current_pos):
    line, col = current_pos
    return [
        error['msg'] for error in errors[line]
        if error["start"] <= col <= error["end"]
    ]


def errors_per_line(errors):
    rv = defaultdict(list)
    for error in errors:
        rv[error['line']].append(error)
    return rv


def get_we_count(bid):
    warnings, errors = 0, 0
    for error in persist.errors[bid]:
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
