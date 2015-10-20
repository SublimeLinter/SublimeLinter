#
# linter.py
# Linter for SublimeLinter3, a code checking framework for Sublime Text 3
#
# Written by __user__
# Copyright (c) __year__ __user__
#
# License: MIT
#

"""This module exports the __class__ plugin class."""

from SublimeLinter.lint import __superclass__, util


class __class__(__superclass__):
    """Provides an interface to __linter__."""

    syntax = ''
    cmd = '__cmd__'
    executable = None
    version_args = '--version'
    version_re = r'(?P<version>\d+\.\d+\.\d+)'
    version_requirement = '>= 1.0'
    regex = r''
    multiline = False
    line_col_base = (1, 1)
    tempfile_suffix = None
    error_stream = util.STREAM_BOTH
    selectors = {}
    word_re = None
    defaults = {}
    inline_settings = None
    inline_overrides = None
    # __extra_attributes__
