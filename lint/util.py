# coding=utf8
#
# util.py
# Part of SublimeLinter3, a code checking framework for Sublime Text 3
#
# Written by Ryan Hileman and Aparajita Fishman
#
# Project: https://github.com/SublimeLinter/SublimeLinter3
# License: MIT
#

"""This module provides general utility methods."""

from functools import lru_cache
from glob import glob
import json
import locale
from numbers import Number
import os
import getpass
import re
import shutil
from string import Template
import stat
import sublime
import subprocess
import sys
import tempfile
from xml.etree import ElementTree

if sublime.platform() != 'windows':
    import pwd

#
# Public constants
#
STREAM_STDOUT = 1
STREAM_STDERR = 2
STREAM_BOTH = STREAM_STDOUT + STREAM_STDERR

PYTHON_CMD_RE = re.compile(r'(?P<script>[^@]+)?@python(?P<version>[\d\.]+)?')
VERSION_RE = re.compile(r'(?P<major>\d+)(?:\.(?P<minor>\d+))?')

INLINE_SETTINGS_RE = re.compile(r'(?i).*?\[sublimelinter[ ]+(?P<settings>[^\]]+)\]')
INLINE_SETTING_RE = re.compile(r'(?P<key>[@\w][\w\-]*)\s*:\s*(?P<value>[^\s]+)')

MENU_INDENT_RE = re.compile(r'^(\s+)\$menus', re.MULTILINE)

MARK_COLOR_RE = (
    r'(\s*<string>sublimelinter\.{}</string>\s*\r?\n'
    r'\s*<key>settings</key>\s*\r?\n'
    r'\s*<dict>\s*\r?\n'
    r'\s*<key>foreground</key>\s*\r?\n'
    r'\s*<string>)#.+?(</string>\s*\r?\n)'
)

ANSI_COLOR_RE = re.compile(r'\033\[[0-9;]*m')

UNSAVED_FILENAME = 'untitled'

# Temp directory used to store temp files for linting
tempdir = os.path.join(tempfile.gettempdir(), 'SublimeLinter3-' + getpass.getuser())


# settings utils

def merge_user_settings(settings):
    """Return the default linter settings merged with the user's settings."""

    default = settings.get('default', {})
    user = settings.get('user', {})

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
            from . import persist
            persist.printf('ERROR: could not load \'{}\': {}'.format(path, str(ex)))
    else:
        return None


def generate_color_scheme(from_reload=True):
    """
    Asynchronously call generate_color_scheme_async.

    from_reload is True if this is called from the change callback for user settings.

    """

    # If this was called from a reload of prefs, turn off the prefs observer,
    # otherwise we'll end up back here when ST updates the prefs with the new color.
    if from_reload:
        from . import persist

        def prefs_reloaded():
            persist.settings.observe_prefs()

        persist.settings.observe_prefs(observer=prefs_reloaded)

    # ST crashes unless this is run async
    sublime.set_timeout_async(generate_color_scheme_async, 0)


def generate_color_scheme_async():
    """
    Generate a modified copy of the current color scheme that contains SublimeLinter color entries.

    The current color scheme is checked for SublimeLinter color entries. If any are missing,
    the scheme is copied, the entries are added, and the color scheme is rewritten to Packages/User/SublimeLinter.

    """

    # First make sure the user prefs are valid. If not, bail.
    path = os.path.join(sublime.packages_path(), 'User', 'Preferences.sublime-settings')

    if (os.path.isfile(path)):
        try:
            with open(path, mode='r', encoding='utf-8') as f:
                json = f.read()

            sublime.decode_value(json)
        except:
            from . import persist
            persist.printf('generate_color_scheme: Preferences.sublime-settings invalid, aborting')
            return

    prefs = sublime.load_settings('Preferences.sublime-settings')
    scheme = prefs.get('color_scheme')

    if scheme is None:
        return

    scheme_text = sublime.load_resource(scheme)

    # Ensure that all SublimeLinter colors are in the scheme
    scopes = {
        'mark.warning': False,
        'mark.error': False,
        'gutter-mark': False
    }

    for scope in scopes:
        if re.search(MARK_COLOR_RE.format(re.escape(scope)), scheme_text):
            scopes[scope] = True

    if False not in scopes.values():
        return

    # Append style dicts with our styles to the style array
    plist = ElementTree.XML(scheme_text)
    styles = plist.find('./dict/array')

    from . import persist

    for style in COLOR_SCHEME_STYLES:
        color = persist.settings.get('{}_color'.format(style), DEFAULT_MARK_COLORS[style]).lstrip('#')
        styles.append(ElementTree.XML(COLOR_SCHEME_STYLES[style].format(color)))

    if not os.path.exists(os.path.join(sublime.packages_path(), 'User', 'SublimeLinter')):
        os.makedirs(os.path.join(sublime.packages_path(), 'User', 'SublimeLinter'))

    # Write the amended color scheme to Packages/User/SublimeLinter
    original_name = os.path.splitext(os.path.basename(scheme))[0]
    name = original_name + ' (SL)'
    scheme_path = os.path.join(sublime.packages_path(), 'User', 'SublimeLinter', name + '.tmTheme')

    with open(scheme_path, 'w', encoding='utf8') as f:
        f.write(COLOR_SCHEME_PREAMBLE)
        f.write(ElementTree.tostring(plist, encoding='unicode'))

    # Set the amended color scheme to the current color scheme
    path = os.path.join('User', 'SublimeLinter', os.path.basename(scheme_path))
    prefs.set('color_scheme', packages_relative_path(path))
    sublime.save_settings('Preferences.sublime-settings')


