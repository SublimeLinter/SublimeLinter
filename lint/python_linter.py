#
# python_linter.py
# Part of SublimeLinter3, a code checking framework for Sublime Text 3
#
# Written by Aparajita Fishman
#
# Project: https://github.com/SublimeLinter/SublimeLinter3
# License: MIT
#

"""This module exports the PythonLinter subclass of Linter."""

import importlib
import os
import re

from . import linter, persist, util


class PythonLinter(linter.Linter):

    """
    This Linter subclass provides python-specific functionality.

    Linters that check python should inherit from this class.
    By doing so, they automatically get the following features:

    - comment_re is defined correctly for python.

    - A python shebang is returned as the @python:<version> meta setting.

    - Execution directly via a module method or via an executable.

    If the module attribute is defined and is successfully imported,
    whether it is used depends on the following algorithm:

      - If the cmd attribute specifies @python and ST's python
        satisfies that version, the module will be used. Note that this
        check is done during class construction.

      - If the check_version attribute is False, the module will be used
        because the module is not version-sensitive.

      - If the "@python" setting is set and ST's python satisfies
        that version, the module will be used.

      - Otherwise the executable will be used with the python specified
        in the "@python" setting, the cmd attribute, or the default system
        python.

    """

    SHEBANG_RE = re.compile(r'\s*#!(?:(?:/[^/]+)*[/ ])?python(?P<version>\d(?:\.\d)?)')

    comment_re = r'\s*#'

    # If the linter wants to import a module and run a method directly,
    # it should set this attribute to the module name, suitable for passing
    # to importlib.import_module. During class construction, the named module
    # will be imported, and if successful, the attribute will be replaced
    # with the imported module.
    module = None

    # Some python-based linters are version-sensitive, i.e. the python version
    # they are run with has to match the version of the code they lint.
    # If a linter is version-sensitive, this attribute should be set to True.
    check_version = False

    @staticmethod
    def match_shebang(code):
        """Convert and return a python shebang as a @python:<version> setting."""

        match = PythonLinter.SHEBANG_RE.match(code)

        if match:
            return '@python', match.group('version')
        else:
            return None

    shebang_match = match_shebang

    @classmethod
    def initialize(cls):
        """Perform class-level initialization."""

        super().initialize()
        persist.import_sys_path()
        cls.import_module()

    @classmethod
    def reinitialize(cls):
        """Perform class-level initialization after plugins have been loaded at startup."""

        # Be sure to clear _cmd so that import_module will re-import.
        if hasattr(cls, '_cmd'):
            delattr(cls, '_cmd')

        cls.initialize()

    @classmethod
    def import_module(cls):
        """
        Attempt to import the configured module.

        If it could not be imported, use the executable.

        """

        if hasattr(cls, '_cmd'):
            return

        module = getattr(cls, 'module', None)
        cls._cmd = None
        cmd = cls.cmd
        script = None

        if isinstance(cls.cmd, (list, tuple)):
            cmd = cls.cmd[0]

        if module is not None:
            try:
                module = importlib.import_module(module)
                persist.debug('{} imported {}'.format(cls.name, module))

                # If the linter specifies a python version, check to see
                # if ST's python satisfies that version.
                if cmd and not callable(cmd):
                    match = util.PYTHON_CMD_RE.match(cmd)

                    if match and match.group('version'):
                        version, script = match.group('version', 'script')
                        version = util.find_python(version=version, script=script, module=module)

                        # If we cannot find a python or script of the right version,
                        # we cannot use the module.
                        if version[0] is None or script and version[1] is None:
                            module = None

            except ImportError:
                message = '{}import of {} module in {} failed'

                if cls.check_version:
                    warning = 'WARNING: '
                    message += ', linter will not work with python 3 code'
                else:
                    warning = ''
                    message += ', linter will not run using built in python'

                persist.printf(message.format(warning, module, cls.name))
                module = None

            except Exception as ex:
                persist.printf(
                    'ERROR: unknown exception in {}: {}'
                    .format(cls.name, str(ex))
                )
                module = None

        # If no module was specified, or the module could not be imported,
        # or ST's python does not satisfy the version specified, see if
        # any version of python available satisfies the linter. If not,
        # set the cmd to '' to disable the linter.
        can_lint = True

        if not module and cmd and not callable(cmd):
            match = util.PYTHON_CMD_RE.match(cmd)

            if match and match.group('version'):
                can_lint = False
                version, script = match.group('version', 'script')
                version = util.find_python(version=version, script=script)

                if version[0] is not None and (not script or version[1] is not None):
                    can_lint = True

        if can_lint:
            cls._cmd = cls.cmd

            # If there is a module, setting cmd to None tells us to
            # use the check method.
            if module:
                cls.cmd = None
        else:
            persist.printf(
                'WARNING: {} deactivated, no available version of python{} satisfies {}'
                .format(
                    cls.name,
                    ' or {}'.format(script) if script else '',
                    cmd
                ))

            cls.disabled = True

        cls.module = module

    def context_sensitive_executable_path(self, cmd):
        """
        Calculate the context-sensitive executable path, using @python and check_version.

        Return a tuple of (have_path, path).

        Return have_path == False if not self.check_version.
        Return have_path == True if cmd is in [script]@python[version] form.
        Return None for path if the desired version of python/script cannot be found.
        Return '<builtin>' for path if the built-in python should be used.

        """

        if not self.check_version:
            return False, None

        # Check to see if we have a @python command
        match = util.PYTHON_CMD_RE.match(cmd[0])

        if match:
            settings = self.get_view_settings()

            if '@python' in settings:
                script = match.group('script') or ''
                which = '{}@python{}'.format(script, settings.get('@python'))
                path = self.which(which)

                if path:
                    if path[0] == '<builtin>':
                        return True, '<builtin>'
                    elif path[0] is None:
                        return True, None

                return True, path

        return False, None

    @classmethod
    def get_module_version(cls):
        """
        Return the string version of the imported module, without any prefix/suffix.

        This method handles the common case where a module (or one of its parents)
        defines a __version__ string. For other cases, subclasses should override
        this method and return the version string.

        """

        if cls.module:
            module = cls.module

            while True:
                if isinstance(getattr(module, '__version__', None), str):
                    return module.__version__

                if hasattr(module, '__package__'):
                    try:
                        module = importlib.import_module(module.__package__)
                    except ImportError:
                        return None
        else:
            return None

    def run(self, cmd, code):
        """Run the module checker or executable on code and return the output."""
        if self.module is not None:
            use_module = False

            if not self.check_version:
                use_module = True
            else:
                settings = self.get_view_settings()
                version = settings.get('@python')

                if version is None:
                    use_module = cmd is None or cmd[0] == '<builtin>'
                else:
                    version = util.find_python(version=version, module=self.module)
                    use_module = version[0] == '<builtin>'

            if use_module:
                if persist.debug_mode():
                    persist.printf(
                        '{}: {} <builtin>'.format(
                            self.name,
                            os.path.basename(self.filename or '<unsaved>')
                        )
                    )

                try:
                    errors = self.check(code, os.path.basename(self.filename or '<unsaved>'))
                except Exception as err:
                    persist.printf(
                        'ERROR: exception in {}.check: {}'
                        .format(self.name, str(err))
                    )
                    errors = ''

                if isinstance(errors, (tuple, list)):
                    return '\n'.join([str(e) for e in errors])
                else:
                    return errors
            else:
                cmd = self._cmd
        else:
            cmd = self.cmd or self._cmd

        cmd = self.build_cmd(cmd=cmd)

        if cmd:
            return super().run(cmd, code)
        else:
            return ''

    def check(self, code, filename):
        """
        Run a built-in check of code, returning errors.

        Subclasses that provide built in checking must override this method
        and return a string with one more lines per error, an array of strings,
        or an array of objects that can be converted to strings.

        """

        persist.printf(
            '{}: subclasses must override the PythonLinter.check method'
            .format(self.name)
        )

        return ''
