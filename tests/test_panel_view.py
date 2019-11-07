import os

from unittesting import DeferrableTestCase
from SublimeLinter.tests.parameterized import parameterized as p
from SublimeLinter.tests.mockito import unstub, when


import sublime
from SublimeLinter import panel_view


CODE = 'arbitrary_violation'
STD_ERROR = {
    'line': 0,
    'start': 0,
    'end': '2',
    'region': sublime.Region(0, 2),
    'error_type': 'error',
    'linter': 'the_foo',
    'code': CODE,
    'msg': 'The error is arbitrary.',
}


def std_error(**kw):
    rv = STD_ERROR.copy()
    rv.update(kw)
    return rv


class TestResultRegexes(DeferrableTestCase):
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
        window = self.window = sublime.active_window()
        panel_view.ensure_panel(window)
        window.run_command('sublime_linter_panel_toggle')  # make it visible
        self.create_view(window)

    def tearDown(self):
        self.window.run_command('close_window')
        unstub()

    def create_view(self, window):
        view = window.new_file()
        self.addCleanup(self.close_view, view)
        return view

    def close_view(self, view):
        view.set_scratch(True)
        view.close()

    @p.expand(
        [
            (
                'sorted files',
                {'/foo/b.py': [std_error()], '/foo/a.py': [std_error()]},
                [('/foo/a.py', 1, 1), ('/foo/b.py', 1, 1)],
            ),
            (
                'absolute windows paths',
                {'C:\\zoo\\b.py': [std_error()], 'D:\\xoo\\f.py': [std_error()]},
                [('/C/zoo/b.py', 1, 1), ('/D/xoo/f.py', 1, 1)]
                if os.name == 'nt'
                else [('C:\\zoo\\b.py', 1, 1), ('D:\\xoo\\f.py', 1, 1)],
            ),
            (
                'message ends with colon',
                {'/foo/a.py': [std_error(msg='Message ends with a colon:')]},
                [('/foo/a.py', 1, 1)],
            ),
        ]
    )
    def test_(self, _, ERRORS, RESULT):
        window = self.window
        when(panel_view).get_window_errors(...).thenReturn(ERRORS)

        panel_view.fill_panel(window)
        panel = panel_view.get_panel(window)
        # The interface updates async.
        yield lambda: panel.find(CODE, 0, sublime.LITERAL)

        results = panel.find_all_results()
        self.assertEqual(results, RESULT)

    @p.expand(
        [
            (
                {'/a.py': [std_error()], '/b.py': [std_error()], '/c.py': [std_error()]},
                [('/b.py', 1, 1), ('/c.py', 1, 1), ('/a.py', 1, 1)],
                '/a.py'
            ),
        ]
    )
    def test_active_file_comes_last(self, ERRORS, RESULT, ACTIVE_FILE):
        window = self.window
        when(panel_view).get_window_errors(...).thenReturn(ERRORS)
        panel_view.State['active_filename'] = ACTIVE_FILE

        panel_view.fill_panel(window)
        panel = panel_view.get_panel(window)
        # The interface updates async.
        yield lambda: panel.find(CODE, 0, sublime.LITERAL)

        results = panel.find_all_results()
        self.assertEqual(results, RESULT)

    @p.expand(
        [
            (
                {'/b.py': [std_error()], '/c.py': [std_error()]},
                [('/b.py', 1, 1), ('/c.py', 1, 1)],
                '/a.py'
            ),
        ]
    )
    def test_clean_active_file_displays_std_message(self, ERRORS, RESULT, ACTIVE_FILE):
        window = self.window
        when(panel_view).get_window_errors(...).thenReturn(ERRORS)
        panel_view.State['active_filename'] = ACTIVE_FILE

        panel_view.fill_panel(window)
        panel = panel_view.get_panel(window)
        # The interface updates async.
        match = yield lambda: panel.find('a.py:\n  No lint results', 0, sublime.LITERAL)
        self.assertTrue(match)