def change_mark_colors(error_color, warning_color):
    """Change SublimeLinter error/warning colors in user color schemes."""

    error_color = error_color.lstrip('#')
    warning_color = warning_color.lstrip('#')

    base_path = os.path.join(sublime.packages_path(), 'User', '*.tmTheme')
    sublime_path = os.path.join(sublime.packages_path(), 'User', 'SublimeLinter', '*.tmTheme')
    themes = glob(sublime_path) + glob(base_path)

    for theme in themes:
        with open(theme, encoding='utf8') as f:
            text = f.read()

        if re.search(MARK_COLOR_RE.format(r'mark\.error'), text):
            text = re.sub(MARK_COLOR_RE.format(r'mark\.error'), r'\1#{}\2'.format(error_color), text)
            text = re.sub(MARK_COLOR_RE.format(r'mark\.warning'), r'\1#{}\2'.format(warning_color), text)

            with open(theme, encoding='utf8', mode='w') as f:
                f.write(text)


def update_syntax_map():
    """Update the user syntax_map setting with any missing entries from the defaults."""

    from . import persist

    syntax_map = {}
    syntax_map.update(persist.settings.get('syntax_map', {}))
    default_syntax_map = persist.settings.plugin_settings.get('default', {}).get('syntax_map', {})
    modified = False

    for key, value in default_syntax_map.items():
        if key not in syntax_map:
            syntax_map[key] = value
            modified = True
            persist.debug('added syntax mapping: \'{}\' => \'{}\''.format(key, value))

    if modified:
        persist.settings.set('syntax_map', syntax_map)
        persist.settings.save()


# menu utils

def indent_lines(text, indent):
    """Return all of the lines in text indented by prefixing with indent."""
    return re.sub(r'^', indent, text, flags=re.MULTILINE)[len(indent):]


def generate_menus(**kwargs):
    """Asynchronously call generate_menus_async."""
    sublime.set_timeout_async(generate_menus_async, 0)


def generate_menus_async():
    """
    Generate context and Tools SublimeLinter menus.

    This is done dynamically so that we can have a submenu with all
    of the available gutter themes.

    """

    commands = []

    for chooser in CHOOSERS:
        commands.append({
            'caption': chooser,
            'menus': build_submenu(chooser),
            'toggleItems': ''
        })

    menus = []
    indent = MENU_INDENT_RE.search(CHOOSER_MENU).group(1)

    for cmd in commands:
        # Indent the commands to where they want to be in the template.
        # The first line doesn't need to be indented, remove the extra indent.
        cmd['menus'] = indent_lines(cmd['menus'], indent)

        if cmd['caption'] in TOGGLE_ITEMS:
            cmd['toggleItems'] = TOGGLE_ITEMS[cmd['caption']]
            cmd['toggleItems'] = indent_lines(cmd['toggleItems'], indent)

        menus.append(Template(CHOOSER_MENU).safe_substitute(cmd))

    menus = ',\n'.join(menus)
    text = generate_menu('Context', menus)
    generate_menu('Main', text)


