"""This module exports the NodeLinter subclass of Linter."""

from functools import lru_cache
import json
import logging
import os
import shutil

from .. import linter


if False:
    from typing import Any, Dict, Iterator, List, Optional, Tuple, Union


logger = logging.getLogger(__name__)


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


def paths_with_installed_package_json(start_dir):
    # type: (str) -> Iterator[str]
    for path in paths_upwards(start_dir):
        if (
            os.path.exists(os.path.join(path, 'package.json')) and
            os.path.exists(os.path.join(path, 'node_modules', '.bin'))
        ):
            yield path


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
        # type: (str, str) -> Optional[str]
        manifest_path = next(paths_with_installed_package_json(start_dir), None)
        if not manifest_path:
            return None

        try:
            manifest = read_json_file(os.path.join(manifest_path, 'package.json'))
        except Exception:
            ...
        else:
            try:
                return os.path.normpath(os.path.join(manifest_path, manifest['bin'][npm_name]))
            except KeyError:
                ...

        for path in paths_upwards(manifest_path):
            executable = shutil.which(npm_name, path=os.path.join(path, 'node_modules', '.bin'))
            if executable:
                return executable
        else:
            return None
