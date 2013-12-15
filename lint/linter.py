#
# linter.py
# Part of SublimeLinter3, a code checking framework for Sublime Text 3
#
# Written by Ryan Hileman and Aparajita Fishman
#
# Project: https://github.com/SublimeLinter/SublimeLinter3
# License: MIT
#

"""
This module exports linter-related classes.

Registrar       Metaclass for Linter classes that does setup when they are loaded.
Linter          The main base class for linters.
PythonLinter    Linter subclass that provides base python configuration.

"""

from fnmatch import fnmatch
from functools import lru_cache
from numbers import Number
import os
import re
import shlex
import sublime
import traceback

from . import highlight, persist, util

#
# Private constants
#
ARG_RE = re.compile(r'(?P<prefix>--?)?(?P<name>[@\w][\w\-]*)(?:(?P<joiner>[=:])(?:(?P<sep>.)(?P<multiple>\+)?)?)?')
BASE_CLASSES = ('PythonLinter',)


class Registrar(type):

    """Metaclass for Linter and its subclasses."""

    def __init__(self, name, bases, attrs):
        """
        Initialize a Linter class.

        When a Linter subclass is loaded by Sublime Text, this method is called.
        We take this opportunity to do some transformations:

        - Replace regex patterns with compiled regex objects.
        - Convert strings to tuples where necessary.
        - Add a leading dot to the tempfile_suffix if necessary.
        - Build a map between defaults and linter arguments.
        - Add '@python' as an inline setting to PythonLinter subclasses.

        Finally, the class is registered as a linter for its configured syntax.

        """

        if bases:
            cmd = attrs.get('cmd')

            if isinstance(cmd, str):
                setattr(self, 'cmd', shlex.split(cmd))

            if 'word_re' in attrs and isinstance(attrs['word_re'], str):
                setattr(self, 'word_re', re.compile(self.word_re))

            if attrs.get('tempfile_suffix') and attrs['tempfile_suffix'][0] != '.':
                setattr(self, 'tempfile_suffix', '.' + attrs['tempfile_suffix'])

            for attr in ('inline_settings', 'inline_overrides'):
                if attr in attrs and isinstance(attrs[attr], str):
                    setattr(self, attr, (attrs[attr],))

            # If this class has its own defaults, create an args_map.
            # Otherwise we use the superclass' args_map.
            if 'defaults' in attrs and attrs['defaults']:
                self.map_args(attrs['defaults'])

            if 'PythonLinter' in [base.__name__ for base in bases]:
                # Set attributes necessary for the @python inline setting
                inline_settings = list(getattr(self, 'inline_settings') or [])
                setattr(self, 'inline_settings', inline_settings + ['@python'])

            if 'syntax' in attrs and name not in BASE_CLASSES:
                persist.register_linter(self, name, attrs)

    def map_args(self, defaults):
        """
        Map plain setting names to args that will be passed to the linter executable.

        For each item in defaults, the key is matched with ARG_RE. If there is a match,
        the key is stripped of meta information and the match groups are stored as a dict
        under the stripped key.

        """

        # Check if the settings specify an argument.
        # If so, add a mapping between the setting and the argument format,
        # then change the name in the defaults to the setting name.
        args_map = {}
        setattr(self, 'defaults', {})

        for name, value in defaults.items():
            match = ARG_RE.match(name)

            if match:
                name = match.group('name')
                args_map[name] = match.groupdict()

            self.defaults[name] = value

        setattr(self, 'args_map', args_map)


