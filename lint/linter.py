from collections import namedtuple, OrderedDict
from distutils.versionpredicate import VersionPredicate
from fnmatch import fnmatch
from functools import lru_cache
from numbers import Number

import os
import re
import shlex
import sublime

from . import highlight, persist, util
from .const import STATUS_KEY, WARNING, ERROR
from .style import LinterStyleStore

ARG_RE = re.compile(r'(?P<prefix>@|--?)?(?P<name>[@\w][\w\-]*)(?:(?P<joiner>[=:])(?:(?P<sep>.)(?P<multiple>\+)?)?)?')
BASE_CLASSES = ('PythonLinter',)

MATCH_DICT = OrderedDict(
    (
        ("match", None),
        ("line", None),
        ("col", None),
        ("error", None),
        ("warning", None),
        ("message", ''),
        ("near", None)
    )
)
LintMatch = namedtuple("LintMatch", MATCH_DICT.keys())
LintMatch.__new__.__defaults__ = tuple(MATCH_DICT.values())


class LinterMeta(type):
    """Metaclass for Linter and its subclasses."""

    def __init__(cls, name, bases, attrs):
        """
        Initialize a Linter class.

        When a Linter subclass is loaded by Sublime Text, this method is called.
        We take this opportunity to do some transformations:

        - Compile regex patterns.
        - Convert strings to tuples where necessary.
        - Add a leading dot to the tempfile_suffix if necessary.
        - Build a map between defaults and linter arguments.
        - Add '@python' as an inline setting to PythonLinter subclasses.

        Finally, the class is registered as a linter for its configured syntax.
        """
        if bases:
            setattr(cls, 'disabled', False)

            if name in ('PythonLinter', 'RubyLinter', 'NodeLinter', 'ComposerLinter'):
                return

            cls.alt_name = cls.make_alt_name(name)
            cmd = attrs.get('cmd')

            if isinstance(cmd, str):
                setattr(cls, 'cmd', shlex.split(cmd))

            syntax = attrs.get('syntax')

            try:
                if isinstance(syntax, str) and syntax[0] == '^':
                    setattr(cls, 'syntax', re.compile(syntax))
            except re.error as err:
                util.printf(
                    'ERROR: {} disabled, error compiling syntax: {}'
                    .format(name.lower(), str(err))
                )
                setattr(cls, 'disabled', True)

            if not cls.disabled:
                for regex in ('regex', 'word_re', 'version_re'):
                    attr = getattr(cls, regex)

                    if isinstance(attr, str):
                        if regex == 'regex' and cls.multiline:
                            setattr(cls, 're_flags', cls.re_flags | re.MULTILINE)

                        try:
                            setattr(cls, regex, re.compile(attr, cls.re_flags))
                        except re.error as err:
                            util.printf(
                                'ERROR: {} disabled, error compiling {}: {}'
                                .format(name.lower(), regex, str(err))
                            )
                            setattr(cls, 'disabled', True)

            if not cls.disabled:
                if not cls.syntax or (cls.cmd is not None and not cls.cmd) or not cls.regex:
                    util.printf('ERROR: {} disabled, not fully implemented'.format(name.lower()))
                    setattr(cls, 'disabled', True)

            # If this class has its own defaults, create an args_map.
            # Otherwise we use the superclass' args_map.
            if 'defaults' in attrs and attrs['defaults']:
                cls.map_args(attrs['defaults'])

            if persist.plugin_is_loaded:
                # If the plugin has already loaded, then we get here because
                # a linter was added or reloaded. In that case we run reinitialize.
                cls.reinitialize()

            if 'syntax' in attrs and name not in BASE_CLASSES:
                cls.register_linter(name, attrs)

    def register_linter(cls, name, attrs):
        """Add a linter class to our mapping of class names <-> linter classes."""
        if name:
            name = name.lower()
            persist.linter_classes[name] = cls

            # By setting the lint_settings to None, they will be set the next
            # time linter_class.settings() is called.
            cls.lint_settings = None

            # The sublime plugin API is not available until plugin_loaded is executed
            if persist.plugin_is_loaded:
                persist.settings.load(force=True)

                # If the linter had previously been loaded, just reassign that linter
                if name in persist.linter_classes:
                    linter_name = name
                else:
                    linter_name = None

                for view in persist.views.values():
                    cls.assign(view, linter_name=linter_name)

                persist.debug('{} linter reloaded'.format(name))

            else:
                persist.debug('{} linter loaded'.format(name))

    def map_args(cls, defaults):
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
        setattr(cls, 'defaults', {})

        for name, value in defaults.items():
            match = ARG_RE.match(name)

            if match:
                name = match.group('name')
                args_map[name] = match.groupdict()

            cls.defaults[name] = value

        setattr(cls, 'args_map', args_map)

    @staticmethod
    def make_alt_name(name):
        """Convert and return a camel-case name to lowercase with dashes."""
        previous = name[0]
        alt_name = previous.lower()

        for c in name[1:]:
            if c.isupper() and previous.islower():
                alt_name += '-'

            alt_name += c.lower()
            previous = c

        return alt_name

    @property
    def name(cls):
        """Return the class name lowercased."""
        return cls.__name__.lower()