def generate_menu(name, menu_text):
    """Generate and return a sublime-menu from a template."""

    from . import persist
    plugin_dir = os.path.join(sublime.packages_path(), persist.PLUGIN_DIRECTORY)
    path = os.path.join(plugin_dir, '{}.sublime-menu.template'.format(name))

    with open(path, encoding='utf8') as f:
        template = f.read()

    # Get the indent for the menus within the template,
    # indent the chooser menus except for the first line.
    indent = MENU_INDENT_RE.search(template).group(1)
    menu_text = indent_lines(menu_text, indent)

    text = Template(template).safe_substitute({'menus': menu_text})
    path = os.path.join(plugin_dir, '{}.sublime-menu'.format(name))

    with open(path, mode='w', encoding='utf8') as f:
        f.write(text)

    return text


def build_submenu(caption):
    """Generate and return a submenu with commands to select a lint mode, mark style, or gutter theme."""

    setting = caption.lower()

    if setting == 'lint mode':
        from . import persist
        names = [mode[0].capitalize() for mode in persist.LINT_MODES]
    elif setting == 'mark style':
        from . import highlight
        names = highlight.mark_style_names()

    commands = []

    for name in names:
        commands.append(CHOOSER_COMMAND.format(setting.replace(' ', '_'), name))

    return ',\n'.join(commands)


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
        persist.printf('shell timed out after {} seconds, executing {}'.format(timeout, cmd))

    return out


def extract_path(cmd, delim=':'):
    """Return the user's PATH as a colon-delimited list."""
    from . import persist
    persist.debug('user shell:', cmd[0])

    out = run_shell_cmd(cmd).decode()
    path = out.split('__SUBL_PATH__', 2)

    if len(path) > 1:
        path = path[1]
        return ':'.join(path.strip().split(delim))
    else:
        persist.printf('Could not parse shell PATH output:\n' + (out if out else '<empty>'))
        sublime.error_message(
            'SublimeLinter could not determine your shell PATH. '
            'It is unlikely that any linters will work. '
            '\n\n'
            'Please see the troubleshooting guide for info on how to debug PATH problems.')
        return ''


def get_shell_path(env):
    """
    Return the user's shell PATH using shell --login.

    This method is only used on Posix systems.

    """

    if 'SHELL' in env:
        shell_path = env['SHELL']
        shell = os.path.basename(shell_path)

        # We have to delimit the PATH output with markers because
        # text might be output during shell startup.
        if shell in ('bash', 'zsh'):
            return extract_path(
                (shell_path, '-l', '-c', 'echo "__SUBL_PATH__${PATH}__SUBL_PATH__"')
            )
        elif shell == 'fish':
            return extract_path(
                (shell_path, '-l', '-c', 'echo "__SUBL_PATH__"; for p in $PATH; echo $p; end; echo "__SUBL_PATH__"'),
                '\n'
            )
        else:
            from . import persist
            persist.printf('Using an unsupported shell:', shell)

    # guess PATH if we haven't returned yet
    split = env['PATH'].split(':')
    p = env['PATH']

    for path in (
        '/usr/bin', '/usr/local/bin',
        '/usr/local/php/bin', '/usr/local/php5/bin'
    ):
        if path not in split:
            p += (':' + path)

    return p


@lru_cache(maxsize=None)
def get_environment_variable(name):
    """Return the value of the given environment variable, or None if not found."""

    if os.name == 'posix':
        value = None

        if 'SHELL' in os.environ:
            shell_path = os.environ['SHELL']

            # We have to delimit the output with markers because
            # text might be output during shell startup.
            out = run_shell_cmd((shell_path, '-l', '-c', 'echo "__SUBL_VAR__${{{}}}__SUBL_VAR__"'.format(name))).strip()

            if out:
                value = out.decode().split('__SUBL_VAR__', 2)[1].strip() or None
    else:
        value = os.environ.get(name, None)

    from . import persist
    persist.debug('ENV[\'{}\'] = \'{}\''.format(name, value))

    return value


def get_path_components(path):
    """Split a file path into its components and return the list of components."""
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