class Linter(metaclass=Registrar):

    """
    The base class for linters.

    Subclasses must at a minimum define the attributes syntax, cmd, and regex.

    """

    #
    # Public attributes
    #

    # The syntax that the linter handles. May be a string or
    # list/tuple of strings. Names should be all lowercase.
    syntax = ''

    # A string, list, tuple or callable that returns a string, list or tuple, containing the
    # command line (with arguments) used to lint.
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

    # A regex pattern used to extract information from the executable's output.
    regex = ''

    # Set to True if the linter outputs multiline error messages. When True,
    # regex will be created with the re.MULTILINE flag. Do NOT rely on setting
    # the re.MULTILINE flag within the regex yourself, this attribute must be set.
    multiline = False

    # If you want to set flags on the regex *other* than re.MULTILINE, set this.
    re_flags = 0

    # The default type assigned to non-classified errors. Should be either
    # highlight.ERROR or highlight.WARNING.
    default_type = highlight.ERROR

    # Linters usually report errors with a line number, some with a column number
    # as well. In general, most linters report one-based line numbers and column
    # numbers. If a linter uses zero-based line numbers or column numbers, the
    # linter class should define this attribute accordingly.
    line_col_base = (1, 1)

    # If the linter executable cannot receive from stdin and requires a temp file,
    # set this attribute to the suffix of the temp file (with or without leading '.').
    tempfile_suffix = None

    # Linters may output to both stdout and stderr. You may be interested
    # in one or both.
    error_stream = util.STREAM_STDOUT

    # Tab width
    tab_width = 1

    # If a linter can be used with embedded code, you need to tell SublimeLinter
    # which portions of the source code contain the embedded code by specifying
    # the embedded scope selectors. This attribute maps syntax names
    # to embedded scope selectors.
    #
    # For example, the HTML syntax uses the scope `source.js.embedded.html`
    # for embedded JavaScript. To allow a JavaScript linter to lint that embedded
    # JavaScript, you would set this attribute to {'html': 'source.js.embedded.html'}.
    selectors = {}

    # If a linter reports a column position, SublimeLinter highlights the nearest
    # word at that point. You can customize the regex used to highlight words
    # by setting this to a pattern string or a compiled regex.
    word_re = None

    # If you want to provide default settings for the linter, set this attribute.
    # If a setting will be passed as an argument to the linter executable,
    # you may specify the format of the argument here and the setting will
    # automatically be passed as an argument to the executable. The format
    # specification is as follows:
    #
    # <prefix><name><joiner>[<sep>[+]]
    #
    # - <prefix>: Either '-' or '--'.
    # - <name>: The name of the setting.
    # - <joiner>: Either '=' or ':'. If '=', the setting value is joined
    #   with <name> by '=' and passed as a single argument. If ':', <name>
    #   and the value are passed as separate arguments.
    # - <sep>: If the argument accepts a list of values, <sep> specifies
    #   the character used to delimit the list (usually ',').
    # - +: If the setting can be a list of values, but each value must be
    #   passed as a separate argument, terminate the setting with '+'.
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
    # is the lowercase name of the linter class.
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

    # Some linters may want to turn a shebang into an inline setting.
    # To do so, set this attribute to a callback which receives the first line
    # of code and returns a tuple/list which contains the name and value for the
    # inline setting, or None if there is no match.
    shebang_match = None

    #
    # Internal class storage, do not set
    #
    RC_SEARCH_LIMIT = 3
    errors = None
    highlight = None
    lint_settings = None

    def __init__(self, view, syntax, filename=None):
        self.view = view
        self.syntax = syntax
        self.filename = filename
        self.code = ''

        if self.regex:
            if self.multiline:
                self.re_flags |= re.MULTILINE

            try:
                self.regex = re.compile(self.regex, self.re_flags)
            except re.error:
                persist.debug('error compiling regex for {}'.format(self.syntax))

        self.highlight = highlight.Highlight()

        if isinstance(self.comment_re, str):
            self.__class__.comment_re = re.compile(self.comment_re)

    @classmethod
    def settings(cls):
        """Return the default settings for this linter, merged with the user settings."""

        if cls.lint_settings is None:
            linters = persist.settings.get('linters', {})
            cls.lint_settings = (cls.defaults or {}).copy()
            cls.lint_settings.update(linters.get(cls.name, {}))

        return cls.lint_settings

    @staticmethod
    def meta_settings(settings):
        """Return a dict with the items in settings whose keys begin with '@'."""
        return {key: value for key, value in settings.items() if key.startswith('@')}

    @lru_cache(maxsize=None)
    def get_view_settings(self, no_inline=False):
        """
        Return a union of all settings specific to this linter, related to the given view.

        The settings are merged in the following order:

        default settings
        user settings
        project settings
        user + project meta settings
        rc settings
        rc meta settings
        shebang or inline settings (overrides)

        """

        # Start with the overall project settings
        data = self.view.window().project_data() or {}
        project_settings = data.get(persist.PLUGIN_NAME, {})

        # Merge global meta settings with project meta settings
        meta = self.meta_settings(persist.settings.settings)
        meta.update(self.meta_settings(project_settings))

        # Get the linter's project settings, update them with meta settings
        project_settings = project_settings.get('linters', {}).get(self.name, {})
        project_settings.update(meta)

        # Update the linter's settings with the project settings
        settings = self.merge_project_settings(self.settings().copy(), project_settings)

        # Update with rc settings
        self.merge_rc_settings(settings)

        if not no_inline:
            inline_settings = {}

            if self.shebang_match:
                eol = self.code.find('\n')

                if eol != -1:
                    setting = self.shebang_match(self.code[0:eol])

                    if setting is not None:
                        inline_settings[setting[0]] = setting[1]

            if self.comment_re and (self.inline_settings or self.inline_overrides):
                inline_settings.update(util.inline_settings(
                    self.comment_re,
                    self.code,
                    self.name
                ))

            settings = self.merge_inline_settings(settings.copy(), inline_settings)

        return settings

    def merge_rc_settings(self, settings):
        """
        Merge .sublimelinterrc settings with settings.

        Searches for .sublimelinterrc in, starting at the directory of the linter's view.
        The search is limited to rc_search_limit directories. If found, the meta settings
        and settings for this linter in the rc file are merged with settings.

        """

        search_limit = persist.settings.get('rc_search_limit', self.RC_SEARCH_LIMIT)
        rc_settings = util.get_view_rc_settings(self.view, limit=search_limit)

        if rc_settings:
            meta = self.meta_settings(rc_settings)
            rc_settings = rc_settings.get('linters', {}).get(self.name, {})
            rc_settings.update(meta)
            settings.update(rc_settings)

    def merge_inline_settings(self, view_settings, inline_settings):
        """
        Return view settings merged with inline settings.

        view_settings is merged with inline_settings specified by
        the class attributes inline_settings and inline_overrides.
        view_settings is updated in place and returned.

        """

        for setting, value in inline_settings.items():
            if self.inline_settings and setting in self.inline_settings:
                view_settings[setting] = value
            elif self.inline_overrides and setting in self.inline_overrides:
                options = view_settings[setting]
                sep = self.args_map.get(setting, {}).get('sep')

                if sep:
                    kwargs = {'sep': sep}
                    options = options or ''
                else:
                    kwargs = {}
                    options = options or ()

                view_settings[setting] = self.override_options(options, value, **kwargs)

        return view_settings

    def merge_project_settings(self, view_settings, project_settings):
        """
        Return this linter's view settings merged with the current project settings.

        Subclasses may override this if they wish to do something more than
        replace view settings with inline settings of the same name.
        The settings object may be changed in place.

        """
        view_settings.update(project_settings)
        return view_settings

    def override_options(self, options, overrides, sep=','):
        """
        Return a list of options with overrides applied.

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

        For example, given the options 'E101,E501,W' and the overrides
        '-E101,E202,-W,+W324', we would end up with 'E501,E202,W324'.

        """

        if isinstance(options, str):
            options = options.split(sep) if options else ()
            return_str = True
        else:
            return_str = False

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

        if return_str:
            return sep.join(modified_options)
        else:
            return list(modified_options)

    @classmethod
    def assign(cls, view, linter_name=None, reset=False):
        """
        Assign linters to a view.

        If reset is True, the list of linters for view is completely rebuilt.

        can_lint for each known linter class is called to determine
        if the linter class can lint the syntax for view. If so, a new instance
        of the linter class is assigned to the view, unless linter_name is non-empty
        and does not match the 'name' attribute of any of the view's linters.

        Each view has its own linters so that linters can store persistent data
        about a view.

        """

        vid = view.id()
        persist.views[vid] = view
        syntax = persist.get_syntax(view)

        if not syntax:
            cls.remove(vid)
            return

        view_linters = persist.view_linters.get(vid, set())
        linters = set()

        for name, linter_class in persist.linter_classes.items():
            if linter_class.can_lint(syntax):

                if reset:
                    instantiate = True
                else:
                    linter = None

                    for l in view_linters:
                        if name == l.name:
                            linter = l
                            break

                    if linter is None:
                        instantiate = True
                    else:
                        # If there is an existing linter and no linter_name was passed,
                        # leave it. If linter_name was passed, re-instantiate only if
                        # the linter's name matches linter_name.
                        instantiate = linter_name == linter.name

                if instantiate:
                    linter = linter_class(view, syntax, view.file_name())

                linters.add(linter)

        if linters:
            persist.view_linters[vid] = linters
        elif reset and not linters and vid in persist.view_linters:
            del persist.view_linters[vid]

    @classmethod
    def remove(cls, vid):
        """Remove a the mapping between a view and its set of linters."""

        if vid in persist.view_linters:
            for linters in persist.view_linters[vid]:
                linters.clear()

            del persist.view_linters[vid]

    @classmethod
    def reload(cls):
        """Assign new instances of linters to views."""

        # Merge linter default settings with user settings
        for name, linter in persist.linter_classes.items():
            linter.lint_settings = None

        for vid, linters in persist.view_linters.items():
            for linter in linters:
                linter.clear()
                persist.view_linters[vid].remove(linter)
                linter_class = persist.linter_classes[linter.name]
                linter = linter_class(linter.view, linter.syntax, linter.filename)
                persist.view_linters[vid].add(linter)

    @classmethod
    def apply_to_all_highlights(cls, action):
        """Apply an action to the highlights of all views."""

        def apply(view):
            highlights = persist.highlights.get(view.id())

            if highlights:
                getattr(highlights, action)(view)

        util.apply_to_all_views(apply)

    @classmethod
    def clear_all(cls):
        """Clear highlights and errors in all views."""
        cls.apply_to_all_highlights('reset')
        persist.errors.clear()

    @classmethod
    def redraw_all(cls):
        """Redraw all highlights in all views."""
        cls.apply_to_all_highlights('redraw')

    @classmethod
    def text(cls, view):
        """Return the entire text of a view."""
        return view.substr(sublime.Region(0, view.size()))

    @classmethod
    def get_view(cls, vid):
        """Return the view object with the given id."""
        return persist.views.get(vid)

    @classmethod
    def get_linters(cls, vid):
        """Return a tuple of linters for the view with the given id."""
        if vid in persist.view_linters:
            return tuple(persist.view_linters[vid])

        return ()

    @classmethod
    def get_selectors(cls, vid, syntax=None):
        """
        Return scope selectors and linters for the view with the given id.

        For each linter assigned to the view with the given id, if it
        has selectors, return a tuple of the selector and the linter.

        """
        view = persist.views[vid]

        if not syntax:
            syntax = persist.get_syntax(view)

        return [
            (linter.selectors[syntax], linter)
            for linter in cls.get_linters(vid)
            if syntax in linter.selectors
        ]

    @classmethod
    def lint_view(cls, vid, filename, code, sections, hit_time, callback):
        """
        Lint the view with the given view id.

        This is the top level lint dispatcher. It is called
        asynchronously. The following checks are done for each linter
        assigned to the view:

        - Check if the linter has been disabled in settings.
        - Check if the filename matches any patterns in the "excludes" setting.

        If a linter fails the checks, it is disabled for this run.
        Otherwise, if the mapped syntax is not in the linter's selectors,
        the linter is run on the entirety of code.

        Then the set of selectors for all linters assigned to the view is
        aggregated, and for each selector, if it occurs in sections,
        the corresponding section is linted as embedded code.

        A list of the linters that ran is returned.

        """

        if not code:
            return

        linters = persist.view_linters.get(vid)

        if not linters:
            return

        disabled = set()
        syntax = persist.get_syntax(persist.views[vid])

        for linter in linters:
            # Because get_view_settings is expensive, we use an lru_cache
            # to cache its results. Before each lint, reset the cache.
            linter.get_view_settings.cache_clear()
            view_settings = linter.get_view_settings(no_inline=True)

            if view_settings.get('@disable'):
                disabled.add(linter)
                continue

            if filename:
                filename = os.path.realpath(filename)
                excludes = util.convert_type(view_settings.get('excludes', []), [])

                if excludes:
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

            if syntax not in linter.selectors:
                linter.reset(code, filename=filename or 'untitled')
                linter.lint()

        selectors = Linter.get_selectors(vid, syntax=syntax)

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

    def reset(self, code, filename=None):
        """Reset a linter to work on the given code and filename."""
        self.errors = {}
        self.code = code
        self.filename = filename or self.filename
        self.highlight = highlight.Highlight(self.code)

    @classmethod
    def which(cls, cmd):
        """Call util.which with this class' module and return the result."""
        return util.which(cmd, module=getattr(cls, 'module', None))

    def get_cmd(self):
        """
        Calculate and return a tuple/list of the command line to be executed.

        The cmd class attribute may be a string, a tuple/list, or a callable.
        If cmd is callable, it is called. If the result of the method is
        a string, it is parsed into a list with shlex.split.

        Otherwise the result of build_cmd is returned.

        """
        if callable(self.cmd):
            cmd = self.cmd()

            if isinstance(cmd, str):
                cmd = shlex.split(cmd)

            return cmd
        else:
            return self.build_cmd()

    def build_cmd(self, cmd=None):
        """
        Return a tuple with the command line to execute.

        We start with cmd or the cmd class attribute. If it is a string,
        it is parsed with shlex.split.

        If the first element of the command line matches [script]@python[version],
        and '@python' is in the aggregated view settings, util.which is called
        to determine the path to the script and given version of python. This
        allows settings to override the version of python used.

        Otherwise, if self.executable_path has already been calculated, that
        is used. If not, the executable path is located with util.which.

        If the path to the executable can be determined, a list of extra arguments
        is built with build_args. If the cmd contains '*', it is replaced
        with the extra argument list, otherwise the extra args are appended to
        cmd.

        """

        cmd = cmd or self.cmd

        if isinstance(cmd, str):
            cmd = shlex.split(cmd)
        else:
            cmd = list(cmd)

        which = cmd[0]

        # Check to see if we have a @python command
        match = util.PYTHON_CMD_RE.match(cmd[0])
        settings = self.get_view_settings()

        if match and '@python' in settings:
            script = match.group('script') or ''
            which = '{}@python{}'.format(script, settings.get('@python'))
            path = self.which(which)

            if path:
                # Returning None means the linter runs code internally
                if path[0] == '<builtin>':
                    return None
                elif path[0] is None or script and path[1] is None:
                    path = None
        elif self.executable_path:
            path = self.executable_path

            if isinstance(path, tuple) and None in path:
                path = None
        else:
            path = self.which(which)

        if not path:
            persist.debug('cannot locate \'{}\''.format(which))
            return ''

        cmd[0:1] = util.convert_type(path, [])
        args = self.build_args(settings)

        if '*' in cmd:
            i = cmd.index('*')

            if args:
                cmd[i:i + 1] = args
            else:
                cmd.pop(i)
        else:
            cmd += args

        return tuple(cmd)

    def build_args(self, settings):
        """
        Return a list of args to add to cls.cmd.

        First any args specified in the "args" linter setting are retrieved.
        Then the args map (built by map_args during class construction) is
        iterated. For each item in the args map:

        - Check to see if the arg is in settings, which is the aggregated
          default/user/view settings. If arg is not in settings or is a meta
          setting (beginning with '@'), it is skipped.

        - Get the setting value. If it is None or an empty string/list, skip this arg.

        - If the setting value is a non-empty list and the arg was specified
          as taking a single list of values, join the values.

        - If the setting value is a non-empty string or the boolean True,
          convert it into a single-element list with that value.

        Once a list of values is built, iterate over the values to build
        the args list:

        - Start with the prefix and arg name.
        - If the joiner is '=', join '=' and the value and append to the args.
        - If the joiner is ':', append the arg and value as separate args.

        Return the arg list.

        """

        args = settings.get('args', [])

        if isinstance(args, str):
            args = shlex.split(args)
        else:
            args = args[:]

        args_map = getattr(self, 'args_map', {})

        for setting, arg_info in args_map.items():
            if setting not in settings or setting[0] == '@':
                continue

            values = settings[setting]

            if values is None:
                continue
            elif isinstance(values, (list, tuple)):
                if values:
                    # If the values can be passed as a single list, join them now
                    if arg_info['sep'] and not arg_info['multiple']:
                        values = [arg_info['sep'].join(values)]
                else:
                    continue
            elif isinstance(values, str):
                if values:
                    values = [values]
                else:
                    continue
            elif isinstance(values, Number):
                if values is False:
                    continue
                else:
                    values = [values]
            else:
                # Unknown type
                continue

            for value in values:
                arg = arg_info['prefix'] + arg_info['name']
                joiner = arg_info['joiner']

                if joiner == '=':
                    args.append('{}={}'.format(arg, value))
                elif joiner == ':':
                    args.append(arg)
                    args.append(str(value))

        return args

    def build_options(self, options, type_map, transform=None):
        """
        Build a list of options to be passed directly to a linting method.

        This method is designed for use with linters that do linting directly
        in code and need to pass a dict of options.

        options is the starting dict of options. For each of the settings
        listed in self.args_map:

        - See if the setting name is in view settings.

        - If so, and the value is non-empty, see if the setting
          name is in type_map. If so, convert the value to the type
          of the value in type_map.

        - If transform is not None, pass the name to it and assign to the result.

        - Add the name/value pair to options.

        """

        view_settings = self.get_view_settings()

        for name, info in self.args_map.items():
            value = view_settings.get(name)

            if value:
                value = util.convert_type(value, type_map.get(name), sep=info.get('sep'))

                if value is not None:
                    if transform:
                        name = transform(name)

                    options[name] = value

    def lint(self):
        """
        Perform the lint, retrieve the results, and add marks to the view.

        The flow of control is as follows:

        1. Ensure the linter has the minimum configuration necessary to lint.
        2. Get the command line. If it is an empty string, bail.
        3. Run the linter.
        4. Parse the linter output with the regex.
        5. Highlight warnings and errors.

        """

        if not (self.syntax and (self.cmd or self.cmd is None) and self.regex):
            persist.debug('{}: not implemented'.format(self.name))

        if self.cmd is None:
            cmd = None
        else:
            cmd = self.get_cmd()

            if cmd is not None and not cmd:
                return

        output = self.run(cmd, self.code)

        if not output:
            return

        if persist.settings.get('debug'):
            stripped_output = output.replace('\r', '').rstrip()
            persist.printf('{} output:\n{}'.format(self.name, stripped_output))

        for match, line, col, error, warning, message, near in self.find_errors(output):
            if match and line is not None:
                if error:
                    error_type = highlight.ERROR
                elif warning:
                    error_type = highlight.WARNING
                else:
                    error_type = self.default_type

                if col is not None:
                    # Pin the column to the start/end line offsets
                    start, end = self.highlight.full_line(line)
                    col = max(min(col, (end - start) - 1), 0)

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

                    self.highlight.range(line, col, error_type=error_type, word_re=self.word_re)
                elif near:
                    col = self.highlight.near(line, near, error_type=error_type, word_re=self.word_re)
                else:
                    self.highlight.range(line, 0, length=0, error_type=error_type, word_re=self.word_re)

                self.error(line, col, message, error_type)

    def draw(self):
        """Draw the marks from the last lint."""
        self.highlight.draw(self.view)

    @staticmethod
    def clear_view(view):
        """Clear marks, status and all other cached error info for the given view."""

        view.erase_status('sublimelinter')
        highlight.Highlight.clear(view)

        if view.id() in persist.errors:
            del persist.errors[view.id()]

    def clear(self):
        """Clear marks, status and all other cached error info for the given view."""
        self.clear_view(self.view)

    # Helper methods

    @classmethod
    def can_lint(cls, syntax):
        """
        Determine if a linter class can lint the given syntax.

        This method is called when a view has not had a linter assigned
        or when its syntax changes.

        The following tests must all pass for this method to return True:

        1. syntax must be one of the syntaxes the linter defines.
        2. If the linter uses an external executable, it must be available.
        3. can_lint_syntax must return True.

        """

        can = False
        syntax = syntax.lower()

        if cls.syntax:
            if isinstance(cls.syntax, (tuple, list)) and syntax in cls.syntax:
                can = True
            elif syntax == cls.syntax:
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
                cls.executable_path = cls.which(executable) or ''
            elif cls.cmd is None:
                cls.executable_path = '<builtin>'
            else:
                cls.executable_path = ''

            can = cls.can_lint_syntax(syntax)

            persist.printf('{} {}'.format(
                cls.name,
                'enabled: {}'.format(cls.executable_path) if can
                else 'disabled, cannot locate \'{}\''.format(executable)
            ))

        return can

    @classmethod
    def can_lint_syntax(cls, syntax):
        """
        Return whether a linter can lint a given syntax.

        Subclasses may override this if the built in mechanism in can_lint
        is not sufficient. When this method is called, cls.executable_path
        has been set. If it is '', that means the executable was not specified
        or could not be found.

        """
        return cls.executable_path != ''

    def error(self, line, col, error, error_type):
        """Add a reference to an error/warning on the given line and column."""
        self.highlight.line(line, error_type)

        # Capitalize the first word
        error = error[0].upper() + error[1:]

        # Strip trailing CR, space and period
        error = ((col or 0), str(error).rstrip('\r .'))

        if line in self.errors:
            self.errors[line].append(error)
        else:
            self.errors[line] = [error]

    def find_errors(self, output):
        """
        A generator which matches the linter's regex against the linter output.

        If multiline is True, split_match is called for each non-overlapping
        match of self.regex. If False, split_match is called for each line
        in output.

        """

        if self.multiline:
            errors = self.regex.finditer(output)

            if errors:
                for error in errors:
                    yield self.split_match(error)
            else:
                yield self.split_match(None)
        else:
            for line in output.splitlines():
                yield self.split_match(self.regex.match(line.rstrip()))

    def split_match(self, match):
        """
        Split a match into the standard elements of an error and return them.

        If subclasses need to modify the values returned by the regex, they
        should override this method, call super(), then modify the values
        and return them.

        """

        if match:
            items = {'line': None, 'col': None, 'error': None, 'warning': None, 'message': '', 'near': None}
            items.update(match.groupdict())
            line, col, error, warning, message, near = [
                items[k] for k in ('line', 'col', 'error', 'warning', 'message', 'near')
            ]

            if line is not None:
                line = int(line) - self.line_col_base[0]

            if col is not None:
                if col.isdigit():
                    col = int(col) - self.line_col_base[1]
                else:
                    col = len(col)

            return match, line, col, error, warning, message, near
        else:
            return match, None, None, None, None, '', None

    def run(self, cmd, code):
        """
        Execute the linter's executable or built in code and return its output.

        If a linter uses built in code, it should override this method and return
        a string as the output.

        If a linter needs to do complicated setup or will use the tmpdir
        method, it will need to override this method.

        """
        if persist.settings.get('debug'):
            persist.printf('{}: {} {}'.format(self.name,
                                              os.path.basename(self.filename),
                                              cmd or '<builtin>'))

        if self.tempfile_suffix:
            return self.tmpfile(cmd, code, suffix=self.tempfile_suffix)
        else:
            return self.communicate(cmd, code)

    # popen wrappers

    def communicate(self, cmd, code):
        """Run an external executable using stdin to pass code and return its output."""
        return util.communicate(cmd, code, output_stream=self.error_stream)

    def tmpfile(self, cmd, code, suffix=''):
        """Run an external executable using a temp file to pass code and return its output."""
        return util.tmpfile(cmd, code, suffix or self.tempfile_suffix, output_stream=self.error_stream)

    def tmpdir(self, cmd, files, code):
        """Run an external executable using a temp dir filled with files and return its output."""
        return util.tmpdir(cmd, files, self.filename, code, output_stream=self.error_stream)

    def popen(self, cmd, env=None):
        """Run cmd in a subprocess with the given environment and return the output."""
        return util.popen(cmd, env)


