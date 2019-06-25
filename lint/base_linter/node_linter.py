"""This module exports the NodeLinter subclass of Linter."""

from functools import lru_cache
from itertools import takewhile
import json
import logging
import os
import shutil

from .. import linter


if False:
    from typing import Any, Dict, Iterator, List, Optional, Tuple, Union


logger = logging.getLogger(__name__)
HOME = os.path.expanduser('~')


def paths_upwards(path):
    # type: (str) -> Iterator[str]
    while True:
        yield path

        next_path = os.path.dirname(path)
        # Stop just before root in *nix systems
        if next_path == '/':
            return

        if next_path == path:
            return

        path = next_path


def paths_upwards_until_home(path):
    # type: (str) -> Iterator[str]
    return takewhile(lambda p: p != HOME, paths_upwards(path))


def read_json_file(path):
    # type: (str) -> Dict[str, Any]
    return _read_json_file(path, os.path.getmtime(path))


@lru_cache(maxsize=4)
def _read_json_file(path, _mtime):
    # type: (str, float) -> Dict[str, Any]
    with open(path, 'r', encoding='utf8') as f:
        return json.load(f)


class NodeLinter(linter.Linter):
    """
    This Linter subclass provides NodeJS-specific functionality.

    Linters installed with npm should inherit from this class.
    By doing so, they automatically get the following features:

    """

    def context_sensitive_executable_path(self, cmd):
        # type: (List[str]) -> Tuple[bool, Union[None, str, List[str]]]
        """
        Attempt to locate the npm module specified in cmd.

        Searches the local node_modules/.bin folder first before
        looking in the global system node_modules folder. return
        a tuple of (have_path, path).
        """
        # The default implementation will look for a user defined `executable`
        # setting.
        success, executable = super().context_sensitive_executable_path(cmd)
        if success:
            return True, executable

        npm_name = cmd[0]
        start_dir = self.get_start_dir()
        if start_dir:
            local_cmd = self.find_local_executable(start_dir, npm_name)
            if local_cmd:
                return True, local_cmd

        if self.get_view_settings().get('disable_if_not_dependency', False):
            logger.info(
                "Skipping '{}' since it is not installed locally.\n"
                "You can change this behavior by setting 'disable_if_not_dependency' to 'false'."
                .format(self.name)
            )
            self.notify_unassign()
            raise linter.PermanentError('disable_if_not_dependency')

        return False, None

    def get_start_dir(self):
        # type: () -> Optional[str]
        return (
            self.settings.context.get('file_path') or
            self.get_working_dir(self.settings)
        )

    def find_local_executable(self, start_dir, npm_name):
        # type: (str, str) -> Union[None, str, List[str]]
        for path in paths_upwards(start_dir):
            executable = shutil.which(npm_name, path=os.path.join(path, 'node_modules', '.bin'))
            if executable:
                return executable

        for path in paths_upwards_until_home(start_dir):
            manifest_file = os.path.join(path, 'package.json')
            if os.path.exists(manifest_file):
                try:
                    manifest = read_json_file(manifest_file)
                except Exception as err:
                    logger.warning(
                        "We found a 'package.json' at {}; however, reading it raised\n  {}"
                        .format(path, str(err))
                    )
                    self.notify_failure()
                    raise linter.PermanentError()

                # Edge case: when hacking on the linter itself it is not installed
                # but must run as a normal script. E.g. `/usr/bin/env node eslint.js`
                try:
                    script = os.path.normpath(os.path.join(path, manifest['bin'][npm_name]))
                except (KeyError, TypeError):
                    pass
                else:
                    if not os.path.exists(os.path.join(path, 'node_modules', '.bin')):
                        logger.warning(
                            "We want to execute 'node {}'; but you should first "
                            "'npm install' this project.".format(script)
                        )
                        self.notify_failure()
                        raise linter.PermanentError()

                    node_binary = self.which('node')
                    if node_binary:
                        return [node_binary, script]

                    logger.warning(
                        "We want to execute 'node {}'; however, finding a node executable "
                        "failed.".format(script)
                    )
                    self.notify_failure()
                    raise linter.PermanentError()

                # A 'package.json' not yet installed?
                if not os.path.exists(os.path.join(path, 'node_modules', '.bin')):
                    is_dep = bool(manifest.get('dependencies', {}).get(npm_name))
                    is_dev_dep = bool(manifest.get('devDependencies', {}).get(npm_name))
                    if is_dep or is_dev_dep:
                        logger.warning(
                            "Skipping '{}' for now which is listed as a {} "
                            "in {} but not installed.  Forgot to 'npm install'?"
                            .format(
                                npm_name,
                                'dependency' if is_dep else 'devDependency',
                                manifest_file
                            )
                        )
                        self.notify_failure()
                        raise linter.PermanentError()

        return None
