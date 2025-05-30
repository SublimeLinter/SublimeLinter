"""This module provides persistent global storage for other modules."""
from __future__ import annotations

from collections import defaultdict
import subprocess
import threading
from typing import DefaultDict, Type, TypedDict, TYPE_CHECKING

import sublime
from . import events, util
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


def assign_linters_to_view(view: sublime.View, next_linters: set[LinterName]) -> None:
    # We do not want to update `assigned_linters` for detached views bc `on_close`
    # already has been called at this time.
    if not view.is_valid():
        return

    bid = view.buffer_id()
    filename = util.canonical_filename(view)
    current_linters = assigned_linters.get(bid, set())

    assigned_linters[bid] = next_linters
    events.broadcast(events.LINTER_ASSIGNED, {
        'filename': filename,
        'linter_names': next_linters
    })

    affected_files = affected_filenames_per_filename[filename]
    for linter in (current_linters - next_linters):
        affected_files.pop(linter, None)
        update_file_errors(filename, linter, [])


def group_by_filename_and_update(
    window: sublime.Window,
    main_filename: FileName,
    reason: Reason,
    linter: LinterName,
    errors: list[LintError]
) -> None:
    """Group lint errors by filename and update them."""
    grouped: defaultdict[FileName, list[LintError]] = defaultdict(list)
    for error in errors:
        grouped[error['filename']].append(error)

    # The contract for a simple linter is that it reports `[errors]` or an
    # empty list `[]` if the buffer is clean. For linters that report errors
    # for multiple files we collect information about which files are actually
    # reported by a given linted file so that we can clean the results.
    affected_filenames = affected_filenames_per_filename[main_filename]
    previous_filenames = affected_filenames[linter]

    current_filenames = set(grouped.keys()) - {main_filename}
    affected_filenames[linter] = current_filenames

    # Basically, we must fake a `[]` response for every filename that is no
    # longer reported.
    # For the main view we MUST *always* report an outcome. This is not for
    # cleanup but functions as a signal that we're done. Merely for the status
    # bar view.
    clean_files = previous_filenames - current_filenames
    for filename in clean_files | {main_filename}:
        grouped[filename]  # For the side-effect of creating a new empty `list`

    for filename, errors in grouped.items():
        # Ignore errors of other files if their view is dirty; but still
        # propagate if there are no errors, t.i. cleanup is allowed even
        # then.
        if filename != main_filename and errors:
            view = window.find_open_file(filename)
            if view and view.is_dirty():
                continue

        update_file_errors(filename, linter, errors, reason)


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
