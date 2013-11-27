#
# lint.__init__
# Part of SublimeLinter3, a code checking framework for Sublime Text 3
#
# Written by Ryan Hileman and Aparajita Fishman
#
# Project: https://github.com/SublimeLinter/SublimeLinter3
# License: MIT
#

"""This module exports the linter classes and the highlight, linter, persist and util submodules."""

from .linter import Linter, PythonLinter

from . import (
    highlight,
    linter,
    persist,
    util,
)

__all__ = [
    'highlight',
    'Linter',
    'PythonLinter',
    'linter',
    'persist',
    'util',
]
