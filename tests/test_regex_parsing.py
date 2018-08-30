from functools import partial

import sublime
from SublimeLinter.lint import Linter, backend
from unittesting import DeferrableTestCase

from SublimeLinter.tests.mockito import when, patch, unstub

version = sublime.version()


execute_lint_task = partial(
    backend.execute_lint_task, offset=(0, 0), view_has_changed=lambda: False
)


class FakeLinter1(Linter):
    defaults = {'selector': 'NONE'}
    cmd = 'fake_linter_1'
    regex = (
        r'^stdin:(?P<line>\d+):(?P<col>\d+)\s(?P<error>ERROR):\s(?P<message>.*)$'
    )


class TestRegexBasedParsing(DeferrableTestCase):
    def setUp(self):
        self.view = sublime.active_window().new_file()
        # make sure we have a window to work with
        s = sublime.load_settings("Preferences.sublime-settings")
        s.set("close_windows_when_empty", False)

    def tearDown(self):
        if self.view:
            self.view.set_scratch(True)
            self.view.window().focus_view(self.view)
            self.view.window().run_command("close_file")
        unstub()

    def create_linter(self):
        linter = FakeLinter1(self.view, settings={})
        when(linter).which('fake_linter_1').thenReturn('fake_linter_1')

        return linter

    def test_no_offset(self):
        linter = self.create_linter()

        INPUT = "This is the source code."
        OUTPUT = "stdin:1:1 ERROR: The message"
        when(linter)._communicate(['fake_linter_1'], INPUT).thenReturn(OUTPUT)

        result = execute_lint_task(linter, INPUT, offset=(0, 0))

        self.assertResult(
            [
                {
                    'line': 0,
                    'start': 0,
                    'end': 4,
                    'error_type': 'error',
                    'code': 'ERROR',
                    'msg': 'The message',
                    'region': sublime.Region(0, 4),
                    'linter': 'fakelinter1',
                }
            ],
            result,
        )

    def test_apply_offset(self):
        linter = self.create_linter()

        INPUT = "This is the source code."
        OUTPUT = "stdin:1:1 ERROR: The message"
        when(linter)._communicate(['fake_linter_1'], INPUT).thenReturn(OUTPUT)

        result = execute_lint_task(linter, INPUT, offset=(5, 10))
        drop_info_keys(result)

        self.assertResult(
            [
                {
                    'line': 5,
                    'start': 10,
                    'end': 14,
                    'region': sublime.Region(10, 14),
                }
            ],
            result,
        )

    def test_apply_line_start(self):
        linter = self.create_linter()

        when(self.view).text_point(0, 0).thenReturn(100)  # <==========

        INPUT = "This is the source code."
        OUTPUT = "stdin:1:1 ERROR: The message"
        when(linter)._communicate(['fake_linter_1'], INPUT).thenReturn(OUTPUT)

        result = execute_lint_task(linter, INPUT)
        drop_info_keys(result)

        self.assertResult(
            [
                {
                    'line': 0,
                    'start': 0,
                    'end': 4,
                    'region': sublime.Region(100, 104),
                }
            ],
            result,
        )

    def test_minimum_length_of_region_is_one(self):
        linter = self.create_linter()

        INPUT = "    This is the source code."  # <===========
        OUTPUT = "stdin:1:1 ERROR: The message"
        when(linter)._communicate(['fake_linter_1'], INPUT).thenReturn(OUTPUT)

        result = execute_lint_task(linter, INPUT)
        drop_info_keys(result)

        self.assertResult(
            [
                {
                    'line': 0,
                    'start': 0,
                    'end': 1,  # <============
                    'region': sublime.Region(0, 1),
                }
            ],
            result,
        )

    def assertResult(self, expected, actual):
        drop_keys(['uid', 'priority'], actual)
        self.assertEqual(expected, actual)


def drop_keys(keys, array, strict=False):
    rv = []
    for item in array:
        for k in keys:
            item.pop(k) if strict else item.pop(k, None)

        rv.append(item)
    return rv


drop_info_keys = partial(drop_keys, ['error_type', 'code', 'msg', 'linter'])
