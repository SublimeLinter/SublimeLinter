"""This module provides general utility methods."""
from collections import ChainMap
from contextlib import contextmanager
from functools import lru_cache, wraps
import locale
import logging
import os
import re
import shutil
import subprocess
import time
import threading

import sublime
from . import events


MYPY = False
if MYPY:
    from typing import Iterator, List, MutableMapping, Optional, TypeVar, Union
    T = TypeVar('T')


logger = logging.getLogger(__name__)


STREAM_STDOUT = 1
STREAM_STDERR = 2
STREAM_BOTH = STREAM_STDOUT + STREAM_STDERR

ANSI_COLOR_RE = re.compile(r'\033\[[0-9;]*m')


@events.on('settings_changed')
def on_settings_changed(settings, **kwargs):
    get_augmented_path.cache_clear()


@contextmanager
def print_runtime(message):
    start_time = time.perf_counter()
    yield
    end_time = time.perf_counter()
    duration = round((end_time - start_time) * 1000)
    thread_name = threading.current_thread().name[0]
    print('{} took {}ms [{}]'.format(message, duration, thread_name))


def show_message(message, window=None):
    if window is None:
        window = sublime.active_window()
    window.run_command("sublime_linter_display_panel", {"msg": message})


def clear_message():
    window = sublime.active_window()
    window.run_command("sublime_linter_remove_panel")


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


def canonical_filename(view):
    return (
        os.path.basename(view.file_name()) if view.file_name()
        else '<untitled {}>'.format(view.buffer_id())
    )


def get_filename(view):
    # type: (sublime.View) -> str
    return view.file_name() or '<untitled {}>'.format(view.buffer_id())


def get_syntax(view):
    """
    Return the view's syntax.

    or the syntax it is mapped to in the "syntax_map" setting.
    """
    syntax_re = re.compile(r'(?i)/([^/]+)\.(?:tmLanguage|sublime-syntax)$')
    view_syntax = view.settings().get('syntax') or ''
    mapped_syntax = ''

    if view_syntax:
        match = syntax_re.search(view_syntax)

        if match:
            view_syntax = match.group(1).lower()
            from .persist import settings
            mapped_syntax = settings.get(
                'syntax_map', {}).get(view_syntax, '').lower()
        else:
            view_syntax = ''

    return mapped_syntax or view_syntax


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
        if output_:
            output_ = process_popen_output(output_)
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

        rv = super().__new__(cls, combined_output)  # type: ignore
        rv.combined_output = combined_output
        rv.stdout = stdout
        rv.stderr = stderr
        rv.proc = proc
        rv.pid = proc.pid
        rv.returncode = proc.returncode
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
    if os.name == 'nt':
        info = subprocess.STARTUPINFO()
        info.dwFlags |= subprocess.STARTF_USESTDHANDLES | subprocess.STARTF_USESHOWWINDOW
        info.wShowWindow = subprocess.SW_HIDE
        return info

    return None


def get_creationflags():
    if os.name == 'nt':
        return subprocess.CREATE_NEW_PROCESS_GROUP

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
