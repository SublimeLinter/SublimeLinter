import sublime
import sublime_plugin

from .lint import persist
from .lint import quick_fix
from .lint import util


MYPY = False
if MYPY:
    from typing import Callable, List

    LintError = persist.LintError


class sublime_linter_quick_actions(sublime_plugin.TextCommand):
    def is_enabled(self, prefer_panel=False, **kwargs):
        # type: (bool, object) -> bool
        if prefer_panel:
            return len(self.view.sel()) == 1
        else:
            return True

    def run(self, edit, prefer_panel=False, **kwargs):
        # type: (sublime.Edit, bool, object) -> None
        view = self.view
        window = view.window()
        assert window

        if len(self.view.sel()) != 1:
            window.status_message("Quick actions don't support multiple selections")
            return

        sel = view.sel()[0]
        filename = util.get_filename(view)
        if sel.empty():
            char_selection = sublime.Region(sel.a, sel.a + 1)
            errors = get_errors_where(
                filename,
                lambda region: region.intersects(char_selection)
            )
            if not errors:
                sel = view.full_line(sel.a)
                errors = get_errors_where(
                    filename,
                    lambda region: region.intersects(sel)
                )
        else:
            errors = get_errors_where(
                filename,
                lambda region: region.intersects(sel)
            )

        def on_done(idx):
            # type: (int) -> None
            if idx < 0:
                return

            action = actions[idx]
            quick_fix.apply_fix(action.fn, view)

        actions = sorted(
            list(quick_fix.actions_for_errors(errors, view)),
            key=lambda action: (-len(action.solves), action.description)
        )
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


def get_errors_where(filename, fn):
    # type: (str, Callable[[sublime.Region], bool]) -> List[LintError]
    return [
        error for error in persist.file_errors[filename]
        if fn(error['region'])
    ]
