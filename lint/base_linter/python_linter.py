"""This module exports the PythonLinter subclass of Linter."""
from __future__ import annotations

from functools import lru_cache
import os
import re
import shutil

import sublime

from .. import linter, util

from typing import Optional


POSIX = sublime.platform() in ('osx', 'linux')
ON_WINDOWS = sublime.platform() == 'windows'
BIN = 'bin' if POSIX else 'Scripts'
VIRTUAL_ENV_MARKERS = ('venv', '.env', '.venv')
ROOT_MARKERS = ("setup.cfg", "pyproject.toml", "tox.ini", ".git", ".hg", )


class SimplePath(str):
    def append(self, *parts: str) -> SimplePath:
        return SimplePath(os.path.join(self, *parts))

    def exists(self) -> bool:
        return os.path.exists(self)


class PythonLinter(linter.Linter):
    """
    This Linter subclass provides Python-specific functionality.

    Linters that check python should inherit from this class.
    By doing so, they automatically get the following features:

    - Automatic discovery of virtual environments in typical local folders
      like ".env", "venv", or ".venv".  Ask `pipenv` or `poetry` for the
      location o a virtual environment if it finds their lock files.
    - Support for a "python" setting which can be version (`3.10` or `"3.10"`)
      or a string pointing to a python executable.
    - Searches and sets `project_root` which in turn affects which
      `working_dir` we will use (if not overridden by the user).
    """
    __abstract__ = True

    config_file_names = (".flake8", "pytest.ini", ".pylintrc")
    """File or directory names that would count as marking the root of a project.
    This is always in addition to what `ROOT_MARKERS` in SL core defines.
    """

    def context_sensitive_executable_path(self, cmd: list[str]) -> tuple[bool, str | list[str] | None]:
        """Try to find an executable for a given cmd."""
        # The default implementation will look for a user defined `executable`
        # setting.
        success, executable = super().context_sensitive_executable_path(cmd)
        if success:
            return success, executable

        python = self.settings.get('python', None)
        self.logger.info(
            "{}: wanted python is '{}'".format(self.name, python)
        )

        cmd_name = cmd[0]

        if python:
            python = str(python)
            if VERSION_RE.match(python):
                if ON_WINDOWS:
                    py_exe = util.which('py')
                    if py_exe:
                        return True, [py_exe, '-{}'.format(python), '-m', cmd_name]
                python_bin = find_python_version(python)
                if python_bin is None:
                    self.logger.error(
                        "{} deactivated, cannot locate '{}' "
                        "for given python '{}'"
                        .format(self.name, cmd_name, python)
                    )
                    # Do not fallback, user specified something we didn't find
                    return True, None

                self.logger.info(
                    "{}: Using '{}' for given python '{}'"
                    .format(self.name, python_bin, python)
                )
                return True, [python_bin, '-m', cmd_name]

            else:
                if not os.path.exists(python):
                    self.logger.error(
                        "{} deactivated, cannot locate '{}'"
                        .format(self.name, python)
                    )
                    # Do not fallback, user specified something we didn't find
                    return True, None

                return True, [python, '-m', cmd_name]

        # If we're here the user didn't specify anything. This is the default
        # experience. So we kick in some 'magic'
        executable = self.find_local_executable(cmd_name)
        if executable:
            self.logger.info(
                "{}: Using '{}'"
                .format(self.name, executable)
            )
            return True, executable

        if self.settings.get('disable_if_not_dependency', False):
            self.logger.info(
                "Skipping '{}' since it is not installed locally.\n"
                "You can change this behavior by setting "
                "'disable_if_not_dependency' to 'false'."
                .format(self.name)
            )
            self.notify_unassign()
            raise linter.PermanentError('disable_if_not_dependency')

        self.logger.info(
            "{}: trying to use globally installed {}"
            .format(self.name, cmd_name)
        )
        # fallback, similar to a which(cmd)
        executable = util.which(cmd_name)
        if executable is None:
            self.logger.warning(
                "cannot locate '{}'. Fill in the 'python' or "
                "'executable' setting."
                .format(self.name)
            )
        return True, executable

    def find_local_executable(self, linter_name: str) -> str | None:
        start_dir = self.get_start_dir()
        if start_dir:
            self.logger.info(
                "Searching executable for '{}' starting at '{}'."
                .format(linter_name, start_dir)
            )
            root_dir, venv = self._nearest_virtual_environment(start_dir)
            if root_dir:
                self.logger.info(
                    "Setting 'project_root' to '{}'".format(root_dir)
                )
                self.context['project_root'] = root_dir
            if venv:
                # Set "VIRTUAL_ENV" even if the tool is not installed in it.
                # A tool either ignores this setting or supports it.
                self.env.setdefault("VIRTUAL_ENV", venv)
                self.env.setdefault(
                    "PATH",
                    os.pathsep.join(
                        [os.path.join(venv, BIN)]
                        + [_path] if (_path := self.context.get("PATH", "")) else []
                    )
                )

                executable = find_script_by_python_env(venv, linter_name)
                if executable:
                    return executable

                self.logger.info(
                    "{} is not installed in the virtual env at '{}'."
                    .format(linter_name, venv)
                )
        return None

    def get_start_dir(self) -> str | None:
        return (
            self.context.get('file_path') or
            self.get_working_dir()
        )

    def _nearest_virtual_environment(self, start_dir: str) -> tuple[Optional[str], Optional[str]]:
        paths = util.paths_upwards_until_home(start_dir)
        root_dir_markers = ROOT_MARKERS + self.config_file_names
        root_dir = None
        for path in paths:
            path_to = SimplePath(path).append
            for candidate in VIRTUAL_ENV_MARKERS:
                if os.path.isdir(path_to(candidate, BIN)):
                    return root_dir or path, path_to(candidate)

            poetrylock = path_to('poetry.lock')
            if poetrylock.exists():
                venv = ask_utility_for_venv(path, ('poetry', 'env', 'info', '-p'))
                if not venv:
                    self.logger.info(
                        "virtualenv for '{}' not created yet".format(poetrylock)
                    )
                return root_dir or path, venv

            pipfile = path_to('Pipfile')
            if pipfile.exists():
                venv = ask_utility_for_venv(path, ('pipenv', '--venv'))
                if not venv:
                    self.logger.info(
                        "virtualenv for '{}' not created yet".format(pipfile)
                    )
                return root_dir or path, venv

            if not root_dir and any(
                path_to(candidate).exists()
                for candidate in root_dir_markers
            ):
                root_dir = path

        return root_dir, None


