#
# linter.py
# Part of SublimeLinter3, a code checking framework for Sublime Text 3
#
# Written by Ryan Hileman and Aparajita Fishman
#
# Project: https://github.com/SublimeLinter/SublimeLinter3
# License: MIT
#

from copy import deepcopy
from fnmatch import fnmatch
from numbers import Number
import re
import shlex
import sublime

from . import highlight as hilite, persist, util

ARG_RE = re.compile(r'(?P<prefix>--?)(?P<name>\w[\w\-]*)(?:(?P<joiner>[=:])(?:(?P<sep>.)(?P<multiple>\+)?)?)?')
WARNING_RE = re.compile(r'^w(?:arn(?:ing)?)?$', re.IGNORECASE)


class Registrar(type):
    '''This metaclass registers the linter when the class is declared.'''
    def __init__(cls, name, bases, attrs):
        if bases:
            if 'word_re' in attrs and isinstance(attrs['word_re'], str):
                setattr(cls, 'word_re', re.compile(cls.word_re))

            if 'tempfile_suffix' in attrs and attrs['tempfile_suffix'][0] != '.':
                setattr(cls, 'tempfile_suffix', '.' + attrs['tempfile_suffix'])

            for attr in ('inline_settings', 'inline_overrides'):
                if attr in attrs and isinstance(attrs[attr], str):
                    setattr(cls, attr, (attrs[attr],))

            # If this class has its own defaults, create an args_map.
            # Otherwise we use the superclass' args_map.
            if 'defaults' in attrs:
                cls.map_args()

            persist.register_linter(cls, name, attrs)

    def map_args(cls):
        '''
        Maps plain setting names to the args that will be passed
        to the linter executable.
        '''
        setattr(cls, 'args_map', {})

        settings = []

        for attr in ('defaults', 'inline_settings', 'inline_overrides'):
            if getattr(cls, attr):
                setattr(cls, attr, deepcopy(getattr(cls, attr)))
                settings.append(getattr(cls, attr))

        # For each list of settings, check if the settings specify an argument.
        # If so, add a mapping between the setting and the argument format,
        # then change the name in the list to the setting name.
        for args in settings:
            for arg in args:
                match = ARG_RE.match(arg)

                if match:
                    name = match.group('name')
                    cls.args_map[name] = match.groupdict()

                    value = args[arg]
                    del args[arg]
                    args[name] = value


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

    # A string, tuple or callable that returns a string, list or tuple, containing the
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

    # Set to True if the linter outputs multiline error messages. When True,
    # regex will be created with the re.MULTILINE flag.
    multiline = False

    # If you want to set flags on the regex other than re.MULTILINE, set this.
    re_flags = 0

    # If the linter executable cannot receive from stdin and requires a temp file,
    # set this attribute to the suffix of the temp file (with or without leading '.').
    tempfile_suffix = None

    # Tab width
    tab_width = 1

    # If you want to limit the linter to specific portions of the source
    # based on a scope selector, set this attribute to the selector. For example,
    # in an html file with embedded php, you would set the selector for a php
    # linter to 'source.php'.
    selector = None

    # If a linter reports a column position, SublimeLinter selects the nearest
    # word at that point. You can customize the regex used to select words
    # by setting this to a pattern string or a compiled regex.
    word_re = None

    # If you want to provide default settings for the linter, set this attribute.
    # If a setting will be passed as an argument to the linter executable,
    # you may specify the format of the argument here and the setting will
    # automatically be passed as an argument to the executable. The format
    # specification is as follows:
    #
    # <prefix><name><suffix>
    #
    # - <prefix>: Either '-' or '--'.
    # - <name>: The name of the setting.
    # - <suffix>: Optional. If not present, the setting is boolean,
    #   and if the value is true, the argument is passed. If <suffix> is present,
    #   it has the following structure:
    #
    #   <joiner>[<sep>[+]]
    #
    #   - <joiner>: Either '=' or ':'. If '=', the setting value is joined
    #     with <name> by '=' and passed as a single argument. If ':', <name>
    #     and the value are passed as separate arguments.
    #   - <sep>: If the argument accepts a list of values, <sep> specifies
    #     the character used to delimit the list (usually ',').
    #   - +: If the setting can be a list of values, but each value must be
    #     passed as a separate argument, terminate the setting with '+'.
    #
    # After the format is parsed, the prefix and suffix are removed and the
    # setting is replaced with <name>.
    defaults = None

    # Linters may define a list of settings that can be specified inline.
    # As with defaults, you can specify that an inline setting should be passed
    # as an argument by using a prefix and optional suffix. However, if
    # the same setting was already specified as an argument in defaults,
    # you do not need to use the prefix or suffix here.
    #
    # Within a file, the actual inline setting name is '<linter>-setting', where <linter>
    # is the lowercase name of the linter class, excluding an 'Embedded' prefix.
    inline_settings = None

    # Many linters allow a list of options to be specified for a single setting.
    # For example, you can often specify a list of errors to ignore.
    # This attribute is like inline_settings, but inline values will override
    # existing values instead of replacing them, using the override_options method.
    inline_overrides = None

    # If the linter supports inline settings, you need to specify the regex that
    # begins a comment. comment_re should be an unanchored pattern (no ^)
    # that matches everything through the comment prefix, including leading whitespace.
    #
    # For example, to specify JavaScript comments, you would use the pattern:
    #    r'\s*/[/*]'
    # and for python:
    #    r'\s*#'
    comment_re = None

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
        self.code = ''
        self.linter_settings = None

        if self.regex:
            if self.multiline:
                self.re_flags |= re.MULTILINE

            try:
                self.regex = re.compile(self.regex, self.re_flags)
            except:
                persist.debug('error compiling regex for {}'.format(self.language))

        self.highlight = hilite.Highlight()

        if isinstance(self.comment_re, str):
            self.__class__.comment_re = re.compile(self.comment_re)

    @classmethod
    def get_settings(cls):
        '''Return the default settings for this linter, merged with the user settings.'''
        linters = persist.settings.get('linters', {})
        settings = (cls.defaults or {}).copy()
        settings.update(linters.get(cls.name, {}))
        return settings

    @property
    def settings(cls):
        return cls.lint_settings

    def get_view_settings(self, no_inline=False):
        data = self.view.window().project_data().get(persist.PLUGIN_NAME, {})
        project_settings = data.get('linters', {}).get(self.name, {})
        settings = self.merge_project_settings(self.lint_settings.copy(), project_settings)

        # If the linter has a comment_re set, it supports inline settings.
        if not no_inline and self.comment_re and (self.inline_settings or self.inline_overrides):
            inline_settings = util.inline_settings(
                self.comment_re,
                self.code,
                self.name
            )
            settings = self.merge_inline_settings(settings.copy(), inline_settings)

        return settings

    def merge_inline_settings(self, view_settings, inline_settings):
        '''
        Merges view_settings with settings in inline_settings specified by
        the class attributes inline_settings and inline_overrides.
        '''
        for setting, value in inline_settings.items():
            if setting in self.inline_settings:
                view_settings[setting] = value
            elif setting in self.inline_overrides:
                view_settings[setting] = self.override_options(view_settings[setting] or (), value)

        return view_settings

    def merge_project_settings(self, view_settings, project_settings):
        '''
        Merge this linter's view settings with the current project settings.
        Subclasses may override this if they wish to do something more than
        replace view settings with inline settings of the same name.
        The settings object may be changed in place.
        '''
        view_settings.update(project_settings)
        return view_settings

    def override_options(self, options, overrides, sep=','):
        '''
        If you want inline settings to override but not replace view settings,
        this method makes it easier. Given a set or sequence of options and some
        overrides, this method will do the following:

        - Copies options into a set.
        - Split overrides into a list if it's a string, using sep to split.
        - Iterates over each value in the overrides list:
            - If it begins with '+', the value (without '+') is added to the options set.
            - If it begins with '-', the value (without '-') is removed from the options set.
            - Otherwise the value is added to the options set.
        - The options set is converted to a list and returned.

        For example, given the options ['E101', 'E501', 'W'] and the overrides
        '-E101;E202;-W;+W324', we would end up with ['E501', 'E202', 'W324'].
        '''
        modified_options = set(options)

        if isinstance(overrides, str):
            overrides = overrides.split(sep)

        for override in overrides:
            if not override:
                continue
            elif override[0] == '+':
                modified_options.add(override[1:])
            elif override[0] == '-':
                modified_options.discard(override[1:])
            else:
                modified_options.add(override)

        return list(modified_options)

    @classmethod
    def assign(cls, view, reassign=False):
        '''
        Assign a view to an instance of a linter.
        Find a linter for a specified view if possible, then add it
        to our view <--> lint class map and return it.
        Each view has its own linter so that linters can store persistent data about a view.
        '''
        vid = view.id()
        persist.views[vid] = view
        syntax = persist.syntax(view)

        if not syntax:
            cls.remove(vid)
            return

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

        if linters:
            persist.linters[vid] = linters
        elif reassign and not linters and vid in persist.linters:
            del persist.linters[vid]

        return linters

    @classmethod
    def remove(cls, vid):
        '''Remove a the mapping between a view and its set of linters.'''
        if vid in persist.linters:
            for linters in persist.linters[vid]:
                linters.clear()

            del persist.linters[vid]

    @classmethod
    def reload(cls):
        '''Reload all linters.'''

        # Merge linter default settings with user settings
        for name, linter in persist.languages.items():
            if not name.startswith('embedded'):
                linter.lint_settings = linter.get_settings()

        for vid, linters in persist.linters.items():
            for linter in linters:
                linter.clear()
                persist.linters[vid].remove(linter)
                linter_class = persist.languages[linter.name]
                linter = linter_class(linter.view, linter.syntax, linter.filename)
                persist.linters[vid].add(linter)

    @classmethod
    def apply_to_all(cls, action):
        def apply(view):
            highlights = persist.highlights.get(view.id())

            if highlights:
                getattr(highlights, action)(view)

        util.apply_to_all_views(apply)

    @classmethod
    def clear_all(cls):
        cls.apply_to_all('reset')
        persist.errors.clear()

    @classmethod
    def redraw_all(cls):
        cls.apply_to_all('redraw')

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

        linters = persist.linters.get(vid)

        if not linters:
            return

        disabled = set()

        for linter in linters:
            view_settings = linter.get_view_settings(no_inline=True)

            if view_settings.get('@disable'):
                disabled.add(linter)
                continue

            if filename:
                excludes = view_settings.get('excludes')

                if excludes:
                    if isinstance(excludes, str):
                        excludes = (excludes,)

                    matched = False

                    for pattern in excludes:
                        if fnmatch(filename, pattern):
                            persist.debug(
                                '{} skipped \'{}\', excluded by \'{}\''
                                .format(linter.name, filename, pattern)
                            )
                            matched = True
                            break

                    if matched:
                        disabled.add(linter)
                        continue

            if not linter.selector:
                linter.reset(code, filename=filename or 'untitled')
                linter.lint()

        selectors = Linter.get_selectors(vid)

        for sel, linter in selectors:
            if linter in disabled:
                continue

            linters.add(linter)

            if sel in sections:
                linter.reset(code, filename=filename or 'untitled')
                errors = {}

                for line_offset, start, end in sections[sel]:
                    linter.highlight.move_to(line_offset, start)
                    linter.code = code[start:end]
                    linter.errors = {}
                    linter.lint()

                    for line, line_errors in linter.errors.items():
                        errors[line + line_offset] = line_errors

                linter.errors = errors

        # Remove disabled linters
        linters = list(linters - disabled)

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

            if isinstance(cmd, str):
                cmd = shlex.split(cmd)

            return cmd
        elif self.cmd is not None:
            return self.build_cmd()

        return None

    def build_cmd(self):
        # First we get merged settings: default, user, project and inline
        settings = self.get_view_settings()

        # Now map settings to args
        args = self.build_args(settings)
        cmd = self.cmd

        if isinstance(cmd, str):
            cmd = [cmd]
        else:
            cmd = list(cmd)

        if '*' in cmd:
            i = cmd.index('*')

            if args:
                cmd = cmd[0:i] + args + cmd[i + 1:]
            else:
                cmd.pop(i)
        else:
            cmd += args

        if persist.settings.get('debug'):
            persist.printf('{}: {}'.format(self.__class__.__name__, repr(cmd)))

        return tuple(cmd)

    def build_args(self, settings):
        # Build a list of args to add to the cmd, starting with any
        # args specified by the user in the "args" setting.
        args = settings.get('args', [])

        if isinstance(args, str):
            args = [args]
        else:
            args = [] + args

        args_map = getattr(self, 'args_map', {})

        for setting, arg_info in args_map.items():
            if setting not in settings:
                continue

            options = settings[setting]

            if options is None:
                continue
            elif isinstance(options, (list, tuple)):
                if options:
                    if arg_info['sep'] and not arg_info['multiple']:
                        options = [arg_info['sep'].join(options)]
                else:
                    continue
            elif isinstance(options, str):
                if options:
                    options = [options]
                else:
                    continue
            elif isinstance(options, Number):
                if options is False:
                    continue
                else:
                    options = [options]
            else:
                # Unknown type
                continue

            for option in options:
                arg = arg_info['prefix'] + arg_info['name']
                joiner = arg_info['joiner']

                if joiner == '=':
                    args.append('{}={}'.format(arg, option))
                elif joiner == ':':
                    args.append(arg)
                    args.append(str(option))
                elif not joiner and option is True:
                    args.append(arg)

        return args

    def lint(self):
        if not (self.language and (self.cmd or self.cmd is None) and self.regex):
            raise NotImplementedError

        cmd = self.get_cmd()

        if cmd is not None and not cmd:
            return

        output = self.run(cmd, self.code)

        if not output:
            return

        if persist.settings.get('debug'):
            persist.printf('{} output:\n{}'.format(self.__class__.__name__, output.strip()))

        for match, row, col, error_type, message, near in self.find_errors(output):
            if match and row is not None:
                if error_type and WARNING_RE.match(error_type) is not None:
                    error_type = hilite.WARNING
                else:
                    error_type = hilite.ERROR

                if col is not None:
                    # Pin the column to the line's length
                    start, end = self.highlight.full_line(row)
                    col = min(col, (end - start) - 1)

                    # Adjust column numbers to match the linter's tabs if necessary
                    if self.tab_width > 1:
                        code_line = self.code[start:end]
                        diff = 0

                        for i in range(len(code_line)):
                            if code_line[i] == '\t':
                                diff += (self.tab_width - 1)

                            if col - diff <= i:
                                col = i
                                break

                    self.highlight.range(row, col, error_type=error_type, word_re=self.word_re)
                elif near:
                    col = self.highlight.near(row, near, error_type=error_type, word_re=self.word_re)
                else:
                    self.highlight.range(row, 0, length=0, error_type=error_type, word_re=self.word_re)

                self.error(row, col, message, error_type)

    def draw(self):
        self.highlight.draw(self.view)

    @staticmethod
    def clear_view(view):
        view.erase_status('sublimelinter')
        hilite.Highlight.clear(view)

        if view.id() in persist.errors:
            del persist.errors[view.id()]

    def clear(self):
        self.clear_view(self.view)

    # Helper methods

    @classmethod
    def can_lint(cls, language):
        can = False
        language = language.lower()

        if cls.language:
            if isinstance(cls.language, (tuple, list)) and language in cls.language:
                can = True
            elif language == cls.language:
                can = True

        if can and cls.executable_path is None:
            executable = ''

            if not callable(cls.cmd):
                if isinstance(cls.cmd, (tuple, list)):
                    executable = (cls.cmd or [''])[0]
                elif isinstance(cls.cmd, str):
                    executable = cls.cmd

            if not executable and cls.executable:
                executable = cls.executable

            if executable:
                cls.executable_path = util.which(executable) or ''
            elif cls.cmd is None:
                cls.executable_path = '<builtin>'
            else:
                cls.executable_path = ''

            can = cls.can_lint_language(language)

            persist.printf('{} {}'.format(
                cls.__name__,
                'enabled ({})'.format(cls.executable_path) if can
                else 'disabled, cannot locate \'{}\''.format(executable)
            ))

        return can

    @classmethod
    def can_lint_language(cls, language):
        '''
        Subclass hook to determine if a linter can lint a given language.
        Subclasses may override this if the built in mechanism is not sufficient.
        When this is called, cls.executable_path has been set. If it is '',
        that means the executable was not specified or could not be found.
        '''
        return cls.executable_path != ''

    def error(self, line, col, error, error_type):
        self.highlight.line(line, error_type)

        # Capitalize the first word
        error = error[0].upper() + error[1:]

        # Strip trailing space and period
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
            items = {'line': None, 'col': None, 'type': None, 'error': '', 'near': None}
            items.update(match.groupdict())
            row, col, error_type, error, near = [
                items[k] for k in ('line', 'col', 'type', 'error', 'near')
            ]

            if row is not None:
                row = int(row) - 1

            if col is not None:
                if col.isdigit():
                    col = int(col) - 1
                else:
                    col = len(col)

            return match, row, col, error_type, error, near
        else:
            return match, None, None, None, '', None

    def match_error(self, r, line):
        return self.split_match(r.match(line))

    # Subclasses may need to override this in complex cases
    def run(self, cmd, code):
        if self.tempfile_suffix:
            return self.tmpfile(cmd, code, suffix=self.tempfile_suffix)
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
