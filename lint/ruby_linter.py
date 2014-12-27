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

import os
import re
import shlex
import sublime

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
        Attempt to locate the gem and ruby specified in cmd, return new cmd list.

        The following forms are valid:

        gem@ruby
        gem
        ruby

        If rbenv is installed and the gem is also under rbenv control,
        the gem will be executed directly. Otherwise [ruby <, gem>] will
        be returned.

        If rvm-auto-ruby is installed, [rvm-auto-ruby <, gem>] will be
        returned.

        Otherwise [ruby] or [gem] will be returned.

        """

        ruby = None
        rbenv = util.which('rbenv')

        if not rbenv:
            ruby = util.which('rvm-auto-ruby')

        if not ruby:
            ruby = util.which('ruby')

        if not rbenv and not ruby:
            persist.printf(
                'WARNING: {} deactivated, cannot locate ruby, rbenv or rvm-auto-ruby'
                .format(cls.name, cmd[0])
            )
            return []

        if isinstance(cmd, str):
            cmd = shlex.split(cmd)

        match = CMD_RE.match(cmd[0])

        if match:
            gem = match.group('gem')
        elif cmd[0] != 'ruby':
            gem = cmd[0]
        else:
            gem = ''

        if gem:
            gem_path = util.which(gem)

            if gem_path:
                if (rbenv and
                    ('{0}.rbenv{0}shims{0}'.format(os.sep) in gem_path or
                     (os.altsep and '{0}.rbenv{0}shims{0}'.format(os.altsep in gem_path)))):
                    ruby_cmd = [gem_path]
                elif (sublime.platform() == 'windows'):
                    ruby_cmd = [gem_path]
                else:
                    ruby_cmd = [ruby, gem_path]
            else:
                persist.printf(
                    'WARNING: {} deactivated, cannot locate the gem \'{}\''
                    .format(cls.name, gem)
                )
                return []
        else:
            ruby_cmd = [ruby]

        if cls.env is None:
            # Don't use GEM_HOME with rbenv, it prevents it from using gem shims
            if rbenv:
                cls.env = {}
            else:
                gem_home = util.get_environment_variable('GEM_HOME')

                if gem_home:
                    cls.env = {'GEM_HOME': gem_home}
                else:
                    cls.env = {}

        return ruby_cmd
