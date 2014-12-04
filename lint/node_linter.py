#
# node_linter.py
# Part of SublimeLinter3, a code checking framework for Sublime Text 3
#
# Written by Andrew de Andrade <andrew@deandrade.com.br>
#
# Project: https://github.com/SublimeLinter/SublimeLinter3
# License: MIT
#

"""This module exports the NodeLinter subclass of Linter."""

import json

from os import path, access, X_OK
from . import linter, persist, util


class NodeLinter(linter.Linter):

    """
    This Linter subclass provides NodeJS-specific functionality.

    Linters installed with npm should inherit from this class.
    By doing so, they automatically get the following features:

    - Support for finding local binaries in a project's
      ./node_modules/.bin/ folder.

    - comment_re is defined correctly for JavaScript. If your
      linter can be found in the node_modules folder, but lints
      a different language, you should override this with the
      correct regular expression for the comments in the files
      being linted.

    """

    comment_re = r'\s*/[/*]'

    def lint(self, hit_time):
        """
        Check NodeLinter options then run lint() in super.

        """
        view_settings = self.get_view_settings(inline=True)

        is_dep = self.is_dependency()

        enable_if_dependency = view_settings.get('enable_if_dependency', False)
        disable_if_not_dependency = \
            view_settings.get('disable_if_not_dependency', False)

        if enable_if_dependency and is_dep:
            self.disabled = False

        if disable_if_not_dependency and not is_dep:
            self.disabled = True

        super(NodeLinter, self).lint(hit_time)

    def is_dependency(self):
        """
        Check package.json to see if linter is a dependency.
        """

        is_dep = False

        npm_name = 'lint-trap'

        pkgpath = self.get_pkgpath()

        pkg = json.load(open(pkgpath))

        # also return true if the name is the same so linters can lint their
        # own code (e.g. eslint can lint the eslint project)
        is_dep = True if npm_name == pkg['name'] else False

        if not is_dep:
            is_dep = True if (
                'dependencies' in pkg and
                npm_name in pkg['dependencies']
            ) else False

        if not is_dep:
            is_dep = True if (
                'devDependencies' in pkg and
                npm_name in pkg['devDependencies']
            ) else False

        print("is_dependency", is_dep)
        return is_dep

    def context_sensitive_executable_path(self, cmd):
        """
        Attempt to locate the npm module specified in cmd.

        Searches the local node_modules/.bin folder first before
        looking in the global system node_modules folder. return
        a tuple of (have_path, path).

        """

        local_cmd = None
        global_cmd = util.which(cmd[0])

        pkgpath = self.get_pkgpath()

        if pkgpath:
            local_cmd = self.find_local_cmd_path(pkgpath, cmd[0])

        if not local_cmd and not global_cmd:
            persist.printf(
                'WARNING: {} deactivated, cannot locate local or global binary'
                .format(self.name, cmd[0])
            )
            return False, ''

        node_cmd_path = local_cmd if local_cmd else global_cmd
        self.executable_path = node_cmd_path

        return False, node_cmd_path

    def get_pkgpath(self):
        """
        Get the path to the package.json file for the current file.
        """
        curr_file = self.view.file_name()

        pkgpath = None

        if curr_file:
            cwd = path.dirname(curr_file)

            if cwd:
                pkgpath = self.rev_parse_pkgpath(cwd)

        return pkgpath

    def rev_parse_pkgpath(self, cwd):
        """
        Search parent directories for package.json.

        Starting at the current working directory. Go up one directory
        at a time checking if that directory contains a package.json
        file. If it does, return that directory.

        """

        name = 'package.json'
        pkgpath = path.normpath(path.join(cwd, name))

        if path.isfile(pkgpath):
            return pkgpath

        parent = path.normpath(path.join(cwd, '../'))

        if parent == '/':
            return None

        return self.rev_parse_pkgpath(parent)

    def find_local_cmd_path(self, pkgpath, cmd):
        """
        Find a local binary in node_modules/.bin.

        Given package.json filepath and a local binary to find,
        look in node_modules/.bin for that binary.

        """

        cwd = path.dirname(pkgpath)

        binary = self.get_pkg_bin_cmd(pkgpath, cmd)

        if binary:
            return path.normpath(path.join(cwd, binary))

        node_modules_bin = path.normpath(path.join(cwd, 'node_modules/.bin/'))

        binary = path.join(node_modules_bin, cmd)

        return binary if binary and access(binary, X_OK) else None

    def get_pkg_bin_cmd(self, pkgpath, cmd):
        """
        Check is binary path is defined in package.json bin property.

        Loading a linter to check its own source code is a special case.
        For example, the local eslint binary when linting eslint is
        installed at ./bin/eslint.js and not ./node_modules/.bin/eslint

        This function checks the package.json `bin` property keys to
        see if the cmd we're looking for is defined for the current
        project.

        """

        pkg = json.load(open(pkgpath))
        return pkg['bin'][cmd] if 'bin' in pkg and cmd in pkg['bin'] else None
