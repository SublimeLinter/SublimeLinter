from collections import defaultdict
from functools import partial
from itertools import chain
import webbrowser
import re

import sublime

from . import persist
from .generic_text_command import replace_view_content, text_command
flatten = chain.from_iterable


MYPY = False
if MYPY:
    from typing import (
        Callable, DefaultDict, Dict, Final, Iterable, Iterator, List,
        NamedTuple, Optional, Set, TypeVar, Union
    )
    T = TypeVar("T")
    S = TypeVar("S")
    LintError = persist.LintError
    TextRange = NamedTuple("TextRange", [("text", str), ("range", sublime.Region)])
    Fixer = Callable[[LintError, sublime.View], Iterator[TextRange]]
    Fix = Callable[[sublime.View], Iterator[TextRange]]

else:
    from collections import namedtuple
    TextRange = namedtuple("TextRange", "text range")


class QuickAction:
    def __init__(self, subject, fn, detail, solves):
        # type: (str, Fix, Optional[str], List[LintError]) -> None
        self.subject = subject  # type: Final[str]
        self.fn = fn  # type: Final[Fix]
        self.detail = detail  # type: Final[Optional[str]]
        self.solves = solves  # type: Final[List[LintError]]

    @property
    def description(self):
        # type: () -> str
        return " — ".join(filter(None, (self.subject, self.detail)))


def actions_for_errors(errors, view=None):
    # type: (List[LintError], Optional[sublime.View]) -> Iterator[QuickAction]
    grouped = defaultdict(list)
    for error in errors:
        grouped[error['linter']].append(error)

    return flatten(
        provider(errors_by_linter, view)
        for linter_name, errors_by_linter in sorted(grouped.items())
        for provider in PROVIDERS[linter_name].values()
    )


def best_action_for_error(error):
    # type: (LintError) -> Optional[QuickAction]
    return next(actions_for_errors([error]), None)


def apply_fix(fix, view):
    # type: (Fix, sublime.View) -> None
    edits = fix(view)
    apply_edits(view, edits)


@text_command
def apply_edits(view, edits):
    # type: (sublime.View, Iterator[TextRange]) -> None
    for edit in reversed(sorted(edits, key=lambda edit: edit.range.a)):
        replace_view_content(view, edit.text, edit.range)


if MYPY:
    Provider = Callable[[List[LintError], Optional[sublime.View]], Iterator[QuickAction]]
    F = TypeVar("F", bound=Provider)

PROVIDERS = defaultdict(
    dict
)  # type: DefaultDict[str, Dict[str, Provider]]
DEFAULT_SUBJECT = '{linter}: Disable {code}'
DEFAULT_DETAIL = '{msg}'


def namespacy_name(fn):
    # type: (Callable) -> str
    # TBC: No methods supported, only simple functions!
    return "{}.{}".format(fn.__module__, fn.__name__)


def quick_actions_for(linter_name):
    # type: (str) -> Callable[[F], F]
    def register(fn):
        # type: (F) -> F
        ns_name = namespacy_name(fn)
        PROVIDERS[linter_name][ns_name] = fn
        fn.unregister = lambda: PROVIDERS[linter_name].pop(ns_name, None)  # type: ignore[attr-defined]
        return fn

    return register


def ignore_rules_inline(
    linter_name,
    subject=DEFAULT_SUBJECT,
    detail=DEFAULT_DETAIL,
    except_for=set()
):
    # type: (str, str, str, Set[str]) -> Callable[[Fixer], Fixer]
    def register(fn):
        # type: (Fixer) -> Fixer
        ns_name = namespacy_name(fn)
        provider = partial(ignore_rules_actions, subject, detail, except_for, fn)
        PROVIDERS[linter_name][ns_name] = provider
        fn.unregister = lambda: PROVIDERS[linter_name].pop(ns_name, None)  # type: ignore[attr-defined]
        return fn

    return register


