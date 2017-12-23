"""This module provides general utility methods."""

from functools import lru_cache
import json
import locale
from numbers import Number
import os
import getpass
import re
import shutil
import stat
import sublime
import subprocess
import tempfile


from copy import deepcopy

from .const import WARNING, ERROR

if sublime.platform() != 'windows':
    import pwd


STREAM_STDOUT = 1
STREAM_STDERR = 2
STREAM_BOTH = STREAM_STDOUT + STREAM_STDERR


INLINE_SETTINGS_RE = re.compile(
    r'(?i).*?\[sublimelinter[ ]+(?P<settings>[^\]]+)\]'
)
INLINE_SETTING_RE = re.compile(
    r'(?P<key>[@\w][\w\-]*)\s*:\s*(?P<value>[^\s]+)'
)


ANSI_COLOR_RE = re.compile(r'\033\[[0-9;]*m')

# Temp directory used to store temp files for linting
tempdir = os.path.join(
    tempfile.gettempdir(),
    "SublimeLinter3-" + getpass.getuser()
)


# Code migrated from 'lint/persist.py'
def printf(*args):
    """Print args to the console, prefixed by the plugin name."""
    print('SublimeLinter: ', end='')
    for arg in args:
        print(arg, end=' ')
    print()


def get_syntax(view):
    """
    Return the view's syntax
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


def is_scratch(view):
    """
    Return whether a view is effectively scratch.

    There is a bug (or feature) in the current ST3 where the Find panel
    is not marked scratch but has no window.

    There is also a bug where settings files opened from within .sublime-package
    files are not marked scratch during the initial on_modified event, so we have
    to check that a view with a filename actually exists on disk if the file
    being opened is in the Sublime Text packages directory.

    """

    if view.is_scratch() or view.is_read_only() or not view.window() or view.settings().get("repl"):
        return True
    elif (
        view.file_name() and
        view.file_name().startswith(sublime.packages_path() + os.path.sep) and
        not os.path.exists(view.file_name())
    ):
        return True
    else:
        return False


def is_none_or_zero(we_count):
    """Function to check warning/error count of dict."""
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


def get_focused_view(view):
    """
    Return the focused view which shares view's buffer.

    When updating the status, we want to make sure we get
    the selection of the focused view, since multiple views
    into the same buffer may be open.

    """
    active_view = get_active_view(view)
    if not active_view:
        return

    if is_scratch(view):
        return

    if not view.window():
        return

    for view in view.window().views():
        if view == active_view:
            return view


def get_new_dict():
    return deepcopy({WARNING: {}, ERROR: {}})


def msg_count(l_dict):
    w_count = len(l_dict.get("warning", []))
    e_count = len(l_dict.get("error", []))
    return w_count, e_count


def any_key_in(target, source):
    """Performs an m:n member check between two iterables."""
    return any(key in target for key in source)


# settings utils

def inline_settings(comment_re, code, prefix=None, alt_prefix=None):
    r"""
    Return a dict of inline settings within the first two lines of code.

    This method looks for settings in the form [SublimeLinter <name>:<value>]
    on the first or second line of code if the lines match comment_re.
    comment_re should be a compiled regex object whose pattern is unanchored (no ^)
    and matches everything through the comment prefix, including leading whitespace.

    For example, to specify JavaScript comments, you would use the pattern:

    r'\s*/[/*]'

    If prefix or alt_prefix is a non-empty string, setting names must begin with
    the given prefix or alt_prefix to be considered as a setting.

    A dict of matching name/value pairs is returned.

    """

    if prefix:
        prefix = prefix.lower() + '-'

    if alt_prefix:
        alt_prefix = alt_prefix.lower() + '-'

    settings = {}
    pos = -1

    for i in range(0, 2):
        # Does this line start with a comment marker?
        match = comment_re.match(code, pos + 1)

        if match:
            # If it's a comment, does it have inline settings?
            match = INLINE_SETTINGS_RE.match(code, pos + len(match.group()))

            if match:
                # We have inline settings, stop looking
                break

        # Find the next line
        pos = code.find('\n', )

        if pos == -1:
            # If no more lines, stop looking
            break

    if match:
        for key, value in INLINE_SETTING_RE.findall(match.group('settings')):
            if prefix and key[0] != '@':
                if key.startswith(prefix):
                    key = key[len(prefix):]
                elif alt_prefix and key.startswith(alt_prefix):
                    key = key[len(alt_prefix):]
                else:
                    continue

            settings[key] = value

    return settings


def get_view_rc_settings(view, limit=None):
    """Return the rc settings, starting at the parent directory of the given view."""
    filename = view.file_name()

    if filename:
        return get_rc_settings(os.path.dirname(filename), limit=limit)
    else:
        return None


@lru_cache(maxsize=None)
def get_rc_settings(start_dir, limit=None):
    """
    Search for a file named .sublimelinterrc starting in start_dir.

    From start_dir it ascends towards the root directory for a maximum
    of limit directories (including start_dir). If the file is found,
    it is read as JSON and the resulting object is returned. If the file
    is not found, None is returned.

    """

    if not start_dir:
        return None

    path = find_file(start_dir, '.sublimelinterrc', limit=limit)

    if path:
        try:
            with open(path, encoding='utf8') as f:
                rc_settings = json.loads(f.read())

            return rc_settings
        except (OSError, ValueError) as ex:
            printf('ERROR: could not load \'{}\': {}'.format(path, str(ex)))
    else:
        return None


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


def run_shell_cmd(cmd):
    """Run a shell command and return stdout."""
    proc = popen(cmd, env=os.environ)
    from . import persist

    try:
        timeout = persist.settings.get('shell_timeout', 10)
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        out = b''
        printf(
            'shell timed out after {} seconds, executing {}'.format(timeout, cmd))

    return out


@lru_cache(maxsize=None)
def get_environment_variable(name):
    """Return the value of the given environment variable, or None if not found."""

    if os.name == 'posix':
        value = None

        if 'SHELL' in os.environ:
            shell_path = os.environ['SHELL']

            # We have to delimit the output with markers because
            # text might be output during shell startup.
            out = run_shell_cmd(
                (shell_path, '-l', '-c', 'echo "__SUBL_VAR__${{{}}}__SUBL_VAR__"'.format(name))).strip()

            if out:
                value = out.decode().split('__SUBL_VAR__', 2)[
                    1].strip() or None
    else:
        value = os.environ.get(name, None)

    from . import persist
    persist.debug('ENV[\'{}\'] = \'{}\''.format(name, value))

    return value


@lru_cache(maxsize=None)
def create_environment():
    """
    Return a dict with os.environ augmented with a better PATH.

    On Posix systems, the user's shell PATH is added to PATH.

    Platforms paths are then added to PATH by getting the
    "paths" user settings for the current platform. If "paths"
    has a "*" item, it is added to PATH on all platforms.

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

    from . import persist

    if persist.debug_mode():
        if os.name == 'posix':
            if 'SHELL' in env:
                shell = 'using ' + env['SHELL']
            else:
                shell = 'using standard paths'
        else:
            shell = 'from system'

        if env['PATH']:
            printf('computed PATH {}:\n{}\n'.format(
                shell, env['PATH'].replace(os.pathsep, '\n')))

    # Many linters use stdin, and we convert text to utf-8
    # before sending to stdin, so we have to make sure stdin
    # in the target executable is looking for utf-8. Some
    # linters (like ruby) need to have LANG and/or LC_CTYPE
    # set as well.
    env['PYTHONIOENCODING'] = 'utf8'
    env['LANG'] = 'en_US.UTF-8'
    env['LC_CTYPE'] = 'en_US.UTF-8'

    return env


