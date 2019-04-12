"""This module provides persistent global storage for other modules."""

from collections import defaultdict
import threading

from .util import printf
from .settings import Settings


if False:
    from typing import DefaultDict, Dict, List, Tuple, Type, Optional
    from mypy_extensions import TypedDict
    import sublime
    import subprocess
    from .linter import Linter

    LintError = TypedDict('LintError', {
        'line': int,
        'start': int,
        'end': int,
        'region': sublime.Region,
        'linter': str,
        'error_type': str,
        'code': Optional[str],
        'msg': str,
        'filename': str,
        'uid': str,
        'priority': int,
        'panel_line': Tuple[int, int]
    }, total=False)


api_ready = False
kill_switch = True

settings = Settings()

# A mapping between buffer ids and errors,
# Dict[buffer_id, [error]]
errors = defaultdict(list)  # type: DefaultDict[sublime.BufferId, List[LintError]]

# A mapping between linter class names and linter classes
linter_classes = {}  # type: Dict[str, Type[Linter]]

# A mapping between buffer ids and a list of linter instances
view_linters = {}  # type: Dict[sublime.BufferId, List[Linter]]

# Dict[buffer_id, [Popen]]
active_procs = defaultdict(list)  # type: DefaultDict[sublime.BufferId, List[subprocess.Popen]]
active_procs_lock = threading.Lock()


def debug_mode():
    # type: () -> bool
    """Return whether the "debug" setting is True."""
    return settings.get('debug', False)


def debug(*args):
    # type: (...) -> None
    """Print args to the console if the "debug" setting is True."""
    if debug_mode():
        printf(*args)
