# coding=utf8
#
# test_util.py
# Part of SublimeLinter3, a code checking framework for Sublime Text 3
#
# Written by Joshua Hagins
#
# Project: https://github.com/SublimeLinter/SublimeLinter3
# License: MIT
#

"""This module tests functions in the lint.util module."""

from pytest import fixture
from mock import call, MagicMock


class TestSettingsUtils:

    """Test cases for functions in lint.util pertaining to settings."""

    @fixture(params=[
        ({'default': {'linters': {'pep8': {}}}},
         {'linters': {'pep8': {}}}),

        ({'user':    {'linters': {'pep8': {}}}},
         {'linters': {'pep8': {}}}),

        ({'default': {'linters': {'pep8': {}}},
          'user':    {'linters': {'pep257': {}}}},
         {'linters': {'pep8': {}, 'pep257': {}}}),

        ({'default': {'linters': {'pep8': {'@disable': True}}},
          'user':    {'linters': {'pep8': {'@disable': False}}}},
         {'linters': {'pep8': {'@disable': False}}})],
        ids=['no_user', 'no_default', 'no_overwrite', 'overwrite'])
    def linter_settings(self, request):
        """Fixture for linter settings."""
        return request.param

    def test_merge_user_settings(self, linter_settings):
        """Test that user linter settings override defaults."""
        from lint import util
        settings, expected = linter_settings
        actual = util.merge_user_settings(settings)
        assert actual == expected


class TestViewUtils:

    """Test cases for functions in lint.util pertaining to sublime views."""

    def test_apply_to_all_views(self):
        """Test that apply_to_all_views invokes the given callback for each view."""
        import sublime
        from lint import util

        mock_windows = [MagicMock(), MagicMock()]

        for idx, mock_window in enumerate(mock_windows):
            views = ['view'+str(x) for x in (idx*2, idx*2 + 1)]
            mock_window.views.return_value = views

        sublime.windows.return_value = mock_windows
        mock_callback = MagicMock()
        util.apply_to_all_views(mock_callback)
        sublime.windows.assert_called_once()

        for idx, mock_window in enumerate(mock_windows):
            mock_window.views.assert_called_once()

        expected_calls = [call('view'+str(x)) for x in range(4)]
        mock_callback.assert_has_calls(expected_calls)
