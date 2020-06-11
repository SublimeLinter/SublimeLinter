from collections import defaultdict
from functools import partial
from itertools import chain
import re

import sublime
import sublime_plugin

from . import persist
from . import util
from .generic_text_command import replace_view_content
flatten = chain.from_iterable

MYPY = False
if MYPY:
    from typing import (
        Callable, DefaultDict, Dict, List, Iterator, NamedTuple, Optional
    )
    LintError = persist.LintError
    TextRange = NamedTuple("TextRange", [("text", str), ("range", sublime.Region)])
    Fixer = Callable[[LintError, sublime.View], Iterator[TextRange]]
    Fix = Callable[[sublime.View], Iterator[TextRange]]
    QuickAction = NamedTuple("QuickAction", [("description", str), ("fn", Fix)])

else:
    from collections import namedtuple
    QuickAction = namedtuple("QuickAction", "description fn")
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
    # type: (sublime.View, int) -> List[QuickAction]
    filename = util.get_filename(view)
    line = view.full_line(pt)
    errors = get_errors_where(filename, lambda region: region.intersects(line))
    return list(actions_for_errors(errors))


def get_errors_where(filename, fn):
    # type: (str, Callable[[sublime.Region], bool]) -> List[LintError]
    return [
        error for error in persist.file_errors[filename]
        if fn(error['region'])
    ]


def actions_for_errors(errors):
    # type: (List[LintError]) -> Iterator[QuickAction]
    grouped = defaultdict(list)
    for error in errors:
        grouped[error['linter']].append(error)

    return flatten(
        provider(errors_by_linter)
        for linter_name, errors_by_linter in sorted(grouped.items())
        for provider in PROVIDERS[linter_name].values()
    )


def best_action_for_error(error):
    # type: (LintError) -> Optional[QuickAction]
    return next(actions_for_errors([error]), None)


def apply_fix(fix, view):
    # type: (Fix, sublime.View) -> None
    edits = fix(view)
    apply_edit(edits, view)


def apply_edit(edits, view):
    # type: (Iterator[TextRange], sublime.View) -> None
    for edit in reversed(sorted(edits, key=lambda edit: edit.range.a)):
        replace_view_content(view, edit.text, edit.range)


if MYPY:
    Provider = Callable[[List[LintError]], Iterator[QuickAction]]


PROVIDERS = defaultdict(
    dict
)  # type: DefaultDict[str, Dict[str, Provider]]
DEFAULT_DESCRIPTION = "Disable [{code}] for this line"


def actions_provider(linter_name):
    # type: (str) -> Callable[[Provider], Provider]
    def register(fn):
        # type: (Provider) -> Provider
        ns_name = namespacy_name(fn)
        PROVIDERS[linter_name][ns_name] = fn
        fn.unregister = lambda: PROVIDERS[linter_name].pop(ns_name, None)  # type: ignore[attr-defined]
        return fn

    return register


def quick_action_for_error(linter_name, description=DEFAULT_DESCRIPTION):
    # type: (str, str) -> Callable[[Fixer], Fixer]
    def register(fn):
        # type: (Fixer) -> Fixer
        ns_name = namespacy_name(fn)
        PROVIDERS[linter_name][ns_name] = partial(std_provider, description, fn)
        fn.unregister = lambda: PROVIDERS[linter_name].pop(ns_name, None)  # type: ignore[attr-defined]
        return fn

    return register


def namespacy_name(fn):
    # type: (Callable) -> str
    # TBC: No methods supported, only simple functions!
    return "{}.{}".format(fn.__module__, fn.__name__)


def std_provider(description, fixer, errors):
    # type: (str, Fixer, List[LintError]) -> Iterator[QuickAction]
    return (
        QuickAction(description.format(**error), partial(fixer, error))
        for error in errors
    )


@actions_provider("flake8")
def flake8_actions(errors):
    # type: (List[LintError]) -> Iterator[QuickAction]
    return (
        QuickAction(
            'Disable [{code}] "{msg}" for this line'.format(**error),
            partial(fix_flake8_error, error)
        )
        for error in errors
    )


@quick_action_for_error("eslint")
def fix_eslint_error(error, view):
    # type: (LintError, sublime.View) -> Iterator[TextRange]
    line = line_error_is_on(view, error)
    previous_line = read_previous_line(view, line)
    code = error["code"]
    yield (
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


# @quick_action_for_error("flake8", 'Disable [{code}] "{msg}" for this line')
def fix_flake8_error(error, view):
    # type: (LintError, sublime.View) -> Iterator[TextRange]
    line = line_error_is_on(view, error)
    code = error["code"]
    yield (
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


@quick_action_for_error("mypy")
def fix_mypy_error(error, view):
    # type: (LintError, sublime.View) -> Iterator[TextRange]
    line = line_error_is_on(view, error)
    code = error["code"]
    yield (
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


def line_error_is_on(view, error):
    # type: (sublime.View, LintError) -> TextRange
    pt = error["region"].begin()
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
