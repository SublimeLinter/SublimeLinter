from __future__ import annotations
import sublime
import sublime_plugin

from .lint import persist, events, util

from typing import Iterable, Optional, TypedDict

FileName = str
LinterName = str
LintError = persist.LintError


class State_(TypedDict):
    active_view: Optional[sublime.View]
    active_filename: Optional[FileName]
    current_pos: int


STATUS_COUNTER_KEY = "sublime_linter_status_counter"
STATUS_MSG_KEY = "sublime_linter_status_messages"

State: State_ = {
    'active_view': None,
    'active_filename': None,
    'current_pos': -1
}


def plugin_loaded():
    active_view = sublime.active_window().active_view()
    State.update({
        'active_view': active_view,
        'active_filename': util.canonical_filename(active_view) if active_view else None,
    })


def plugin_unloaded():
    events.off(on_lint_result)
    for window in sublime.windows():
        for view in window.views():
            view.erase_status(STATUS_COUNTER_KEY)
            view.erase_status(STATUS_MSG_KEY)


@events.on(events.LINT_RESULT)
def on_lint_result(filename, **kwargs):
    if State['active_filename'] == filename:
        draw(**State)


class UpdateState(sublime_plugin.EventListener):
    # Fires once per view with the actual view, not necessary the primary
    def on_activated_async(self, active_view):
        State.update({
            'active_view': active_view,
            'active_filename': util.canonical_filename(active_view),
            'current_pos': get_current_pos(active_view)
        })
        draw(**State)

    # Fires multiple times for each view into the same buffer, but
    # the argument is unfortunately always the same view, the primary.
    # Activating a view via mouse click fires this also, twice per view.
    def on_selection_modified_async(self, view):
        active_view = State['active_view']
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


def draw(active_view, active_filename, current_pos, **kwargs):
    message = messages_under_cursor(active_filename, current_pos)
    if message:
        active_view.set_status(STATUS_MSG_KEY, message)
    else:
        active_view.erase_status(STATUS_MSG_KEY)


def messages_under_cursor(filename: FileName, current_pos: int) -> str:
    message_template = persist.settings.get('statusbar.messages_template')
    if message_template != "":
        msgs = (
            message_template.format(
                linter=error["linter"],
                type=error["error_type"],
                message=error["msg"].splitlines()[0],
                code=error["code"]
            )
            for error in get_errors_under_cursor(filename, current_pos)
        )
        return "; ".join(msgs)
    else:
        return ""


def get_errors_under_cursor(filename: FileName, cursor: int) -> Iterable[LintError]:
    return (
        error for error in persist.file_errors.get(filename, [])
        if error['region'].contains(cursor)
    )


def get_current_pos(view: sublime.View) -> int:
    try:
        return view.sel()[0].begin()
    except (AttributeError, IndexError):
        return -1
