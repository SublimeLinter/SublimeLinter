"""This module provides persistent global storage for other modules."""

from collections import defaultdict
import threading

from .settings import Settings


MYPY = False
if MYPY:
    from typing import DefaultDict, Dict, List, Set, Tuple, Type
    from mypy_extensions import TypedDict
    import sublime
    import subprocess
    from .linter import Linter

    Bid = sublime.BufferId
    FileName = str
    LinterName = str
    LintError = TypedDict('LintError', {
        'line': int,
        'start': int,
        'region': sublime.Region,
        'linter': LinterName,
        'error_type': str,
        'code': str,
        'msg': str,
        'filename': FileName,
        'uid': str,
        'priority': int,
        'panel_line': Tuple[int, int],
        'offending_text': str
    }, total=False)


api_ready = False
kill_switch = True

settings = Settings()

file_errors = defaultdict(list)  # type: DefaultDict[FileName, List[LintError]]
linter_classes = {}  # type: Dict[str, Type[Linter]]
assigned_linters = {}  # type: Dict[Bid, Set[LinterName]]
actual_linters = {}  # type: Dict[FileName, Set[LinterName]]

# A mapping between actually linted files and other filenames that they
# reported errors for
affected_filenames_per_filename = defaultdict(
    lambda: defaultdict(set)
)  # type: DefaultDict[FileName, DefaultDict[LinterName, Set[FileName]]]

active_procs = defaultdict(list)  # type: DefaultDict[Bid, List[subprocess.Popen]]
active_procs_lock = threading.Lock()