def can_exec(path):
    """Return whether the given path is a file and is executable."""
    return os.path.isfile(path) and os.access(path, os.X_OK)


@lru_cache(maxsize=None)
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


@lru_cache(maxsize=None)
def get_python_paths():
    """
    Return sys.path for the system version of python 3.

    If python 3 cannot be found on the system, [] is returned.

    """

    from . import persist

    python_path = which('@python3')[0]

    if python_path:
        code = r'import sys;print("\n".join(sys.path).strip())'
        out = communicate(python_path, code)
        paths = out.splitlines()

        if persist.debug_mode():
            printf('sys.path for {}:\n{}\n'.format(
                python_path, '\n'.join(paths)))
    else:
        persist.debug('no python 3 available to augment sys.path')
        paths = []

    return paths


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


def communicate(cmd, code=None, output_stream=STREAM_STDOUT, env=None):
    """
    Return the result of sending code via stdin to an executable.

    The result is a string which comes from stdout, stderr or the
    combining of the two, depending on the value of output_stream.
    If env is not None, it is merged with the result of create_environment.

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
                output_stream=output_stream, extra_env=env)

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


def create_tempdir():
    """Create a directory within the system temp directory used to create temp files."""
    try:
        if os.path.isdir(tempdir):
            shutil.rmtree(tempdir)

        os.mkdir(tempdir)

        # Make sure the directory can be removed by anyone in case the user
        # runs ST later as another user.
        os.chmod(tempdir, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)

    except PermissionError:
        if sublime.platform() != 'windows':
            current_user = pwd.getpwuid(os.geteuid())[0]
            temp_uid = os.stat(tempdir).st_uid
            temp_user = pwd.getpwuid(temp_uid)[0]
            message = (
                'The SublimeLinter temp directory:\n\n{0}\n\ncould not be cleared '
                'because it is owned by \'{1}\' and you are logged in as \'{2}\'. '
                'Please use sudo to remove the temp directory from a terminal.'
            ).format(tempdir, temp_user, current_user)
        else:
            message = (
                'The SublimeLinter temp directory ({}) could not be reset '
                'because it belongs to a different user.'
            ).format(tempdir)

        sublime.error_message(message)

    from . import persist
    persist.debug('temp directory:', tempdir)


def tmpfile(cmd, code, filename, suffix='', output_stream=STREAM_STDOUT, env=None):
    """
    Return the result of running an executable against a temporary file containing code.

    It is assumed that the executable launched by cmd can take one more argument
    which is a filename to process.

    The result is a string combination of stdout and stderr.
    If env is not None, it is merged with the result of create_environment.

    """

    if not filename:
        filename = "untitled"
    else:
        filename = os.path.basename(filename)

    if suffix:
        filename = os.path.splitext(filename)[0] + suffix

    path = os.path.join(tempdir, filename)

    try:
        with open(path, mode='wb') as f:
            if isinstance(code, str):
                code = code.encode('utf-8')

            f.write(code)
            f.flush()

        cmd = list(cmd)

        if '@' in cmd:
            cmd[cmd.index('@')] = path
        else:
            cmd.append(path)

        return communicate(cmd, output_stream=output_stream, env=env)
    finally:
        os.remove(path)


def tmpdir(cmd, files, filename, code, output_stream=STREAM_STDOUT, env=None):
    """
    Run an executable against a temporary file containing code.

    It is assumed that the executable launched by cmd can take one more argument
    which is a filename to process.

    Returns a string combination of stdout and stderr.
    If env is not None, it is merged with the result of create_environment.

    """

    filename = os.path.basename(filename) if filename else ''
    out = None

    with tempfile.TemporaryDirectory(dir=tempdir) as d:
        for f in files:
            try:
                os.makedirs(os.path.join(d, os.path.dirname(f)))
            except OSError:
                pass

            target = os.path.join(d, f)

            if os.path.basename(target) == filename:
                # source file hasn't been saved since change, so update it from our live buffer
                f = open(target, 'wb')

                if isinstance(code, str):
                    code = code.encode('utf8')

                f.write(code)
                f.close()
            else:
                shutil.copyfile(f, target)

        os.chdir(d)
        out = communicate(cmd, output_stream=output_stream, env=env)

        if out:
            # filter results from build to just this filename
            # no guarantee all syntaxes are as nice about this as Go
            # may need to improve later or just defer to communicate()
            out = '\n'.join([
                line for line in out.split('\n') if filename in line.split(':', 1)[0]
            ])

    return out or ''


def popen(cmd, stdout=None, stderr=None, output_stream=STREAM_BOTH, env=None, extra_env=None):
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

    if extra_env is not None:
        env.update(extra_env)

    try:
        return subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=stdout,
            stderr=stderr,
            startupinfo=info,
            env=env
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

def clear_path_caches():
    """Clear the caches of all path-related methods in this module that use an lru_cache."""
    create_environment.cache_clear()
    which.cache_clear()
    get_python_paths.cache_clear()


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


class cd:
    """Context manager for changing the current working directory."""

    def __init__(self, newPath):
        """Save the new wd."""
        self.newPath = os.path.expanduser(newPath)

    def __enter__(self):
        """Save the old wd and change to the new wd."""
        self.savedPath = os.getcwd()
        os.chdir(self.newPath)

    def __exit__(self, etype, value, traceback):
        """Go back to the old wd."""
        os.chdir(self.savedPath)