class PythonMeta(Registrar):

    """
    Metaclass for PythonLinter that dynamically sets the 'cmd' attribute.

    If a linter can work both using an executable and built in code,
    the best way to deal with that is to set the cmd class attribute
    during class construction. This allows the linter to take advantage
    of the rest of the SublimeLinter machinery for everything but run().

    """

    def __init__(self, name, bases, attrs):
        # Attempt to import the configured module.
        # If it could not be imported, use the executable.
        # We have to do this before super().__init__ because
        # that registers the class, and we need this attribute set first.
        from importlib import import_module

        module = None

        if attrs.get('module') is not None:
            try:
                module = import_module(attrs['module'])

                # If the linter specifies a python version, check to see
                # if ST's python satisfies that version.
                cmd = self.cmd

                if isinstance(self.cmd, tuple):
                    cmd = self.cmd[0]

                if cmd:
                    match = util.PYTHON_CMD_RE.match(cmd)

                    if match:
                        args = match.groupdict()
                        args['module'] = module
                        setattr(self, 'python_version', util.find_python(**args))

                # If the module is successfully imported, save cmd and set cmd to None
                # so that the run method controls the building of cmd.
                setattr(self, '_cmd', self.cmd)
                setattr(self, 'cmd', None)

            except:
                pass

        setattr(self, 'module', module)

        super().__init__(name, bases, attrs)


