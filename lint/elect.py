from __future__ import annotations
import sublime

from dataclasses import dataclass
from functools import lru_cache
import logging
import os
import sys

from . import linter as linter_module
from . import persist


from typing import Iterable, Iterator

Linter = linter_module.Linter
LinterName = str
LinterSettings = linter_module.LinterSettings
LintError = persist.LintError
Reason = str
ViewContext = linter_module.ViewContext


@dataclass(frozen=True)
class LinterInfo:
    name: LinterName
    klass: type[Linter]
    settings: LinterSettings
    context: ViewContext
    regions: list[sublime.Region]
    runnable: bool


logger = logging.getLogger(__name__)


def forget_unloaded_linters() -> None:
    """Drop linters whose plugin module has been unloaded.

    When a linter package is removed (or disabled), Sublime unloads its plugin
    module and pops it from `sys.modules`, but nothing tells us. The class would
    stay in `persist.linter_classes` and keep linting until Sublime is
    restarted. Views that were linted by such a linter lose it in
    `assign_linters_to_buffer`, which also clears its errors.
    """
    for name, klass in list(persist.linter_classes.items()):
        if klass.__module__ not in sys.modules:
            logger.info(
                "Forgetting linter '{}'; its plugin '{}' is no longer loaded."
                .format(name, klass.__module__)
            )
            del persist.linter_classes[name]


def assignable_linters_for_view(
    view: sublime.View,
    reason: Reason,
    only_run: set[LinterName] = None
) -> Iterator[LinterInfo]:
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

    forget_unloaded_linters()

    ctx = linter_module.get_view_context(view, {'reason': reason})
    for name, klass in persist.linter_classes.items():
        settings = linter_module.get_linter_settings(klass, view, ctx)
        if (
            klass.can_lint_view(view, settings)
            and (regions := klass.match_selector(view, settings))
        ):
            yield LinterInfo(
                name=name,
                klass=klass,
                settings=settings,
                context=ctx,
                regions=regions,
                runnable=(
                    False
                    if only_run and name not in only_run
                    else can_run_now(view, reason, klass, settings)
                ),
            )


def runnable_linters_for_view(view: sublime.View, reason: Reason) -> Iterator[LinterInfo]:
    return filter_runnable_linters(assignable_linters_for_view(view, reason))


def filter_runnable_linters(linters: Iterable[LinterInfo]) -> Iterator[LinterInfo]:
    return (linter for linter in linters if linter.runnable)


def can_run_now(
    view: sublime.View,
    reason: Reason,
    linter: type[Linter],
    settings: LinterSettings
) -> bool:
    return linter.should_lint(view, settings, reason)


def flash_once(window: sublime.Window | None, message: str) -> None:
    if window:
        _flash_once(window.id(), message)


@lru_cache()
def _flash_once(wid: sublime.WindowId, message: str) -> None:
    window = sublime.Window(wid)
    window.status_message(message)