def packages_relative_path(path, prefix_packages=True):
    """
    Return a Packages-relative version of path with '/' as the path separator.

    Sublime Text wants Packages-relative paths used in settings and in the plugin API
    to use '/' as the path separator on all platforms. This method converts platform
    path separators to '/'. If insert_packages = True, 'Packages' is prefixed to the
    converted path.

    """

    components = get_path_components(path)

    if prefix_packages and components and components[0] != 'Packages':
        components.insert(0, 'Packages')

    return '/'.join(components)


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

    if os.name == 'posix':
        env['PATH'] = get_shell_path(os.environ)

    paths = persist.settings.get('paths', {})

    if sublime.platform() in paths:
        paths = convert_type(paths[sublime.platform()], [])
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
            persist.printf('computed PATH {}:\n{}\n'.format(shell, env['PATH'].replace(os.pathsep, '\n')))

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
def which(cmd, module=None):
    """
    Return the full path to the given command, or None if not found.

    If cmd is in the form [script]@python[version], find_python is
    called to locate the appropriate version of python. If an executable
    version of the script can be found, its path is returned. Otherwise
    the result is a tuple of the full python path and the full path to the script
    (or None if there is no script).

    """

    match = PYTHON_CMD_RE.match(cmd)

    if match:
        args = match.groupdict()
        args['module'] = module
        path = find_python(**args)[0:2]

        # If a script is requested and an executable path is returned
        # with no script path, just use the executable.
        if (
            path is not None and
            path[0] is not None and
            path[1] is None and
            args['script']  # for the case where there is no script in cmd
        ):
            return path[0]
        else:
            return path
    else:
        return find_executable(cmd)


def extract_major_minor_version(version):
    """Extract and return major and minor versions from a string version."""

    match = VERSION_RE.match(version)

    if match:
        return {key: int(value) if value is not None else None for key, value in match.groupdict().items()}
    else:
        return {'major': None, 'minor': None}


@lru_cache(maxsize=None)
def get_python_version(path):
    """Return a dict with the major/minor version of the python at path."""

    try:
        # Different python versions use different output streams, so check both
        output = communicate((path, '-V'), '', output_stream=STREAM_BOTH)

        # 'python -V' returns 'Python <version>', extract the version number
        return extract_major_minor_version(output.split(' ')[1])
    except Exception as ex:
        from . import persist
        persist.printf(
            'ERROR: an error occurred retrieving the version for {}: {}'
            .format(path, str(ex)))

        return {'major': None, 'minor': None}


@lru_cache(maxsize=None)
def find_python(version=None, script=None, module=None):
    """
    Return the path to and version of python and an optional related script.

    If not None, version should be a string/numeric version of python to locate, e.g.
    '3' or '3.3'. Only major/minor versions are examined. This method then does
    its best to locate a version of python that satisfies the requested version.
    If module is not None, Sublime Text's python version is tested against the
    requested version.

    If version is None, the path to the default system python is used, unless
    module is not None, in which case '<builtin>' is returned.

    If not None, script should be the name of a python script that is typically
    installed with easy_install or pip, e.g. 'pep8' or 'pyflakes'.

    A tuple of the python path, script path, major version, minor version is returned.

    """

    from . import persist
    persist.debug(
        'find_python(version={!r}, script={!r}, module={!r})'
        .format(version, script, module)
    )

    path = None
    script_path = None

    requested_version = {'major': None, 'minor': None}

    if module is None:
        available_version = {'major': None, 'minor': None}
    else:
        available_version = {
            'major': sys.version_info.major,
            'minor': sys.version_info.minor
        }

    if version is None:
        # If no specific version is requested and we have a module,
        # assume the linter will run using ST's python.
        if module is not None:
            result = ('<builtin>', script, available_version['major'], available_version['minor'])
            persist.debug('find_python: <=', repr(result))
            return result

        # No version was specified, get the default python
        path = find_executable('python')
        persist.debug('find_python: default python =', path)
    else:
        version = str(version)
        requested_version = extract_major_minor_version(version)
        persist.debug('find_python: requested version =', repr(requested_version))

        # If there is no module, we will use a system python.
        # If there is a module, a specific version was requested,
        # and the builtin version does not fulfill the request,
        # use the system python.
        if module is None:
            need_system_python = True
        else:
            persist.debug('find_python: available version =', repr(available_version))
            need_system_python = not version_fulfills_request(available_version, requested_version)
            path = '<builtin>'

        if need_system_python:
            if sublime.platform() in ('osx', 'linux'):
                path = find_posix_python(version)
            else:
                path = find_windows_python(version)

            persist.debug('find_python: system python =', path)

    if path and path != '<builtin>':
        available_version = get_python_version(path)
        persist.debug('find_python: available version =', repr(available_version))

        if version_fulfills_request(available_version, requested_version):
            if script:
                script_path = find_python_script(path, script)
                persist.debug('find_python: {!r} path = {}'.format(script, script_path))

                if script_path is None:
                    path = None
                elif script_path.endswith('.exe'):
                    path = script_path
                    script_path = None
        else:
            path = script_path = None

    result = (path, script_path, available_version['major'], available_version['minor'])
    persist.debug('find_python: <=', repr(result))
    return result