class PythonLinter(Linter, metaclass=PythonMeta):

    """
    This Linter subclass provides python-specific functionality.

    Linters that check python should inherit from this class.
    By doing so, they automatically get the following features:

    - comment_re is defined correctly for python.

    - A python shebang is returned as the @python:<version> meta setting.

    - Execution directly via a module method or via an executable.

    If the module attribute is defined and is successfully imported,
    whether it is used depends on the following algorithm:

      - If the check_version attribute is False, the module will be used
        because the module is not version-sensitive.

      - If the "@python" setting is set and ST's python satisfies
        that version, the module will be used.

      - If the cmd attribute specifies @python and ST's python
        satisfies that version, the module will be used. Note that this
        check is done during class construction.

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

    # Used internally, do not modify.
    python_version = None

    @staticmethod
    def match_shebang(code):
        """Convert and return a python shebang as a @python:<version> setting."""

        match = PythonLinter.SHEBANG_RE.match(code)

        if match:
            return '@python', match.group('version')
        else:
            return None

    shebang_match = match_shebang

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
                if persist.settings.get('debug'):
                    persist.printf(
                        '{}: {} <builtin>'.format(
                            self.name,
                            os.path.basename(self.filename)
                        )
                    )

                try:
                    errors = self.check(code, os.path.basename(self.filename))
                except:
                    if persist.settings.get('debug'):
                        persist.printf(traceback.format_exc())

                    errors = ''

                if isinstance(errors, (tuple, list)):
                    return '\n'.join([str(e) for e in errors])
                else:
                    return errors
            else:
                cmd = self._cmd
        else:
            cmd = self.cmd

        cmd = self.build_cmd(cmd=cmd)
        return super().run(cmd, code)

    def check(self, code, filename):
        """
        Run a built-in check of code, returning errors.

        Subclasses that provide built in checking must override this method
        and return a string with one more lines per error, an array of strings,
        or an array of objects that can be converted to strings.

        """

        persist.debug(
            '{}: subclasses must override the PythonLinter.check method'
            .format(self.name)
        )

        return ''
