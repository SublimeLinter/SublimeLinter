"""This module provides general utility methods."""

from functools import lru_cache
import locale
from numbers import Number
import os
import re
import sublime
import subprocess
import tempfile

from copy import deepcopy

from .const import WARNING, ERROR

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


def get_syntax(view):
    """
    Return the view's syntax.

    or the syntax it is mapped to in the "syntax_map" setting.
    """
    syntax_re = re.compile(r'(?i)/([^/]+)\.(?:tmLanguage|sublime-syntax)$')
    view_syntax = view.settings().get('syntax', '')
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


class Borg:
    _shared_state = {}

    def __init__(self):
        self.__dict__ = self._shared_state


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
        not view or
        not view.window() or
        view.is_scratch() or
        view.is_read_only() or
        view.settings().get("repl")
    ):
        return False
    elif (
        view.file_name() and
        view.file_name().startswith(sublime.packages_path() + os.path.sep) and
        not os.path.exists(view.file_name())
    ):
        return False
    else:
        return True


def is_none_or_zero(we_count):
    """Check warning/error count of dict."""
    if not we_count:
        return True
    elif we_count[WARNING] + we_count[ERROR] == 0:
        return True
    else:
        return False


def get_active_view(view=None):
    if view:
        window = view.window()
        if not window:
            return
        return window.active_view()

    return sublime.active_window().active_view()


def get_new_dict():
    return deepcopy({WARNING: {}, ERROR: {}})


def msg_count(l_dict):
    w_count = len(l_dict.get("warning", []))
    e_count = len(l_dict.get("error", []))
    return w_count, e_count


def any_key_in(target, source):
    """Perform an m:n member check between two iterables."""
    return any(key in target for key in source)


# file/directory/environment utils

def climb(start_dir, limit=None):
    """
    Generate directories, starting from start_dir.

    If limit is None, stop at the root directory.
    Otherwise return a maximum of limit directories.
    """
    right = True

    while right and (limit is None or limit > 0):
        yield start_dir
        start_dir, right = os.path.split(start_dir)

        if limit is not None:
            limit -= 1


@lru_cache(maxsize=None)
def find_file(start_dir, name, parent=False, limit=None, aux_dirs=[]):
    """
    Find the given file by searching up the file hierarchy from start_dir.

    If the file is found and parent is False, returns the path to the file.
    If parent is True the path to the file's parent directory is returned.

    If limit is None, the search will continue up to the root directory.
    Otherwise a maximum of limit directories will be checked.

    If aux_dirs is not empty and the file hierarchy search failed,
    those directories are also checked.
    """
    for d in climb(start_dir, limit=limit):
        target = os.path.join(d, name)

        if os.path.exists(target):
            if parent:
                return d

            return target

    for d in aux_dirs:
        d = os.path.expanduser(d)
        target = os.path.join(d, name)

        if os.path.exists(target):
            if parent:
                return d

            return target


@lru_cache(maxsize=1)  # print once every time the path changes
def debug_print_env(path):
    printf('PATH:\n{}\n'.format(path.replace(os.pathsep, '\n')))


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

    if persist.debug_mode() and env['PATH']:
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


def combine_output(out, sep=''):
    """Return stdout and/or stderr combined into a string, stripped of ANSI colors."""
    output = sep.join((decode(out[0]), decode(out[1])))

    return ANSI_COLOR_RE.sub('', output)


def communicate(cmd, code=None, output_stream=STREAM_STDOUT, env=None, cwd=None):
    """
    Return the result of sending code via stdin to an executable.

    The result is a string which comes from stdout, stderr or the
    combining of the two, depending on the value of output_stream.
    If env is None, the result of create_environment is used.

    """
    # On Windows, using subprocess.PIPE with Popen() is broken when not
    # sending input through stdin. So we use temp files instead of a pipe.
    if code is None and os.name == 'nt':
        if output_stream != STREAM_STDERR:
            stdout = tempfile.TemporaryFile()
        else:
            stdout = None

        if output_stream != STREAM_STDOUT:
            stderr = tempfile.TemporaryFile()
        else:
            stderr = None
    else:
        stdout = stderr = None

    out = popen(cmd, stdout=stdout, stderr=stderr,
                output_stream=output_stream, env=env, cwd=cwd)

    if out is not None:
        if code is not None:
            code = code.encode('utf8')

        out = out.communicate(code)

        if code is None and os.name == 'nt':
            out = list(out)

            for f, index in ((stdout, 0), (stderr, 1)):
                if f is not None:
                    f.seek(0)
                    out[index] = f.read()

        return combine_output(out)
    else:
        return ''


def tmpfile(cmd, code, filename, suffix='', output_stream=STREAM_STDOUT, env=None, cwd=None):
    """
    Return the result of running an executable against a temporary file containing code.

    It is assumed that the executable launched by cmd can take one more argument
    which is a filename to process.

    The result is a string combination of stdout and stderr.
    If env is None, the result of create_environment is used.
    """
    if not filename:
        filename = "untitled"
    else:
        filename = os.path.basename(filename)

    if suffix:
        filename = os.path.splitext(filename)[0] + suffix

    file = tempfile.NamedTemporaryFile(delete=False)
    path = file.name

    try:
        file.write(bytes(code, 'UTF-8'))
        file.close()

        cmd = list(cmd)

        if '@' in cmd:
            cmd[cmd.index('@')] = path
        else:
            cmd.append(path)

        return communicate(cmd, output_stream=output_stream, env=env, cwd=cwd)
    finally:
        os.remove(path)


def popen(cmd, stdout=None, stderr=None, output_stream=STREAM_BOTH, env=None, cwd=None):
    """Open a pipe to an external process and return a Popen object."""
    info = None

    if os.name == 'nt':
        info = subprocess.STARTUPINFO()
        info.dwFlags |= subprocess.STARTF_USESTDHANDLES | subprocess.STARTF_USESHOWWINDOW
        info.wShowWindow = subprocess.SW_HIDE

    if output_stream == STREAM_BOTH:
        stdout = stdout or subprocess.PIPE
        stderr = stderr or subprocess.PIPE
    elif output_stream == STREAM_STDOUT:
        stdout = stdout or subprocess.PIPE
        stderr = subprocess.DEVNULL
    else:  # STREAM_STDERR
        stdout = subprocess.DEVNULL
        stderr = stderr or subprocess.PIPE

    if env is None:
        env = create_environment()

    try:
        return subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=stdout,
            stderr=stderr,
            startupinfo=info,
            env=env,
            cwd=cwd,
        )
    except Exception as err:
        printf('ERROR: could not launch', repr(cmd))
        printf('reason:', str(err))
        printf('PATH:', env.get('PATH', ''))


# view utils

def apply_to_all_views(callback):
    """Apply callback to all views in all windows."""
    for window in sublime.windows():
        for view in window.views():
            callback(view)


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
