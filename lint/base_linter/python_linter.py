"""This module exports the PythonLinter subclass of Linter."""

from functools import lru_cache
import logging
import os
import re

import sublime
from .. import linter, util


logger = logging.getLogger(__name__)


class PythonLinter(linter.Linter):
    """
    This Linter subclass provides Python-specific functionality.

    Linters that check python should inherit from this class.
    By doing so, they automatically get the following features:

    - Automatic discovery of virtual environments using `pipenv`
    - Support for a "python" setting.
    - Support for a "executable" setting.
    """

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

        logger.info(
            "{}: wanted python is '{}'".format(self.name, python)
        )

        cmd_name = cmd[0] if isinstance(cmd, (list, tuple)) else cmd

        if python:
            python = str(python)
            if VERSION_RE.match(python):
                python_bin = find_python_version(python)
                if python_bin is None:
                    logger.error(
                        "{} deactivated, cannot locate '{}' "
                        "for given python '{}'"
                        .format(self.name, cmd_name, python)
                    )
                    # Do not fallback, user specified something we didn't find
                    return True, None

                logger.info(
                    "{}: Using '{}' for given python '{}'"
                    .format(self.name, python_bin, python)
                )
                return True, [python_bin, '-m', cmd_name]

            else:
                if not os.path.exists(python):
                    logger.error(
                        "{} deactivated, cannot locate '{}'"
                        .format(self.name, python)
                    )
                    # Do not fallback, user specified something we didn't find
                    return True, None

                return True, [python, '-m', cmd_name]

        # If we're here the user didn't specify anything. This is the default
        # experience. So we kick in some 'magic'
        cwd = self.get_working_dir(settings)
        executable = ask_pipenv(cmd_name, cwd)
        if executable:
            logger.info(
                "{}: Using {} according to 'pipenv'"
                .format(self.name, executable)
            )
            return True, executable

        # Should we try a `pyenv which` as well? Problem: I don't have it,
        # it's MacOS only.

        logger.info(
            "{}: trying to use globally installed {}"
            .format(self.name, cmd_name)
        )
        # fallback, similiar to a which(cmd)
        executable = util.which(cmd_name)
        if executable is None:
            logger.warning(
                "cannot locate '{}'. Fill in the 'python' or "
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
            return python

    return None


def find_script_by_python_env(python_env_path, script):
    """Return full path to a script, given a python environment base dir."""
    posix = sublime.platform() in ('osx', 'linux')

    if posix:
        full_path = os.path.join(python_env_path, 'bin', script)
    else:
        full_path = os.path.join(python_env_path, 'Scripts', script + '.exe')

    logger.info("trying {}".format(full_path))
    if os.path.exists(full_path):
        return full_path

    return None


def ask_pipenv(linter_name, cwd):
    """Ask pipenv for a virtual environment and maybe resolve the linter."""
    # Some pre-checks bc `pipenv` is super slow
    if cwd is None:
        return

    pipfile = os.path.join(cwd, 'Pipfile')
    if not os.path.exists(pipfile):
        return

    try:
        venv = ask_pipenv_for_venv(linter_name, cwd)
    except Exception:
        return

    return find_script_by_python_env(venv, linter_name)


@lru_cache(maxsize=None)
def ask_pipenv_for_venv(linter_name, cwd):
    cmd = ['pipenv', '--venv']
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
        items = match.groupdict().items()
        return {k: int(v) if v is not None else None for k, v in items}
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
