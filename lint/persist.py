"""This module provides persistent global storage for other modules."""

from collections import defaultdict
import threading

from .util import printf
from .settings import Settings


api_ready = False
kill_switch = True

settings = Settings()

# A mapping between buffer ids and errors,
# Dict[buffer_id, [error]]
errors = defaultdict(list)

# A mapping between linter class names and linter classes
linter_classes = {}

# A mapping between buffer ids and a list of linter instances
view_linters = {}

# Dict[buffer_id, [Popen]]
active_procs = defaultdict(list)
active_procs_lock = threading.Lock()


def debug_mode():
    """Return whether the "debug" setting is True."""
    return settings.get('debug', False)


def debug(*args):
    """Print args to the console if the "debug" setting is True."""
    if debug_mode():
        printf(*args)
