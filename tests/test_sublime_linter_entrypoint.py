from threading import Lock

from unittesting import DeferrableTestCase
from SublimeLinter.tests.mockito import unstub, verify, when

import sublime
from SublimeLinter import sublime_linter
from SublimeLinter.lint import Linter, persist
from SublimeLinter.lint.generic_text_command import replace_view_content


class TestLinterElection(DeferrableTestCase):
    @classmethod
    def setUpClass(cls):
        s = sublime.load_settings("Preferences.sublime-settings")
        s.set("close_windows_when_empty", False)
        # make sure we have a window to work with
        sublime.run_command("new_window")
        cls.window = window = sublime.active_window()
        cls.addClassCleanup(lambda: window.run_command('close_window'))

    @classmethod
    def tearDownClass(cls):
        unstub()

    def setUp(self):
        persist.linter_classes.clear()

    def tearDown(self):
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

    def test_file_only_linter_skip_on_unsaved_file(self):
        class FakeLinter(Linter):
            defaults = {'selector': ''}
            cmd = 'fake_linter_1'
            tempfile_suffix = '-'

        when(sublime_linter.backend).lint_view(...).thenReturn(None)

        view = self.create_view(self.window)
        assert not view.is_dirty(), "Just created views should not be marked dirty"
        assert view.file_name() is None
        sublime_linter.lint(view, lambda: False, Lock(), 'on_user_request')

        verify(sublime_linter.backend, times=0).lint_view(...)

    def test_file_only_linter_skip_dirty_file(self):
        class FakeLinter(Linter):
            defaults = {'selector': ''}
            cmd = 'fake_linter_1'
            tempfile_suffix = '-'

        when(sublime_linter.backend).lint_view(...).thenReturn(None)

        view = self.create_view(self.window)
        when(view).file_name().thenReturn("some_filename.txt")
        replace_view_content(view, "Some text.")
        assert view.is_dirty()
        assert view.file_name()
        sublime_linter.lint(view, lambda: False, Lock(), 'on_user_request')

        verify(sublime_linter.backend, times=0).lint_view(...)
        # Strangely, `set_scratch(True)` is not enough to close the view
        # without Sublime wanting to save it.  Empty the view to succeed.
        replace_view_content(view, "")

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
