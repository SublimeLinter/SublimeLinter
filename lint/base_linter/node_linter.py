"""This module exports the NodeLinter subclass of Linter."""

import codecs
import json
import hashlib
import os

import sublime

from .. import linter, util


class NodeLinter(linter.Linter):
    """
    This Linter subclass provides NodeJS-specific functionality.

    Linters installed with npm should inherit from this class.
    By doing so, they automatically get the following features:

    - Support for finding local binaries in a project's
      ./node_modules/.bin/ folder. You need to override npm_name
      variable to use this linter.

    """

    # must be overridden by the linter
    npm_name = None

    def __init__(self, view, syntax):
        """Initialize a new NodeLinter instance."""
        super(NodeLinter, self).__init__(view, syntax)

        self.manifest_path = self.get_manifest_path()

        if self.manifest_path:
            self.read_manifest(os.path.getmtime(self.manifest_path))

    def context_sensitive_executable_path(self, cmd):
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

        if self.manifest_path:
            local_cmd = self.find_local_cmd_path(cmd[0])
            if local_cmd:
                return True, local_cmd
            elif self.get_view_settings().get('disable_if_not_dependency', False):
                util.printf(
                    "Disabled {}. Did you `npm install {}`?."
                    .format(self.name, cmd[0]))
                return True, None

        global_cmd = util.which(cmd[0])
        if global_cmd:
            return True, global_cmd
        else:
            msg = 'WARNING: {} cannot locate \'{}\''.format(self.name, cmd[0])
            util.printf(msg)
            util.message(msg)
            return True, None

    def get_manifest_path(self):
        """Get the path to the package.json file for the current file."""
        filename = self.view.file_name()
        cwd = (
            os.path.dirname(filename) if filename else
            self._guess_project_path(self.view.window(), filename)
        )
        return self.rev_parse_manifest_path(cwd) if cwd else None

    def rev_parse_manifest_path(self, cwd):
        """
        Search parent directories for package.json.

        Starting at the current working directory. Go up one directory
        at a time checking if that directory contains a package.json
        file. If it does, return that directory.
        """
        manifest_path = os.path.join(cwd, 'package.json')
        bin_path = os.path.normpath(os.path.join(cwd, 'node_modules/.bin/'))

        if os.path.isfile(manifest_path) and os.path.isdir(bin_path):
            return manifest_path

        parent = os.path.dirname(cwd)

        if parent == '/' or parent == cwd:
            return None

        return self.rev_parse_manifest_path(parent)

    def find_local_cmd_path(self, cmd):
        """
        Find a local binary in node_modules/.bin.

        Given package.json filepath and a local binary to find,
        look in node_modules/.bin for that binary.
        """
        cwd = os.path.dirname(self.manifest_path)

        binary = self.get_pkg_bin_cmd(cmd)

        if binary:
            return os.path.normpath(os.path.join(cwd, binary))

        return self.find_ancestor_cmd_path(cmd, cwd)

    def find_ancestor_cmd_path(self, cmd, cwd):
        """Recursively check for command binary in ancestors' node_modules/.bin directories."""
        node_modules_bin = os.path.normpath(os.path.join(cwd, 'node_modules/.bin/'))

        binary = os.path.join(node_modules_bin, cmd)

        if sublime.platform() == 'windows' and os.path.splitext(binary)[1] != '.cmd':
            binary += '.cmd'

        if util.can_exec(binary):
            return binary

        parent = os.path.dirname(cwd)

        if parent == '/' or parent == cwd:
            return None

        return self.find_ancestor_cmd_path(cmd, parent)

    def get_pkg_bin_cmd(self, cmd):
        """
        Check is binary path is defined in package.json bin property.

        Loading a linter to check its own source code is a special case.
        For example, the local eslint binary when linting eslint is
        installed at ./bin/eslint.js and not ./node_modules/.bin/eslint

        This function checks the package.json `bin` property keys to
        see if the cmd we're looking for is defined for the current
        project.
        """
        pkg = self.get_manifest()
        return pkg['bin'][cmd] if 'bin' in pkg and cmd in pkg['bin'] else None

    def get_manifest(self):
        """Load manifest file (package.json)."""
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

    @classmethod
    def can_lint(cls):
        """Assume the linter can lint."""
        return True
