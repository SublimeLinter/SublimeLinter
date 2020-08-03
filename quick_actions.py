import sublime
import sublime_plugin

from .lint import persist
from .lint import quick_fix
from .lint import util


MYPY = False
if MYPY:
    from typing import Callable, List, Optional, TypedDict

    LintError = persist.LintError
    QuickAction = quick_fix.QuickAction
    Event = TypedDict("Event", {"x": float, "y": float})


class sublime_linter_quick_actions(sublime_plugin.TextCommand):
    def want_event(self):
        return True

    def is_visible(self, event=None, prefer_panel=False):
        # type: (Event, bool) -> bool
        if event:
            return bool(self.available_actions(self.view, event))
        else:
            return len(self.view.sel()) == 1

    def run(self, edit, event=None, prefer_panel=False):
        # type: (sublime.Edit, Event, bool) -> None
        view = self.view
        window = view.window()
        assert window

        # We currently only allow multiple selections for the
        # context menu where we can select *one* of the selections
        # using the click event data.
        if event is None and len(self.view.sel()) != 1:
            window.status_message("Quick actions don't support multiple selections")
            return

        def on_done(idx):
            # type: (int) -> None
            if idx < 0:
                return

            action = actions[idx]
            quick_fix.apply_fix(action.fn, view)

        actions = self.available_actions(view, event)
        if not actions:
            if prefer_panel:
                window.show_quick_panel(
                    ["No quick action available."],
                    lambda x: None
                )
            else:
                window.status_message("No quick action available")
        elif len(actions) == 1 and not prefer_panel:
            on_done(0)
        else:
            window.show_quick_panel(
                [action.description for action in actions],
                on_done
            )

    def available_actions(self, view, event):
        # type: (sublime.View, Optional[Event]) -> List[QuickAction]
        errors = self.affected_errors(view, event)
        return sorted(
            list(quick_fix.actions_for_errors(errors, view)),
            key=lambda action: (-len(action.solves), action.description)
        )

    def affected_errors(self, view, event):
        # type: (sublime.View, Optional[Event]) -> List[LintError]
        if event:
            vector = (event['x'], event['y'])
            point = view.window_to_text(vector)
            for selection in view.sel():
                if selection.contains(point):
                    sel = selection
                    break
            else:
                sel = sublime.Region(point)
        else:
            sel = view.sel()[0]

        filename = util.get_filename(view)
        if sel.empty():
            char_selection = sublime.Region(sel.a, sel.a + 1)
            errors = get_errors_where(
                filename,
                lambda region: region.intersects(char_selection)
            )
            if errors:
                return errors

            sel = view.full_line(sel.a)

        return get_errors_where(
            filename,
            lambda region: region.intersects(sel)
        )


def get_errors_where(filename, fn):
    # type: (str, Callable[[sublime.Region], bool]) -> List[LintError]
    return [
        error for error in persist.file_errors[filename]
        if fn(error['region'])
    ]