def ignore_rules_actions(subject, detail, except_for, fixer, errors, _view):
    # type: (str, str, Set[str], Fixer, List[LintError], Optional[sublime.View]) -> Iterator[QuickAction]
    make_action = lambda error: QuickAction(
        subject.format(**error),
        partial(fixer, error),
        detail.format(**error),
        solves=[error]
    )

    grouped_by_code = group_by(
        lambda e: e["code"],
        (e for e in errors if e["code"] and e["code"] not in except_for)
    )
    for code, errors_with_same_code in sorted(grouped_by_code.items()):
        grouped_by_line = group_by(lambda e: e["line"], errors_with_same_code)

        actions_per_line = []
        for line, errors_on_same_line_with_same_code in grouped_by_line.items():
            as_actions = list(map(make_action, errors_on_same_line_with_same_code))
            actions_per_line.append(as_actions)

        if len(actions_per_line) > 1:
            yield merge_actions(actions_per_line)
        else:
            actions = actions_per_line[0]
            head = actions[0]
            if len(actions) == 1:
                yield head
            else:
                yield QuickAction(
                    subject_for_multiple_actions(actions),
                    head.fn,
                    detail_for_multiple_actions(actions),
                    solves=list(flatten(action.solves for action in actions))
                )


def merge_actions(actions):
    # type: (List[List[QuickAction]]) -> QuickAction
    first_action_per_chunk = next(zip(*actions))
    return QuickAction(
        subject_for_multiple_actions(list(flatten(actions))),
        lambda view: flatten(map(lambda action: action.fn(view), first_action_per_chunk)),
        detail_for_multiple_actions(list(flatten(actions))),
        solves=list(flatten(action.solves for action in flatten(actions)))
    )


def subject_for_multiple_actions(actions):
    # type: (List[QuickAction]) -> str
    solves_count = len(list(flatten(a.solves for a in actions)))
    return "{} ({}x)".format(actions[0].subject, solves_count)


def detail_for_multiple_actions(actions):
    # type: (List[QuickAction]) -> Optional[str]
    detail = next(filter(None, (a.detail for a in actions)), None)
    if not detail:
        return detail
    distinct = any(detail != action.detail for action in actions)

    if distinct:
        return "e.g. {}".format(detail)
    else:
        return detail


def group_by(key, iterable):
    # type: (Callable[[T], S], Iterable[T]) -> DefaultDict[S, List[T]]
    grouped = defaultdict(list)
    for item in iterable:
        grouped[key(item)].append(item)
    return grouped


def fix(linter_name, only_for=set()):
    # type: (str, Union[str, Set[str]]) -> Callable[[Fixer], Fixer]
    if isinstance(only_for, str):
        only_for = {only_for}

    def register(fn):
        # type: (Fixer) -> Fixer
        ns_name = namespacy_name(fn)
        provider = partial(std_fix_provider, linter_name, only_for, fn)
        PROVIDERS[linter_name][ns_name] = provider
        fn.unregister = lambda: PROVIDERS[linter_name].pop(ns_name, None)  # type: ignore[attr-defined]
        return fn
    return register


def std_fix_provider(linter_name, only_for, fixer, errors, _view):
    return (
        QuickAction(
            "{linter}: Fix {code} {msg}".format(**error),
            partial(fixer, error),
            "",
            solves=[error]
        )
        for error in errors
        if error["code"] in only_for or not only_for
    )


# --- FIXERS --- #


@ignore_rules_inline("eslint")
def fix_eslint_error(error, view):
    # type: (LintError, sublime.View) -> Iterator[TextRange]
    line = line_error_is_on(view, error)
    code = error["code"]
    yield (
        extend_existing_comment(
            r"// eslint-disable-next-line (?P<codes>[\w\-/]+(?:,\s?[\w\-/]+)*)(?P<comment>\s+-{2,})?",
            ", ",
            {code},
            read_previous_line(view, line)
        )
        or insert_preceding_line(
            "// eslint-disable-next-line {}".format(code),
            line
        )
    )


@quick_actions_for("eslint")
def eslint_block_ignorer(errors, view):
    # type: (List[LintError], Optional[sublime.View]) -> Iterator[QuickAction]
    if view and selection_across_multiple_lines(view):
        region = view.sel()[0]
        len_errors = len(errors)
        yield QuickAction(
            "eslint: Block comment {} error{}".format(
                len_errors,
                "s" if len_errors != 1 else ""
            ),
            partial(eslint_ignore_block, errors, region),
            "",
            solves=errors
        )


def selection_across_multiple_lines(view):
    # type: (sublime.View) -> bool
    s = view.sel()[0]
    return view.rowcol(s.a)[0] != view.rowcol(s.b)[0]


