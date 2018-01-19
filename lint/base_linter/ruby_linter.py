"""This module exports the RubyLinter subclass of Linter."""

import os
import re
import shlex
import sublime

from functools import lru_cache

from .. import linter, util

CMD_RE = re.compile(r'(?P<gem>.+?)@ruby')


class RubyLinter(linter.Linter):
    """
    This Linter subclass provides ruby-specific functionality.

    Linters that check ruby using gems should inherit from this class.
    By doing so, they automatically get the following features:

    - Support for rbenv and rvm (via rvm-auto-ruby).

    """

    @classmethod
    @lru_cache(maxsize=None)
    def can_lint(cls, syntax):
        """Determine optimistically if the linter can handle the provided syntax."""
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

    def context_sensitive_executable_path(self, cmd):
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
        # The default implementation will look for a user defined `executable`
        # setting.
        success, executable = super().context_sensitive_executable_path(cmd)
        if success:
            return success, executable

        ruby = None
        rbenv = util.which('rbenv')

        if not rbenv:
            ruby = util.which('rvm-auto-ruby')

        if not ruby:
            ruby = util.which('ruby')

        if not ruby:
            ruby = util.which('jruby')

        if not rbenv and not ruby:
            util.printf(
                'WARNING: {} deactivated, cannot locate ruby, rbenv or rvm-auto-ruby'
                .format(self.name, cmd[0])
            )
            return True, None

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
                elif sublime.platform() == 'windows':
                    ruby_cmd = [gem_path]
                else:
                    ruby_cmd = [ruby, gem_path]
            else:
                util.printf(
                    'WARNING: {} deactivated, cannot locate the gem \'{}\''
                    .format(self.name, gem)
                )
                return True, None
        else:
            ruby_cmd = [ruby]

        # Attention readers! All self mutations can have surprising
        # side-effects for concurrent/async linting.

        # Don't use GEM_HOME with rbenv, it prevents it from using gem shims
        if rbenv:
            self.env = {}
        else:
            gem_home = os.environ.get('GEM_HOME', None)

            if gem_home:
                self.env = {'GEM_HOME': gem_home}
            else:
                self.env = {}

        return True, ruby_cmd
