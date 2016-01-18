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
    sublime_mock = MagicMock()
    sublime_mock.packages_path = MagicMock(return_value='mocked_sublime_packages_path')

    module_patcher = patch.dict('sys.modules', {'sublime': sublime_mock})
    module_patcher.start()

    def fin():
        module_patcher.stop()
    request.addfinalizer(fin)
