from collections import namedtuple, OrderedDict, ChainMap, Mapping, Sequence
from contextlib import contextmanager
from fnmatch import fnmatch
import logging
import os
import re
import shlex
import subprocess
import tempfile

import sublime
from . import persist, util
from .const import WARNING, ERROR


logger = logging.getLogger(__name__)


ARG_RE = re.compile(r'(?P<prefix>@|--?)?(?P<name>[@\w][\w\-]*)(?:(?P<joiner>[=:])?(?:(?P<sep>.)(?P<multiple>\+)?)?)?')
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

# _ACCEPTABLE_REASONS_MAP defines a list of acceptable reasons
# for each lint_mode. It aims to provide a better visibility to
# how lint_mode is implemented. The map is supposed to be used in
# this module only.
_ACCEPTABLE_REASONS_MAP = {
    "manual": ("on_user_request",),
    "save": ("on_user_request", "on_save"),
    "load_save": ("on_user_request", "on_save", "on_load"),
    "background": ("on_user_request", "on_save", "on_load", None),
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


class TransientError(Exception):
    ...


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


class ViewSettings:
    """
    Small wrapper around Sublime's view settings so we can use it in a
    ChainMap.

    In the standard Sublime settings system we store flattened objects.
    So what is `{SublimeLinter: {linters: {flake8: args}}}` for the global
    settings, becomes 'SublimeLinter.linters.flake8.args'
    """

    # We need to use a str as marker bc the value gets *serialized* during
    # roundtripping the Sublime API. A normal sentinel obj like `{}` would
    # loose its identity.
    NOT_PRESENT = '__NOT_PRESENT_MARKER__'

    def __init__(self, view, prefix):
        self.view = view
        self.prefix = prefix

    def _compute_final_key(self, key):
        return self.prefix + key

    def __getitem__(self, key):
        value = self.view.settings().get(
            self._compute_final_key(key), self.NOT_PRESENT)
        if value == self.NOT_PRESENT:  # must use '==' (!) see above
            raise KeyError(key)

        return value

    def __contains__(self, key):
        return self.view.settings().has(self._compute_final_key(key))

    def __repr__(self):
        return "ViewSettings({}, {!r})".format(
            self.view.id(), self.prefix.rstrip('.'))


class LinterSettings:
    """
    Smallest possible dict-like container for linter settings to lazy
    substitute/expand variables found in the settings
    """

    def __init__(self, settings, context):
        self.settings = settings
        self.context = context

        self.computed_settings = {}

    def __getitem__(self, key):
        try:
            return self.computed_settings[key]
        except KeyError:
            try:
                value = self.settings[key]
            except KeyError:
                raise KeyError(key)
            else:
                final_value = substitute_variables(self.context, value)
                self.computed_settings[key] = final_value
                return final_value

    def get(self, key, default=None):
        return self[key] if key in self else default

    def __contains__(self, key):
        return key in self.computed_settings or key in self.settings

    def __setitem__(self, key, value):
        self.computed_settings[key] = value

    has = __contains__
    set = __setitem__


def get_raw_linter_settings(linter, view):
    """Return 'raw' linter settings without variables substituted.

    Settings are merged in the following order:

    default settings (on the class)
    global user settings
    project settings
    view settings
    """
    # Note: linter can be a linter class or a linter instance

    defaults = linter.defaults or {}
    user_settings = persist.settings.get('linters', {}).get(linter.name, {})

    # We actually don't want to lint detached views, so failing here
    # when there is no window would be more appropriate, but also less
    # convenient. See `get_linters_for_view` where we check once for detached
    # views, and actually abort the lint job.
    window = view.window()
    if window:
        data = window.project_data() or {}
        project_settings = (
            data.get('SublimeLinter', {})
                .get('linters', {})
                .get(linter.name, {})
        )
    else:
        project_settings = {}

    view_settings = ViewSettings(
        view, 'SublimeLinter.linters.{}.'.format(linter.name))

    return ChainMap({}, view_settings, project_settings, user_settings, defaults)


def get_linter_settings(linter, view):
    """Return 'final' linter settings with all variables expanded."""
    # Note: linter can be a linter class or a linter instance
    settings = get_raw_linter_settings(linter, view)
    context = get_view_context(view)
    return LinterSettings(settings, context)


def guess_project_root_of_view(view):
    window = view.window()
    if not window:
        return None

    folders = window.folders()
    if not folders:
        return None

    filename = view.file_name()
    if not filename:
        return folders[0]

    for folder in folders:
        # Take the first one; should we take the deepest one? The shortest?
        if filename.startswith(folder + os.path.sep):
            return folder

    return None


def get_view_context(view):
    # Note that we ship a enhanced version for 'folder' if you have multiple
    # folders open in a window. See `guess_project_root_of_view`.

    window = view.window()
    context = ChainMap(
        {}, window.extract_variables() if window else {}, os.environ)

    project_folder = guess_project_root_of_view(view)
    if project_folder:
        context['folder'] = project_folder

    # `window.extract_variables` actually resembles data from the
    # `active_view`, so we need to pass in all the relevant data around
    # the filename manually in case the user switches to a different
    # view, before we're done here.
    filename = view.file_name()
    if filename:
        basename = os.path.basename(filename)
        file_base_name, file_extension = os.path.splitext(basename)

        context['file'] = filename
        context['file_path'] = os.path.dirname(filename)
        context['file_name'] = basename
        context['file_base_name'] = file_base_name
        context['file_extension'] = file_extension

    return context


def substitute_variables(variables, value):
    # Utilizes Sublime Text's `expand_variables` API, which uses the
    # `${varname}` syntax and supports placeholders (`${varname:placeholder}`).

    if isinstance(value, str):
        value = sublime.expand_variables(value, variables)
        return os.path.expanduser(value)
    elif isinstance(value, Mapping):
        return {key: substitute_variables(variables, val)
                for key, val in value.items()}
    elif isinstance(value, Sequence):
        return [substitute_variables(variables, item)
                for item in value]
    else:
        return value


class LinterMeta(type):
    """Metaclass for Linter and its subclasses."""

    def __init__(cls, cls_name, bases, attrs):
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

        if cls_name in BASE_CLASSES:
            return

        name = attrs.get('name') or cls_name.lower()
        setattr(cls, 'disabled', None)
        setattr(cls, 'name', name)

        # BEGIN DEPRECATIONS
        for key in ('syntax', 'selectors'):
            if key in attrs:
                logger.warning(
                    "{}: Defining 'cls.{}' has been deprecated. Use "
                    "http://www.sublimelinter.com/en/stable/linter_settings.html#selector"
                    .format(name, key)
                )

        for key in (
            'version_args', 'version_re', 'version_requirement',
            'inline_settings', 'inline_overrides',
            'comment_re', 'shebang_match',
            'npm_name', 'composer_name'
        ):
            if key in attrs:
                logger.info(
                    "{}: Defining 'cls.{}' has no effect anymore. You can "
                    "safely remove these settings.".format(name, key))

        for key in ('build_cmd', 'insert_args'):
            if key in attrs:
                logger.warning(
                    "{}: Do not implement 'cls.{}()'. SublimeLinter will "
                    "change here in the near future.".format(name, key))

        for key in ('can_lint', 'can_lint_syntax'):
            if key in attrs:
                logger.warning(
                    "{}: Implementing 'cls.{}' has no effect anymore. You "
                    "can safely remove these methods.".format(name, key))
        # END DEPRECATIONS

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
            for regex in ('regex', 'word_re'):
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

        if not cls.syntax and 'selector' not in cls.defaults:
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
            sublime.run_command('sublime_linter_config_changed')
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

    # DEPRECATED: Will not be evaluated. They stay here so that old plugins
    # do not throw an AttributeError, but they will always be None
    executable = None
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

    # `disabled` has three states (None, True, False). It takes precedence
    # over all other user or project settings.
    disabled = None

    def __init__(self, view, settings):
        self.view = view
        self.settings = settings
        # Using `self.env` is deprecated, bc it can have surprising
        # side-effects for concurrent/async linting. We initialize it here
        # bc some ruby linters rely on that behavior.
        self.env = {}

        # Ensure instances have their own copy in case a plugin author
        # mangles it.
        if self.defaults is not None:
            self.defaults = self.defaults.copy()

    @property
    def filename(self):
        """Return the view's file path or '' if unsaved."""
        return self.view.file_name() or ''

    @property
    def executable_path(self):
        logger.info(
            "'executable_path' has been deprecated. "
            "Just use an ordinary binary name instead. ")
        return self.executable

    def get_view_settings(self):
        return self.settings

    def notify_failure(self):
        window = self.view.window()
        if window:
            window.run_command('sublime_linter_failed', {
                'bid': self.view.buffer_id(),
                'linter_name': self.name
            })

    def on_stderr(self, output):
        logger.warning('{} output:\n{}'.format(self.name, output))
        logger.info(
            'Note: above warning will become an error in the future. '
            'Implement `on_stderr` if you think this is wrong.')
        self.notify_failure()

    def which(self, cmd):
        """Return full path to a given executable.

        This version just delegates to `util.which` but plugin authors can
        override this method.

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
            logger.warning(
                "The '@python' in '{}' has been deprecated and no effect "
                "anymore. You can safely remove it.".format(which))
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
            # If `cmd` is a method, it can try to find an executable on its own.
            if util.can_exec(which):
                path = which
            else:
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
        """Return a list of args to add to cls.cmd.

        This basically implements our DSL around arguments on the command
        line. See `ARG_RE` and `LinterMeta.map_args`. All potential args
        are defined in `cls.defaults` with a prefix of `-` or `--`.
        (All other defaults are just normal settings.)

        Note that all falsy values except the Zero are skipped. The value
        `True` acts as a flag. In all other cases args are key value pairs.
        """
        args = self.get_user_args(settings)
        args_map = getattr(self, 'args_map', {})

        for setting, arg_info in args_map.items():
            prefix = arg_info['prefix']
            if prefix is None:
                continue

            values = settings.get(setting, None)
            if not values and not values == 0:
                continue

            arg = prefix + arg_info['name']

            # The value 'True' should act like a flag
            if values is True:
                args.append(arg)
                continue
            elif isinstance(values, (list, tuple)):
                # If the values can be passed as a single list, join them now
                if arg_info['sep'] and not arg_info['multiple']:
                    values = [str(value) for value in values]
                    values = [arg_info['sep'].join(values)]
            else:
                values = [values]

            joiner = arg_info['joiner']
            for value in values:
                if prefix == '@':
                    args.append(str(value))
                elif joiner == '=':
                    args.append('{}={}'.format(arg, value))
                else:  # joiner == ':' or ''
                    args.append(arg)
                    args.append(str(value))

        return args

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
            guess_project_root_of_view(self.view) or
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

    @classmethod
    def can_lint_view(cls, view, settings):
        if cls.disabled is True:
            return False

        if cls.disabled is None and settings.get('disable'):
            return False

        if not cls.matches_selector(view, settings):
            return False

        filename = view.file_name()
        filename = os.path.realpath(filename) if filename else '<untitled>'
        excludes = util.convert_type(settings.get('excludes', []), [])
        if excludes:
            for pattern in excludes:
                if pattern.startswith('!'):
                    matched = not fnmatch(filename, pattern[1:])
                else:
                    matched = fnmatch(filename, pattern)

                if matched:
                    logger.info(
                        "{} skipped '{}', excluded by '{}'"
                        .format(cls.name, filename, pattern)
                    )
                    return False

        return True

    @classmethod
    def matches_selector(cls, view, settings):
        selector = settings.get('selector', None)
        if selector is not None:
            return bool(
                # Use `score_selector` here as well, so that empty views
                # select their 'main' linters
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

    def should_lint(self, reason=None):
        """
        should_lint takes reason then decides whether the linter should start or not.

        should_lint allows each Linter to programmatically decide whether it should take
        action on each trigger or not.
        """
        # A 'saved-file-only' linter does not run on unsaved views
        if self.tempfile_suffix == '-' and self.view.is_dirty():
            return False

        fallback_mode = persist.settings.get('lint_mode', 'background')
        settings = self.get_view_settings()
        lint_mode = settings.get('lint_mode', fallback_mode)
        logger.info(
            'Checking lint mode {} vs lint reason {}'
            .format(lint_mode, reason)
        )

        return reason in _ACCEPTABLE_REASONS_MAP[lint_mode]

    def lint(self, code, view_has_changed):
        """Perform the lint, retrieve the results, and add marks to the view.

        The flow of control is as follows:

        - Get the command line.
        - Run the linter.
        - If the view has been modified in between, stop.
        - Parse the linter output with the regex.
        """
        canonical_filename = (
            os.path.basename(self.view.file_name()) if self.view.file_name()
            else '<untitled {}>'.format(self.view.buffer_id()))
        logger.info(
            "'{}' is linting '{}'"
            .format(self.name, canonical_filename))

        # `cmd = None` is a special API signal, that the plugin author
        # implemented its own `run`
        if self.cmd is None:
            output = self.run(None, code)     # type: str
        else:
            cmd = self.get_cmd()
            if not cmd:  # We couldn't find an executable
                self.notify_failure()
                return []

            output = self.run(cmd, code)  # type: util.popen_output

        if view_has_changed():
            raise TransientError('View not consistent.')

        virtual_view = VirtualView(code)
        return self.parse_output(output, virtual_view)

    def parse_output(self, proc, virtual_view):
        # Note: We support type str for `proc`. E.g. the user might have
        # implemented `run`.
        try:
            output, stderr = proc.stdout, proc.stderr
        except AttributeError:
            output = proc
        else:
            # Try to handle `on_stderr`, but only for STREAM_BOTH linters
            if (
                output is not None and
                stderr is not None and
                callable(self.on_stderr)
            ):
                if stderr.strip():
                    self.on_stderr(stderr)
            else:
                output = proc.combined_output

        return self.parse_output_via_regex(output, virtual_view)

    def parse_output_via_regex(self, output, virtual_view):
        if not output:
            return []

        if logger.isEnabledFor(logging.INFO):
            import textwrap
            logger.info('{} output:\n{}'.format(
                self.name, textwrap.indent(output.strip(), 4 * ' ')))

        errors = []
        for m in self.find_errors(output):
            if not m or not m[0]:
                continue

            if not isinstance(m, LintMatch):  # ensure right type
                m = LintMatch(*m)

            if m.message and m.line is not None:
                error = self.process_match(m, virtual_view)
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
            # `line` is not optional, but if a user implements `split_match`
            # and calls `super` first, she has still the chance to fill in
            # a value on her own.
            match_dict["line"] = None

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

    # popen wrappers

    def communicate(self, cmd, code=None):
        """Run an external executable using stdin to pass code and return its output."""
        ctx = get_view_context(self.view)
        ctx['file_on_disk'] = self.filename

        cmd = self.finalize_cmd(
            cmd, ctx, at_value=self.filename, auto_append=code is None)
        return self._communicate(cmd, code)

    def tmpfile(self, cmd, code, suffix=None):
        """Create temporary file with code and lint it."""
        if suffix is None:
            suffix = self.get_tempfile_suffix()

        with make_temp_file(suffix, code) as file:
            ctx = get_view_context(self.view)
            ctx['file_on_disk'] = self.filename
            ctx['temp_file'] = file.name

            cmd = self.finalize_cmd(
                cmd, ctx, at_value=file.name, auto_append=True)
            return self._communicate(cmd)

    def finalize_cmd(self, cmd, context, at_value='', auto_append=False):
        # Note: Both keyword arguments are deprecated.
        original_cmd = cmd
        cmd = substitute_variables(context, cmd)
        if '@' in cmd:
            logger.info(
                'The `@` symbol in cmd has been deprecated. Use $file, '
                '$temp_file or $file_on_disk instead.')
            cmd[cmd.index('@')] = at_value

        if cmd == original_cmd and auto_append:
            logger.info(
                'Automatically appending the filename to cmd has been '
                'deprecated. Use $file, $temp_file or $file_on_disk instead.')
            cmd.append(at_value)

        return cmd

    def get_tempfile_suffix(self):
        """Return a good filename suffix."""
        if self.view.file_name():
            name = self.view.file_name()
            _, suffix = os.path.splitext(name)

        elif isinstance(self.tempfile_suffix, dict):
            syntax = util.get_syntax(self.view)
            try:
                suffix = self.tempfile_suffix[syntax]
            except KeyError:
                logger.info(
                    'No default filename suffix for the syntax `{}` '
                    'defined in `tempfile_suffix`.'.format(syntax)
                )
                suffix = ''

        else:
            suffix = self.tempfile_suffix

        if suffix and not suffix.startswith('.'):
            suffix = '.' + suffix

        return suffix

    def _communicate(self, cmd, code=None):
        """Run command and return result."""
        settings = self.get_view_settings()
        cwd = self.get_working_dir(settings)
        env = self.get_environment(settings)

        output_stream = self.error_stream
        view = self.view

        if code is not None:
            code = code.encode('utf8')

        uses_stdin = code is not None
        stdin = subprocess.PIPE if uses_stdin else None
        stdout = subprocess.PIPE if output_stream & util.STREAM_STDOUT else None
        stderr = subprocess.PIPE if output_stream & util.STREAM_STDERR else None

        try:
            proc = subprocess.Popen(
                cmd, env=env, cwd=cwd,
                stdin=stdin, stdout=stdout, stderr=stderr,
                startupinfo=util.create_startupinfo(),
                creationflags=util.get_creationflags()
            )
        except Exception as err:
            augmented_env = dict(ChainMap(*env.maps[0:-1]))
            logger.error(make_nice_log_message(
                '  Execution failed\n\n  {}'.format(str(err)),
                cmd, uses_stdin, cwd, view, augmented_env))

            self.notify_failure()
            return ''

        if logger.isEnabledFor(logging.INFO):
            logger.info(make_nice_log_message(
                'Running ...', cmd, uses_stdin, cwd, view, env=None))

        bid = view.buffer_id()
        with store_proc_while_running(bid, proc):
            try:
                out = proc.communicate(code)

            except BrokenPipeError as err:
                friendly_terminated = getattr(proc, 'friendly_terminated', False)
                if friendly_terminated:
                    logger.info('Broken pipe after friendly terminating '
                                '<pid {}>'.format(proc.pid))
                    raise TransientError('Friendly terminated')
                else:
                    logger.warning('Exception: {}'.format(str(err)))
                    self.notify_failure()
                    return ''

            except OSError as err:
                # There are rare reports of '[Errno 9] Bad file descriptor'.
                # We just eat them here for user convenience, although there
                # is no deeper knowledge about why this happens.
                if err.errno == 9:
                    logger.warning('Exception: {}'.format(str(err)))
                    self.notify_failure()
                    raise TransientError('Bad File Descriptor')
                else:
                    raise

            else:
                friendly_terminated = getattr(proc, 'friendly_terminated', False)
                if friendly_terminated:
                    raise TransientError('Friendly terminated')

        return util.popen_output(proc, *out)


@contextmanager
def make_temp_file(suffix, code):
    file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        file.write(bytes(code, 'UTF-8'))
        file.close()
        yield file

    finally:
        os.remove(file.name)


@contextmanager
def store_proc_while_running(bid, proc):
    with persist.active_procs_lock:
        persist.active_procs[bid].append(proc)

    try:
        yield proc
    finally:
        with persist.active_procs_lock:
            persist.active_procs[bid].remove(proc)


RUNNING_TEMPLATE = """{headline}

  {cwd}  (working dir)
  {prompt}{pipe} {cmd}
"""

PIPE_TEMPLATE = ' type {} |' if os.name == 'nt' else ' cat {} |'
ENV_TEMPLATE = """
  Modified environment:

  {env}

  Type: `import os, pprint; pprint.pprint(os.environ.copy())` in the Sublime console to get the full environment.
"""


def make_nice_log_message(headline, cmd, is_stdin,
                          cwd, view, env=None):
    import pprint
    import textwrap

    filename = view.file_name()
    if filename and cwd:
        rel_filename = os.path.relpath(filename, cwd)
    elif not filename:
        rel_filename = '<buffer {}>'.format(view.buffer_id())

    real_cwd = cwd if cwd else os.path.realpath(os.path.curdir)

    on_win = os.name == 'nt'
    exec_msg = RUNNING_TEMPLATE.format(
        headline=headline,
        cwd=real_cwd,
        prompt='>' if on_win else '$',
        pipe=PIPE_TEMPLATE.format(rel_filename) if is_stdin else '',
        cmd=subprocess.list2cmdline(cmd) if on_win else ' '.join(cmd)
    )

    env_msg = ENV_TEMPLATE.format(
        env=textwrap.indent(
            pprint.pformat(env, indent=2),
            '  ',
            predicate=lambda line: not line.startswith('{')
        )
    ) if env else ''

    return exec_msg + env_msg