def eslint_ignore_block(errors, region, view):
    # type: (List[LintError], sublime.Region, sublime.View) -> Iterator[TextRange]
    # Assumes region is not empty.
    codes = {e["code"] for e in errors}
    starting_line = line_from_point(view, region.begin())
    # For example the user selects multiple lines, then `region.end()`
    # (the cursor) is at the zero pos of the next line. "-1" should
    # be okay here since region cannot be empty at this point.
    end_line = line_from_point(view, region.end() - 1)

    joiner = ", "
    yield (
        extend_existing_comment(
            r"\/\* eslint-disable (?P<codes>[\w\-/]+(?:,\s?[\w\-/]+)*)(?P<comment>\s+-{2,}.*)? \*\/",
            joiner,
            codes,
            read_previous_line(view, starting_line)
        )
        or insert_preceding_line(
            "/* eslint-disable {} */".format(joiner.join(sorted(codes))),
            starting_line
        )
    )
    yield (
        extend_existing_comment(
            r"\/\* eslint-enable (?P<codes>[\w\-/]+(?:,\s?[\w\-/]+)*)(?P<comment>\s+-{2,}.*)? \*\/",
            joiner,
            codes,
            read_next_line(view, end_line)
        )
        or insert_subsequent_line(
            "/* eslint-enable {} */".format(joiner.join(sorted(codes))),
            end_line
        )
    )


@ignore_rules_inline("stylelint")
def fix_stylelint_error(error, view):
    # type: (LintError, sublime.View) -> Iterator[TextRange]
    line = line_error_is_on(view, error)
    code = error["code"]
    yield (
        extend_existing_comment(
            r"\/\* stylelint-disable-line (?P<codes>[\w\-\/]+(?:,\s?[\w\-\/]+)*).*\*\/",
            ", ",
            {code},
            line
        ) or add_at_eol(
            " /* stylelint-disable-line {} */".format(code),
            line
        )
    )


@ignore_rules_inline("phpcs")
def fix_phpcs_error(error, view):
    # type: (LintError, sublime.View) -> Iterator[TextRange]
    line = line_error_is_on(view, error)
    code = error["code"]
    yield (
        extend_existing_comment(
            r"\/\/ phpcs:ignore (?P<codes>[\w\-\/.]+(?:,\s?[\w\-\/.]+)*)",
            ", ",
            {code},
            read_previous_line(view, line)
        ) or insert_preceding_line(
            "// phpcs:ignore {}".format(code),
            line
        )
    )


@ignore_rules_inline("flake8", except_for={
    # some indentation rules are not stylistic in python
    # the following violations cannot be ignored
    "E112",  # expected an indented block
    "E113",  # unexpected indentation
    "E116",  # unexpected indentation (comment)
    "E901",  # SyntaxError or IndentationError
    "E902",  # IOError
    "E999",  # SyntaxError
    "F721",  # syntax error in doctest
    "F722",  # syntax error in forward annotation
    "F723",  # syntax error in type comment

    # easter egg: provide real fixes for the basic
    # comment style rules
    "E261",  # at least two spaces before inline comment
    "E262",  # inline comment should start with ‘# ‘
    "E265",  # block comment should start with ‘# ‘
    "E266",  # too many leading ‘#’ for block comment
})
def fix_flake8_error(error, view):
    # type: (LintError, sublime.View) -> Iterator[TextRange]
    line = line_error_is_on(view, error)
    code = error["code"]
    yield (
        extend_existing_comment(
            r"(?i)# noqa:[\s]?(?P<codes>[A-Z]+[0-9]+((?:,\s?)[A-Z]+[0-9]+)*)",
            ", ",
            {code},
            line
        )
        or add_at_eol(
            "  # noqa: {}".format(code),
            line
        )
    )


@fix("flake8", {"E261"})
def fix_e261(error, view):
    # type: (LintError, sublime.View) -> Iterator[TextRange]
    if view.substr(error["region"]) == " ":
        yield TextRange("  ", error["region"])
    else:
        yield TextRange("  #", error["region"])


@fix("flake8", {"E262", "E265"})
def fix_e262(error, view):
    # type: (LintError, sublime.View) -> Iterator[TextRange]
    yield TextRange("# ", error["region"])


@fix("flake8", {"E266"})
def fix_e266(error, view):
    # type: (LintError, sublime.View) -> Iterator[TextRange]
    line = line_error_is_on(view, error)
    col = error["start"]
    tail_text = line.text[col:]
    count_comment_sign = len(tail_text) - len(tail_text.lstrip("#"))
    yield TextRange(
        "#",
        sublime.Region(line.range.a + col, line.range.a + col + count_comment_sign)
    )


