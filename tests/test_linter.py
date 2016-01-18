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

from mock import MagicMock


class TestLinter:

    """ Class for testing Linter class """

    def mock_view_window(self):
        mwindow = MagicMock('window')
        mview = MagicMock('view')
        mview.window = MagicMock(return_value=mwindow)
        mview.project_file_name = MagicMock(return_value='ppp')
        return mview, mwindow

    def test_replace_settings_tokens__no_replace(self):
        """ Testing if can leave settings without changes if no tokens match """
        from lint import linter

        mview, mwindow = self.mock_view_window()

        m = linter.Linter(mview, mwindow)
        settings = {'ignore_match': {'rb': ['.*unexpected.*end.*', 'some error']}}
        m.replace_settings_tokens(settings)
        assert settings == {'ignore_match': {'rb': ['.*unexpected.*end.*', 'some error']}}

    def test_replace_settings_tokens__replace(self):
        """ Testing if can leave settings without changes if token matches """
        from lint import linter
        mview, mwindow = self.mock_view_window()

        m = linter.Linter(mview, mwindow)
        settings = {'ignore_match': {'rb': ['.*unexpected.*end.*', '${sublime} error']}}
        m.replace_settings_tokens(settings)
        assert settings == {'ignore_match': {'rb': ['.*unexpected.*end.*', 'mocked_sublime_packages_path error']}}
