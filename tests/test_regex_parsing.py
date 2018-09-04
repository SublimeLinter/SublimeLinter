from functools import partial
import re
import unittest

from SublimeLinter.tests.parameterized import parameterized as p

import sublime
from SublimeLinter.lint import (
    Linter,
    backend,
    persist,
    linter as linter_module,
    util,
)
from unittesting import DeferrableTestCase

from SublimeLinter.tests.mockito import (
    when,
    patch,
    unstub,
    spy,
    spy2,
    mock,
    verify,
)

version = sublime.version()


execute_lint_task = partial(
    backend.execute_lint_task, offset=(0, 0), view_has_changed=lambda: False
)


class FakeLinter(Linter):
    defaults = {'selector': 'NONE'}
    cmd = 'fake_linter_1'
    regex = r"""(?x)
        ^stdin:(?P<line>\d+):(?P<col>\d+)?\s
        (?P<error>ERROR):\s
        (?P<near>'[^']+')?
        (?P<message>.*)$
    """
    line_col_base = (1, 1)


class FakeLinterNearSingleQuoted(Linter):
    defaults = {'selector': 'NONE'}
    cmd = 'fake_linter_1'
    regex = r"""(?x)
        ^stdin:(?P<line>\d+):(?P<col>\d+)?\s
        (?P<error>ERROR):\s
        (?P<near>'[^']+')?
        (?P<message>.*)$
    """


class FakeLinterNearDoubleQuoted(Linter):
    defaults = {'selector': 'NONE'}
    cmd = 'fake_linter_1'
    regex = r"""(?x)
        ^stdin:(?P<line>\d+):(?P<col>\d+)?\s
        (?P<error>ERROR):\s
        (?P<near>\"[^\"]+\")?
        (?P<message>.*)$
    """


class FakeLinterNearNotQuoted(Linter):
    defaults = {'selector': 'NONE'}
    cmd = 'fake_linter_1'
    regex = r"""(?x)
        ^stdin:(?P<line>\d+):(?P<col>\d+)?\s
        (?P<error>ERROR):\s
        ('(?P<near>[^']+)')?
        (?P<message>.*)$
    """