def find_python_version(version: str) -> str | None:
    """Return python binaries on PATH matching a specific version."""
    requested_version = extract_major_minor_version(version)
    for python in util.where('python'):
        python_version = get_python_version(python)
        if version_fulfills_request(python_version, requested_version):
            return python

    return None


def find_script_by_python_env(python_env_path: str, script: str) -> str | None:
    """Return full path to a script, given a python environment base dir."""
    full_path = os.path.join(python_env_path, BIN)
    return shutil.which(script, path=full_path)


def ask_utility_for_venv(cwd: str, cmd: tuple[str, ...]) -> str | None:
    try:
        return _ask_utility_for_venv(cwd, cmd)
    except Exception:
        return None


@lru_cache(maxsize=None)
def _ask_utility_for_venv(cwd: str, cmd: tuple[str, ...]) -> str:
    return util.check_output(cmd, cwd=cwd).strip().split('\n')[-1]


VERSION_RE = re.compile(r'(?P<major>\d+)(?:\.(?P<minor>\d+))?')


@lru_cache(maxsize=None)
def get_python_version(path):
    """Return a dict with the major/minor version of the python at path."""
    try:
        output = util.check_output([path, '-V'])
    except Exception:
        output = ''

    return extract_major_minor_version(output.split(' ')[-1])


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
