import sublime

from functools import lru_cache
import logging
import os

from . import linter as linter_module
from . import persist


MYPY = False
if MYPY:
    from typing import List, Optional, Type
    from mypy_extensions import TypedDict

    Linter = linter_module.Linter
    LinterName = str
    LinterSettings = linter_module.LinterSettings
    LintError = persist.LintError

    LinterInfo = TypedDict('LinterInfo', {
        'name': LinterName,
        'klass': Type[Linter],
        'settings': LinterSettings
    })


logger = logging.getLogger(__name__)


def assignable_linters_for_view(view, reason):
    # type: (sublime.View, str) -> List[LinterInfo]
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
        return []

    ctx = linter_module.get_view_context(view, {'reason': reason})
    wanted_linters = []  # type: List[LinterInfo]
    for name, klass in persist.linter_classes.items():
        settings = linter_module.get_linter_settings(klass, view, ctx)
        if klass.can_lint_view(view, settings):
            wanted_linters.append({
                'name': name,
                'klass': klass,
                'settings': settings
            })

    return wanted_linters


def filter_runnable_linters(view, reason, linters):
    # type: (sublime.View, str, List[LinterInfo]) -> List[LinterInfo]
    return [linter for linter in linters if can_run_now(view, reason, linter)]


def can_run_now(view, reason, linter):
    # type: (sublime.View, str, LinterInfo) -> bool
    return linter['klass'].should_lint(view, linter['settings'], reason)


def flash_once(window, message):
    # type: (Optional[sublime.Window], str) -> None
    if window:
        _flash_once(window.id(), message)


@lru_cache()
def _flash_once(wid, message):
    # type: (sublime.WindowId, str) -> None
    window = sublime.Window(wid)
    window.status_message(message)
