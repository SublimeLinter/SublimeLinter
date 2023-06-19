"""This module provides general utility methods."""
from collections import ChainMap
from contextlib import contextmanager
from functools import lru_cache, partial, wraps
import locale
import logging
import os
import re
import shutil
import subprocess
import sys
import time
import threading

import sublime
from . import events
from .const import IS_ENABLED_SWITCH


MYPY = False
if MYPY:
    from typing import (
        Callable, Iterator, List, MutableMapping, Optional, TypeVar, Union)
    from typing_extensions import Concatenate as Con, ParamSpec
    P = ParamSpec('P')
    T = TypeVar('T')
    Q = TypeVar('Q', bound=Union[sublime.Window, sublime.View])


logger = logging.getLogger(__name__)


STREAM_STDOUT = 1
STREAM_STDERR = 2
STREAM_BOTH = STREAM_STDOUT + STREAM_STDERR
UI_THREAD_NAME = None  # type: Optional[str]
ANSI_COLOR_RE = re.compile(r'\033\[[0-9;]*m')
ERROR_PANEL_NAME = "SublimeLinter Messages"
ERROR_OUTPUT_PANEL = "output." + ERROR_PANEL_NAME


@events.on('settings_changed')
def on_settings_changed(settings, **kwargs):
    get_augmented_path.cache_clear()


def determine_thread_names():
    def callback():
        global UI_THREAD_NAME
        UI_THREAD_NAME = threading.current_thread().name
    sublime.set_timeout(callback)


def ensure_on_ui_thread(fn):
    # type: (Callable[P, T]) -> Callable[P, None]
    """Decorate a `fn` to always run on the UI thread

    Check at runtime on which thread the code runs and maybe
    enqueue a task on the UI thread.  If already on the UI
    thread run `fn` immediately and blocking.  Otherwise
    return immediately.
    """
    @wraps(fn)
    def wrapped(*args, **kwargs):
        # type: (P.args, P.kwargs) -> None
        if it_runs_on_ui():
            fn(*args, **kwargs)
        else:
            enqueue_on_ui(fn, *args, **kwargs)
    return wrapped


def assert_on_ui_thread(fn):
    # type: (Callable[P, T]) -> Callable[P, T]
    @wraps(fn)
    def wrapped(*args, **kwargs):
        # type: (P.args, P.kwargs) -> T
        if it_runs_on_ui():
            return fn(*args, **kwargs)
        msg = "'{}' must be called from the UI thread".format(fn.__name__)
        sublime.status_message("RuntimeError: {}".format(msg))
        raise RuntimeError(msg)
    return wrapped


def it_runs_on_ui():
    # type: () -> bool
    return threading.current_thread().name == UI_THREAD_NAME


def enqueue_on_ui(fn, *args, **kwargs):
    # type: (Callable[P, T], P.args, P.kwargs) -> None
    sublime.set_timeout(partial(fn, *args, **kwargs))


def ui_block(fn):
    # type: (Callable[Con[Q, P], T]) -> Callable[Con[Q, P], None]
    """Mark a function as UI block and mimic `run_command` behavior.

    Annotates a function that takes as its first argument either a `View`
    or a `Window`.  Calling that function will then ensure it will run
    on the UI thread and with a valid subject, t.i. we call `is_valid()`
    on the first argument.  The function will be a no-op if the subject
    is not valid anymore.  The function will run sync and blocking if
    called from the UI thread, otherwise a task will be enqueud on the
    UI.  In this case the function will return immediately before it has
    run.
    """
    return ensure_on_ui_thread(skip_if_invalid_subject(fn))


def skip_if_invalid_subject(fn):
    # type: (Callable[Con[Q, P], T]) -> Callable[Con[Q, P], None]
    @wraps(fn)
    def wrapped(__view_or_window, *args, **kwargs):
        # type: (Q, P.args, P.kwargs) -> None
        if __view_or_window.is_valid():
            fn(__view_or_window, *args, **kwargs)

    return wrapped


@contextmanager
def print_runtime(message):
    start_time = time.perf_counter()
    yield
    end_time = time.perf_counter()
    duration = round((end_time - start_time) * 1000)
    thread_name = threading.current_thread().name[0]
    print('{} took {}ms [{}]'.format(message, duration, thread_name))


