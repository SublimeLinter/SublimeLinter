"""This module exports the ComposerLinter subclass of Linter."""
from __future__ import annotations

import os
import shutil

from .. import linter, util
from ..util import read_json_file


class PhpLinter(linter.Linter):
    """
    This Linter subclass provides composer-specific functionality.

    Linters installed with composer should inherit from this class.
    By doing so, they automatically get the following features:

    - The ability to locate a local vendor/bin folder and use binaries from it.
      In this case, 'project_root' will be set too which affects how the
      working directory is computed.

    - Support for a `disable_if_not_dependency` setting, which will
      automatically disable the linter if it is not installed locally.

    """
    __abstract__ = True

    def context_sensitive_executable_path(self, cmd) -> tuple[bool, str | list[str] | None]:
        """
        Attempt to locate the composer package specified in cmd.

        Searches the local vendor/bin folder first before
        looking in the global system .composer/vendor/bin folder.

        Return a tuple of (have_path, path).
        """
        # The default implementation will look for a user defined `executable`
        # setting.
        success, executable = super().context_sensitive_executable_path(cmd)
        if success:
            return success, executable

        cmd_name = cmd[0]
        start_dir = self.get_start_dir()
        if start_dir:
            self.logger.info(
                "Searching executable for '{}' starting at '{}'."
                .format(cmd_name, start_dir)
            )
            local_cmd = self.find_local_executable(start_dir, cmd_name)
            if local_cmd:
                return True, local_cmd

        if self.settings.get('disable_if_not_dependency', False):
            self.logger.info(
                "Skipping '{}' since it is not installed locally.\n"
                "You can change this behavior by setting 'disable_if_not_dependency' to 'false'."
                .format(self.name)
            )
            self.notify_unassign()
            raise linter.PermanentError('disable_if_not_dependency')

        return False, None

    def get_start_dir(self) -> str | None:
        return (
            self.context.get('file_path') or
            self.get_working_dir()
        )

    def find_local_executable(self, start_dir: str, cmd: str) -> str | None:
        """
        Find a local binary in vendor/bin.

        Given composer.json filepath and a local binary to find,
        look in vendor/bin for that binary.
        """
        for path in util.paths_upwards_until_home(start_dir):
            manifest_file = os.path.join(path, 'composer.json')
            bin_path = os.path.join(path, 'vendor', 'bin')
            if os.path.isfile(manifest_file) and os.path.isdir(bin_path):
                manifest_path = path
                break
        else:
            return None

        try:
            manifest = read_json_file(manifest_file)
        except Exception as err:
            self.logger.warning(
                "We found a 'composer.json' at {}; however, reading it raised\n  {}"
                .format(manifest_path, str(err))
            )
            self.notify_failure()
            raise linter.PermanentError()
        else:
            self.context['project_root'] = manifest_path

            # Edge case: when hacking on the linter itself it is not installed
            # at e.g. ./vendor/bin/phpcs but ./scripts/phpcs
            for executable in manifest.get('bin', []):
                if cmd in executable:
                    return os.path.normpath(os.path.join(manifest_path, executable))

        for path in util.paths_upwards_until_home(manifest_path):
            vendor_bin = os.path.join(path, 'vendor', 'bin')
            if binary := shutil.which(cmd, path=vendor_bin):
                return binary

        return None


ComposerLinter = PhpLinter
