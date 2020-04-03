# flake8: noqa
"""API for plugin authors."""

VERSION = 4

from . import (
    linter,
    persist,
    util,
)

from .const import WARNING, ERROR
from .util import STREAM_STDOUT, STREAM_STDERR, STREAM_BOTH

from .linter import Linter, LintMatch, TransientError, PermanentError
from .base_linter.python_linter import PythonLinter
from .base_linter.ruby_linter import RubyLinter
from .base_linter.node_linter import NodeLinter
from .base_linter.composer_linter import ComposerLinter



# For compatibility with SL3, export a pseudo highlight class.
# Deprecated, don't use it.
class highlight:
    WARNING=WARNING
    ERROR=ERROR