class Linter(metaclass=LinterMeta):
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

    # Some linter plugins have version requirements as far as the linter executable.
    # The following three attributes can be defined to define the requirements.
    # version_args is a string/list/tuple that represents the args used to get
    # the linter executable's version as a string.
    version_args = None

    # A regex pattern or compiled regex used to match the numeric portion of the version
    # from the output of version_args. It must contain a named capture group called
    # "version" that captures only the version, including dots but excluding a prefix
    # such as "v".
    version_re = None

    # A string which describes the version requirements, suitable for passing to
    # the distutils.versionpredicate.VersionPredicate constructor, as documented here:
    # http://pydoc.org/2.5.1/distutils.versionpredicate.html
    # Only the version requirements (what is inside the parens) should be
    # specified here, do not include the package name or parens.
    version_requirement = None

    # A regex pattern used to extract information from the executable's output.
    regex = ''

    # Set to True if the linter outputs multiline error messages. When True,
    # regex will be created with the re.MULTILINE flag. Do NOT rely on setting
    # the re.MULTILINE flag within the regex yourself, this attribute must be set.
    multiline = False

    # If you want to set flags on the regex *other* than re.MULTILINE, set this.
    re_flags = 0

    # The default type assigned to non-classified errors. Should be either
    # ERROR or WARNING.
    default_type = ERROR

    # Linters usually report errors with a line number, some with a column number
    # as well. In general, most linters report one-based line numbers and column
    # numbers. If a linter uses zero-based line numbers or column numbers, the
    # linter class should define this attribute accordingly.
    line_col_base = (1, 1)

    # If the linter executable cannot receive from stdin and requires a temp file,
    # set this attribute to the suffix of the temp file (with or without leading '.').
    # If the suffix needs to be mapped to the syntax of a file, you may make this
    # a dict that maps syntax names (all lowercase, as used in the syntax attribute),
    # to tempfile suffixes. The syntax used to lookup the suffix is the mapped
    # syntax, after using "syntax_map" in settings. If the view's syntax is not
    # in this map, the class' syntax will be used.
    #
    # Some linters can only work from an actual disk file, because they
    # rely on an entire directory structure that cannot be realistically be copied
    # to a temp directory (e.g. javac). In such cases, set this attribute to '-',
    # which marks the linter as "file-only". That will disable the linter for
    # any views that are dirty.
    tempfile_suffix = None

    # Linters may output to both stdout and stderr. By default stdout and sterr are captured.
    # If a linter will never output anything useful on a stream (including when
    # there is an error within the linter), you can ignore that stream by setting
    # this attribute to the other stream.
    error_stream = util.STREAM_BOTH

    # Many linters look for a config file in the linted file’s directory and in
    # all parent directories up to the root directory. However, some of them
    # will not do this if receiving input from stdin, and others use temp files,
    # so looking in the temp file directory doesn’t work. If this attribute
    # is set to a tuple of a config file argument and the name of the config file,
    # the linter will automatically try to find the config file, and if it is found,
    # add the config file argument to the executed command.
    #
    # Example: config_file = ('--config', '.jshintrc')
    #
    config_file = None

    # Either '=' or ':'. if '=', the config file argument is joined with the config file
    # path found by '=' and passed as a single argument. If ':', config file argument and
    # the value are passed as separate arguments.
    config_joiner = ':'

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
    # - <prefix>: Either empty, '@', '-' or '--'.
    # - <name>: The name of the setting.
    # - <joiner>: Either '=' or ':'. If <prefix> is empty or '@', <joiner> is ignored.
    #   Otherwise, if '=', the setting value is joined with <name> by '=' and
    #   passed as a single argument. If ':', <name> and the value are passed
    #   as separate arguments.
    # - <sep>: If the argument accepts a list of values, <sep> specifies
    #   the character used to delimit the list (usually ',').
    # - +: If the setting can be a list of values, but each value must be
    #   passed as a separate argument, terminate the setting with '+'.
    #
    # After the format is parsed, the prefix and suffix are removed and the
    # setting is replaced with <name>.
    defaults = None

    #
    # Internal class storage, do not set
    #
    errors = None
    highlight = None
    lint_settings = None
    env = None
    disabled = False
    executable_version = None

    @classmethod
    def initialize(cls):
        """
        Perform class-level initialization.

        If subclasses override this, they should call super().initialize() first.

        """
        pass

    @classmethod
    def reinitialize(cls):
        """
        Perform class-level initialization after plugins have been loaded at startup.

        This occurs if a new linter plugin is added or reloaded after startup.
        Subclasses may override this to provide custom behavior, then they must
        call cls.initialize().

        """
        cls.initialize()

    def __init__(self, view, syntax):  # noqa: D107
        self.view = view
        self.syntax = syntax
        self.code = ''
        self.highlight = highlight.Highlight()
        self.style_store = LinterStyleStore(self.name)

    @property
    def filename(self):
        """Return the view's file path or '' if unsaved."""
        return self.view.file_name() or ''

    @property
    def name(self):
        """Return the class name lowercased."""
        return self.__class__.__name__.lower()

    @classmethod
    def settings(cls):
        """Return the default settings for this linter, merged with the user settings."""
        if cls.lint_settings is None:
            linters = persist.settings.get('linters', {})
            cls.lint_settings = (cls.defaults or {}).copy()
            cls.lint_settings.update(linters.get(cls.name, {}))

        return cls.lint_settings

    def get_view_settings(self):
        """
        Return a union of all non-inline settings specific to this view's linter.

        The settings are merged in the following order:

        default settings
        user settings
        project settings

        After merging, tokens in the settings are replaced.
        """
        # Start with the overall project settings. Note that when
        # files are loaded during quick panel preview, it can happen
        # that they are linted without having a window.
        window = self.view.window()

        if window:
            data = window.project_data() or {}
            project_settings = data.get('SublimeLinter', {})
        else:
            project_settings = {}

        project_settings = project_settings.get('linters', {}).get(self.name, {})

        # Update the linter's settings with the project settings and rc settings
        settings = self.merge_project_settings(self.settings().copy(), project_settings)
        self.replace_settings_tokens(settings)
        return settings

    def replace_settings_tokens(self, settings):
        """
        Replace tokens with values in settings.

        Supported tokens, in the order they are expanded:
        drive
            sandbox
                project 1
                    path to file
                        file to lint
                project 2
                    path to file
                        file to lint
                project 3
                    path to file
                        file to lint

        ${project}:
            full path of the project root directory
            -> "/drive/sandbox/project 1"

        ${directory}:
            full path the current view's parent directory
            -> "/drive/sandbox/project 1/path to file"

        ${project} and ${directory} expansion are dependent on
        having a window. Paths do not contain trailing directory separators.

        ${home}: the user's $HOME directory.
        ${sublime}: sublime text settings directory.
        ${env:x}: the environment variable 'x'.


        """
        def recursive_replace_value(expressions, value):
            if isinstance(value, dict):
                value = recursive_replace(expressions, value, nested=True)
            elif isinstance(value, list):
                value = [recursive_replace_value(expressions, item) for item in value]
            elif isinstance(value, str):
                for exp in expressions:
                    if isinstance(exp['value'], str):
                        value = value.replace(exp['token'], exp['value'])
                    else:
                        value = exp['token'].sub(exp['value'], value)

            return value

        def recursive_replace(expressions, mutable_input, nested=False):
            for key, value in mutable_input.items():
                mutable_input[key] = recursive_replace_value(expressions, value)
            if nested:
                return mutable_input

        # Expressions are evaluated in list order.
        expressions = []
        window = self.view.window()
        if window:
            view = window.active_view()

            if not view or not view.file_name():
                return

            # window.project_data delivers the root folder(s) of the view,
            # even without any project file! more flexible that way:
            #
            # 1) have your folder open with no project settings
            # 2) have more than one folder opened with no project settings
            # 3) project settings file inside your folder structure
            # 4) project settings file outside your folder structure

            if window.project_file_name():
                project = os.path.dirname(window.project_file_name()).replace('\\', '/')

                expressions.append({
                    'token': '${project}',
                    'value': project
                })
            else:
                data = window.project_data() or {}
                folders = data.get('folders', [])
                for folder in folders:
                    # extract the root folder of the currently watched file
                    filename = view.file_name() or 'FILE NOT ON DISK'
                    if folder['path'] in filename:
                        expressions.append({
                            'token': '${project}',
                            'value': folder['path']
                        })

            expressions.append({
                'token': '${directory}',
                'value': (
                    os.path.dirname(view.file_name()).replace('\\', '/') if
                    view and view.file_name() else "FILE NOT ON DISK"
                )
            })

        expressions.append({
            'token': '${home}',
            'value': os.path.expanduser('~').rstrip(os.sep).rstrip(os.altsep).replace('\\', '/') or 'HOME NOT SET'
        })

        expressions.append({
            'token': '${sublime}',
            'value': sublime.packages_path()
        })

        expressions.append({
            'token': re.compile(r'\${env:(?P<variable>[^}]+)}'),
            'value': (
                lambda m: os.getenv(m.group('variable')) if
                os.getenv(m.group('variable')) else
                "%s NOT SET" % m.group('variable'))
        })

        recursive_replace(expressions, settings)

    def merge_project_settings(self, view_settings, project_settings):
        """
        Return this linter's view settings merged with the current project settings.

        Subclasses may override this if they wish to do something more than
        replace view settings with inline settings of the same name.
        The settings object may be changed in place.

        """
        view_settings.update(project_settings)
        return view_settings

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
        syntax = util.get_syntax(view)

        if not syntax:
            cls.remove(vid)
            return

        view_linters = persist.view_linters.get(vid, set())
        linters = set()

        for name, linter_class in persist.linter_classes.items():
            if not linter_class.disabled and linter_class.can_lint(syntax):

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
                    linter = linter_class(view, syntax)

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
                linter = linter_class(linter.view, linter.syntax)
                persist.view_linters[vid].add(linter)

    @classmethod
    def clear_all(cls):
        """Clear highlights and errors in all views."""
        persist.errors.clear()

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
    def get_selectors(cls, vid, syntax):
        """
        Return scope selectors and linters for the view with the given id.

        For each linter assigned to the view with the given id, if it
        has selectors, return a tuple of the selector and the linter.

        """
        selectors = []

        for linter in cls.get_linters(vid):
            if syntax in linter.selectors:
                selectors.append((linter.selectors[syntax], linter))

            if '*' in linter.selectors:
                selectors.append((linter.selectors['*'], linter))

        return selectors

    @classmethod
    def lint_view(cls, view, filename, code, hit_time, callback):
        """
        Lint the given view.

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

        vid = view.id()
        linters = persist.view_linters.get(vid)

        if not linters:
            return

        disabled = set()
        syntax = util.get_syntax(persist.views[vid])

        for linter in linters:
            # First check to see if the linter can run in the current lint mode.
            if linter.tempfile_suffix == '-' and view.is_dirty():
                disabled.add(linter)
                continue

            view_settings = linter.get_view_settings()

            if view_settings.get('disable'):
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

            if syntax not in linter.selectors and '*' not in linter.selectors:
                linter.reset(code, view_settings)
                linter.lint(hit_time)

        selectors = Linter.get_selectors(vid, syntax)

        for selector, linter in selectors:
            if linter in disabled:
                continue

            linters.add(linter)
            regions = []

            for region in view.find_by_selector(selector):
                regions.append(region)

            linter.reset(code, view_settings)
            errors = {}

            for region in regions:
                line_offset, col = view.rowcol(region.begin())
                linter.highlight.move_to(line_offset, col)
                linter.code = code[region.begin():region.end()]
                linter.errors = {}
                linter.lint(hit_time)

                for line, line_errors in linter.errors.items():
                    errors[line + line_offset] = line_errors

            linter.errors = errors

        # Remove disabled linters
        linters = list(linters - disabled)

        # Merge our result back to the main thread
        callback(cls.get_view(vid), linters, hit_time)

    def reset(self, code, settings):
        """Reset a linter to work on the given code and filename."""
        self.errors = {}
        self.code = code
        self.highlight = highlight.Highlight(self.code)

    @classmethod
    def which(cls, cmd):
        """Return full path to a given executable.

        This version just delegates to `util.which` but plugin authors can
        override this method.

        Note that this method will be called statically as well as per
        instance. So you can rely on `get_view_settings` to be available.

        `context_sensitive_executable_path` is guaranteed to be called per
        instance and might be the better override point.
        """
        return util.which(cmd)

    def get_cmd(self):
        """
        Calculate and return a tuple/list of the command line to be executed.

        The cmd class attribute may be a string, a tuple/list, or a callable.
        If cmd is callable, it is called. If the result of the method is
        a string, it is parsed into a list with shlex.split.

        Otherwise the result of build_cmd is returned.
        """
        cmd = self.cmd
        if cmd is None:
            return None

        if callable(cmd):
            cmd = cmd()

        if isinstance(cmd, str):
            cmd = shlex.split(cmd)
        else:
            cmd = list(cmd)

        # For backwards compatibility: SL3 allowed a '@python' suffix which,
        # when set, triggered special handling. SL4 doesn't need this marker,
        # bc all the special handling is just done in the subclass.
        which = cmd[0]
        if '@python' in which:
            cmd[0] = which[:which.find('@python')]

        return self.build_cmd(cmd)

    def build_cmd(self, cmd):
        """
        Return a tuple with the command line to execute.

        Tries to find an executable with its complete path for cmd and replaces
        cmd[0] with it.

        The delegates to `insert_args` and returns whatever it returns.

        """
        which = cmd[0]
        have_path, path = self.context_sensitive_executable_path(cmd)

        if have_path:
            # happy path
            ...
        elif util.can_exec(which):
            # If `cmd` is a method, it is expected it finds an executable on
            # its own. (Unless `context_sensitive_executable_path` is also
            # implemented.)
            path = which
        elif self.executable_path:
            # `executable_path` is set statically by `can_lint`.
            path = self.executable_path
        else:
            # `which` here is a fishy escape hatch bc it was almost always
            # asked in `can_lint` already.
            path = self.which(which)

        if not path:
            util.printf('WARNING: {} cannot locate \'{}\''.format(self.name, which))
            return ''

        cmd[0:1] = util.convert_type(path, [])
        return self.insert_args(cmd)

    def context_sensitive_executable_path(self, cmd):
        """
        Calculate the context-sensitive executable path, return a tuple of (have_path, path).

        Subclasses may override this to return a special path.

        Return (True, '<path>') if you can resolve the executable given at cmd[0]
        Return (True, None) if you want to skip the linter
        Return (False, None) if you want to kick in the default implementation
            of SublimeLinter

        """
        return False, None

    def insert_args(self, cmd):
        """Insert user arguments into cmd and return the result."""
        args = self.build_args(self.get_view_settings())
        cmd = list(cmd)

        if '*' in cmd:
            i = cmd.index('*')

            if args:
                cmd[i:i + 1] = args
            else:
                cmd.pop(i)
        else:
            cmd += args

        return cmd

    def get_user_args(self, settings=None):
        """Return any args the user specifies in settings as a list."""
        if settings is None:
            settings = self.get_view_settings()

        args = settings.get('args', [])

        if isinstance(args, str):
            args = shlex.split(args)
        else:
            args = args[:]

        return args

    def build_args(self, settings):
        """
        Return a list of args to add to cls.cmd.

        First any args specified in the "args" linter setting are retrieved.
        Then the args map (built by map_args during class construction) is
        iterated. For each item in the args map:

        - Check to see if the arg is in settings, which is the aggregated
          default/user/view settings. If arg is not in settings or is a meta
          setting (beginning with '@'), it is skipped.

        - If the arg has no prefix, it is skipped.

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

        Finally, if the config_file attribute is set and the user has not
        set the config_file arg in the linter's "args" setting, try to
        locate the config file and if found add the config file arg.

        Return the arg list.
        """
        args = self.get_user_args(settings)
        args_map = getattr(self, 'args_map', {})

        for setting, arg_info in args_map.items():
            prefix = arg_info['prefix']

            if setting not in settings or setting[0] == '@' or prefix is None:
                continue

            values = settings[setting]

            if values is None:
                continue
            elif isinstance(values, (list, tuple)):
                if values:
                    # If the values can be passed as a single list, join them now
                    if arg_info['sep'] and not arg_info['multiple']:
                        values = [str(value) for value in values]
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
                if prefix == '@':
                    args.append(str(value))
                else:
                    arg = prefix + arg_info['name']
                    joiner = arg_info['joiner']

                    if joiner == '=':
                        args.append('{}={}'.format(arg, value))
                    elif joiner == ':':
                        args.append(arg)
                        args.append(str(value))

        if self.config_file:
            if self.config_file[0] not in args and self.filename:
                config = util.find_file(
                    os.path.dirname(self.filename),
                    self.config_file[1],
                    aux_dirs=self.config_file[2:]
                )

                if config:
                    if self.config_joiner == '=':
                        args.append('{}={}'.format(self.config_file[0], config))
                    elif self.config_joiner == ':':
                        args += [self.config_file[0], config]

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

    def get_chdir(self, settings):
        """Find the chdir to use with the linter."""
        chdir = settings.get('chdir', None)

        if chdir and os.path.isdir(chdir):
            persist.debug('chdir has been set to: {0}'.format(chdir))
            return chdir
        else:
            if self.filename:
                return os.path.dirname(self.filename)
            else:
                return os.path.realpath('.')

    def get_error_type(self, error, warning):  # noqa:D102
        if error:
            return ERROR
        elif warning:
            return WARNING
        else:
            return self.default_type

    def lint(self, hit_time):
        """
        Perform the lint, retrieve the results, and add marks to the view.

        The flow of control is as follows:

        - Get the command line. If it is an empty string, bail.
        - Run the linter.
        - If the view has been modified since the original hit_time, stop.
        - Parse the linter output with the regex.
        - Highlight warnings and errors.
        """
        if self.disabled:
            return

        cmd = self.get_cmd()
        settings = self.get_view_settings()
        chdir = self.get_chdir(settings)

        with util.cd(chdir):
            output = self.run(cmd, self.code)

        if not output:
            return

        # If the view has been modified since the lint was triggered, no point in continuing.
        if hit_time and persist.last_hit_times.get(self.view.id(), 0) > hit_time:
            return

        if persist.debug_mode():
            stripped_output = output.replace('\r', '').rstrip()
            util.printf('{} output:\n{}'.format(self.name, stripped_output))

        for m in self.find_errors(output):
            if not m or not m[0]:
                continue

            if not isinstance(m, LintMatch):  # ensure right type
                m = LintMatch(*m)

            if m.message and m.line is not None:
                self.process_match(m)

    def process_match(self, m):
        error_type = self.get_error_type(m.error, m.warning)
        style = self.style_store.get_style(m.error or m.warning, error_type)

        assert style

        col = m.col

        if col:
            start, end = self.highlight.full_line(m.line)

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

            # Pin the column to the start/end line offsets
            col = max(min(col, (end - start) - 1), 0)

        length = None
        if col:
            length = self.highlight.range(
                m.line,
                col,
                near=m.near,
                error_type=error_type,
                word_re=self.word_re,
                style=style
            )
        elif m.near:
            col, length = self.highlight.near(
                m.line,
                m.near,
                error_type=error_type,
                word_re=self.word_re,
                style=style
            )
        else:
            if (
                persist.settings.get('no_column_highlights_line') or
                not persist.settings.has('gutter_theme')
            ):
                pos = -1
            else:
                pos = 0

            length = self.highlight.range(
                m.line,
                pos,
                length=0,
                error_type=error_type,
                word_re=self.word_re,
                style=style
            )

        self.error(m.line, col, m.message, error_type, style=style, code=m.warning or m.error, length=length)

    def draw(self):
        """Draw the marks from the last lint."""
        self.highlight.draw(self.view)

    @staticmethod
    def clear_view(view):
        """Clear marks, status and all other cached error info for the given view."""
        if not view:
            return

        view.erase_status(STATUS_KEY)
        highlight.Highlight.clear(view)
        persist.errors.pop(view.id(), None)

    def clear(self):
        self.clear_view(self.view)

    # Helper methods

    @classmethod
    @lru_cache(maxsize=None)
    def can_lint(cls, syntax):
        """
        Determine if a linter class can lint the given syntax.

        This method is called when a view has not had a linter assigned
        or when its syntax changes.

        The following tests must all pass for this method to return True:

        1. syntax must match one of the syntaxes the linter defines.
        2. If the linter uses an external executable, it must be available.
        3. If there is a version requirement and the executable is available,
           its version must fulfill the requirement.
        4. can_lint_syntax must return True.
        """
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

        if can:
            if cls.executable_path is None:
                executable = None
                cmd = cls.cmd

                if cmd and not callable(cmd):
                    if isinstance(cls.cmd, str):
                        cmd = shlex.split(cmd)
                    executable = cmd[0]
                else:
                    executable = cls.executable

                if not executable:
                    return True

                if executable:
                    cls.executable_path = cls.which(executable) or ''
                elif cmd is None:
                    cls.executable_path = '<builtin>'
                else:
                    cls.executable_path = ''

            status = None

            if cls.executable_path:
                can = cls.fulfills_version_requirement()

                if not can:
                    status = ''  # Warning was already printed

            if can:
                can = cls.can_lint_syntax(syntax)

            elif status is None:
                status = 'WARNING: {} deactivated, cannot locate \'{}\''.format(cls.name, cls.executable_path)

            if status:
                persist.debug(status)

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

    @classmethod
    def fulfills_version_requirement(cls):
        """
        Return whether the executable fulfills version_requirement.

        When this is called, cls.executable_path has been set.
        """
        if not(cls.version_args is not None and cls.version_re and cls.version_requirement):
            return True

        cls.executable_version = cls.get_executable_version()

        if cls.executable_version:
            predicate = VersionPredicate(
                '{} ({})'.format(cls.name.replace('-', '.'), cls.version_requirement)
            )

            if predicate.satisfied_by(cls.executable_version):
                persist.debug(
                    '{}: ({}) satisfied by {}'
                    .format(cls.name, cls.version_requirement, cls.executable_version)
                )
                return True
            else:
                util.printf(
                    'WARNING: {} deactivated, version requirement ({}) not fulfilled by {}'
                    .format(cls.name, cls.version_requirement, cls.executable_version)
                )

        return False

    @classmethod
    def get_executable_version(cls):
        """Extract and return the string version of the linter executable."""
        args = cls.version_args

        if isinstance(args, str):
            args = shlex.split(args)
        else:
            args = list(args)

        if isinstance(cls.executable_path, str):
            cmd = [cls.executable_path]
        else:
            cmd = list(cls.executable_path)

        cmd += args
        persist.debug('{} version query: {}'.format(cls.name, ' '.join(cmd)))

        version = util.communicate(cmd, output_stream=util.STREAM_BOTH)
        match = cls.version_re.search(version)

        if match:
            version = match.group('version')
            persist.debug('{} version: {}'.format(cls.name, version))
            return version
        else:
            util.printf('WARNING: no {} version could be extracted from:\n{}'.format(cls.name, version))
            return None

    def error(self, line, col, message, error_type, style=None, code=None, length=None):
        """Add a reference to an error/warning on the given line and column."""
        self.highlight.line(line, error_type, style=style)

        col = col or 0

        if not code:
            code = ""

        payload = {
            "start": col,
            "end": col + (length or 0),
            "linter": self.name,
            "code": code,
            "msg": message
        }

        l1 = self.errors.setdefault(line, {})
        l2 = l1.setdefault(error_type, [])
        l2.append(payload)

    def find_errors(self, output):
        """
        Match the linter's regex against the linter output with this generator.

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
        match_dict = MATCH_DICT.copy()

        if not match:
            persist.debug('No match for regex: {}'.format(self.regex.pattern))
        else:
            match_dict.update(match.groupdict())
            match_dict["match"] = match

            # normalize line and col if necessary
            line = match_dict["line"]
            if line:
                match_dict["line"] = int(line) - self.line_col_base[0]

            col = match_dict["col"]
            if col:
                if col.isdigit():
                    col = int(col) - self.line_col_base[1]
                else:
                    col = len(col)
                match_dict["col"] = col

        return LintMatch(**match_dict)

    def run(self, cmd, code):
        """
        Execute the linter's executable or built in code and return its output.

        If a linter uses built in code, it should override this method and return
        a string as the output.

        If a linter needs to do complicated setup or will use the tmpdir
        method, it will need to override this method.

        """
        if persist.debug_mode():
            util.printf('{}: {} {}'.format(
                self.name,
                os.path.basename(self.filename or '<unsaved>'),
                cmd)
            )

        if self.tempfile_suffix:
            if self.tempfile_suffix != '-':
                return self.tmpfile(cmd, code)
            else:
                return self.communicate(cmd)
        else:
            return self.communicate(cmd, code)

    def get_tempfile_suffix(self):
        """Return the mapped tempfile_suffix."""
        if self.tempfile_suffix and not self.view.file_name():
            if isinstance(self.tempfile_suffix, dict):
                suffix = self.tempfile_suffix.get(util.get_syntax(self.view), self.syntax)
            else:
                suffix = self.tempfile_suffix

            if not suffix.startswith('.'):
                suffix = '.' + suffix

            return suffix
        else:
            return ''

    # popen wrappers

    def communicate(self, cmd, code=None):
        """Run an external executable using stdin to pass code and return its output."""
        if '@' in cmd:
            cmd[cmd.index('@')] = self.filename
        elif not code:
            cmd.append(self.filename)

        return util.communicate(
            cmd,
            code,
            output_stream=self.error_stream,
            env=self.env)

    def tmpfile(self, cmd, code, suffix=''):
        """Run an external executable using a temp file to pass code and return its output."""
        return util.tmpfile(
            cmd,
            code,
            self.filename,
            suffix or self.get_tempfile_suffix(),
            output_stream=self.error_stream,
            env=self.env)

    def tmpdir(self, cmd, files, code):
        """Run an external executable using a temp dir filled with files and return its output."""
        return util.tmpdir(
            cmd,
            files,
            self.filename,
            code,
            output_stream=self.error_stream,
            env=self.env)
