#
# composer_linter.py
# Part of SublimeLinter3, a code checking framework for Sublime Text 3
#
# Written by Christy Quinn <christyjquinn@gmail.com>
#
# Project: https://github.com/SublimeLinter/SublimeLinter3
# License: MIT
#

"""This module exports the ComposerLinter subclass of Linter."""

import json
import hashlib
import codecs

from functools import lru_cache
from os import path, access, X_OK
from . import linter, persist, util


class ComposerLinter(linter.Linter):
    """
    This Linter subclass provides composer-specific functionality.

    Linters installed with composer should inherit from this class.
    By doing so, they automatically get the following features:

    - Support for finding local binaries in a project's
      vendor/bin folder. You need to override composer_name
      variable to use this linter.

    - comment_re is defined correctly for PHP. If your
      linter can be found in the vendor/bin folder, but lints
      a different language, you should override this with the
      correct regular expression for the comments in the files
      being linted.
    """

    comment_re = r'\s*/[/*]'

    # must be overridden by the linter
    composer_name = None

    def __init__(self, view, syntax):
        """Initialize a new ComposerLinter instance."""
        super(ComposerLinter, self).__init__(view, syntax)

        self.manifest_path = self.get_manifest_path()

        if self.manifest_path:
            self.read_manifest(path.getmtime(self.manifest_path))

    def context_sensitive_executable_path(self, cmd):
        """
        Attempt to locate the composer package specified in cmd.

        Searches the local vendor/bin folder first before
        looking in the global system .composer/vendor/bin folder.

        Return a tuple of (have_path, path).
        """
        local_cmd = None
        global_cmd = util.which(cmd[0])

        if self.manifest_path:
            local_cmd = self.find_local_cmd_path(cmd[0])

        if not local_cmd and not global_cmd:
            persist.printf(
                'WARNING: {} deactivated, cannot locate local or global binary'
                .format(self.name, cmd[0])
            )
            return False, ''

        composer_cmd_path = local_cmd if local_cmd else global_cmd
        self.executable_path = composer_cmd_path
        return False, composer_cmd_path

    def get_manifest_path(self):
        """Get the path to the composer.json file for the current file."""
        curr_file = self.view.file_name()

        manifest_path = None

        if curr_file:
            cwd = path.dirname(curr_file)

            if cwd:
                manifest_path = self.rev_parse_manifest_path(cwd)

        return manifest_path

    def rev_parse_manifest_path(self, cwd):
        """
        Search parent directories for composer.json.

        Starting at the current working directory. Go up one directory
        at a time checking if that directory contains a composer.json
        file. If it does, return that directory.
        """
        name = 'composer.json'
        manifest_path = path.normpath(path.join(cwd, name))

        bin_path = path.join(cwd, 'vendor/bin/')

        if path.isfile(manifest_path) and path.isdir(bin_path):
            return manifest_path

        parent = path.normpath(path.join(cwd, '../'))

        if parent == '/' or parent == cwd:
            return None

        return self.rev_parse_manifest_path(parent)

    def find_local_cmd_path(self, cmd):
        """
        Find a local binary in vendor/bin.

        Given composer.json filepath and a local binary to find,
        look in vendor/bin for that binary.
        """
        cwd = path.dirname(self.manifest_path)

        binary = self.get_pkg_bin_cmd(cmd)

        if binary:
            return path.normpath(path.join(cwd, binary))

        return self.find_ancestor_cmd_path(cmd, cwd)

    def find_ancestor_cmd_path(self, cmd, cwd):
        """Recursively check for command binary in ancestors' vendor/bin directories."""
        vendor_bin = path.normpath(path.join(cwd, 'vendor/bin/'))

        binary = path.join(vendor_bin, cmd)

        if binary and access(binary, X_OK):
            return binary

        parent = path.normpath(path.join(cwd, '../'))

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
        current_manifest_mtime = path.getmtime(self.manifest_path)

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

    @classmethod
    @lru_cache(maxsize=None)
    def can_lint(cls, syntax):
        """
        Determine if the linter can handle the provided syntax.

        This is an optimistic determination based on the linter's syntax alone.
        """
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
