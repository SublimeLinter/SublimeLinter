from threading import Lock

from unittesting import DeferrableTestCase
from SublimeLinter.tests.mockito import unstub, verify, when

import sublime
from SublimeLinter import sublime_linter
from SublimeLinter.lint import Linter, persist


class TestLinterElection(DeferrableTestCase):
    @classmethod
    def setUpClass(cls):

        # make sure we have a window to work with
        s = sublime.load_settings("Preferences.sublime-settings")
        s.set("close_windows_when_empty", False)

    @classmethod
    def tearDownClass(cls):
        unstub()

    def setUp(self):
        sublime.run_command("new_window")
        self.window = sublime.active_window()

    def tearDown(self):
        self.window.run_command('close_window')
        persist.linter_classes.clear()
        unstub()

    def create_view(self, window):
        view = window.new_file()
        self.addCleanup(self.close_view, view)
        return view

    def close_view(self, view):
        view.set_scratch(True)
        view.close()

    def test_happy_path(self):
        class FakeLinter(Linter):
            defaults = {'selector': ''}
            cmd = 'fake_linter_1'

        when(sublime_linter.backend).lint_view(...).thenReturn(None)

        view = self.create_view(self.window)
        sublime_linter.lint(view, lambda: False, Lock(), 'on_user_request')

        verify(sublime_linter.backend).lint_view(...)

    def test_log_info_if_no_assignable_linter(self):
        class FakeLinter(Linter):
            defaults = {'selector': 'foobar'}
            cmd = 'fake_linter_1'

        when(sublime_linter.logger).info(...).thenReturn(None)

        view = self.create_view(self.window)
        sublime_linter.lint(view, lambda: False, Lock(), 'on_user_request')

        verify(sublime_linter.logger).info(
            "No installed linter matches the view."
        )

    def test_log_if_no_linter_installed(self):
        when(sublime_linter.logger).info(...).thenReturn(None)

        view = self.create_view(self.window)
        sublime_linter.lint(view, lambda: False, Lock(), 'on_user_request')

        verify(sublime_linter.logger).info(
            "No installed linter matches the view."
        )
