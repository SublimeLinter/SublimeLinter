"""This module exports the PythonLinter subclass of Linter."""

from functools import lru_cache
import os
import re
import subprocess

import sublime
from .. import linter, persist, util


class PythonLinter(linter.Linter):
    """
    This Linter subclass provides Python-specific functionality.

    Linters that check python should inherit from this class.
    By doing so, they automatically get the following features:

    - Automatic discovery of virtual environments using `pipenv`

    - Support for a "python" setting.

      python can be set to a version, in which case we try to find
      a python on your system matching that version.

      python can alternatively set to a base path of a python
      environment. We then look for linter binaries within that
      environment. A python environment can be a real installation
      or a virtual environment

    - Support for a "executable" setting.

      A set "executable" will take precedence over any other method.
      It must point to a real, executable binary.

    """

    @classmethod
    @lru_cache(maxsize=None)
    def can_lint(cls, syntax):
        """Determine optimistically if the linter can handle the provided syntax."""
        can = False
        syntax = syntax.lower()

        if cls.syntax:
            if isinstance(cls.syntax, (tuple, list)):
                can = syntax in cls.syntax
            elif cls.syntax == '*':
                can = True
            elif isinstance(cls.syntax, str):
                can = syntax == cls.syntax
            else:
                can = cls.syntax.match(syntax) is not None

        return can

    def context_sensitive_executable_path(self, cmd):
        """Try to find an executable for a given cmd."""
        # The default implementation will look for a user defined `executable`
        # setting.
        success, executable = super().context_sensitive_executable_path(cmd)
        if success:
            return success, executable

        settings = self.get_view_settings()

        # `python` can be number or a string. If it is a string it should
        # point to a python environment, NOT a python binary.
        python = settings.get('python', None)

        persist.debug(
            "{}: wanted python is '{}'".format(self.name, python)
        )

        cmd_name = cmd[0] if isinstance(cmd, (list, tuple)) else cmd

        if python:
            if isinstance(python, str):
                executable = find_script_by_python_env(
                    python, cmd_name
                )
                if not executable:
                    persist.printf(
                        "WARNING: {} deactivated, cannot locate '{}' "
                        "for given python '{}'"
                        .format(self.name, cmd_name, python)
                    )
                    # Do not fallback, user specified something we didn't find
                    return True, None

                return True, executable

            else:
                executable = find_script_by_python_version(
                    cmd_name, str(python)
                )

                if executable is None:
                    persist.printf(
                        "WARNING: {} deactivated, cannot locate '{}' "
                        "for given python '{}'"
                        .format(self.name, cmd_name, python)
                    )
                    return True, None

                persist.debug(
                    "{}: Using {} for given python '{}'"
                    .format(self.name, executable, python)
                )
                return True, executable

        # If we're here the user didn't specify anything. This is the default
        # experience. So we kick in some 'magic'
        chdir = self.get_chdir(settings)
        executable = ask_pipenv(cmd[0], chdir)
        if executable:
            persist.debug(
                "{}: Using {} according to 'pipenv'"
                .format(self.name, executable)
            )
            return True, executable

        # Should we try a `pyenv which` as well? Problem: I don't have it,
        # it's MacOS only.

        persist.debug(
            "{}: trying to use globally installed {}"
            .format(self.name, cmd_name)
        )
        # fallback, similiar to a which(cmd)
        executable = util.which(cmd_name)
        if executable is None:
            persist.printf(
                "WARNING: cannot locate '{}'. Fill in the 'python' or "
                "'executable' setting."
                .format(self.name)
            )
        return True, executable


def find_python_version(version):  # type: Str
    """Return python binaries on PATH matching a specific version."""
    requested_version = extract_major_minor_version(version)
    for python in util.find_executables('python'):
        python_version = get_python_version(python)
        if version_fulfills_request(python_version, requested_version):
            yield python

    return None


@lru_cache(maxsize=None)
def find_script_by_python_version(script_name, version):
    """Return full path to a script, given just a python version."""
    # They can be multiple matching pythons. We try to find a python with
    # its complete environment, not just a symbolic link or so.
    for python in find_python_version(version):
        python_env = os.path.dirname(python)
        script_path = find_script_by_python_env(python_env, script_name)
        if script_path:
            return script_path

    return None


@lru_cache(maxsize=None)
def find_script_by_python_env(python_env_path, script):
    """Return full path to a script, given a python environment base dir."""
    posix = sublime.platform() in ('osx', 'linux')

    if posix:
        full_path = os.path.join(python_env_path, 'bin', script)
    else:
        full_path = os.path.join(python_env_path, 'Scripts', script + '.exe')

    persist.printf("trying {}".format(full_path))
    if os.path.exists(full_path):
        return full_path

    return None


def get_project_path():
    """Return the project_path using Sublime's window.project_data() API."""
    window = sublime.active_window()
    # window.project_data() is a relative new API.
    # I don't know what we can expect from 'folders' here. Can we just take
    # the first one, if any, and be happy?
    project_data = window.project_data() or {}
    folders = project_data.get('folders', [])
    if folders:
        return folders[0]['path']  # ?


def ask_pipenv(linter_name, chdir):
    """Ask pipenv for a virtual environment and maybe resolve the linter."""
    # Some pre-checks bc `pipenv` is super slow
    project_path = get_project_path()
    if not project_path:
        return

    pipfile = os.path.join(project_path, 'Pipfile')
    if not os.path.exists(pipfile):
        return

    # Defer the real work to another function we can cache.
    # ATTENTION: If the user has a Pipfile, but did not (yet) installed the
    # environment, we will cache a wrong result here.
    return _ask_pipenv(linter_name, chdir)


@lru_cache(maxsize=None)
def _ask_pipenv(linter_name, chdir):
    cmd = ['pipenv', '--venv']
    venv = _communicate(cmd, cwd=chdir).strip().split('\n')[-1]

    if not venv:
        return

    return find_script_by_python_env(venv, linter_name)


def _communicate(cmd, cwd):
    """Short wrapper around subprocess.check_output to eat all errors."""
    env = util.create_environment()
    info = None

    # On Windows, start process without a window
    if os.name == 'nt':
        info = subprocess.STARTUPINFO()
        info.dwFlags |= subprocess.STARTF_USESTDHANDLES | subprocess.STARTF_USESHOWWINDOW
        info.wShowWindow = subprocess.SW_HIDE

    try:
        return subprocess.check_output(
            cmd, env=env, startupinfo=info, universal_newlines=True, cwd=cwd
        )
    except Exception as err:
        persist.debug(
            "executing {} failed: reason: {}".format(cmd, str(err))
        )
        return ''


VERSION_RE = re.compile(r'(?P<major>\d+)(?:\.(?P<minor>\d+))?')


@lru_cache(maxsize=None)
def get_python_version(path):
    """Return a dict with the major/minor version of the python at path."""
    try:
        # Different python versions use different output streams, so check both
        output = util.communicate((path, '-V'), '', output_stream=util.STREAM_BOTH)

        # 'python -V' returns 'Python <version>', extract the version number
        return extract_major_minor_version(output.split(' ')[1])
    except Exception as ex:
        util.printf(
            'ERROR: an error occurred retrieving the version for {}: {}'
            .format(path, str(ex)))

        return {'major': None, 'minor': None}


def extract_major_minor_version(version):
    """Extract and return major and minor versions from a string version."""
    match = VERSION_RE.match(version)

    if match:
        return {key: int(value) if value is not None else None for key, value in match.groupdict().items()}
    else:
        return {'major': None, 'minor': None}


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