def show_message(message, window=None):
    # type: (str, Optional[sublime.Window]) -> None
    if window is None:
        window = sublime.active_window()
    _show_message(window, message)


@ui_block
def _show_message(window, message):
    # type: (sublime.Window, str) -> None
    if window.active_panel() == ERROR_OUTPUT_PANEL:
        panel = window.find_output_panel(ERROR_PANEL_NAME)
        assert panel
    else:
        panel = window.create_output_panel(ERROR_PANEL_NAME)
        syntax_path = "Packages/SublimeLinter/panel/message_view.sublime-syntax"
        try:  # Try the resource first, in case we're in the middle of an upgrade
            sublime.load_resource(syntax_path)
        except Exception:
            return

        panel.assign_syntax(syntax_path)

    scroll_to = panel.size()
    msg = message.rstrip() + '\n\n\n'

    panel.set_read_only(False)
    panel.run_command('append', {'characters': msg})
    panel.set_read_only(True)
    panel.show(scroll_to)
    window.run_command("show_panel", {"panel": ERROR_OUTPUT_PANEL})


def close_all_error_panels():
    # type: () -> None
    for window in sublime.windows():
        close_error_panel(window)


def close_error_panel(window=None):
    # type: (Optional[sublime.Window]) -> None
    if window is None:
        window = sublime.active_window()
    window.destroy_output_panel(ERROR_PANEL_NAME)


def flash(view, msg):
    # type: (sublime.View, str) -> None
    window = view.window() or sublime.active_window()
    window.status_message(msg)


def distinct_until_buffer_changed(method):
    # Sublime has problems to hold the distinction between buffers and views.
    # It usually emits multiple identical events if you have multiple views
    # into the same buffer.
    last_call = None

    @wraps(method)
    def wrapper(self, view):
        nonlocal last_call

        this_call = (view.buffer_id(), view.change_count())
        if this_call == last_call:
            return

        last_call = this_call
        method(self, view)

    return wrapper


def short_canonical_filename(view):
    return (
        os.path.basename(view.file_name())
        if view.file_name()
        else '<untitled {}>'.format(view.buffer_id())
    )


def canonical_filename(view):
    # type: (sublime.View) -> str
    return view.file_name() or '<untitled {}>'.format(view.buffer_id())


def get_syntax(view):
    # type: (sublime.View) -> str
    """
    Return a short syntax name used as a key against "syntax_map"
    and in `get_tempfile_suffix()`.
    """
    from .persist import settings
    syntax = view.settings().get('syntax') or ''
    stem = os.path.splitext(os.path.basename(syntax))[0].lower()
    return settings.get('syntax_map', {}).get(stem, stem)


def is_lintable(view):
    """
    Return true when a view is not lintable, e.g. scratch, read_only, etc.

    There is a bug (or feature) in the current ST3 where the Find panel
    is not marked scratch but has no window.

    There is also a bug where settings files opened from within .sublime-package
    files are not marked scratch during the initial on_modified event, so we have
    to check that a view with a filename actually exists on disk if the file
    being opened is in the Sublime Text packages directory.

    """
    enabled = view.settings().get(IS_ENABLED_SWITCH)
    if enabled is not None:
        return enabled

    if (
        not view.window() or
        view.is_scratch() or
        view.is_read_only() or
        view.settings().get("repl") or
        view.settings().get('is_widget')
    ):
        return False

    filename = view.file_name()
    if (
        filename and
        filename.startswith(sublime.packages_path() + os.path.sep) and
        not os.path.exists(filename)
    ):
        return False

    return True


# file/directory/environment utils


@lru_cache(maxsize=1)  # print once every time the path changes
def debug_print_env(path):
    import textwrap
    logger.info('PATH:\n{}'.format(textwrap.indent(path.replace(os.pathsep, '\n'), '    ')))


def create_environment():
    # type: () -> MutableMapping[str, str]
    """Return a dict with os.environ augmented with a better PATH.

    Platforms paths are added to PATH by getting the "paths" user settings
    for the current platform.
    """
    return ChainMap({'PATH': get_augmented_path()}, os.environ)


