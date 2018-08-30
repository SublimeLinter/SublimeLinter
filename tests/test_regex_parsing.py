from functools import partial
import unittest

import sublime
from SublimeLinter.lint import Linter, backend, persist, linter as linter_module
from unittesting import DeferrableTestCase

from SublimeLinter.tests.mockito import when, patch, unstub, spy2 as spy

version = sublime.version()


execute_lint_task = partial(
    backend.execute_lint_task, offset=(0, 0), view_has_changed=lambda: False
)


class FakeLinter1(Linter):
    defaults = {'selector': 'NONE'}
    cmd = 'fake_linter_1'
    regex = r"""(?x)
        ^stdin:(?P<line>\d+):(?P<col>\d+)?\s
        (?P<error>ERROR):\s
        (?P<near>'[^']+')?
        (?P<message>.*)$
    """
    line_col_base = (1, 1)


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

    def test_basic_info(self):
        linter = self.create_linter()

        INPUT = "This is the source code."
        OUTPUT = "stdin:1:1 ERROR: The message"
        when(linter)._communicate(['fake_linter_1'], INPUT).thenReturn(OUTPUT)

        result = execute_lint_task(linter, INPUT, offset=(0, 0))
        drop_position_keys(result)

        self.assertResult(
            [
                {
                    'error_type': 'error',
                    'code': 'ERROR',
                    'msg': 'The message',
                    'linter': 'fakelinter1',
                }
            ],
            result,
        )

    def test_no_offset(self):
        linter = self.create_linter()

        INPUT = "This is the source code."
        OUTPUT = "stdin:1:1 ERROR: The message"
        when(linter)._communicate(['fake_linter_1'], INPUT).thenReturn(OUTPUT)

        result = execute_lint_task(linter, INPUT, offset=(0, 0))
        drop_info_keys(result)

        self.assertResult(
            [{'line': 0, 'start': 0, 'end': 4, 'region': sublime.Region(0, 4)}],
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

    def test_if_col_and_not_on_a_word_set_length_1(self):
        linter = self.create_linter()

        INPUT = "    This is the source code."  # <===========
        OUTPUT = "stdin:1:1 ERROR: The message"
        when(linter)._communicate(['fake_linter_1'], INPUT).thenReturn(OUTPUT)

        result = execute_lint_task(linter, INPUT)
        drop_info_keys(result)

        self.assertResult(
            [{'line': 0, 'start': 0, 'end': 1, 'region': sublime.Region(0, 1)}],
            result,
        )

    @unittest.expectedFailure
    def test_if_no_col_and_no_near_mark_line(self):
        # FIXME: Reported end is currently 9, but must be 10

        spy(persist.settings.get)
        when(persist.settings).get('no_column_highlights_line').thenReturn(True)

        linter = self.create_linter()

        INPUT = "0123456789"
        OUTPUT = "stdin:1: ERROR: The message"
        when(linter)._communicate(['fake_linter_1'], INPUT).thenReturn(OUTPUT)

        result = execute_lint_task(linter, INPUT)
        drop_info_keys(result)

        self.assertResult(
            [
                {
                    'line': 0,
                    'start': 0,
                    'end': 10,
                    'region': sublime.Region(0, 10),
                }
            ],
            result,
        )

    def test_mark_line_should_not_select_the_trailing_newline_char(self):
        # NOTE: Bc underlining the trailing \n looks ugly

        spy(persist.settings.get)
        when(persist.settings).get('no_column_highlights_line').thenReturn(True)

        linter = self.create_linter()

        INPUT = "0123456789\n"
        OUTPUT = "stdin:1: ERROR: The message"
        when(linter)._communicate(['fake_linter_1'], INPUT).thenReturn(OUTPUT)

        result = execute_lint_task(linter, INPUT)
        drop_info_keys(result)

        self.assertResult(
            [
                {
                    'line': 0,
                    'start': 0,
                    'end': 10,
                    'region': sublime.Region(0, 10),
                }
            ],
            result,
        )

    def test_if_no_col_and_no_near_mark_zero(self):
        # NOTE: 'end' == 0 but Region still (0, 1)
        # Proposed: Region(0, 10), but start and end == None
        # Wanted sideeffect: no underlining but just a gutter mark

        spy(persist.settings.get)
        when(persist.settings).get('no_column_highlights_line').thenReturn(False)

        linter = self.create_linter()

        INPUT = "0123456789"
        OUTPUT = "stdin:1: ERROR: The message"
        when(linter)._communicate(['fake_linter_1'], INPUT).thenReturn(OUTPUT)

        result = execute_lint_task(linter, INPUT)
        drop_info_keys(result)

        self.assertResult(
            [{'line': 0, 'start': 0, 'end': 0, 'region': sublime.Region(0, 1)}],
            result,
        )

    def test_if_col_and_near_set_length(self):
        linter = self.create_linter()

        INPUT = "0123456789"
        OUTPUT = "stdin:1:2 ERROR: '....' The message"
        when(linter)._communicate(['fake_linter_1'], INPUT).thenReturn(OUTPUT)

        result = execute_lint_task(linter, INPUT)
        drop_info_keys(result)

        self.assertResult(
            [{'line': 0, 'start': 1, 'end': 5, 'region': sublime.Region(1, 5)}],
            result,
        )

    def test_if_no_col_but_near_search_term(self):
        linter = self.create_linter()

        INPUT = "0123 foo 456789"
        OUTPUT = "stdin:1: ERROR: 'foo' The message"
        when(linter)._communicate(['fake_linter_1'], INPUT).thenReturn(OUTPUT)

        result = execute_lint_task(linter, INPUT)
        drop_info_keys(result)

        self.assertResult(
            [{'line': 0, 'start': 5, 'end': 8, 'region': sublime.Region(5, 8)}],
            result,
        )

    def test_if_no_col_but_near_and_search_fails_select_line(self):
        spy(persist.settings.get)
        when(persist.settings).get('no_column_highlights_line').thenReturn(True)

        linter = self.create_linter()

        INPUT = "0123456789\n"
        OUTPUT = "stdin:1: ERROR: 'foo' The message"
        when(linter)._communicate(['fake_linter_1'], INPUT).thenReturn(OUTPUT)

        result = execute_lint_task(linter, INPUT)
        drop_info_keys(result)

        self.assertResult(
            [
                {
                    'line': 0,
                    'start': 0,
                    'end': 10,
                    'region': sublime.Region(0, 10),
                }
            ],
            result,
        )

    def test_if_no_col_but_near_and_search_fails_select_zero(self):
        spy(persist.settings.get)
        when(persist.settings).get('no_column_highlights_line').thenReturn(False)

        linter = self.create_linter()

        INPUT = "0123456789\n"
        OUTPUT = "stdin:1: ERROR: 'foo' The message"
        when(linter)._communicate(['fake_linter_1'], INPUT).thenReturn(OUTPUT)

        result = execute_lint_task(linter, INPUT)
        drop_info_keys(result)

        self.assertResult(
            [{'line': 0, 'start': 0, 'end': 0, 'region': sublime.Region(0, 1)}],
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
drop_position_keys = partial(drop_keys, ['line', 'start', 'end', 'region'])
