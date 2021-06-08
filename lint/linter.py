from collections import ChainMap, Mapping, Sequence
from contextlib import contextmanager
from fnmatch import fnmatch
from functools import lru_cache
import inspect
from itertools import chain
import logging
import os
import re
import shlex
import subprocess
import tempfile

import sublime
from . import persist, util
from .const import WARNING, ERROR


MYPY = False
if MYPY:
    from typing import (
        Any, Callable, Dict, List, IO, Iterator, Match, MutableMapping,
        Optional, Pattern, Tuple, Type, Union
    )
    from .persist import LintError

    Reason = str


logger = logging.getLogger(__name__)


ARG_RE = re.compile(r'(?P<prefix>@|--?)?(?P<name>[@\w][\w\-]*)(?:(?P<joiner>[=:])?(?:(?P<sep>.)(?P<multiple>\+)?)?)?')
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

# ACCEPTED_REASONS_PER_MODE defines a list of acceptable reasons
# for each lint_mode. It aims to provide a better visibility to
# how lint_mode is implemented. The map is supposed to be used in
# this module only.
ACCEPTED_REASONS_PER_MODE = {
    "manual": ("on_user_request",),
    "save": ("on_user_request", "on_save"),
    "load_save": ("on_user_request", "on_save", "on_load"),
    "background": ("on_user_request", "on_save", "on_load", 'on_modified'),
}  # type: Dict[str, Tuple[str, ...]]
KNOWN_REASONS = set(chain(*ACCEPTED_REASONS_PER_MODE.values()))

LEGACY_LINT_MATCH_DEF = ("match", "line", "col", "error", "warning", "message", "near")
COMMON_CAPTURING_NAMES = (
    "filename", "error_type", "code", "end_line", "end_col"
) + LEGACY_LINT_MATCH_DEF


class LintMatch(dict):
    """Convenience dict-a-like type representing Lint errors.

    Historically, lint errors were tuples, and later namedtuples. This dict
    class implements enough to be backwards compatible to a namedtuple as a
    `LEGACY_LINT_MATCH_DEF` set.

    Some convenience for the user: All present keys can be accessed like an
    attribute. All commonly used names (see: COMMON_CAPTURING_NAMES) can
    be safely accessed like an attribute, returning `None` if not present.
    E.g.

        error = LintMatch({'foo': 'bar'})
        error.foo  # 'bar'
        error.error_type  # None
        error.quux  # raises AttributeError

    """

    if MYPY:
        match = None       # type: Optional[object]
        filename = None    # type: Optional[str]
        line = None        # type: int
        col = None         # type: Optional[int]
        end_line = None    # type: Optional[int]
        end_col = None     # type: Optional[int]
        error_type = None  # type: Optional[str]
        code = None        # type: Optional[str]
        message = None     # type: str
        error = None       # type: Optional[str]
        warning = None     # type: Optional[str]
        near = None        # type: Optional[str]

    def __init__(self, *args, **kwargs):
        if len(args) == 7:
            self.update(zip(LEGACY_LINT_MATCH_DEF, args))
        else:
            super().__init__(*args, **kwargs)

    def _replace(self, **kwargs):
        self.update(kwargs)
        return self

    def __getattr__(self, name):
        if name in COMMON_CAPTURING_NAMES:
            return self.get(name, '' if name == 'message' else None)

        try:
            return self[name]
        except KeyError:
            raise AttributeError(
                "'{}' object has no attribute '{}'".format(type(self).__name__, name)
            ) from None

    def __getitem__(self, name):
        if isinstance(name, int):
            return tuple(iter(self))[name]
        return super().__getitem__(name)

    def __iter__(self):
        return iter(tuple(getattr(self, name) for name in LEGACY_LINT_MATCH_DEF))

    def copy(self):
        return type(self)(self)

    def __repr__(self):
        return "{}({})".format(type(self).__name__, super().__repr__())


class TransientError(Exception):
    ...


class PermanentError(Exception):
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
        # type: (int) -> Tuple[int, int]
        """Return the start/end character positions for the given line."""
        start = self._newlines[line]
        end = self._newlines[min(line + 1, len(self._newlines) - 1)]
        return start, end

    def full_line_region(self, line):
        # type: (int) -> sublime.Region
        """Return the (full) line region including any trailing newline char."""
        return sublime.Region(*self.full_line(line))

    def line_region(self, line):
        # type: (int) -> sublime.Region
        """Return the line region without the possible trailing newline char."""
        r = self.full_line_region(line)
        t = self.substr(r).rstrip('\n')
        return sublime.Region(r.a, r.a + len(t))

    def select_line(self, line):
        # type: (int) -> str
        """Return code for the given line."""
        start, end = self.full_line(line)
        return self._code[start:end]

    def max_lines(self):
        # type: () -> int
        return len(self._newlines) - 2

    def size(self):
        # type: () -> int
        return len(self._code)

    def substr(self, region):
        # type: (sublime.Region) -> str
        return self._code[region.begin():region.end()]

    # Actual Sublime API would look like:
    # def full_line(self, region)
    # def full_line(self, point) => Region
    # def substr(self, region)
    # def text_point(self, row, col) => Point
    # def rowcol(self, point) => (row, col)

    @staticmethod
    def from_file(filename):
        # type: (str) -> VirtualView
        """Return a VirtualView with the contents of file."""
        return _virtual_view_from_file(filename, os.path.getmtime(filename))