def version_fulfills_request(available_version, requested_version):
    """
    Return whether available_version fulfills requested_version.

    Both are dicts with 'major' and 'minor' items.

    """

    # No requested major version is fulfilled by anything
    if requested_version['major'] is None:
        return True

    # If major version is requested, that at least must match
    if requested_version['major'] != available_version['major']:
        return False

    # Major version matches, if no requested minor version it's a match
    if requested_version['minor'] is None:
        return True

    # If a minor version is requested, the available minor version must be >=
    return (
        available_version['minor'] is not None and
        available_version['minor'] >= requested_version['minor']
    )


@lru_cache(maxsize=None)
def find_posix_python(version):
    """Find the nearest version of python and return its path."""

    from . import persist

    if version:
        # Try the exact requested version first
        path = find_executable('python' + version)
        persist.debug('find_posix_python: python{} => {}'.format(version, path))

        # If that fails, try the major version
        if not path:
            path = find_executable('python' + version[0])
            persist.debug('find_posix_python: python{} => {}'.format(version[0], path))

            # If the major version failed, see if the default is available
            if not path:
                path = find_executable('python')
                persist.debug('find_posix_python: python =>', path)
    else:
        path = find_executable('python')
        persist.debug('find_posix_python: python =>', path)

    return path


@lru_cache(maxsize=None)
def find_windows_python(version):
    """Find the nearest version of python and return its path."""

    if version:
        # On Windows, there may be no separately named python/python3 binaries,
        # so it seems the only reliable way to check for a given version is to
        # check the root drive for 'Python*' directories, and try to match the
        # version based on the directory names. The 'Python*' directories end
        # with the <major><minor> version number, so for matching with the version
        # passed in, strip any decimal points.
        stripped_version = version.replace('.', '')
        prefix = os.path.abspath('\\Python')
        prefix_len = len(prefix)
        dirs = sorted(glob(prefix + '*'), reverse=True)
        from . import persist

        # Try the exact version first, then the major version
        for version in (stripped_version, stripped_version[0]):
            for python_dir in dirs:
                path = os.path.join(python_dir, 'python.exe')
                python_version = python_dir[prefix_len:]
                persist.debug('find_windows_python: matching =>', path)

                # Try the exact version first, then the major version
                if python_version.startswith(version) and can_exec(path):
                    persist.debug('find_windows_python: <=', path)
                    return path

    # No version or couldn't find a version match, try the default python
    path = find_executable('python')
    persist.debug('find_windows_python: <=', path)
    return path


@lru_cache(maxsize=None)
def find_python_script(python_path, script):
    """Return the path to the given script, or None if not found."""
    if sublime.platform() in ('osx', 'linux'):
        pyenv = which('pyenv')
        if pyenv:
            out = run_shell_cmd((pyenv, 'which', script)).strip().decode()
            if os.path.isfile(out):
                return out
        return which(script)
    else:
        # On Windows, scripts may be .exe files or .py files in <python directory>/Scripts
        scripts_path = os.path.join(os.path.dirname(python_path), 'Scripts')
        script_path = os.path.join(scripts_path, script + '.exe')

        if os.path.exists(script_path):
            return script_path

        script_path = os.path.join(scripts_path, script + '-script.py')

        if os.path.exists(script_path):
            return script_path

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
            persist.printf('sys.path for {}:\n{}\n'.format(python_path, '\n'.join(paths)))
    else:
        persist.debug('no python 3 available to augment sys.path')
        paths = []

    return paths


