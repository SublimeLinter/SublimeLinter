#
# linter.py
# Part of SublimeLinter3, a code checking framework for Sublime Text 3
#
# Written by Ryan Hileman and Aparajita Fishman
#
# Project: https://github.com/SublimeLinter/SublimeLinter3
# License: MIT
#

import re
import shlex
import sublime

from . import highlight as hilite
from . import persist
from . import util

SYNTAX_RE = re.compile(r'/([^/]+)\.tmLanguage$')
WARNING_RE = re.compile(r'^w(?:arn(?:ing)?)?$', re.IGNORECASE)


class Registrar(type):
    '''This metaclass registers the linter when the class is declared.'''
    def __init__(cls, name, bases, attrs):
        if bases:
            persist.register_linter(cls, name, attrs)


class Linter(metaclass=Registrar):
    '''
    The base class for linters. Subclasses must at a minimum define
    the attributes language, cmd, and regex.
    '''

    #
    # Public attributes
    #

    # The name of the linter's language for display purposes.
    # By convention this is all lowercase.
    language = ''

    # A string, tuple or callable that returns a string or tuple, containing the
    # command line arguments used to lint.
    cmd = ''

    # If the name of the executable cannot be determined by the first element of cmd
    # (for example when cmd is a method that dynamically generates the command line arguments),
    # this can be set to the name of the executable used to do linting.
    #
    # Once the executable's name is determined, its existence is checked in the user's path.
    # If it is not available, the linter is disabled.
    executable = None

    # If the executable is available, this is set to the full path of the executable.
    # If the executable is not available, it is set an empty string.
    # Subclasses should consider this read only.
    executable_path = None

    # A regex pattern used to extract information from the linter's executable output.
    regex = ''

    # Set to True if the linter outputs multiple errors or multiline errors. When True,
    # regex will be created with the re.MULTILINE flag.
    multiline = False

    # If you want to set flags on the regex other than re.MULTILINE, set this.
    re_flags = 0

    # If the linter executable cannot receive from stdin and requires a temp file,
    # set this attribute to the suffix of the temp file (including leading '.').
    tempfile_suffix = None

    # Tab width
    tab_width = 1

    # If you want to limit the linter to specific portions of the source
    # based on a scope selector, set this attribute to the selector. For example,
    # in an html file with embedded php, you would set the selector for a php
    # linter to 'source.php'.
    selector = None

    # If you want to provide default settings for the linter, set this attribute.
    defaults = None

    #
    # Internal class storage, do not set
    #
    errors = None
    highlight = None
    lint_settings = None

    def __init__(self, view, syntax, filename=None):
        self.view = view
        self.syntax = syntax
        self.filename = filename

        if self.regex:
            if self.multiline:
                self.re_flags |= re.MULTILINE

            try:
                self.regex = re.compile(self.regex, self.re_flags)
            except:
                persist.debug('error compiling regex for {}'.format(self.language))

        self.highlight = hilite.Highlight()

    @classmethod
    def get_settings(cls):
        '''Return the default settings for this linter, merged with the user settings.'''
        linters = persist.settings.get('linters', {})
        settings = cls.defaults or {}
        settings.update(linters.get(cls.__name__, {}))
        return settings

    @property
    def settings(self):
        return self.get_settings()

    @classmethod
    def assign(cls, view, reassign=False):
        '''
        Assign a view to an instance of a linter.
        Find a linter for a specified view if possible, then add it to our view <--> lint class map and return it.
        Each view has its own linter so that linters can store persistent data about a view.
        '''
        vid = view.id()
        persist.views[vid] = view

        settings = view.settings()
        syntax = settings.get('syntax')

        if not syntax:
            cls.remove(vid)
            return

        match = SYNTAX_RE.search(syntax)

        if match:
            syntax = match.group(1)
        else:
            syntax = ''

        if syntax:
            if vid in persist.linters and persist.linters[vid] and not reassign:
                # If a linter in the set of linters for the given view
                # already handles the view's syntax, we have nothing more to do.
                for linter in tuple(persist.linters[vid]):
                    if linter.syntax == syntax:
                        return

            linters = set()

            for name, linter_class in persist.languages.items():
                if linter_class.can_lint(syntax):
                    linter = linter_class(view, syntax, view.file_name())
                    linters.add(linter)

            persist.linters[vid] = linters
            return linters

        cls.remove(vid)

    @classmethod
    def remove(cls, vid):
        '''Remove a the mapping between a view and its set of linters.'''
        if vid in persist.linters:
            for linters in persist.linters[vid]:
                linters.clear()

            del persist.linters[vid]

    @classmethod
    def reload(cls, mod=None):
        '''Reload all linters, optionally filtering by module.'''

        # Merge linter default settings with user settings
        linter_settings = persist.settings.get('linters', {})

        for name, linter in persist.languages.items():
            settings = linter_settings.get(name, {})
            defaults = (linter.defaults or {}).copy()
            defaults.update(settings)
            linter.lint_settings = defaults

        for vid, linters in persist.linters.items():
            for linter in linters:
                if mod and linter.__module__ != mod:
                    continue

                linter.clear()
                persist.linters[vid].remove(linter)
                linter = persist.languages[linter.name](linter.view, linter.syntax, linter.filename)
                persist.linters[vid].add(linter)
                linter.draw()

    @classmethod
    def text(cls, view):
        '''Returns the entire text of a view.'''
        return view.substr(sublime.Region(0, view.size()))

    @classmethod
    def get_view(cls, vid):
        '''Returns the view object with the given id.'''
        return persist.views.get(vid)

    @classmethod
    def get_linters(cls, vid):
        '''Returns a tuple of linters for the view with the given id.'''
        if vid in persist.linters:
            return tuple(persist.linters[vid])

        return ()

    @classmethod
    def get_selectors(cls, vid):
        '''Returns a list of scope selectors for all linters for the view with the given id.'''
        return [
            (linter.selector, linter)
            for linter in cls.get_linters(vid)
            if linter.selector
        ]

    @classmethod
    def lint_view(cls, vid, filename, code, sections, hit_time, callback):
        if not code or vid not in persist.linters:
            return

        linters = list(persist.linters.get(vid))

        if not linters:
            return

        filename = filename or 'untitled'

        for linter in linters:
            if linter.settings.get('disable'):
                continue

            if not linter.selector:
                linter.reset(code, filename=filename)
                linter.lint()

        selectors = Linter.get_selectors(vid)

        for sel, linter in selectors:
            linters.append(linter)

            if sel in sections:
                linter.reset(code, filename=filename)
                errors = {}

                for line_offset, left, right in sections[sel]:
                    linter.hilite.move_to(line_offset, left)
                    linter.code = code[left:right]
                    linter.errors = {}
                    linter.lint()

                    for line, error in linter.errors.items():
                        errors[line + line_offset] = error

                linter.errors = errors

        # Merge our result back to the main thread
        callback(cls.get_view(vid), linters, hit_time)

    def reset(self, code, filename=None, highlight=None):
        self.errors = {}
        self.code = code
        self.filename = filename or self.filename
        self.highlight = highlight or hilite.Highlight(self.code)

    def get_cmd(self):
        if callable(self.cmd):
            cmd = self.cmd()
        else:
            cmd = self.cmd

        if not cmd:
            return

        if isinstance(cmd, str):
            cmd = shlex.split(cmd)

        return tuple(cmd)

    def lint(self):
        if not (self.language and self.cmd and self.regex):
            raise NotImplementedError

        cmd = self.get_cmd()

        if not cmd:
            return

        output = self.run(cmd, self.code)

        if not output:
            return

        persist.debug('{} output:\n{}'.format(self.__class__.__name__, output.strip()))

        for match, row, col, length, error_type, message, near in self.find_errors(output):
            if match and row is not None:
                if error_type and WARNING_RE.match(error_type) is not None:
                    error_type = hilite.WARNING
                else:
                    error_type = hilite.ERROR

                if col is not None:
                    # Adjust column numbers to match the linter's tabs if necessary
                    if self.tab_width > 1:
                        start, end = self.highlight.full_line(row)
                        code_line = self.code[start:end]
                        diff = 0

                        for i in range(len(code_line)):
                            if code_line[i] == '\t':
                                diff += (self.tab_width - 1)

                            if col - diff <= i:
                                col = i
                                break

                    if length is None:
                        self.highlight.range(row, col, error_type=error_type)
                    else:
                        self.highlight.range(row, col, length=length, error_type=error_type)
                elif near:
                    self.highlight.near(row, near, error_type)
                else:
                    self.highlight.range(row, 0, length=0, error_type=error_type)

                self.error(row, col, message, error_type)

    def draw(self):
        self.highlight.draw(self.view)

    def clear(self):
        self.highlight.clear(self.view)

    # Helper methods

    @classmethod
    def can_lint(cls, language):
        '''
        Determines if a linter can lint a given language. Subclasses may override this
        if the built in mechanism is not sufficient, but should call super().can_list(cls, language)
        first and continue checking only if that returns True.
        '''
        can = False
        language = language.lower()

        if cls.language:
            if language == cls.language:
                can = True
            elif isinstance(cls.language, (tuple, list)) and language in cls.language:
                can = True

        if can and cls.executable_path is None:
            executable = ''

            if not callable(cls.cmd):
                if isinstance(cls.cmd, (tuple, list)):
                    executable = (cls.cmd or [''])[0]
                else:
                    executable = cls.cmd

            if not executable and cls.executable:
                executable = cls.executable

            if executable:
                cls.executable_path = util.which(executable) or ''
            else:
                cls.executable_path = ''

            can = cls.executable_path != ''
            persist.printf('{} {}'.format(
                cls.__name__,
                'enabled ({})'.format(cls.executable_path) if can
                else 'disabled, cannot locate \'{}\''.format(executable)
            ))

        return can

    def error(self, line, col, error, error_type):
        self.highlight.line(line, error_type)
        error = ((col or 0), str(error).rstrip(' .'))

        if line in self.errors:
            self.errors[line].append(error)
        else:
            self.errors[line] = [error]

    def find_errors(self, output):
        if self.multiline:
            errors = self.regex.finditer(output)

            if errors:
                for error in errors:
                    yield self.split_match(error)
            else:
                yield self.split_match(None)
        else:
            for line in output.splitlines():
                yield self.match_error(self.regex, line.strip())

    def split_match(self, match):
        if match:
            items = {'line': None, 'col': None, 'length': None, 'type': None, 'error': '', 'near': None}
            items.update(match.groupdict())
            row, col, length, error_type, error, near = [items[k] for k in ('line', 'col', 'length', 'type', 'error', 'near')]

            if row is not None:
                row = int(row) - 1

            if col is not None:
                col = int(col) - 1

            return match, row, col, length, error_type, error, near
        else:
            return match, None, None, None, None, '', None

    def match_error(self, r, line):
        return self.split_match(r.match(line))

    # Subclasses may need to override this in complex cases
    def run(self, cmd, code):
        if self.tempfile_suffix:
            return self.tmpfile(cmd, suffix=self.tempfile_suffix)
        else:
            return self.communicate(cmd, code)

    # popen wrappers
    def communicate(self, cmd, code):
        return util.communicate(cmd, code)

    def tmpfile(self, cmd, code, suffix=''):
        return util.tmpfile(cmd, code, suffix or self.tempfile_suffix)

    def tmpdir(self, cmd, files, code):
        return util.tmpdir(cmd, files, self.filename, code)

    def popen(self, cmd, env=None):
        return util.popen(cmd, env)