@lru_cache(maxsize=128)
def _virtual_view_from_file(filename, mtime):
    # type: (str, float) -> VirtualView
    with open(filename, 'r', encoding='utf8') as f:
        return VirtualView(f.read())


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


NOT_EXPANDABLE_SETTINGS = {
    "lint_mode",
    "selector",
    "disable",
    "filter_errors",
}


class LinterSettings:
    """
    Smallest possible dict-like container for linter settings to lazy
    substitute/expand variables found in the settings
    """

    def __init__(self, raw_settings, context, _computed_settings=None):
        # type: (Mapping[str, Any], Mapping[str, str], MutableMapping[str, Any]) -> None
        self.raw_settings = raw_settings
        self.context = context

        self._computed_settings = {} if _computed_settings is None else _computed_settings

    def __getitem__(self, key):
        # type: (str) -> Any
        if key in NOT_EXPANDABLE_SETTINGS:
            return self.raw_settings[key]

        try:
            return self._computed_settings[key]
        except KeyError:
            try:
                value = self.raw_settings[key]
            except KeyError:
                raise KeyError(key)
            else:
                final_value = substitute_variables(self.context, value)
                self._computed_settings[key] = final_value
                return final_value

    def get(self, key, default=None):
        # type: (str, Any) -> Any
        return self[key] if key in self else default

    def __contains__(self, key):
        # type: (str) -> bool
        return key in self._computed_settings or key in self.raw_settings

    def __setitem__(self, key, value):
        # type: (str, Any) -> None
        self._computed_settings[key] = value

    has = __contains__
    set = __setitem__

    def clone(self):
        # type: () -> LinterSettings
        return self.__class__(
            self.raw_settings,
            # Dirt-alert: We clone here bc we extract this context-object
            # in `Linter.__init__`. In the scope of a linter instance,
            # `self.context == self.settings.context` must hold.
            ChainMap({}, self.context),
            ChainMap({}, self._computed_settings)
        )


def substitute_variables(variables, value):
    # type: (Mapping, Any) -> Any
    # Utilizes Sublime Text's `expand_variables` API, which uses the
    # `${varname}` syntax and supports placeholders (`${varname:placeholder}`).

    if isinstance(value, str):
        # Workaround https://github.com/SublimeTextIssues/Core/issues/1878
        # (E.g. UNC paths on Windows start with double slashes.)
        value = value.replace(r'\\', r'\\\\')
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


def get_linter_settings(linter, view, context=None):
    # type: (Type[Linter], sublime.View, Optional[Mapping[str, str]]) -> LinterSettings
    """Return 'final' linter settings with all variables expanded."""
    if context is None:
        context = get_view_context(view)
    else:
        context = ChainMap({}, context)

    settings = get_raw_linter_settings(linter, view)
    return LinterSettings(settings, context)


def get_raw_linter_settings(linter, view):
    # type: (Type[Linter], sublime.View) -> MutableMapping[str, Any]
    """Return 'raw' linter settings without variables substituted."""
    defaults = linter.defaults or {}
    global_settings = persist.settings.get('linters', {}).get(linter.name, {})
    view_settings = ViewSettings(
        view, 'SublimeLinter.linters.{}.'.format(linter.name)
    )  # type: Mapping[str, Any]  # type: ignore

    return ChainMap(
        {},
        view_settings,
        global_settings,
        defaults,
        {'lint_mode': persist.settings.get('lint_mode')}
    )


def _extract_window_variables(window):
    # type: (sublime.Window) -> Dict[str, str]
    # We explicitly want to compute all variables around the current file
    # on our own.
    variables = window.extract_variables()
    for key in (
        'file', 'file_path', 'file_name', 'file_base_name', 'file_extension'
    ):
        variables.pop(key, None)
    return variables


