# coding=utf8
#
# conftest.py
# Part of SublimeLinter3, a code checking framework for Sublime Text 3
#
# Written by Joshua Hagins
#
# Project: https://github.com/SublimeLinter/SublimeLinter3
# License: MIT
#

"""This module exports session-scoped fixtures for tests."""

from pytest import fixture
from mock import patch, MagicMock


@fixture(scope='session', autouse=True)
def mock_sublime(request):
    """Patch sys.modules to include a mock sublime module."""
    module_patcher = patch.dict('sys.modules', {'sublime': MagicMock()})
    module_patcher.start()

    def fin():
        module_patcher.stop()
    request.addfinalizer(fin)
