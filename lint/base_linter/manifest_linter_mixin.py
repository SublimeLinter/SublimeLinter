"""This module exports the ManifestLinterMixin of Linter."""

import codecs
import json
import hashlib
import os
import shutil

from .. import linter, util


class ManifestLinterMixin:
    """
    This Linter mixin provides functionality to linters that have
    manifests.

    Linters with manifests should inherit from this mixin.
    By doing so, they automatically get the following features:

    """
    logger = None
    manifest_file = None
    bin_path = None
    executable_checks = set()

    def manifest_init(self, logger, manifest, bin_path):
        if manifest == None or bin_path == None:
            return

        self.logger = logger
        self.manifest_file = manifest
        self.bin_path = bin_path

        self.manifest_path = self.get_manifest_path()

        if self.manifest_path:
            self.read_manifest(os.path.getmtime(self.manifest_path))

    def manifest_register_executable_check(self, check):
        self.executable_checks.add(check)

    def context_sensitive_executable_path(self, cmd):
        """
        Attempt to locate the manifest module specified in cmd.

        Searches the local bin folder first before
        looking in the global system's bin folder.

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

        for check in self.executable_checks:
            success, executable = check(cmd)

            if success:
                return success, executable

        global_cmd = util.which(cmd[0])

        if global_cmd:
            return True, global_cmd
        else:
            self.logger.warning('{} cannot locate \'{}\'\n'
                                'Please refer to the readme of this plugin and our troubleshooting guide: '
                                'http://www.sublimelinter.com/en/stable/troubleshooting.html'
                                .format(self.name, cmd[0]))
            return True, None

    def get_manifest_path(self):
        """Get the path to the manifest file for the current file."""
        filename = self.view.file_name()
        cwd = (
            os.path.dirname(filename) if filename else
            linter.guess_project_root_of_view(self.view)
        )
        return self.rev_parse_manifest_path(cwd) if cwd else None

    def rev_parse_manifest_path(self, cwd):
        """
        Search parent directories for the manifest file.

        Starting at the current working directory. Go up one directory
        at a time checking if that directory contains a manifest file.
        If it does, return that directory.
        """
        manifest_path = os.path.normpath(os.path.join(cwd, self.manifest_file))
        bin_path = os.path.normpath(os.path.join(cwd, self.bin_path))

        if os.path.isfile(manifest_path) and os.path.isdir(bin_path):
            return manifest_path

        parent = os.path.dirname(cwd)

        if parent == '/' or parent == cwd:
            return None

        return self.rev_parse_manifest_path(parent)

    def find_local_cmd_path(self, cmd):
        """
        Find a local binary in bin.

        Given the manifest filepath and a local binary to find,
        look in the bin for that binary.
        """
        cwd = os.path.dirname(self.manifest_path)

        binary = self.get_pkg_bin_cmd(cmd)

        if binary:
            return os.path.normpath(os.path.join(cwd, binary))

        return self.find_ancestor_cmd_path(cmd, cwd)

    def find_ancestor_cmd_path(self, cmd, cwd):
        """Recursively check for command binary in ancestors' bin directories."""
        bin_path = os.path.normpath(os.path.join(cwd, self.bin_path))

        binary = shutil.which(cmd, path=bin_path)
        if binary:
            return binary

        parent = os.path.dirname(cwd)

        if parent == '/' or parent == cwd:
            return None

        return self.find_ancestor_cmd_path(cmd, parent)

    def get_pkg_bin_cmd(self, cmd):
        """
        Check is binary path is defined in the manifest bin property.

        Loading a linter to check its own source code is a special case.
        For example, the local phpcs binary when linting phpcs is
        installed at ./scripts/phpcs and not ./vendor/bin/phpcs

        This function checks the manifest file `bin` property keys to
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
        """Load manifest file."""
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
