"""This module provides persistent global storage for other modules."""
from __future__ import annotations

from collections import defaultdict
import subprocess
import threading
from typing import DefaultDict, Type, TypedDict, TYPE_CHECKING

import sublime
from . import events
from .settings import Settings

if TYPE_CHECKING:
    from .linter import Linter
    Bid = sublime.BufferId

FileName = str
LinterName = str
Reason = str


class LintError(TypedDict, total=False):
    linter: LinterName

    filename: FileName
    line: int
    start: int
    region: sublime.Region
    error_type: str
    code: str
    msg: str
    offending_text: str

    # extensions
    uid: str
    priority: int
    panel_line: tuple[int, int]


api_ready = False
kill_switch = True

settings = Settings()

file_errors: DefaultDict[FileName, list[LintError]] = defaultdict(list)
linter_classes: dict[str, Type[Linter]] = {}
assigned_linters: dict[Bid, set[LinterName]] = {}
actual_linters: dict[FileName, set[LinterName]] = {}

# A mapping between actually linted files and other filenames that they
# reported errors for
affected_filenames_per_filename: \
    DefaultDict[FileName, DefaultDict[LinterName, set[FileName]]] = \
    defaultdict(lambda: defaultdict(set))

active_procs: DefaultDict[Bid, list[subprocess.Popen]] = defaultdict(list)
active_procs_lock = threading.Lock()


def update_file_errors(
    filename: FileName,
    linter: LinterName,
    errors: list[LintError],
    reason: Reason | None = None
) -> None:
    """Persist lint error changes and broadcast."""
    update_errors_store(filename, linter, errors)
    events.broadcast(events.LINT_RESULT, {
        'filename': filename,
        'linter_name': linter,
        'errors': errors,
        'reason': reason
    })


def update_errors_store(filename: FileName, linter_name: LinterName, errors: list[LintError]) -> None:
    file_errors[filename] = [
        error
        for error in file_errors[filename]
        if error['linter'] != linter_name
    ] + errors


def record_filename_change(old_filename: FileName, new_filename: FileName) -> None:
    # update the error store
    if old_filename in file_errors:
        errors = file_errors.pop(old_filename)
        file_errors[new_filename] = errors

    # update the affected filenames
    if old_filename in affected_filenames_per_filename:
        filenames = affected_filenames_per_filename.pop(old_filename)
        affected_filenames_per_filename[new_filename] = filenames

    # notify the views
    events.broadcast('file_renamed', {
        'new_filename': new_filename,
        'old_filename': old_filename
    })
