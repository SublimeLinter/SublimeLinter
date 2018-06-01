"""This module provides general utility methods."""

from functools import lru_cache, wraps
import locale
import logging
from numbers import Number
import os
import re
import sublime
import subprocess


logger = logging.getLogger(__name__)


STREAM_STDOUT = 1
STREAM_STDERR = 2
STREAM_BOTH = STREAM_STDOUT + STREAM_STDERR

ANSI_COLOR_RE = re.compile(r'\033\[[0-9;]*m')


def printf(*args):
    """Print args to the console, prefixed by the plugin name."""
    print('SublimeLinter: ', end='')
    for arg in args:
        print(arg, end=' ')
    print()


def show_message(message, window=None):
    if window is None:
        window = sublime.active_window()
    window.run_command("sublime_linter_display_panel", {"msg": message})


def clear_message():
    window = sublime.active_window()
    window.run_command("sublime_linter_remove_panel")


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


def distinct_until_selection_changed(method):
    last_call = None

    @wraps(method)
    def wrapper(self, view):
        nonlocal last_call

        this_call = (view.buffer_id(),) + tuple(s for s in view.sel())
        if this_call == last_call:
            return

        last_call = this_call
        method(self, view)

    return wrapper


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
    """Return a dict with os.environ augmented with a better PATH.

    Platforms paths are added to PATH by getting the "paths" user settings
    for the current platform.
    """
    from . import persist

    env = {}
    env.update(os.environ)

    paths = persist.settings.get('paths', {})

    if sublime.platform() in paths:
        paths = [os.path.abspath(os.path.expanduser(path))
                 for path in convert_type(paths[sublime.platform()], [])]
    else:
        paths = []

    if paths:
        env['PATH'] = os.pathsep.join(paths) + os.pathsep + env['PATH']

    if logger.isEnabledFor(logging.INFO) and env['PATH']:
        debug_print_env(env['PATH'])

    return env


def can_exec(path):
    """Return whether the given path is a file and is executable."""
    return os.path.isfile(path) and os.access(path, os.X_OK)


def which(cmd):
    """Return the full path to an executable searching PATH."""
    for path in find_executables(cmd):
        return path

    return None


def find_executables(executable):
    """Yield full paths to given executable."""
    env = create_environment()

    for base in env.get('PATH', '').split(os.pathsep):
        path = os.path.join(os.path.expanduser(base), executable)

        # On Windows, if path does not have an extension, try .exe, .cmd, .bat
        if sublime.platform() == 'windows' and not os.path.splitext(path)[1]:
            for extension in ('.exe', '.cmd', '.bat'):
                path_ext = path + extension

                if can_exec(path_ext):
                    yield path_ext
        elif can_exec(path):
            yield path

    return None


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
        logger.warning(
            "Executing `{}` failed\n  {}".format(' '.join(cmd), str(err))
        )
        return ''
    else:
        return process_popen_output(output)


def communicate(cmd, code=None, output_stream=STREAM_STDOUT, env=None, cwd=None):
    """
    Return the result of sending code via stdin to an executable.

    The result is a string which comes from stdout, stderr or the
    combining of the two, depending on the value of output_stream.
    If env is None, the result of create_environment is used.

    """
    logger.warning('`util.communicate` has been deprecated.')

    if code is not None:
        code = code.encode('utf8')
    if env is None:
        env = create_environment()

    uses_stdin = code is not None

    try:
        proc = subprocess.Popen(
            cmd, env=env, cwd=cwd,
            stdin=subprocess.PIPE if uses_stdin else None,
            stdout=subprocess.PIPE if output_stream & STREAM_STDOUT else None,
            stderr=subprocess.PIPE if output_stream & STREAM_STDERR else None,
            startupinfo=create_startupinfo()
        )
    except Exception as err:
        logger.error('  Execution failed\n\n  {}\n  {}{}'.format(
            str(err),
            ' '.join(cmd),
            '\n  {}'.format(cwd) if cwd else ''
        ))

        return ''

    if logger.isEnabledFor(logging.INFO):
        logger.info('Running `{}`'.format(' '.join(cmd)))

    out = proc.communicate(code)
    return popen_output(proc, *out)


class popen_output(str):
    """Hybrid of a Popen process and its output.

    Small compatibility layer: It is both the decoded output
    as str and partially the Popen object.
    """

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


def convert_type(value, type_value, sep=None, default=None):
    """
    Convert value to the type of type_value.

    If the value cannot be converted to the desired type, default is returned.
    If sep is not None, strings are split by sep (plus surrounding whitespace)
    to make lists/tuples, and tuples/lists are joined by sep to make strings.
    """
    if type_value is None or isinstance(value, type(type_value)):
        return value

    if isinstance(value, str):
        if isinstance(type_value, (tuple, list)):
            if sep is None:
                return [value]
            else:
                if value:
                    return re.split(r'\s*{}\s*'.format(sep), value)
                else:
                    return []
        elif isinstance(type_value, Number):
            return float(value)
        else:
            return default

    if isinstance(value, Number):
        if isinstance(type_value, str):
            return str(value)
        elif isinstance(type_value, (tuple, list)):
            return [value]
        else:
            return default

    if isinstance(value, (tuple, list)):
        if isinstance(type_value, str):
            return sep.join(value)
        else:
            return list(value)

    return default


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
