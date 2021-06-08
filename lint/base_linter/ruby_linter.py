"""This module exports the RubyLinter subclass of Linter."""

import os
import re
import shlex
import sublime

from .. import linter, util


CMD_RE = re.compile(r'(?P<gem>.+?)@ruby')


class RubyLinter(linter.Linter):
    """
    This Linter subclass provides ruby-specific functionality.

    Linters that check ruby using gems should inherit from this class.
    By doing so, they automatically get the following features:

    - Support for rbenv and rvm (via rvm-auto-ruby).

    """

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
            msg = "{} deactivated, cannot locate ruby, rbenv or rvm-auto-ruby".format(self.name)
            self.logger.warning(msg)
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
                msg = '{} deactivated, cannot locate the gem \'{}\''.format(self.name, gem)
                self.logger.warning(msg)
                return True, None
        else:
            ruby_cmd = [ruby]

        return True, ruby_cmd
