from collections import namedtuple, OrderedDict, ChainMap, Mapping, Sequence
from distutils.versionpredicate import VersionPredicate
from functools import lru_cache
from numbers import Number

import os
import re
import shlex
import sublime

from . import highlight, persist, util
from .const import STATUS_KEY, WARNING, ERROR

ARG_RE = re.compile(r'(?P<prefix>@|--?)?(?P<name>[@\w][\w\-]*)(?:(?P<joiner>[=:])(?:(?P<sep>.)(?P<multiple>\+)?)?)?')
NEAR_RE_TEMPLATE = r'(?<!"){}({}){}(?!")'
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


# SublimeLinter can lint partial buffers, e.g. `<script>` tags inside a
# HTML-file. The tiny `VirtualView` is just enough code, so we can get the
# source code of a line, the linter reported to be problematic.
class VirtualView:
    def __init__(self, code=''):
        self._code = code
        self._newlines = newlines = [0]
        last = -1

        while True:
            last = code.find('\n', last + 1)

            if last == -1:
                break

            newlines.append(last + 1)

        newlines.append(len(code))

    def full_line(self, line):
        """Return the start/end character positions for the given line."""
        start = self._newlines[line]
        end = self._newlines[min(line + 1, len(self._newlines) - 1)]

        return start, end

    def select_line(self, line):
        """Return code for the given line."""
        start, end = self.full_line(line)
        return self._code[start:end]

    # Actual Sublime API would look like:
    # def full_line(self, region)
    # def full_line(self, point) => Region
    # def substr(self, region)
    # def text_point(self, row, col) => Point
    # def rowcol(self, point) => (row, col)


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

            # The sublime plugin API is not available until plugin_loaded is executed
            if persist.plugin_is_loaded:
                persist.settings.load()

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
    word_re = re.compile(r'^([-\w]+)')

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

    @property
    def filename(self):
        """Return the view's file path or '' if unsaved."""
        return self.view.file_name() or ''

    @property
    def name(self):
        """Return the class name lowercased."""
        return self.__class__.__name__.lower()

    @staticmethod
    def _get_settings(linter, window=None):
        defaults = linter.defaults or {}
        user_settings = persist.settings.get('linters', {}).get(linter.name, {})

        if window:
            data = window.project_data() or {}
            project_settings = data.get('SublimeLinter', {}).get('linters', {}).get(linter.name, {})
        else:
            project_settings = {}

        return ChainMap({}, project_settings, user_settings, defaults)

    def get_view_settings(self):
        """Return a union of all settings specific to this view's linter.

        The settings are merged in the following order:

        default settings
        user settings
        project settings

        After merging, tokens in the settings are replaced.
        """
        # Note that when files are loaded during quick panel preview,
        # it can happen that they are linted without having a window.
        window = self.view.window()
        settings = self._get_settings(self, window)
        return self.replace_settings_tokens(settings)

    def replace_settings_tokens(self, settings):
        """Replace tokens with values in settings.

        Settings can be a string, a mapping or a sequence,
        and replacement is recursive.

        Utilizes Sublime Text's `expand_variables` API,
        which uses the `${varname}` syntax
        and supports placeholders (`${varname:placeholder}`).

        Note that we ship a enhanced version for 'folder' if you have multiple
        folders open in a window. See `_guess_project_path`.
        """
        def recursive_replace(variables, value):
            if isinstance(value, str):
                value = sublime.expand_variables(value, variables)
                return os.path.expanduser(value)
            elif isinstance(value, Mapping):
                return {key: recursive_replace(variables, val)
                        for key, val in value.items()}
            elif isinstance(value, Sequence):
                return [recursive_replace(variables, item)
                        for item in value]
            else:
                return value

        window = self.view.window()
        variables = ChainMap(
            {}, window.extract_variables() if window else {}, os.environ)

        filename = self.view.file_name()
        project_folder = self._guess_project_path(window, filename)
        if project_folder:
            variables['folder'] = project_folder

        if persist.debug_mode():
            import pprint
            self._debug_print_available_variables(pprint.pformat(dict(variables), indent=2))
        return recursive_replace(variables, settings)

    @staticmethod
    @lru_cache(maxsize=1)
    def _debug_print_available_variables(variables):
        persist.debug('Available variables: {}'.format(variables))

    @staticmethod
    def _guess_project_path(window, filename):
        if not window:
            return

        folders = window.folders()
        if not folders:
            return

        if not filename:
            return folders[0]

        for folder in folders:
            # Take the first one; should we take the deepest one? The shortest?
            if folder in filename:
                return folder

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

    def lint(self, code, hit_time):
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
            return []

        cmd = self.get_cmd()
        settings = self.get_view_settings()
        chdir = self.get_chdir(settings)

        with util.cd(chdir):
            output = self.run(cmd, code)

        if not output:
            return []

        # If the view has been modified since the lint was triggered, no point in continuing.
        if hit_time and persist.last_hit_times.get(self.view.id(), 0) > hit_time:
            return None  # ABORT

        if persist.debug_mode():
            stripped_output = output.replace('\r', '').rstrip()
            util.printf('{} output:\n{}'.format(self.name, stripped_output))

        errors = []
        vv = VirtualView(code)
        for m in self.find_errors(output):
            if not m or not m[0]:
                continue

            if not isinstance(m, LintMatch):  # ensure right type
                m = LintMatch(*m)

            if m.message and m.line is not None:
                error = self.process_match(m, vv)
                errors.append(error)

        return errors

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
            match_dict.update({
                k: v
                for k, v in match.groupdict().items()
                if k in match_dict
            })
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

    def process_match(self, m, vv):
        error_type = self.get_error_type(m.error, m.warning)

        col = m.col

        if col is not None:
            col = self.maybe_fix_tab_width(m.line, col, vv)

            # Pin the column to the start/end line offsets
            start, end = vv.full_line(m.line)
            col = max(min(col, (end - start) - 1), 0)

        line, start, end = self.reposition_match(m.line, col, m, vv)
        return {
            "line": line,
            "start": start,
            "end": end,
            "linter": self.name,
            "error_type": error_type,
            "code": m.error or m.warning or '',
            "msg": m.message,
        }

    def maybe_fix_tab_width(self, line, col, vv):
        # Adjust column numbers to match the linter's tabs if necessary
        if self.tab_width > 1:
            code_line = vv.select_line(line)
            diff = 0

            for i in range(len(code_line)):
                if code_line[i] == '\t':
                    diff += (self.tab_width - 1)

                if col - diff <= i:
                    col = i
                    break
        return col

    def reposition_match(self, line, col, m, vv):
        """Chance to reposition the error.

        Must return a tuple (line, start, end)

        The default implementation just finds a good `end` or range for the
        given match. E.g. it uses `self.word_re` to select the whole word
        beginning at the `col`. If `m.near` is given, it selects the first
        occurrence of that word on the give `line`.
        """
        if col is None:
            if m.near:
                text = vv.select_line(m.line)
                near = self.strip_quotes(m.near)

                # Add \b fences around the text if it begins/ends with a word character
                fence = ['', '']

                for i, pos in enumerate((0, -1)):
                    if near[pos].isalnum() or near[pos] == '_':
                        fence[i] = r'\b'

                pattern = NEAR_RE_TEMPLATE.format(fence[0], re.escape(near), fence[1])
                match = re.search(pattern, text)

                if match:
                    col = match.start(1)
                    length = len(near)
                    return line, col, col + length
                # else fall through and mark the line

            if (
                persist.settings.get('no_column_highlights_line') or
                not persist.settings.has('gutter_theme')
            ):
                start, end = vv.full_line(m.line)
                length = end - start - 1  # -1 for the trailing '\n'
                return line, 0, length
            else:
                return line, 0, 0

        else:
            if m.near:
                near = self.strip_quotes(m.near)
                length = len(near)
                return line, col, col + length
            else:
                text = vv.select_line(m.line)[col:]
                match = self.word_re.search(text) if self.word_re else None

                length = len(match.group()) if match else 1
                return line, col, col + length

    @staticmethod
    def strip_quotes(text):
        """Return text stripped of enclosing single/double quotes."""
        first = text[0]

        if first in ('\'', '"') and text[-1] == first:
            text = text[1:-1]

        return text

    @staticmethod
    def clear_view(view):
        """Clear marks, status and all other cached error info for the given view."""
        if not view:
            return

        view.erase_status(STATUS_KEY)
        highlight.clear_view(view)
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
