from collections import namedtuple, OrderedDict, ChainMap, Mapping, Sequence
from distutils.versionpredicate import VersionPredicate
from functools import lru_cache
from numbers import Number
import threading

import logging
import os
import re
import shlex
import sublime

from . import persist, util
from .const import WARNING, ERROR


logger = logging.getLogger(__name__)


ARG_RE = re.compile(r'(?P<prefix>@|--?)?(?P<name>[@\w][\w\-]*)(?:(?P<joiner>[=:])(?:(?P<sep>.)(?P<multiple>\+)?)?)?')
NEAR_RE_TEMPLATE = r'(?<!"){}({}){}(?!")'
BASE_CLASSES = ('PythonLinter', 'RubyLinter', 'NodeLinter', 'ComposerLinter')

# Many linters use stdin, and we convert text to utf-8
# before sending to stdin, so we have to make sure stdin
# in the target executable is looking for utf-8. Some
# linters (like ruby) need to have LANG and/or LC_CTYPE
# set as well.
UTF8_ENV_VARS = {
    'PYTHONIOENCODING': 'utf8',
    'LANG': 'en_US.UTF-8',
    'LC_CTYPE': 'en_US.UTF-8',
}

BASE_LINT_ENVIRONMENT = ChainMap(UTF8_ENV_VARS, os.environ)


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