def get_view_context(view, additional_context=None):
    # type: (sublime.View, Optional[Mapping]) -> MutableMapping[str, str]
    # Note that we ship a enhanced version for 'folder' if you have multiple
    # folders open in a window. See `guess_project_root_of_view`.

    window = view.window()
    context = ChainMap(
        {}, _extract_window_variables(window) if window else {}, os.environ
    )  # type: MutableMapping[str, str]

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

    context['canonical_filename'] = util.get_filename(view)

    if additional_context:
        context.update(additional_context)

    return context


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
        if os.path.commonprefix([folder, filename]) == folder:
            return folder

    return None


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
        cls.logger = logging.getLogger('SublimeLinter.plugin.{}'.format(name))

        # BEGIN DEPRECATIONS
        for key in ('syntax', 'selectors'):
            if key in attrs:
                logger.error(
                    "{}: Defining 'cls.{}' has no effect anymore. Use "
                    "http://www.sublimelinter.com/en/stable/linter_settings.html#selector "
                    "instead."
                    .format(name, key)
                )
                cls.disabled = True

        for key in (
            'version_args', 'version_re', 'version_requirement',
            'inline_settings', 'inline_overrides',
            'comment_re', 'shebang_match',
            'npm_name', 'composer_name',
            'executable', 'executable_path',
            'tab_width', 'config_file'
        ):
            if key in attrs:
                logger.warning(
                    "{}: Defining 'cls.{}' has no effect. Please cleanup and "
                    "remove this setting.".format(name, key))

        for key in ('build_cmd', 'insert_args'):
            if key in attrs:
                logger.warning(
                    "{}: Do not implement '{}'. SublimeLinter will "
                    "change here in the near future.".format(name, key))

        for key in ('can_lint', 'can_lint_syntax'):
            if key in attrs:
                logger.warning(
                    "{}: Implementing 'cls.{}' has no effect anymore. You "
                    "can safely remove this method.".format(name, key))

        if (
            'should_lint' in attrs
            and not isinstance(attrs['should_lint'], classmethod)
        ):
            logger.error(
                "{} disabled. 'should_lint' now is a `@classmethod` and has a "
                "different call signature. \nYou need to adapt the plugin code "
                "because as it is the linter cannot run and thus will be "
                "disabled.  :-( \n\n"
                "(Extending 'should_lint' is an edge-case and you probably don't "
                "even need it, but if you do look it up \nin the source code on "
                "GitHub.)"
                .format(name))
            cls.disabled = True

        if (
            'get_environment' in attrs
            and not len(inspect.getfullargspec(attrs['get_environment']).args) == 1
        ):
            logger.error(
                "{} disabled. 'get_environment' now has a simplified signature:\n"
                "    def get_environment(self): ...\n"
                "The settings object can be retrieved via `self.settings`.\n"
                "You need to update the linter plugin because as it is the "
                "linter cannot run and thus will be disabled.  :-("
                .format(name))
            cls.disabled = True

        if (
            'get_working_dir' in attrs
            and not len(inspect.getfullargspec(attrs['get_working_dir']).args) == 1
        ):
            logger.error(
                "{} disabled. 'get_working_dir' now has a simplified signature:\n"
                "    def get_working_dir(self): ...\n"
                "The settings object can be retrieved via `self.settings`.\n"
                "You need to update the linter plugin because as it is the "
                "linter cannot run and thus will be disabled.  :-("
                .format(name))
            cls.disabled = True
        # END DEPRECATIONS

        # BEGIN CLASS MUTATIONS
        cmd = attrs.get('cmd')
        if isinstance(cmd, str):
            setattr(cls, 'cmd', shlex.split(cmd))

        if attrs.get('multiline', False):
            cls.re_flags |= re.MULTILINE

        for regex in ('regex', 'word_re'):
            attr = attrs.get(regex)

            if isinstance(attr, str):
                try:
                    setattr(cls, regex, re.compile(attr, cls.re_flags))
                except re.error as err:
                    logger.error(
                        '{} disabled, error compiling {}: {}.'
                        .format(name, regex, str(err))
                    )
                    cls.disabled = True
                else:
                    if regex == 'regex' and cls.regex.flags & re.M == re.M:
                        cls.multiline = True

        # If this class has its own defaults, create an args_map.
        defaults = attrs.get('defaults', None)
        if defaults and isinstance(defaults, dict):
            cls.map_args(attrs['defaults'])
        # END CLASS MUTATIONS

        # BEGIN VALIDATION
        if not cls.cmd and cls.cmd is not None:
            logger.error(
                "{} disabled, 'cmd' must be specified."
                .format(name)
            )
            cls.disabled = True

        if not isinstance(cls.defaults, dict):
            logger.error(
                "{} disabled. 'cls.defaults' is mandatory and MUST be a dict."
                .format(name)
            )
            cls.disabled = True
        elif 'selector' not in cls.defaults:
            if 'defaults' not in attrs:
                logger.error(
                    "{} disabled. 'cls.defaults' is mandatory and MUST be a dict."
                    .format(name)
                )
            else:
                logger.error(
                    "{} disabled. 'selector' is mandatory in 'cls.defaults'.\n See "
                    "http://www.sublimelinter.com/en/stable/linter_settings.html#selector"
                    .format(name))
            cls.disabled = True
        # END VALIDATION

        if cls.disabled:
            return

        register_linter(name, cls)

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


def register_linter(name, cls):
    """Add a linter class to our mapping of class names <-> linter classes."""
    persist.linter_classes[name] = cls

    # Trigger a re-lint if SublimeLinter is already up and running. On Sublime
    # start, this is generally not necessary, because SL will trigger various
    # synthetic `on_activated_async` events on load.
    if persist.api_ready:
        deprecation_warning.cache_clear()
        sublime.run_command('sublime_linter_config_changed')
        logger.info('{} linter reloaded'.format(name))


@lru_cache(4)
def deprecation_warning(msg):
    logger.warning(msg)


