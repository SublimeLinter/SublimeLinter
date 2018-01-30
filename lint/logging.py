from contextlib import contextmanager
import os
import threading

import builtins


class Logger:

    # Will be prepended to all print messages
    print_prefix = "[SublimeLinter]"

    def debug(self, fmt, *args, **kwargs):
        """Print a debug message on stdout, if debug mode is enabled.

        Arguments are forwarded to `fmt.format`.
        """
        from . import persist
        if persist.debug_mode():
            self.print(fmt, *args, **kwargs)

    def print(self, fmt, *args, **kwargs):
        """Print a message on stdout. Arguments are forwarded to `fmt.format`."""
        message = fmt.format(*args, **kwargs)
        builtins.print(self.print_prefix, message)


class LinterClsLogger(Logger):

    def __init__(self, linter_cls):
        self.linter_cls = linter_cls
        self.linter_name = linter_cls.name
        self.print_prefix = "[SublimeLinter] [{}]".format(self.linter_name)


class LinterLogger(Logger):

    def __init__(self, linter):
        self.linter = linter
        self.linter_name = linter.name
        self.file_path = linter.view.file_name() or "<untitled {}>".format(linter.view.buffer_id())
        self.file_name = os.path.basename(self.file_path)
        self.print_prefix = "[SublimeLinter] [{}] ({})".format(self.linter_name, self.file_name)


# Maps thread idents to an active logger
_thread_logger_map = {}
# Used when no linter-specific logger is active
default_logger = Logger()


@contextmanager
def logger_context(logger):
    key = threading.get_ident()
    _thread_logger_map[key] = logger
    yield
    del _thread_logger_map[key]


def get_current_logger():
    """Find the active logger for the current thread."""
    logger = _thread_logger_map.get(threading.get_ident())
    if not logger:
        logger = default_logger
    return logger


def debug(*args, **kwargs):
    # late-import to prevent circular imports
    from . import persist
    if persist.debug_mode():
        get_current_logger().print(*args, **kwargs)


def print(*args, **kwargs):
    get_current_logger().print(*args, **kwargs)