@ignore_rules_inline("mypy", except_for={"syntax"})
def fix_mypy_error(error, view):
    # type: (LintError, sublime.View) -> Iterator[TextRange]
    line = line_error_is_on(view, error)
    code = error["code"]
    yield (
        extend_existing_comment(
            r"  # type: ignore\[(?P<codes>.*)\]",
            ", ",
            {code},
            line
        )
        or maybe_add_before_string(
            r"  # (?!type:)",
            "  # type: ignore[{}]".format(code),
            line
        )
        or add_at_eol(
            "  # type: ignore[{}]".format(code),
            line
        )
    )

SHELLCHECK_CODE_PATTERN=r"\[(?P<code>SC\d+)\]$"

@ignore_rules_inline("shellcheck")
def fix_shellcheck_error(error, view):
    # type: (LintError, sublime.View) -> Iterator[TextRange]
    line = line_error_is_on(view, error)
    match = re.search(SHELLCHECK_CODE_PATTERN, error["msg"])

    code = match.groups("code")[0]

    yield (
        extend_existing_comment(
            r"# shellcheck disable=(?P<codes>[\w\-/]+(?:,\s?[\w\-/]+)*)(?P<comment>\s+-{2,})?",
            ",",
            {code},
            read_previous_line(view, line)
        )
        or insert_preceding_line(
            "# shellcheck disable={}".format(code),
            line
        )
    )


@quick_actions_for("shellcheck")
def shellcheck_goto_documentation(errors, view):
    # type: (List[LintError], Optional[sublime.View]) -> Iterator[QuickAction]
    if view:
        region = view.sel()[0]

        for error in errors:
            match = re.search(SHELLCHECK_CODE_PATTERN, error["msg"])

            code = match.groups("code")[0];

            yield QuickAction(
                "shellcheck: Open documentation — {}".format(error['msg']),
                # partial(eslint_ignore_block, errors, region),
                partial(shellcheck_open_documentation_in_browser, code, region),
                "",
                solves=[]
            )

def shellcheck_open_documentation_in_browser(errorCode, region, view):
    # type: (List[LintError], sublime.Region, sublime.View) -> Iterator[TextRange]
    webbrowser.open_new_tab("https://github.com/koalaman/shellcheck/wiki/{}".format(errorCode))

    # return generator without any text commands
    return
    yield

def line_from_point(view, pt):
    # type: (sublime.View, int) -> TextRange
    line_region = view.line(pt)
    line_content = view.substr(line_region)
    return TextRange(line_content, line_region)


def line_error_is_on(view, error):
    # type: (sublime.View, LintError) -> TextRange
    pt = error["region"].begin()
    return line_from_point(view, pt)


def read_previous_line(view, line):
    # type: (sublime.View, TextRange) -> Optional[TextRange]
    if line.range.a == 0:
        return None
    return line_from_point(view, line.range.a - 1)


def read_next_line(view, line):
    # type: (sublime.View, TextRange) -> Optional[TextRange]
    if line.range.b >= view.size():
        return None
    return line_from_point(view, line.range.b + 1)


def extend_existing_comment(search_pattern, joiner, rulenames, line):
    # type: (str, str, Set[str], Optional[TextRange]) -> Optional[TextRange]
    if line is None:
        return None
    match = re.search(search_pattern, line.text)
    if match:
        existing_rules = {
            rule.strip()
            for rule in match.group("codes").split(joiner.strip())
        }
        next_rules = sorted(existing_rules | rulenames)
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


def insert_subsequent_line(text, line):
    # type: (str, TextRange) -> TextRange
    return add_at_eol("\n" + indentation(line) + text, line)


def indentation_level(line):
    # type: (TextRange) -> int
    return len(line.text) - len(line.text.lstrip())


def indentation(line):
    # type: (TextRange) -> str
    level = indentation_level(line)
    return line.text[:level]


def maybe_add_before_string(pattern, text, line):
    # type: (str, str, TextRange) -> Optional[TextRange]
    match = re.search(pattern, line.text)
    if match:
        start, _ = match.span()
        return TextRange(
            text,
            sublime.Region(line.range.a + start)
        )
    return None