class FakeLinterMultiline(Linter):
    defaults = {'selector': 'NONE'}
    cmd = 'fake_linter_1'
    regex = r"""(?x)
        ^stdin:(?P<line>\d+):(?P<col>\d+)?\s
        (?P<error>ERROR):\s
        (?P<near>'[^']+')?
        (?P<message>.*)$
    """
    multiline = True
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

    def assertResult(self, expected, actual):
        drop_keys(['uid', 'priority'], actual)
        self.assertEqual(expected, actual)

    def create_linter(self, linter_factory=FakeLinter):
        linter = linter_factory(self.view, settings={})
        when(util).which('fake_linter_1').thenReturn('fake_linter_1')

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
                    'linter': 'fakelinter',
                }
            ],
            result,
        )

    @p.expand(
        [
            ((0, 0), "stdin:0:0 ERROR: The message"),
            ((1, 1), "stdin:1:1 ERROR: The message"),
        ]
    )
    def test_if_col_and_on_a_word_no_offset(self, line_col_base, OUTPUT):
        linter = self.create_linter()
        linter.line_col_base = line_col_base

        INPUT = "This is the source code."
        when(linter)._communicate(['fake_linter_1'], INPUT).thenReturn(OUTPUT)

        result = execute_lint_task(linter, INPUT, offset=(0, 0))
        drop_info_keys(result)

        self.assertResult(
            [{'line': 0, 'start': 0, 'end': 4, 'region': sublime.Region(0, 4)}],
            result,
        )

    def test_if_col_and_on_a_word_apply_offset_first_line(self):
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

    def test_if_col_and_on_a_word_apply_offset_next_line(self):
        linter = self.create_linter()

        # XXX: Make readable
        when(self.view).text_point(6, 0).thenReturn(2)  # <==========

        INPUT = " \nThis is the source code."
        OUTPUT = "stdin:2:1 ERROR: The message"
        when(linter)._communicate(['fake_linter_1'], INPUT).thenReturn(OUTPUT)

        result = execute_lint_task(linter, INPUT, offset=(5, 10))
        drop_info_keys(result)

        self.assertResult(
            [{'line': 6, 'start': 0, 'end': 4, 'region': sublime.Region(2, 6)}],
            result,
        )

    def test_apply_line_start(self):
        linter = self.create_linter()

        # XXX: Make readable
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

        spy2(persist.settings.get)
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

        spy2(persist.settings.get)
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

        spy2(persist.settings.get)
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

    @p.expand(
        [
            (FakeLinterNearSingleQuoted, "stdin:1:2 ERROR: '....' The message"),
            (FakeLinterNearDoubleQuoted, 'stdin:1:2 ERROR: "...." The message'),
            (FakeLinterNearNotQuoted, "stdin:1:2 ERROR: '....' The message"),
        ]
    )
    def test_if_col_and_near_set_length(self, linter_class, OUTPUT):
        linter = self.create_linter(linter_class)

        INPUT = "0123456789"
        when(linter)._communicate(['fake_linter_1'], INPUT).thenReturn(OUTPUT)

        result = execute_lint_task(linter, INPUT)
        drop_info_keys(result)

        self.assertResult(
            [{'line': 0, 'start': 1, 'end': 5, 'region': sublime.Region(1, 5)}],
            result,
        )

    @p.expand(
        [
            (FakeLinterNearSingleQuoted, "stdin:1: ERROR: 'foo' The message"),
            (FakeLinterNearDoubleQuoted, 'stdin:1: ERROR: "foo" The message'),
            (FakeLinterNearNotQuoted, "stdin:1: ERROR: 'foo' The message"),
        ]
    )
    def test_if_no_col_but_near_search_term(self, linter_class, OUTPUT):
        linter = self.create_linter(linter_class)

        INPUT = "0123 foo 456789"
        when(linter)._communicate(['fake_linter_1'], INPUT).thenReturn(OUTPUT)

        result = execute_lint_task(linter, INPUT)
        drop_info_keys(result)

        self.assertResult(
            [{'line': 0, 'start': 5, 'end': 8, 'region': sublime.Region(5, 8)}],
            result,
        )

    @p.expand(
        [
            (FakeLinterNearSingleQuoted, "stdin:1: ERROR: 'foo' The message"),
            (FakeLinterNearDoubleQuoted, 'stdin:1: ERROR: "foo" The message'),
            (FakeLinterNearNotQuoted, "stdin:1: ERROR: 'foo' The message"),
        ]
    )
    def test_if_no_col_but_near_and_search_fails_select_line(
        self, linter_class, OUTPUT
    ):
        spy2(persist.settings.get)
        when(persist.settings).get('no_column_highlights_line').thenReturn(True)

        linter = self.create_linter(linter_class)

        INPUT = "0123456789\n"
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

    @p.expand(
        [
            (FakeLinterNearSingleQuoted, "stdin:1: ERROR: 'foo' The message"),
            (FakeLinterNearDoubleQuoted, 'stdin:1: ERROR: "foo" The message'),
            (FakeLinterNearNotQuoted, "stdin:1: ERROR: 'foo' The message"),
        ]
    )
    def test_if_no_col_but_near_and_search_fails_select_zero(
        self, linter_class, OUTPUT
    ):
        spy2(persist.settings.get)
        when(persist.settings).get('no_column_highlights_line').thenReturn(False)

        linter = self.create_linter(linter_class)

        INPUT = "0123456789\n"
        when(linter)._communicate(['fake_linter_1'], INPUT).thenReturn(OUTPUT)

        result = execute_lint_task(linter, INPUT)
        drop_info_keys(result)

        self.assertResult(
            [{'line': 0, 'start': 0, 'end': 0, 'region': sublime.Region(0, 1)}],
            result,
        )

    def test_multiline_false(self):
        linter = self.create_linter()
        self.assertNotEqual(linter.regex.flags & re.MULTILINE, re.MULTILINE)

        linter.regex = spy(linter.regex)

        INPUT = "This is the source code."
        OUTPUT = "One\nTwo\nThree"
        when(linter)._communicate(['fake_linter_1'], INPUT).thenReturn(OUTPUT)

        execute_lint_task(linter, INPUT)
        verify(linter.regex).match('One')
        verify(linter.regex).match('Two')
        verify(linter.regex).match('Three')

    def test_multiline_true(self):
        linter = self.create_linter(FakeLinterMultiline)
        self.assertEqual(linter.regex.flags & re.MULTILINE, re.MULTILINE)

        linter.regex = spy(linter.regex)

        INPUT = "This is the source code."
        OUTPUT = "One\nTwo\nThree"
        when(linter)._communicate(['fake_linter_1'], INPUT).thenReturn(OUTPUT)

        execute_lint_task(linter, INPUT)
        verify(linter.regex).finditer(OUTPUT)


def drop_keys(keys, array, strict=False):
    rv = []
    for item in array:
        for k in keys:
            item.pop(k) if strict else item.pop(k, None)

        rv.append(item)
    return rv


drop_info_keys = partial(drop_keys, ['error_type', 'code', 'msg', 'linter'])
drop_position_keys = partial(drop_keys, ['line', 'start', 'end', 'region'])
