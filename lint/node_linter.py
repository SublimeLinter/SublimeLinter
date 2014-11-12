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

import os
import re
import shlex
import sublime_plugin

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

    def context_sensitive_executable_path(self, cmd):
        """
        Attempt to locate the npm module specified in cmd, searching
        the local node_modules/.bin folder first before looking in
        the global system node_modules folder. return a tuple of
        (have_path, path).

        """

        local_cmd = None
        global_cmd = util.which(cmd[0])

        curr_file = self.view.file_name()

        if curr_file:
            cwd = os.path.dirname(curr_file)
            if cwd:
                pkgpath = self.find_pkgpath(cwd)
                if pkgpath:
                    local_cmd = self.find_local_cmd_path(pkgpath, cmd[0])
                    print(local_cmd, "<-- local_cmd")

        if not local_cmd and not global_cmd:
            persist.printf(
                'WARNING: {} deactivated, cannot locate local or global binary'
                .format(cls.name, cmd[0])
            )
            return False, ''

        # if isinstance(cmd, str):
        #     cmd = shlex.split(cmd)

        # node_cmd = local_cmd if local_cmd else global_cmd
        node_cmd = global_cmd
        return True, node_cmd

    def find_pkgpath(self, cwd):
        """
        Given a current working directory, go back until root directory

        """
        name = 'package.json'

        pkgpath = os.path.normpath(os.path.join(cwd, name))

        if os.path.isfile(pkgpath):
            return pkgpath

        parent = os.path.normpath(os.path.join(cwd, '../'))

        # TODO: check if parent is root dir, if so, return False

        return self.find_pkgpath(parent)

    def find_local_cmd_path(self, pkgpath, cmd):
        """
        Given the path to a package.json file and a local binary to find,
        look in node_modules/.bin for that binary.

        """
        cwd = os.path.dirname(pkgpath)

        node_modules_bin = os.path.normpath(os.path.join(cwd, 'node_modules/.bin/'))

        binary = os.path.join(node_modules_bin, cmd)

        # TODO: check if binary is executable: os.access(binary, os.X_OK)

        return binary if binary else None
