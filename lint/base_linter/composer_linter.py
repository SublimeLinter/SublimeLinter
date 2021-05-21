"""This module exports the ComposerLinter subclass of Linter."""

import codecs
import json
import hashlib
import os
import shutil

from .. import linter, util


class ComposerLinter(linter.Linter):
    """
    This Linter subclass provides composer-specific functionality.

    Linters installed with composer should inherit from this class.
    By doing so, they automatically get the following features:

    """

    def __init__(self, view, settings):
        """Initialize a new ComposerLinter instance."""
        super().__init__(view, settings)

        self.manifest_path = self.get_manifest_path()

        if self.manifest_path:
            self.read_manifest(os.path.getmtime(self.manifest_path))

    def context_sensitive_executable_path(self, cmd):
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

        if self.manifest_path:
            local_cmd = self.find_local_cmd_path(cmd[0])
            if local_cmd:
                return True, local_cmd

        global_cmd = util.which(cmd[0])
        if global_cmd:
            return True, global_cmd
        else:
            self.logger.warning(
                '{} cannot locate \'{}\'\n'
                'Please refer to the readme of this plugin and our troubleshooting guide: '
                'http://www.sublimelinter.com/en/stable/troubleshooting.html'.format(self.name, cmd[0])
            )
            return True, None

    def get_manifest_path(self):
        """Get the path to the composer.json file for the current file."""
        filename = self.view.file_name()
        cwd = (
            os.path.dirname(filename) if filename else
            linter.guess_project_root_of_view(self.view)
        )
        return self.rev_parse_manifest_path(cwd) if cwd else None

    def rev_parse_manifest_path(self, cwd):
        """
        Search parent directories for composer.json.

        Starting at the current working directory. Go up one directory
        at a time checking if that directory contains a composer.json
        file. If it does, return that directory.
        """
        manifest_path = os.path.normpath(os.path.join(cwd, 'composer.json'))
        bin_path = os.path.normpath(os.path.join(cwd, 'vendor/bin/'))

        if os.path.isfile(manifest_path) and os.path.isdir(bin_path):
            return manifest_path

        parent = os.path.dirname(cwd)

        if parent == '/' or parent == cwd:
            return None

        return self.rev_parse_manifest_path(parent)

    def find_local_cmd_path(self, cmd):
        """
        Find a local binary in vendor/bin.

        Given composer.json filepath and a local binary to find,
        look in vendor/bin for that binary.
        """
        cwd = os.path.dirname(self.manifest_path)

        binary = self.get_pkg_bin_cmd(cmd)

        if binary:
            return os.path.normpath(os.path.join(cwd, binary))

        return self.find_ancestor_cmd_path(cmd, cwd)

    def find_ancestor_cmd_path(self, cmd, cwd):
        """Recursively check for command binary in ancestors' vendor/bin directories."""
        vendor_bin = os.path.normpath(os.path.join(cwd, 'vendor/bin/'))

        binary = shutil.which(cmd, path=vendor_bin)
        if binary:
            return binary

        parent = os.path.dirname(cwd)

        if parent == '/' or parent == cwd:
            return None

        return self.find_ancestor_cmd_path(cmd, parent)

    def get_pkg_bin_cmd(self, cmd):
        """
        Check is binary path is defined in composer.json bin property.

        Loading a linter to check its own source code is a special case.
        For example, the local phpcs binary when linting phpcs is
        installed at ./scripts/phpcs and not ./vendor/bin/phpcs

        This function checks the composer.json `bin` property keys to
        see if the cmd we're looking for is defined for the current
        project.
        """
        pkg = self.get_manifest()

        if 'bin' in pkg:
            for executable in pkg['bin']:
                if cmd in executable:
                    return executable

        return None

    def get_manifest(self):
        """Load manifest file (composer.json)."""
        current_manifest_mtime = os.path.getmtime(self.manifest_path)

        if (current_manifest_mtime != self.cached_manifest_mtime and
                self.hash_manifest() != self.cached_manifest_hash):
            self.read_manifest(current_manifest_mtime)

        return self.cached_manifest

    def read_manifest(self, current_manifest_mtime):
        """Read manifest and cache mtime, hash and json content."""
        self.cached_manifest_mtime = current_manifest_mtime
        self.cached_manifest_hash = self.hash_manifest()
        self.cached_manifest = json.load(codecs.open(self.manifest_path, 'r', 'utf-8'))

    def hash_manifest(self):
        """Calculate the hash of the manifest file."""
        f = codecs.open(self.manifest_path, 'r', 'utf-8')
        return hashlib.sha1(f.read().encode('utf-8')).hexdigest()