# Typical global context, alive and kicking during the multi-threaded
# (concurrent) `Linter.lint` call.
lint_context = threading.local()


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
        - Build a map between defaults and linter arguments.

        Finally, the class is registered as a linter for its configured syntax.
        """
        if not bases:
            return

        if name in BASE_CLASSES:
            return

        name = name.lower()
        setattr(cls, 'disabled', False)
        setattr(cls, 'name', name)

        cmd = attrs.get('cmd')

        if isinstance(cmd, str):
            setattr(cls, 'cmd', shlex.split(cmd))

        syntax = attrs.get('syntax')

        try:
            if isinstance(syntax, str) and syntax[0] == '^':
                setattr(cls, 'syntax', re.compile(syntax))
        except re.error as err:
            logger.error(
                '{} disabled, error compiling syntax: {}'
                .format(name, str(err))
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
                        logger.error(
                            '{} disabled, error compiling {}: {}'
                            .format(name, regex, str(err))
                        )
                        setattr(cls, 'disabled', True)

        if not cls.disabled:
            if (cls.cmd is not None and not cls.cmd) or not cls.regex:
                logger.error('{} disabled, not fully implemented'.format(name))
                setattr(cls, 'disabled', True)

        # If this class has its own defaults, create an args_map.
        # Otherwise we use the superclass' args_map.
        if 'defaults' in attrs and attrs['defaults']:
            cls.map_args(attrs['defaults'])

        if not cls.syntax and not cls.defaults.get('selector'):
            logger.error(
                "{} disabled, either 'syntax' or 'selector' must be specified"
                .format(name))
            setattr(cls, 'disabled', True)

        cls.register_linter(name)

    def register_linter(cls, name):
        """Add a linter class to our mapping of class names <-> linter classes."""
        persist.linter_classes[name] = cls

        # The sublime plugin API is not available until plugin_loaded is executed
        if persist.api_ready:
            persist.settings.load()
            logger.info('{} linter reloaded'.format(name))

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
    disabled = False
    executable_version = None

    def __init__(self, view, syntax):
        self.view = view
        self.syntax = syntax
        # Using `self.env` is deprecated, bc it can have surprising
        # side-effects for concurrent/async linting. We initialize it here
        # bc some ruby linters rely on that behavior.
        self.env = {}

    @property
    def filename(self):
        """Return the view's file path or '' if unsaved."""
        return self.view.file_name() or ''

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
        try:
            return lint_context.settings
        except AttributeError:
            raise RuntimeError(
                "CRITICAL: {}: Calling 'get_view_settings' outside "
                "of lint context".format(self.name))

    def _get_view_settings(self):
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

        # `window.extract_variables` actually resembles data from the
        # `active_view`, so we need to pass in all the relevant data around
        # the filename manually in case the user switches to a different
        # view, before we're done here.
        if filename:
            basename = os.path.basename(filename)
            file_base_name, file_extension = os.path.splitext(basename)

            variables['file'] = filename
            variables['file_path'] = os.path.dirname(filename)
            variables['file_name'] = basename
            variables['file_base_name'] = file_base_name
            variables['file_extension'] = file_extension

        return recursive_replace(variables, settings)

    @staticmethod
    def _guess_project_path(window, filename):
        if not window:
            return None

        folders = window.folders()
        if not folders:
            return None

        if not filename:
            return folders[0]

        for folder in folders:
            # Take the first one; should we take the deepest one? The shortest?
            if filename.startswith(folder + os.path.sep):
                return folder

        return None

    @classmethod
    def which(cls, cmd):
        """Return full path to a given executable.

        This version just delegates to `util.which` but plugin authors can
        override this method.

        Note that this method will be called statically as well as per
        instance. So you *can't* rely on `get_view_settings` to be available.

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
            # happy path?
            if path is None:
                # Do not log, `context_sensitive_executable_path` should have
                # logged already.
                return None
        else:
            if util.can_exec(which):
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
                logger.warning('{} cannot locate \'{}\''.format(self.name, which))
                return None

        cmd[0:1] = util.convert_type(path, [])
        return self.insert_args(cmd)

    def context_sensitive_executable_path(self, cmd):
        """Calculate the context-sensitive executable path.

        Subclasses may override this to return a special path. The default
        implementation looks for a setting `executable` and if set will use
        that.

        Return (True, '<path>') if you can resolve the executable given at cmd[0]
        Return (True, None) if you want to skip the linter
        Return (False, None) if you want to kick in the default implementation
            of SublimeLinter

        Notable: `<path>` can be a list/tuple or str

        """
        settings = self.get_view_settings()
        executable = settings.get('executable', None)
        if executable:
            logger.info(
                "{}: wanted executable is '{}'".format(self.name, executable)
            )

            # If `executable` is an iterable, we can only assume it will work.
            if isinstance(executable, str) and not util.can_exec(executable):
                logger.error(
                    "{} deactivated, cannot locate '{}' "
                    .format(self.name, executable)
                )
                # no fallback, the user specified something, so we err
                return True, None

            return True, executable

        return False, None

    def insert_args(self, cmd):
        """Insert user arguments into cmd and return the result."""
        settings = self.get_view_settings()
        args = self.build_args(settings)

        if '${args}' in cmd:
            i = cmd.index('${args}')
            cmd[i:i + 1] = args
        elif '*' in cmd:  # legacy SL3 crypto-identifier
            i = cmd.index('*')
            cmd[i:i + 1] = args
        else:
            cmd += args

        return cmd

    def get_user_args(self, settings):
        """Return any args the user specifies in settings as a list."""
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

    def get_working_dir(self, settings):
        """Return the working dir for this lint."""
        cwd = settings.get('working_dir', None)

        if cwd:
            if os.path.isdir(cwd):
                return cwd
            else:
                logger.error(
                    "{}: wanted working_dir '{}' is not a directory"
                    "".format(self.name, cwd)
                )
                return None

        filename = self.view.file_name()
        return (
            self._guess_project_path(self.view.window(), filename) or
            (os.path.dirname(filename) if filename else None)
        )

    def get_environment(self, settings):
        """Return runtime environment for this lint."""
        return ChainMap({}, settings.get('env', {}), self.env, BASE_LINT_ENVIRONMENT)

    def get_error_type(self, error, warning):  # noqa:D102
        if error:
            return ERROR
        elif warning:
            return WARNING
        else:
            return self.default_type

    def lint(self, code, view_has_changed, settings):
        """Perform the lint, retrieve the results, and add marks to the view.

        The flow of control is as follows:

        - Get the command line.
        - Run the linter.
        - If the view has been modified in between, stop.
        - Parse the linter output with the regex.
        """
        if self.disabled:
            return []

        canonical_filename = (
            os.path.basename(self.view.file_name()) if self.view.file_name()
            else '<untitled {}>'.format(self.view.buffer_id()))
        logger.info(
            "'{}' is linting '{}'"
            .format(self.name, canonical_filename))

        # Bc of API constraints we cannot pass the settings down, so we attach
        # them to a global `context` obj. Users can call `get_view_settings`
        # as before, and get a consistent settings object.
        lint_context.settings = settings

        # `cmd = None` is a special API signal, that the plugin author
        # implemented its own `run`
        if self.cmd is None:
            output = self.run(None, code)
        else:
            cmd = self.get_cmd()
            if not cmd:  # We couldn't find a executable
                return []
            output = self.run(cmd, code)

        if not output:
            return []

        # If the view has been modified since the lint was triggered, no point in continuing.
        if view_has_changed():
            return None  # ABORT

        if logger.isEnabledFor(logging.INFO):
            import textwrap
            stripped_output = output.replace('\r', '').rstrip()
            logger.info('{} output:\n{}'.format(self.name, textwrap.indent(stripped_output, '    ')))

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
            matches = list(self.regex.finditer(output))
            if not matches:
                logger.info(
                    '{}: No matches for regex: {}'.format(self.name, self.regex.pattern))
                return

            for match in matches:
                yield self.split_match(match)
        else:
            for line in output.splitlines():
                match = self.regex.match(line.rstrip())
                if match:
                    yield self.split_match(match)
                else:
                    logger.info(
                        "{}: No match for line: '{}'".format(self.name, line))

    def split_match(self, match):
        """
        Split a match into the standard elements of an error and return them.

        If subclasses need to modify the values returned by the regex, they
        should override this method, call super(), then modify the values
        and return them.

        """
        match_dict = MATCH_DICT.copy()

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
        else:
            logger.info("'line' is not optional. {}".format(match_dict))
            return None  # log but do not err for now

        col = match_dict["col"]
        if col:
            if col.isdigit():
                col = int(col) - self.line_col_base[1]
            else:
                col = len(col)
            match_dict["col"] = col
        else:
            # `col` is optional, so we exchange an empty string with None
            match_dict["col"] = None

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
            "msg": m.message.strip(),
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
        if len(text) < 3:
            return text

        first = text[0]

        if first in ('\'', '"') and text[-1] == first:
            text = text[1:-1]

        return text

    @classmethod
    def can_lint_view(cls, view):
        selector = cls._get_settings(cls, view.window()).get('selector')
        if selector:
            return (
                view.score_selector(0, selector) or
                view.find_by_selector(selector)
            )

        # Fallback using deprecated `cls.syntax`
        syntax = util.get_syntax(view).lower()

        if not syntax:
            return False

        if cls.syntax == '*':
            return True

        if hasattr(cls.syntax, 'match'):
            return cls.syntax.match(syntax) is not None

        syntaxes = (
            [cls.syntax] if isinstance(cls.syntax, str)
            else list(cls.syntax)
        )
        return syntax in syntaxes

    @classmethod
    @lru_cache(maxsize=None)
    def can_lint(cls, _syntax=None):  # `syntax` stays here for compatibility
        """
        Determine *eagerly* if a linter's 'executable' can run.

        The following tests must all pass for this method to return True:

        1. If the linter uses an external executable, it must be available.
        2. If there is a version requirement and the executable is available,
           its version must fulfill the requirement.
        """
        can = True

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

        if cls.executable_path == '':
            status = '{} deactivated, cannot locate \'{}\''.format(cls.name, cls.executable_path)
            logger.warning(status)
            return False

        if cls.executable_path:
            can = cls.fulfills_version_requirement()

        return can

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
                logger.info(
                    '{}: ({}) satisfied by {}'
                    .format(cls.name, cls.version_requirement, cls.executable_version)
                )
                return True
            else:
                warning = '{} deactivated, version requirement ({}) not fulfilled by {}'
                msg = warning.format(cls.name, cls.version_requirement, cls.executable_version)
                logger.warning(msg)

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
        logger.info('{} version query: {}'.format(cls.name, ' '.join(cmd)))

        version = util.communicate(cmd, output_stream=util.STREAM_BOTH)
        match = cls.version_re.search(version)

        if match:
            version = match.group('version')
            logger.info('{} version: {}'.format(cls.name, version))
            return version
        else:
            logger.warning('no {} version could be extracted from:\n{}'.format(cls.name, version))
            return None

    def run(self, cmd, code):
        """
        Execute the linter's executable or built in code and return its output.

        If a linter uses built in code, it should override this method and return
        a string as the output.

        If a linter needs to do complicated setup or will use the tmpdir
        method, it will need to override this method.

        """
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
            """Attempt to extract extension from filename, return an empty string otherwise."""
            name = self.view.file_name()
            _, suffix = os.path.splitext(name)
            return suffix

    # popen wrappers

    def communicate(self, cmd, code=None):
        """Run an external executable using stdin to pass code and return its output."""
        if '${file}' in cmd:
            cmd[cmd.index('${file}')] = self.filename
        elif '@' in cmd:  # legacy SL3 crypto-identifier
            cmd[cmd.index('@')] = self.filename
        elif code is None:
            cmd.append(self.filename)

        settings = self.get_view_settings()
        cwd = self.get_working_dir(settings)
        env = self.get_environment(settings)

        if logger.isEnabledFor(logging.INFO):
            logger.info('{}: {} {}'.format(
                self.name,
                os.path.basename(self.filename or '<unsaved>'),
                cmd)
            )
            if cwd:
                logger.info('{}: cwd: {}'.format(self.name, cwd))

        return util.communicate(
            cmd,
            code,
            output_stream=self.error_stream,
            env=env,
            cwd=cwd)

    def tmpfile(self, cmd, code, suffix=''):
        """Run an external executable using a temp file to pass code and return its output."""
        settings = self.get_view_settings()
        cwd = self.get_working_dir(settings)
        env = self.get_environment(settings)

        if logger.isEnabledFor(logging.INFO):
            logger.info('{}: {} {}'.format(
                self.name,
                os.path.basename(self.filename or '<unsaved>'),
                cmd)
            )
            if cwd:
                logger.info('{}: cwd: {}'.format(self.name, cwd))

        return util.tmpfile(
            cmd,
            code,
            self.filename,
            suffix or self.get_tempfile_suffix(),
            output_stream=self.error_stream,
            env=env,
            cwd=cwd)