@lru_cache(maxsize=None)
def find_executable(executable):
    """
    Return the path to the given executable, or None if not found.

    create_environment is used to augment PATH before searching
    for the executable.

    """

    env = create_environment()

    for base in env.get('PATH', '').split(os.pathsep):
        path = os.path.join(os.path.expanduser(base), executable)

        # On Windows, if path does not have an extension, try .exe, .cmd, .bat
        if sublime.platform() == 'windows' and not os.path.splitext(path)[1]:
            for extension in ('.exe', '.cmd', '.bat'):
                path_ext = path + extension

                if can_exec(path_ext):
                    return path_ext
        elif can_exec(path):
            return path

    return None


def touch(path):
    """Perform the equivalent of touch on Posix systems."""
    with open(path, 'a'):
        os.utime(path, None)


def open_directory(path):
    """Open the directory at the given path in a new window."""

    cmd = (get_subl_executable_path(), path)
    subprocess.Popen(cmd, cwd=path)


def get_subl_executable_path():
    """Return the path to the subl command line binary."""

    executable_path = sublime.executable_path()

    if sublime.platform() == 'osx':
        suffix = '.app/'
        app_path = executable_path[:executable_path.rfind(suffix) + len(suffix)]
        executable_path = app_path + 'Contents/SharedSupport/bin/subl'

    return executable_path


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

    out = popen(cmd, stdout=stdout, stderr=stderr, output_stream=output_stream, extra_env=env)

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
        filename = UNSAVED_FILENAME
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
        from . import persist
        persist.printf('ERROR: could not launch', repr(cmd))
        persist.printf('reason:', str(err))
        persist.printf('PATH:', env.get('PATH', ''))


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
    find_python.cache_clear()
    get_python_paths.cache_clear()
    find_executable.cache_clear()


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


def get_user_fullname():
    """Return the user's full name (or at least first name)."""

    if sublime.platform() in ('osx', 'linux'):
        import pwd
        return pwd.getpwuid(os.getuid()).pw_gecos
    else:
        return os.environ.get('USERNAME', 'Me')


def center_region_in_view(region, view):
    """
    Center the given region in view.

    There is a bug in ST3 that prevents a selection change
    from being drawn when a quick panel is open unless the
    viewport moves. So we get the current viewport position,
    move it down 1.0, center the region, see if the viewport
    moved, and if not, move it up 1.0 and center again.

    """

    x1, y1 = view.viewport_position()
    view.set_viewport_position((x1, y1 + 1.0))
    view.show_at_center(region)
    x2, y2 = view.viewport_position()

    if y2 == y1:
        view.set_viewport_position((x1, y1 - 1.0))
        view.show_at_center(region)


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


# color-related constants

DEFAULT_MARK_COLORS = {'warning': 'EDBA00', 'error': 'DA2000', 'gutter': 'FFFFFF'}

COLOR_SCHEME_PREAMBLE = '''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
'''

COLOR_SCHEME_STYLES = {
    'warning': '''
        <dict>
            <key>name</key>
            <string>SublimeLinter Warning</string>
            <key>scope</key>
            <string>sublimelinter.mark.warning</string>
            <key>settings</key>
            <dict>
                <key>foreground</key>
                <string>#{}</string>
            </dict>
        </dict>
    ''',

    'error': '''
        <dict>
            <key>name</key>
            <string>SublimeLinter Error</string>
            <key>scope</key>
            <string>sublimelinter.mark.error</string>
            <key>settings</key>
            <dict>
                <key>foreground</key>
                <string>#{}</string>
            </dict>
        </dict>
    ''',

    'gutter': '''
        <dict>
            <key>name</key>
            <string>SublimeLinter Gutter Mark</string>
            <key>scope</key>
            <string>sublimelinter.gutter-mark</string>
            <key>settings</key>
            <dict>
                <key>foreground</key>
                <string>#FFFFFF</string>
            </dict>
        </dict>
    '''
}


# menu command constants

CHOOSERS = (
    'Lint Mode',
    'Mark Style'
)

CHOOSER_MENU = '''{
    "caption": "$caption",
    "children":
    [
        $menus,
        $toggleItems
    ]
}'''

CHOOSER_COMMAND = '''{{
    "command": "sublimelinter_choose_{}", "args": {{"value": "{}"}}
}}'''

TOGGLE_ITEMS = {
    'Mark Style': '''
{
    "caption": "-"
},
{
    "caption": "No Column Highlights Line",
    "command": "sublimelinter_toggle_setting", "args":
    {
        "setting": "no_column_highlights_line",
        "checked": true
    }
}'''
}