class Linter(metaclass=LinterMeta):
    """
    The base class for linters.

    Subclasses must at a minimum define the attributes syntax, cmd, and regex.

    """

    #
    # Public attributes
    #
    name = ''
    logger = None  # type: logging.Logger

    # A string, list, tuple or callable that returns a string, list or tuple, containing the
    # command line (with arguments) used to lint.
    cmd = ''  # type: Union[None, str, List[str], Tuple[str, ...]]

    # A regex pattern used to extract information from the executable's output.
    regex = None  # type: Union[None, str, Pattern]

    # Set to True if the linter outputs multiline error messages. When True,
    # regex will be created with the re.MULTILINE flag. If instead, you set
    # the re.MULTILINE flag within the regex yourself, we in turn set this attribute
    # to True automatically.
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
    tempfile_suffix = None  # type: Union[None, str, Dict[str, str]]

    # Linters may output to both stdout and stderr. By default stdout and sterr are captured.
    # If a linter will never output anything useful on a stream (including when
    # there is an error within the linter), you can ignore that stream by setting
    # this attribute to the other stream.
    error_stream = util.STREAM_BOTH

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
    defaults = {}  # type: Dict[str, Any]

    # `disabled` has three states (None, True, False). It takes precedence
    # over all other user or project settings.
    disabled = None  # type: Union[None, bool]

    def __init__(self, view, settings):
        # type: (sublime.View, LinterSettings) -> None
        self.view = view
        self.settings = settings
        # Simplify tests which often just pass in a dict instead of
        # real `LinterSettings`.
        self.context = getattr(settings, 'context', {})  # type: MutableMapping[str, str]
        # Using `self.env` is deprecated, bc it can have surprising
        # side-effects for concurrent/async linting. We initialize it here
        # bc some ruby linters rely on that behavior.
        self.env = {}  # type: Dict[str, str]

        # Ensure instances have their own copy in case a plugin author
        # mangles it.
        if self.defaults is not None:
            self.defaults = self.defaults.copy()

    @property
    def filename(self):
        # type: () -> str
        """Return the view's file path or '' if unsaved."""
        return self.view.file_name() or ''

    @property
    def executable_path(self):
        deprecation_warning(
            "{}: `executable_path` has been deprecated. "
            "Just use an ordinary binary name instead. "
            .format(self.name)
        )
        return getattr(self, 'executable', '')

    def get_view_settings(self):
        deprecation_warning(
            "{}: `self.get_view_settings()` has been deprecated.  "
            "Just use the member `self.settings` which is the same thing."
            .format(self.name)
        )
        return self.settings

    def notify_failure(self):
        # Side-effect: the status bar will show `(erred)`
        window = self.view.window()
        if window:
            window.run_command('sublime_linter_failed', {
                'filename': util.get_filename(self.view),
                'linter_name': self.name
            })

    def notify_unassign(self):
        # Side-effect: the status bar will not show the linter at all
        window = self.view.window()
        if window:
            window.run_command('sublime_linter_unassigned', {
                'filename': util.get_filename(self.view),
                'linter_name': self.name
            })

    def on_stderr(self, output):
        self.logger.warning('{} output:\n{}'.format(self.name, output))
        self.logger.info(
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
        # type: () -> Optional[List[str]]
        """
        Calculate and return a tuple/list of the command line to be executed.

        The cmd class attribute may be a string, a tuple/list, or a callable.
        If cmd is callable, it is called. If the result of the method is
        a string, it is parsed into a list with shlex.split.

        Otherwise the result of build_cmd is returned.
        """
        assert self.cmd is not None

        cmd = self.cmd
        if callable(cmd):
            cmd = cmd()

        if isinstance(cmd, str):
            cmd = shlex.split(cmd)
        else:
            cmd = list(cmd)

        return self.build_cmd(cmd)

    def build_cmd(self, cmd):
        # type: (List[str]) -> Optional[List[str]]
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
            path = self.which(which)
            if not path:
                self.logger.warning(
                    "{} cannot locate '{}'\n"
                    "Please refer to the readme of this plugin and our troubleshooting guide: "
                    "http://www.sublimelinter.com/en/stable/troubleshooting.html"
                    .format(self.name, which)
                )
                return None

        cmd[0:1] = util.ensure_list(path)
        return self.insert_args(cmd)

    def context_sensitive_executable_path(self, cmd):
        # type: (List[str]) -> Tuple[bool, Union[None, str, List[str]]]
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
        executable = self.settings.get('executable', None)  # type: Union[None, str, List[str]]
        if executable:
            wanted_executable, *rest = util.ensure_list(executable)
            resolved_executable = self.which(wanted_executable)
            if not resolved_executable:
                if os.path.isabs(wanted_executable):
                    message = (
                        "You set 'executable' to {!r}.  "
                        "However, '{}' does not exist or is not executable. "
                        .format(executable, wanted_executable)
                    )
                else:
                    message = (
                        "You set 'executable' to {!r}.  "
                        "However, 'which {}' returned nothing.\n"
                        "Try setting an absolute path to the binary. "
                        "Also refer our troubleshooting guide: "
                        "http://www.sublimelinter.com/en/stable/troubleshooting.html"
                        .format(executable, wanted_executable)
                    )
                self.logger.error(message)
                self.notify_failure()
                raise PermanentError()

            self.logger.info(
                "{}: wanted executable is {!r}".format(self.name, executable)
            )
            return True, [resolved_executable] + rest

        return False, None

    def insert_args(self, cmd):
        # type: (List[str]) -> List[str]
        """Insert user arguments into cmd and return the result."""
        args = self.build_args(self.settings)

        if '${args}' in cmd:
            i = cmd.index('${args}')
            cmd[i:i + 1] = args
        elif '*' in cmd:
            deprecation_warning(
                "{}: Usage of '*' as a special marker in `cmd` has been "
                "deprecated, use '${{args}}' instead."
                .format(self.name)
            )
            i = cmd.index('*')
            cmd[i:i + 1] = args
        else:
            cmd += args

        return cmd

    def get_user_args(self, settings):
        # type: (LinterSettings) -> List[str]
        """Return any args the user specifies in settings as a list."""
        args = settings.get('args', [])

        if isinstance(args, str):
            args = shlex.split(args)
        else:
            args = args[:]

        return args

    def build_args(self, settings):
        # type: (LinterSettings) -> List[str]
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
            if not values and type(values) is not int:  # Allow `0`!
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
                # We call `substitute_variables` in `finalize_cmd` on the whole
                # command. Since all settings are already transparently
                # 'expanded' we need to make sure to escape remaining '$' chars
                # in the arg value here which otherwise denote variables within
                # Sublime.
                final_value = str(value).replace('$', r'\$')
                if prefix == '@':
                    args.append(final_value)
                elif joiner == '=':
                    args.append('{}={}'.format(arg, final_value))
                else:  # joiner == ':' or ''
                    args.append(arg)
                    args.append(final_value)

        return args

    def get_working_dir(self, settings=None):
        # type: (...) -> Optional[str]
        """Return the working dir for this lint."""
        if settings is not None:
            deprecation_warning(
                "{}: Passing a `settings` object down to `get_working_dir` "
                "has been deprecated and no effect anymore.  "
                "Just use `self.get_working_dir()`."
                .format(self.name)
            )

        cwd = self.settings.get('working_dir', None)
        if cwd:
            if os.path.isdir(cwd):
                return cwd
            else:
                self.logger.error(
                    "{}: wanted working_dir '{}' is not a directory"
                    .format(self.name, cwd)
                )
                return None

        return self.context.get('project_root') or self.context.get('folder') or self.context.get('file_path')

    def get_environment(self, settings=None):
        # type: (...) -> ChainMap
        """Return runtime environment for this lint."""
        if settings is not None:
            deprecation_warning(
                "{}: Passing a `settings` object down to `get_environment` "
                "has been deprecated and no effect anymore.  "
                "Just use `self.get_environment()`."
                .format(self.name)
            )

        return ChainMap({}, self.settings.get('env', {}), self.env, BASE_LINT_ENVIRONMENT)

    @classmethod
    def can_lint_view(cls, view, settings):
        # type: (sublime.View, LinterSettings) -> bool
        """Decide wheter the linter is applicable to given view."""
        if cls.disabled is True:
            return False

        if cls.disabled is None and settings.get('disable'):
            return False

        if not cls.matches_selector(view, settings):
            return False

        excludes = settings.get('excludes', [])  # type: Union[str, List[str]]
        if excludes:
            filename = view.file_name() or '<untitled>'
            for pattern in util.ensure_list(excludes):
                if pattern.startswith('!'):
                    matched = not fnmatch(filename, pattern[1:])
                else:
                    matched = fnmatch(filename, pattern)

                if matched:
                    cls.logger.info(
                        "{} skipped '{}', excluded by '{}'"
                        .format(cls.name, filename, pattern)
                    )
                    return False

        return True

    @classmethod
    def matches_selector(cls, view, settings):
        # type: (sublime.View, LinterSettings) -> bool
        selector = settings.get('selector', None)
        if selector is not None:
            return bool(
                # Use `score_selector` here as well, so that empty views
                # select their 'main' linters
                view.score_selector(0, selector) or
                view.find_by_selector(selector)
            )
        return False

    @classmethod
    def should_lint(cls, view, settings, reason):
        # type: (sublime.View, LinterSettings, Reason) -> bool
        """Decide whether the linter can run at this point in time."""
        # A 'saved-file-only' linter does not run on unsaved views
        if cls.tempfile_suffix == '-' and (
            view.is_dirty() or not view.file_name()
        ):
            return False

        if reason not in KNOWN_REASONS:  # be open
            cls.logger.info(
                "{}: Unknown reason '{}' is okay."
                .format(cls.name, reason)
            )
            return True

        lint_mode = settings.get('lint_mode')
        if lint_mode not in ACCEPTED_REASONS_PER_MODE:
            cls.logger.warning(
                "{}: Unknown lint mode '{}'.  "
                "Check your SublimeLinter settings for typos."
                .format(cls.name, lint_mode)
            )
            return True

        ok = reason in ACCEPTED_REASONS_PER_MODE[lint_mode]
        cls.logger.info(
            "{}: Checking lint mode '{}' vs lint reason '{}'.  {}"
            .format(cls.name, lint_mode, reason, 'Ok.' if ok else 'Skip.')
        )
        return ok

    def lint(self, code, view_has_changed):
        # type: (str, Callable[[], bool]) -> List[LintError]
        """Perform the lint, retrieve the results, and add marks to the view.

        The flow of control is as follows:

        - Get the command line.
        - Run the linter.
        - If the view has been modified in between, stop.
        - Parse the linter output with the regex.
        """
        self.logger.info(
            "{}: linting '{}'"
            .format(self.name, util.canonical_filename(self.view)))

        # `cmd = None` is a special API signal, that the plugin author
        # implemented its own `run`
        if self.cmd is None:
            output = self.run(None, code)  # type: Union[str, util.popen_output]
        else:
            cmd = self.get_cmd()
            if not cmd:
                self.notify_failure()
                raise PermanentError("couldn't find an executable")

            output = self.run(cmd, code)

        if view_has_changed():
            raise TransientError('View not consistent.')

        virtual_view = VirtualView(code)
        return self.filter_errors(self.parse_output(output, virtual_view))

    def filter_errors(self, errors):
        # type: (Iterator[LintError]) -> List[LintError]
        filter_patterns = self.settings.get('filter_errors') or []
        if isinstance(filter_patterns, str):
            filter_patterns = [filter_patterns]

        filters = []
        try:
            for pattern in filter_patterns:
                try:
                    filters.append(re.compile(pattern, re.I))
                except re.error as err:
                    self.logger.error(
                        "'{}' in 'filter_errors' is not a valid "
                        "regex pattern: '{}'.".format(pattern, err)
                    )

        except TypeError:
            self.logger.error(
                "'filter_errors' must be set to a string or a list of strings.\n"
                "Got '{}' instead".format(filter_patterns))

        return [
            error
            for error in errors
            if not any(
                pattern.search(': '.join([error['error_type'], error['code'], error['msg']]))
                for pattern in filters
            )
        ]

    def parse_output(self, proc, virtual_view):
        # type: (Union[str, util.popen_output], VirtualView) -> Iterator[LintError]
        # Note: We support type str for `proc`. E.g. the user might have
        # implemented `run`.
        if isinstance(proc, util.popen_output):
            # Split output, but only for STREAM_BOTH linters, and if
            # `on_stderr` is defined.
            if (
                proc.stdout is not None and
                proc.stderr is not None and
                callable(self.on_stderr)
            ):
                output, stderr = proc.stdout, proc.stderr
                if stderr.strip():
                    self.on_stderr(stderr)
            else:
                output = proc.combined_output
        else:
            output = proc

        return self.parse_output_via_regex(output, virtual_view)

    def parse_output_via_regex(self, output, virtual_view):
        # type: (str, VirtualView) -> Iterator[LintError]
        if not output:
            self.logger.info('{}: no output'.format(self.name))
            return

        if self.logger.isEnabledFor(logging.INFO):
            import textwrap
            self.logger.info('{}: output:\n{}'.format(
                self.name, textwrap.indent(output.strip(), '  ')))

        for m in self.find_errors(output):
            if not m:
                continue

            if not isinstance(m, LintMatch):  # ensure right type
                m = LintMatch(*m)

            if m.message and m.line is not None:
                error = self.process_match(m, virtual_view)
                if error:
                    yield error

    def find_errors(self, output):
        # type: (str) -> Iterator[LintMatch]
        """
        Match the linter's regex against the linter output with this generator.

        If multiline is True, split_match is called for each non-overlapping
        match of self.regex. If False, split_match is called for each line
        in output.
        """
        if not self.regex:
            self.logger.error(
                "{}: 'self.regex' is not defined.  If this is intentional "
                "because e.g. the linter reports JSON, implement your own "
                "'def find_errors(self, output)'."
                .format(self.name)
            )
            raise PermanentError("regex not defined")

        if MYPY:
            assert isinstance(self.regex, Pattern)
            match = None  # type: Optional[Match]

        if self.multiline:
            matches = list(self.regex.finditer(output))
            if not matches:
                self.logger.info(
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
                    self.logger.info(
                        "{}: No match for line: '{}'".format(self.name, line))

    def split_match(self, match):
        # type: (Match) -> LintMatch
        """Convert the regex match to a `LintMatch`

        Basically, a `LintMatch` is the dict of the named capturing groups
        of the user provided regex (AKA `match.groupdict()`).

        The only difference is that we cast `line` and `col` to int's if
        provided.

        Plugin authors can implement this method to skip or modify errors.
        Notes: If you want to skip this error just return `None`. If you want
        to modify the values just mutate the dict. E.g.

            error = super().split_match(match)
            error['message'] = 'The new message'
            # OR:
            error.update({'message': 'Hi!'})
            return error

        """
        error = LintMatch(match.groupdict())
        error['match'] = match
        error['line'] = self.apply_line_base(error.get('line'))
        error['end_line'] = self.apply_line_base(error.get('end_line'))
        error['end_col'] = self.apply_col_base(error.get('end_col'))

        col = error.get('col')
        if col and not col.isdigit():
            error['col'] = len(col)
        else:
            error['col'] = self.apply_col_base(col)

        return error

    def apply_line_base(self, val):
        # type: (Union[int, str, None]) -> Optional[int]
        if val is None:
            return None
        try:
            v = int(val)
        except ValueError:
            return None
        else:
            return v - self.line_col_base[0]

    def apply_col_base(self, val):
        # type: (Union[int, str, None]) -> Optional[int]
        if val is None:
            return None
        try:
            v = int(val)
        except ValueError:
            return None
        else:
            return v - self.line_col_base[1]

    def process_match(self, m, vv):
        # type: (LintMatch, VirtualView) -> Optional[LintError]
        error_type = m.error_type or self.get_error_type(m.error, m.warning)
        code = m.code or m.error or m.warning or ''

        # determine a filename for this match
        filename = self.normalize_filename(m.filename)

        if filename:
            # this is a match for a different file so we need its contents for
            # the below checks
            try:
                vv = VirtualView.from_file(filename)
            except OSError as err:
                # warn about the error and drop this match
                self.logger.warning(
                    "{} reported errors coming from '{}'. "
                    "However, reading that file raised:\n  {}."
                    .format(self.name, filename, str(err))
                )
                self.notify_failure()
                return None
        else:  # main file
            # use the filename of the current view
            filename = util.get_filename(self.view)

        # Ensure `line` is within bounds
        line = max(min(m.line, vv.max_lines()), 0)
        if line != m.line:
            self.logger.warning(
                "Reported line '{}' is not within the code we're linting.\n"
                "Maybe the linter reports problems from multiple files "
                "or `line_col_base` is not set correctly."
                .format(m.line + self.line_col_base[0])
            )

        line_region = vv.full_line_region(line)

        if m.end_line is None and m.end_col is None:
            _col = None if m.col is None else max(min(m.col, len(line_region) - 1), 0)
            line, col, end = self.reposition_match(line, _col, m, vv)
            line_region = vv.full_line_region(line)  # read again as `line` might have changed
            region = sublime.Region(line_region.a + col, line_region.a + end)

        else:
            col = 0 if m.col is None else max(min(m.col, len(line_region) - 1), 0)
            end_line = line if m.end_line is None else max(line, min(m.end_line, vv.max_lines()))
            end_line_region = vv.line_region(end_line)
            end_col = (
                len(end_line_region)
                if m.end_col is None
                else max(
                    col if end_line == line else 0,
                    min(m.end_col, len(end_line_region))
                )
            )

            if m.end_line is not None:
                if m.end_line < line:
                    self.logger.warning(
                        "Reported end_line '{}' is before the start line '{}'."
                        .format(m.end_line, line)
                    )
                elif end_line != m.end_line:
                    self.logger.warning(
                        "Reported end_line '{}' is not within the code we're linting.\n"
                        "Maybe the linter reports problems from multiple files "
                        "or `line_col_base` is not set or applied correctly."
                        .format(m.end_line)
                    )

            if m.end_col is not None:
                if end_line == line and m.end_col < col:
                    self.logger.warning(
                        "Reported end_col '{}' is before the start col '{}'."
                        .format(m.end_col, col)
                    )

            region = sublime.Region(line_region.a + col, end_line_region.a + end_col)

        # ensure a length of 1 but do not exceed eof (`size()`)
        normalized_region = sublime.Region(
            region.a, min(vv.size(), max(region.a + 1, region.b))
        )
        offending_text = vv.substr(normalized_region)

        return {
            "filename": filename,
            "line": line,
            "start": col,
            "region": normalized_region,
            "error_type": error_type,
            "code": code,
            "msg": m.message.strip(),
            "offending_text": offending_text
        }

    def get_error_type(self, error, warning):
        if error:
            return ERROR
        elif warning:
            return WARNING
        else:
            return self.default_type

    @lru_cache(maxsize=32)
    def normalize_filename(self, filename):
        # type: (Optional[str]) -> Optional[str]
        """Return an absolute filename if it is not the main file."""
        if not filename:
            return None

        if self.is_stdin_filename(filename):
            return None

        if not os.path.isabs(filename):
            cwd = self.get_working_dir() or os.getcwd()
            filename = os.path.join(cwd, filename)

        filename = os.path.normpath(filename)

        # Some linters work on temp files but actually output 'real', user
        # filenames, so we need to check both.
        for processed_file in filter(None, (self.context.get('temp_file'), self.filename)):
            if os.path.normcase(filename) == os.path.normcase(processed_file):
                return None

        return filename

    @staticmethod
    def is_stdin_filename(filename):
        # type: (str) -> bool
        return filename in ["stdin", "<stdin>", "-"]

    def reposition_match(self, line, col, m, vv):
        # type: (int, Optional[int], LintMatch, VirtualView) -> Tuple[int, int, int]
        """Chance to reposition the error.

        Must return a tuple (line, start, end)

        The default implementation just finds a good `end` or range for the
        given match. E.g. it uses `self.word_re` to select the whole word
        beginning at the `col`. If `m.near` is given, it selects the first
        occurrence of that word on the give `line`.
        """
        near = self.strip_quotes(m.near) if m.near is not None else m.near
        if col is None:
            # Empty strings won't match anything anyway so we do the simple
            # falsy test
            if near:
                text = vv.select_line(line)

                # Add \b fences around the text if it begins/ends with a word
                # character
                fence = ['', '']

                for i, pos in enumerate((0, -1)):
                    if near[pos].isalnum() or near[pos] == '_':
                        fence[i] = r'\b'

                pattern = '{}({}){}'.format(fence[0], re.escape(near), fence[1])
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
                # `rstrip` bc underlining the trailing '\n' looks ugly
                text = vv.select_line(line).rstrip()
                return line, 0, len(text)
            else:
                return line, 0, 0

        else:
            # Strict 'None' test bc empty strings should be handled here
            if near is not None:
                length = len(near)
                return line, col, col + length
            else:
                text = vv.select_line(line)[col:]
                match = self.word_re.search(text) if self.word_re else None

                length = len(match.group()) if match else 1
                return line, col, col + length

    @staticmethod
    def strip_quotes(text):
        # type: (str) -> str
        """Return text stripped of enclosing single/double quotes."""
        if len(text) < 2:
            return text

        first = text[0]

        if first in ('\'', '"') and text[-1] == first:
            text = text[1:-1]

        return text

    def run(self, cmd, code):
        # type: (Union[List[str], None], str) -> Union[util.popen_output, str]
        # Note the type here is the interface we accept. But we only actually
        # implement `(List[str], str) -> util.popen_output` here. Subclassers
        # might do differently.
        """
        Execute the linter's executable or built in code and return its output.

        If a linter uses built in code, it should override this method and return
        a string as the output.

        If a linter needs to do complicated setup or will use the tmpdir
        method, it will need to override this method.

        """
        assert cmd is not None

        if self.tempfile_suffix:
            if self.tempfile_suffix != '-':
                return self.tmpfile(cmd, code)
            else:
                return self.communicate(cmd)
        else:
            return self.communicate(cmd, code)

    # popen wrappers

    def communicate(self, cmd, code=None):
        # type: (List[str], Optional[str]) -> util.popen_output
        """Run an external executable using stdin to pass code and return its output."""
        self.context['file_on_disk'] = self.filename

        cmd = self.finalize_cmd(
            cmd, self.context, at_value=self.filename, auto_append=code is None)
        return self._communicate(cmd, code)

    def tmpfile(self, cmd, code, suffix=None):
        # type: (List[str], str, Optional[str]) -> util.popen_output
        """Create temporary file with code and lint it."""
        if suffix is None:
            suffix = self.get_tempfile_suffix()

        with make_temp_file(suffix, code) as file:
            self.context['file_on_disk'] = self.filename
            self.context['temp_file'] = file.name

            cmd = self.finalize_cmd(
                cmd, self.context, at_value=file.name, auto_append=True)
            return self._communicate(cmd)

    def finalize_cmd(self, cmd, context, at_value='', auto_append=False):
        # type: (List[str], Mapping[str, str], str, bool) -> List[str]
        # Note: Both keyword arguments are deprecated.
        original_cmd = cmd
        cmd = substitute_variables(context, cmd)
        if '@' in cmd:
            if self.tempfile_suffix == '-':
                deprecation_warning(
                    "{}: Usage of '@' as a special marker in `cmd` "
                    "has been deprecated, use '${{file_on_disk}}' instead."
                    .format(self.name)
                )
            elif self.tempfile_suffix:
                deprecation_warning(
                    "{}: Usage of '@' as a special marker in `cmd` "
                    "has been deprecated, use '${{temp_file}}' instead."
                    .format(self.name)
                )
            else:
                deprecation_warning(
                    "{}: Usage of '@' as a special marker in `cmd` "
                    "has been deprecated, use '${{file}}' instead."
                    .format(self.name)
                )

            cmd[cmd.index('@')] = at_value

        if cmd == original_cmd and auto_append:
            if self.tempfile_suffix == '-':
                deprecation_warning(
                    "{}: Implicit appending a filename to `cmd` "
                    "has been deprecated, add '${{file_on_disk}}' explicitly."
                    .format(self.name)
                )
            elif self.tempfile_suffix:
                deprecation_warning(
                    "{}: Implicit appending a filename to `cmd` "
                    "has been deprecated, add '${{temp_file}}' explicitly."
                    .format(self.name)
                )

            cmd.append(at_value)

        return cmd

    def get_tempfile_suffix(self):
        # type: () -> str
        """Return a good filename suffix."""
        assert self.tempfile_suffix

        filename = self.filename
        if filename:
            _, suffix = os.path.splitext(filename)

        elif isinstance(self.tempfile_suffix, dict):
            syntax = util.get_syntax(self.view)
            try:
                suffix = self.tempfile_suffix[syntax]
            except KeyError:
                self.logger.info(
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
        # type: (List[str], Optional[str]) -> util.popen_output
        """Run command and return result."""
        cwd = self.get_working_dir()
        env = self.get_environment()

        output_stream = self.error_stream
        view = self.view

        code_b = code.encode('utf8') if code is not None else None
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
            self.logger.error(make_nice_log_message(
                '  Execution failed\n\n  {}'.format(str(err)),
                cmd, uses_stdin, cwd, view, augmented_env))

            self.notify_failure()
            raise PermanentError("popen constructor failed")

        if self.logger.isEnabledFor(logging.INFO):
            augmented_env = dict(ChainMap(*env.maps[0:-1]))
            self.logger.info(make_nice_log_message(
                'Running ...', cmd, uses_stdin, cwd, view, env=augmented_env))

        bid = view.buffer_id()
        with store_proc_while_running(bid, proc):
            try:
                out = proc.communicate(code_b)

            except BrokenPipeError as err:
                friendly_terminated = getattr(proc, 'friendly_terminated', False)
                if friendly_terminated:
                    self.logger.info(
                        'Broken pipe after friendly terminating '
                        '<pid {}>'.format(proc.pid)
                    )
                    raise TransientError('Friendly terminated')
                else:
                    self.logger.warning('Exception: {}'.format(str(err)))
                    self.notify_failure()
                    raise PermanentError("non-friendly broken pipe")

            except OSError as err:
                # There are rare reports of '[Errno 9] Bad file descriptor'.
                # We just eat them here for user convenience, although there
                # is no deeper knowledge about why this happens.
                if err.errno == 9:
                    self.logger.warning('Exception: {}'.format(str(err)))
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
    # type: (str, str) -> Iterator[IO]
    file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        file.write(bytes(code, 'UTF-8'))
        file.close()
        yield file

    finally:
        os.remove(file.name)


@contextmanager
def store_proc_while_running(bid, proc):
    # type: (sublime.BufferId, subprocess.Popen) -> Iterator[subprocess.Popen]
    with persist.active_procs_lock:
        persist.active_procs[bid].append(proc)

    try:
        yield proc
    finally:
        with persist.active_procs_lock:
            # During hot-reload `active_procs` gets evicted so we must
            # expect a `ValueError` from time to time
            try:
                persist.active_procs[bid].remove(proc)
            except ValueError:
                pass


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
    # type: (str, List[str], bool, Optional[str], sublime.View, Optional[Dict[str, str]]) -> str
    import pprint
    import textwrap

    filename = view.file_name()
    if filename and cwd:
        rel_filename = (
            os.path.relpath(filename, cwd)
            if os.path.commonprefix([filename, cwd])
            else filename
        )
    elif not filename:
        rel_filename = '<buffer {}>'.format(view.buffer_id())

    on_win = os.name == 'nt'
    exec_msg = RUNNING_TEMPLATE.format(
        headline=headline,
        cwd=cwd or os.getcwd(),
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
