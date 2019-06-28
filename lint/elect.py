import sublime

from functools import lru_cache
import logging
import os

from . import linter as linter_module
from . import persist


MYPY = False
if MYPY:
    from typing import Iterable, Iterator, Optional, Type
    from mypy_extensions import TypedDict

    Linter = linter_module.Linter
    LinterName = str
    LinterSettings = linter_module.LinterSettings
    LintError = persist.LintError
    Reason = str

    LinterInfo = TypedDict('LinterInfo', {
        'name': LinterName,
        'klass': Type[Linter],
        'settings': LinterSettings,
        'runnable': bool
    })


logger = logging.getLogger(__name__)


def assignable_linters_for_view(view, reason):
    # type: (sublime.View, Reason) -> Iterator[LinterInfo]
    """Check and eventually instantiate linters for a view."""
    bid = view.buffer_id()

    filename = view.file_name()
    if filename and not os.path.exists(filename):
        logger.info(
            "Skipping buffer {}; '{}' is unreachable".format(bid, filename))
        flash_once(
            view.window(),
            "{} has become unreachable".format(filename)
        )
        return

    ctx = linter_module.get_view_context(view, {'reason': reason})
    for name, klass in persist.linter_classes.items():
        settings = linter_module.get_linter_settings(klass, view, ctx)
        if klass.can_lint_view(view, settings):
            yield {
                'name': name,
                'klass': klass,
                'settings': settings,
                'runnable': can_run_now(view, reason, klass, settings)
            }


def runnable_linters_for_view(view, reason):
    # type: (sublime.View, Reason) -> Iterator[LinterInfo]
    return filter_runnable_linters(assignable_linters_for_view(view, reason))


def filter_runnable_linters(linters):
    # type: (Iterable[LinterInfo]) -> Iterator[LinterInfo]
    return (linter for linter in linters if linter['runnable'])


def can_run_now(view, reason, linter, settings):
    # type: (sublime.View, Reason, Type[Linter], LinterSettings) -> bool
    return linter.should_lint(view, settings, reason)


def flash_once(window, message):
    # type: (Optional[sublime.Window], str) -> None
    if window:
        _flash_once(window.id(), message)


@lru_cache()
def _flash_once(wid, message):
    # type: (sublime.WindowId, str) -> None
    window = sublime.Window(wid)
    window.status_message(message)
