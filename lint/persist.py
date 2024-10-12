"""This module provides persistent global storage for other modules."""
from __future__ import annotations

from collections import defaultdict
import subprocess
import threading
from typing import DefaultDict, Type, TypedDict, TYPE_CHECKING

import sublime
from .settings import Settings

if TYPE_CHECKING:
    from .linter import Linter
    Bid = sublime.BufferId

FileName = str
LinterName = str


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
