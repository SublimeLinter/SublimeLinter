from functools import partial
import re

import sublime
import sublime_plugin

from . import persist
from . import util
from .generic_text_command import replace_view_content


MYPY = False
if MYPY:
    from typing import Callable, List, Iterator, NamedTuple, Optional
    LintError = persist.LintError
    TextRange = NamedTuple("TextRange", [("text", str), ("range", sublime.Region)])
    Fixer = Callable[[LintError, sublime.View], TextRange]
    Fix = Callable[[sublime.View], TextRange]
    QuickAction = NamedTuple("QuickAction", [("description", str), ("fn", Fixer)])
    Action = NamedTuple("Action", [("description", str), ("fn", Fix)])

else:
    from collections import namedtuple
    QuickAction = namedtuple("QuickAction", "description fn")
    Action = namedtuple("Action", "description fn")
    TextRange = namedtuple("TextRange", "text range")


class sl_fix_by_ignoring(sublime_plugin.TextCommand):
    def run(self, edit):
        view = self.view
        window = view.window()
        assert window
        sel = [s for s in view.sel()]
        if len(sel) > 1:
            window.status_message("Only one cursor please.")
            return

        if not sel[0].empty():
            window.status_message("Only cursors no selections please.")

        cursor = sel[0].a
        actions = available_actions_on_line(view, cursor)
        if not actions:
            window.status_message("No errors here.")

        def on_done(idx):
            # type: (int) -> None
            if idx < 0:
                return

            action = actions[idx]
            apply_fix(action.fn, view)

        window.show_quick_panel(
            [action.description for action in actions],
            on_done
        )


def available_actions_on_line(view, pt):
    # type: (sublime.View, int) -> List[Action]
    filename = util.get_filename(view)
    line = view.full_line(pt)
    errors = get_errors_where(filename, lambda region: region.intersects(line))
    return [
        action
        for error in errors
        for action in actions_for_error(error)
    ]


def get_errors_where(filename, fn):
    # type: (str, Callable[[sublime.Region], bool]) -> List[LintError]
    return [
        error for error in persist.file_errors[filename]
        if fn(error['region'])
    ]


def actions_for_error(error):
    # type: (LintError) -> Iterator[Action]
    return (
        Action(action.description, partial(action.fn, error))
        for action in _actions_for_error(error)
    )


def _actions_for_error(error):
    # type: (LintError) -> Iterator[QuickAction]
    linter_name = error['linter']
    code = error["code"]
    if not code:
        return
    if linter_name == "eslint":
        yield QuickAction(
            "// disable-next-line {}".format(code),
            fix_eslint_error
        )
    elif linter_name == "flake8":
        yield QuickAction(
            "# noqa: {}".format(code),
            fix_flake8_error
        )
    elif linter_name == "mypy":
        yield QuickAction(
            "# type: ignore[{}]".format(code),
            fix_mypy_error
        )


def apply_fix(fix, view):
    # type: (Fix, sublime.View) -> None
    apply_edit(fix(view), view)


def apply_edit(edit, view):
    # type: (TextRange, sublime.View) -> None
    replace_view_content(view, *edit)


def fix_eslint_error(error, view):
    # type: (LintError, sublime.View) -> TextRange
    pt = error['region'].begin()
    code = error["code"]
    line = read_line(view, pt)
    previous_line = read_previous_line(view, line)
    return (
        (
            extend_existing_comment(
                r"// eslint-disable-next-line (?P<codes>[\w\-/]+(?:,\s?[\w\-/]+)*)(\s+-{2,})?",
                ", ",
                code,
                previous_line
            )
            if previous_line
            else None
        )
        or insert_preceding_line(
            "// eslint-disable-next-line {}".format(code),
            line
        )
    )


def fix_flake8_error(error, view):
    # type: (LintError, sublime.View) -> TextRange
    pt = error['region'].begin()
    code = error["code"]
    line = read_line(view, pt)
    return (
        extend_existing_comment(
            r"(?i)# noqa:[\s]?(?P<codes>[A-Z]+[0-9]+((?:,\s?)[A-Z]+[0-9]+)*)",
            ", ",
            code,
            line
        )
        or add_at_eol(
            "  # noqa: {}".format(code),
            line
        )
    )


def fix_mypy_error(error, view):
    # type: (LintError, sublime.View) -> TextRange
    pt = error['region'].begin()
    code = error["code"]
    line = read_line(view, pt)
    return (
        extend_existing_comment(
            r"  # type: ignore\[(?P<codes>.*)\]",
            ", ",
            code,
            line
        )
        or maybe_add_before_string(
            "  # ",
            "  # type: ignore[{}]".format(code),
            line
        )
        or add_at_eol(
            "  # type: ignore[{}]".format(code),
            line
        )
    )


def read_line(view, pt):
    # type: (sublime.View, int) -> TextRange
    line_region = view.line(pt)
    line_content = view.substr(line_region)
    return TextRange(line_content, line_region)


def read_previous_line(view, line):
    # type: (sublime.View, TextRange) -> Optional[TextRange]
    if line.range.a == 0:
        return None
    line_region = view.line(line.range.a - 1)
    line_content = view.substr(line_region)
    return TextRange(line_content, line_region)


def extend_existing_comment(search_pattern, joiner, rulename, line):
    # type: (str, str, str, TextRange) -> Optional[TextRange]
    match = re.search(search_pattern, line.text)
    if match:
        present_rules = match.group("codes")
        next_rules = [rule.strip() for rule in present_rules.split(joiner.strip())]
        if rulename not in next_rules:
            next_rules.append(rulename)
        a, b = match.span("codes")
        return TextRange(
            joiner.join(next_rules),
            sublime.Region(line.range.a + a, line.range.a + b)
        )
    return None


def add_at_eol(text, line):
    # type: (str, TextRange) -> TextRange
    line_length = len(line.text.rstrip())
    return TextRange(
        text,
        sublime.Region(line.range.a + line_length, line.range.b)
    )


def add_at_bol(text, line):
    # type: (str, TextRange) -> TextRange
    return TextRange(
        text,
        sublime.Region(line.range.a)
    )


def insert_preceding_line(text, line):
    # type: (str, TextRange) -> TextRange
    return add_at_bol(indentation(line) + text + "\n", line)


def indentation_level(line):
    # type: (TextRange) -> int
    return len(line.text) - len(line.text.lstrip())


def indentation(line):
    # type: (TextRange) -> str
    level = indentation_level(line)
    return line.text[:level]


def maybe_add_before_string(needle, text, line):
    # type: (str, str, TextRange) -> Optional[TextRange]
    try:
        start = line.text.index(needle)
    except ValueError:
        return None
    else:
        return TextRange(
            text,
            sublime.Region(line.range.a + start)
        )
