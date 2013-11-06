#
# util.py
# Part of SublimeLinter3, a code checking framework for Sublime Text 3
#
# Written by Ryan Hileman and Aparajita Fishman
#
# Project: https://github.com/SublimeLinter/SublimeLinter3
# License: MIT
#

from functools import lru_cache
import os
import re
import shutil
import tempfile
import sublime
import subprocess

INLINE_OPTIONS_RE = re.compile(r'.*?\[SublimeLinter[ ]+(.+?)\]')
INLINE_OPTION_RE = re.compile(r'([\w\-]+)\s*:\s*(.+?)\s*(?:,|$)')


def merge_user_settings(settings):
    '''Merge the default linter settings with the user's settings.'''
    default = settings.get('default') or {}
    user = settings.get('user') or {}

    if user:
        linters = default.pop('linters', {})
        user_linters = user.get('linters', {})

        for name, data in user_linters.items():
            if name in linters:
                linters[name].update(data)
            else:
                linters[name] = data

        default['linters'] = linters

        user.pop('linters', None)
        default.update(user)

    return default


def climb(top):
    right = True

    while right:
        top, right = os.path.split(top)
        yield top


@lru_cache(maxsize=256)
def find_dir(top, name, parent=False):
    for d in climb(top):
        target = os.path.join(d, name)

        if os.path.exists(target):
            if parent:
                return d

            return target


def extract_path(cmd, delim=':'):
    path = popen(cmd, os.environ).communicate()[0].decode()
    path = path.split('__SUBL__', 1)[1].strip('\r\n')
    return ':'.join(path.split(delim))


def find_path(env):
    # find PATH using shell --login
    if 'SHELL' in env:
        shell_path = env['SHELL']
        shell = os.path.basename(shell_path)

        if shell in ('bash', 'zsh'):
            return extract_path(
                (shell_path, '--login', '-c', 'echo __SUBL__$PATH')
            )
        elif shell == 'fish':
            return extract_path(
                (shell_path, '--login', '-c', 'echo __SUBL__; for p in $PATH; echo $p; end'),
                '\n'
            )

    # guess PATH if we haven't returned yet
    split = env['PATH'].split(':')
    p = env['PATH']

    for path in (
        '/usr/bin', '/usr/local/bin',
        '/usr/local/php/bin', '/usr/local/php5/bin'
    ):
        if not path in split:
            p += (':' + path)

    return p


def split_path(path):
    '''Splits a path into its components.'''
    components = []

    while path:
        head, tail = os.path.split(path)

        if tail:
            components.insert(0, tail)

        if head:
            if head == os.path.sep or head == os.path.altsep:
                components.insert(0, head)
                break

            path = head
        else:
            break

    return components


def package_relative_path(path, prefix_packages=True):
    '''
    Sublime Text wants package-relative paths to use '/' as the path separator
    on all platforms. This method prefixes 'Packages' to the path if insert_packages = True
    and returns a new path, replacing os path separators with '/'.
    '''
    components = split_path(path)

    if prefix_packages and components and components[0] != 'Packages':
        components.insert(0, 'Packages')

    return '/'.join(components)


@lru_cache(maxsize=2)
def create_environment():
    from . import persist

    env = {}
    env.update(os.environ)

    if os.name == 'posix':
        env['PATH'] = find_path(os.environ)

    paths = persist.settings.get('paths', {})

    if sublime.platform() in paths:
        paths = paths[sublime.platform()]
    else:
        paths = paths.get('*', [])

    if paths:
        env['PATH'] += os.pathsep + os.pathsep.join(paths)

    # Many linters use stdin, and we convert text to utf-8
    # before sending to stdin, so we have to make sure stdin
    # in the target executable is looking for utf-8.
    env['PYTHONIOENCODING'] = 'utf8'

    return env


def can_exec(fpath):
    return os.path.isfile(fpath) and os.access(fpath, os.X_OK)


@lru_cache(maxsize=256)
def which(cmd):
    env = create_environment()

    # On Windows, if cmd does not have an extension, add .exe
    if sublime.platform() == 'windows' and not os.path.splitext(cmd)[1]:
        cmd += '.exe'

    for base in env.get('PATH', '').split(os.pathsep):
        path = os.path.join(base, cmd)

        if can_exec(path):
            return path

    return None


def touch(path):
    with open(path, 'a'):
        os.utime(path, None)


def inline_options(code):
    options = {}
    m = INLINE_OPTIONS_RE.match(code)

    if m:
        for option in INLINE_OPTION_RE.findall(m.group(1)):
            options[option[0]] = option[1]

    return options


# popen methods

def combine_output(out, sep=''):
    return sep.join((
        (out[0].decode('utf8') or ''),
        (out[1].decode('utf8') or ''),
    ))


def communicate(cmd, code):
    out = popen(cmd)

    if out is not None:
        code = code.encode('utf8')
        out = out.communicate(code)
        return combine_output(out)
    else:
        return ''


def tmpfile(cmd, code, suffix=''):
    if isinstance(cmd, str):
        cmd = cmd,

    f = tempfile.NamedTemporaryFile(suffix=suffix)
    f.write(code.encode('utf8'))
    f.flush()

    cmd = tuple(cmd) + (f.name,)
    out = popen(cmd)

    if out:
        out = out.communicate()
        return combine_output(out)
    else:
        return ''


def tmpdir(cmd, files, filename, code):
    filename = os.path.split(filename)[1]
    d = tempfile.mkdtemp()

    for f in files:
        try:
            os.makedirs(os.path.join(d, os.path.split(f)[0]))
        except:
            pass

        target = os.path.join(d, f)

        if os.path.split(target)[1] == filename:
            # source file hasn't been saved since change, so update it from our live buffer
            f = open(target, 'wb')
            f.write(code)
            f.close()
        else:
            shutil.copyfile(f, target)

    os.chdir(d)
    out = popen(cmd)

    if out:
        out = out.communicate()
        out = combine_output(out, '\n')

        # filter results from build to just this filename
        # no guarantee all languages are as nice about this as Go
        # may need to improve later or just defer to communicate()
        out = '\n'.join([
            line for line in out.split('\n') if filename in line.split(':', 1)[0]
        ])
    else:
        out = ''

    shutil.rmtree(d, True)
    return out


def popen(cmd, env=None):
    if isinstance(cmd, str):
        cmd = cmd,

    info = None

    if os.name == 'nt':
        info = subprocess.STARTUPINFO()
        info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        info.wShowWindow = subprocess.SW_HIDE

    if env is None:
        env = create_environment()

    try:
        return subprocess.Popen(
            cmd, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            startupinfo=info, env=env)
    except OSError as err:
        from . import persist
        persist.debug('error launching', repr(cmd))
        persist.debug('error was:', err.strerror)
        persist.debug('environment:', env)