@lru_cache(maxsize=1)
def get_augmented_path():
    # type: () -> str
    from . import persist

    paths = [
        os.path.expanduser(path)
        for path in persist.settings.get('paths', {}).get(sublime.platform(), [])
    ]  # type: List[str]

    augmented_path = os.pathsep.join(paths + [os.environ['PATH']])
    if logger.isEnabledFor(logging.INFO):
        debug_print_env(augmented_path)
    return augmented_path


def which(cmd):
    # type: (str) -> Optional[str]
    """Return the full path to an executable searching PATH."""
    return shutil.which(cmd, path=get_augmented_path())


def where(executable):
    # type: (str) -> Iterator[str]
    """Yield full paths to given executable."""
    for path in get_augmented_path().split(os.pathsep):
        resolved = shutil.which(executable, path=path)
        if resolved:
            yield resolved


# popen utils

def check_output(cmd, cwd=None):
    """Short wrapper around subprocess.check_output."""
    logger.info('Running `{}`'.format(' '.join(cmd)))
    env = create_environment()

    try:
        output = subprocess.check_output(
            cmd, env=env, cwd=cwd,
            stderr=subprocess.STDOUT,
            startupinfo=create_startupinfo()
        )
    except Exception as err:
        import textwrap
        output_ = getattr(err, 'output', '')
        output_ = process_popen_output(output_)
        if output_:
            output_ = textwrap.indent(output_, '  ')
            output_ = "\n  ...\n{}".format(output_)
        logger.warning(
            "Executing `{}` failed\n  {}{}".format(
                ' '.join(cmd), str(err), output_
            )
        )
        raise
    else:
        return process_popen_output(output)


class popen_output(str):
    """Hybrid of a Popen process and its output.

    Small compatibility layer: It is both the decoded output
    as str and partially the Popen object.
    """

    stdout = ''  # type: Optional[str]
    stderr = ''  # type: Optional[str]
    combined_output = ''

    def __new__(cls, proc, stdout, stderr):
        if stdout is not None:
            stdout = process_popen_output(stdout)
        if stderr is not None:
            stderr = process_popen_output(stderr)

        combined_output = ''.join(filter(None, [stdout, stderr]))

        rv = super().__new__(cls, combined_output)
        rv.combined_output = combined_output
        rv.stdout = stdout
        rv.stderr = stderr
        rv.proc = proc                   # type: ignore[attr-defined]
        rv.pid = proc.pid                # type: ignore[attr-defined]
        rv.returncode = proc.returncode  # type: ignore[attr-defined]
        return rv


def process_popen_output(output):
    # bytes -> string   --> universal newlines
    output = decode(output).replace('\r\n', '\n').replace('\r', '\n')
    return ANSI_COLOR_RE.sub('', output)


def decode(bytes):
    """
    Decode and return a byte string using utf8, falling back to system's encoding if that fails.

    So far we only have to do this because javac is so utterly hopeless it uses CP1252
    for its output on Windows instead of UTF8, even if the input encoding is specified as UTF8.
    Brilliant! But then what else would you expect from Oracle?

    """
    if not bytes:
        return ''

    try:
        return bytes.decode('utf8')
    except UnicodeError:
        return bytes.decode(locale.getpreferredencoding(), errors='replace')


def create_startupinfo():
    if sys.platform == "win32":
        info = subprocess.STARTUPINFO()
        info.dwFlags |= subprocess.STARTF_USESTDHANDLES | subprocess.STARTF_USESHOWWINDOW
        info.wShowWindow = subprocess.SW_HIDE
        return info
    else:
        return None


def get_creationflags():
    if sys.platform == "win32":
        return subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        return 0


# misc utils


def ensure_list(value):
    # type: (Union[T, List[T]]) -> List[T]
    return value if isinstance(value, list) else [value]


def load_json(*segments, from_sl_dir=False):
    base_path = "Packages/SublimeLinter/" if from_sl_dir else ""
    full_path = base_path + "/".join(segments)
    return sublime.decode_value(sublime.load_resource(full_path))


def get_sl_version():
    try:
        metadata = load_json("package-metadata.json", from_sl_dir=True)
        return metadata.get("version")
    except Exception:
        return "unknown"
