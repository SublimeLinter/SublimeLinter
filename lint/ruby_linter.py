#
# ruby_linter.py
# Part of SublimeLinter3, a code checking framework for Sublime Text 3
#
# Written by Aparajita Fishman
#
# Project: https://github.com/SublimeLinter/SublimeLinter3
# License: MIT
#

"""This module exports the RubyLinter subclass of Linter."""

import re
import shlex

from . import linter, persist, util

CMD_RE = re.compile(r'(?P<gem>.+?)@ruby')


class RubyLinter(linter.Linter):

    """
    This Linter subclass provides ruby-specific functionality.

    Linters that check ruby using gems should inherit from this class.
    By doing so, they automatically get the following features:

    - comment_re is defined correctly for ruby.

    - Support for rbenv and rvm (via rvm-auto-ruby).

    """

    comment_re = r'\s*#'

    @classmethod
    def initialize(cls):
        """Perform class-level initialization."""

        super().initialize()

        if cls.executable_path is not None:
            return

        if not callable(cls.cmd) and cls.cmd:
            cls.executable_path = cls.lookup_executables(cls.cmd)
        elif cls.executable:
            cls.executable_path = cls.lookup_executables(cls.executable)

        if not cls.executable_path:
            cls.disabled = True

    @classmethod
    def reinitialize(cls):
        """Perform class-level initialization after plugins have been loaded at startup."""

        # Be sure to clear cls.executable_path so that lookup_executables will run.
        cls.executable_path = None
        cls.initialize()

    @classmethod
    def lookup_executables(cls, cmd):
        """
        Attempt to locate the gem and ruby specified in cmd, return new cmd.

        The following forms are valid:

        gem@ruby
        gem
        ruby

        """

        # See if rvm-auto-ruby is installed. If so use that,
        # otherwise using ruby will work with rbenv as well.
        ruby = util.which('rvm-auto-ruby')

        if not ruby:
            ruby = util.which('ruby')

        if not ruby:
            persist.printf(
                'WARNING: {} deactivated, cannot locate ruby (or rvm-auto-ruby)'
                .format(cls.name, cmd[0])
            )
            return []

        if isinstance(cmd, str):
            cmd = shlex.split(cmd)

        ruby_cmd = [ruby]
        match = CMD_RE.match(cmd[0])

        if match:
            gem = match.group('gem')
        elif cmd[0] != 'ruby':
            gem = cmd[0]
        else:
            gem = ''

        if gem:
            gem_path = util.which(gem)

            if not gem_path:
                persist.printf(
                    'WARNING: {} deactivated, cannot locate the gem \'{}\''
                    .format(cls.name, gem)
                )
                return []

            ruby_cmd.append(gem_path)

        if cls.env is None:
            gem_home = util.get_environment_variable('GEM_HOME')

            if gem_home:
                cls.env = {'GEM_HOME': gem_home}
            else:
                cls.env = {}

        return ruby_cmd
