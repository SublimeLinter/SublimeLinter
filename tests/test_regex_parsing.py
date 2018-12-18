from functools import partial
import re
from textwrap import dedent
from unittest import expectedFailure  # noqa: F401

from SublimeLinter.tests.parameterized import parameterized as p

import sublime
from SublimeLinter.lint import (
    Linter,
    linter as linter_module,
    backend,
    persist,
    util
)
from unittesting import DeferrableTestCase

from SublimeLinter.tests.mockito import (
    when,
    expect,
    unstub,
    spy,
    spy2,
    verify,
    verifyNoUnwantedInteractions
)

version = sublime.version()


VIEW_UNCHANGED = lambda: False  # noqa: E731
execute_lint_task = partial(
    backend.execute_lint_task, offset=(0, 0), view_has_changed=VIEW_UNCHANGED
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


class FakeLinterCaptureNearWithSingleQuotes(Linter):
    defaults = {'selector': 'NONE'}
    cmd = 'fake_linter_1'
    regex = r"""(?x)
        ^stdin:(?P<line>\d+):(?P<col>\d+)?\s
        (?P<error>ERROR):\s
        (?P<near>'[^']*')?
        (?P<message>.*)$
    """


class FakeLinterCaptureNearWithDoubleQuotes(Linter):
    defaults = {'selector': 'NONE'}
    cmd = 'fake_linter_1'
    regex = r"""(?x)
        ^stdin:(?P<line>\d+):(?P<col>\d+)?\s
        (?P<error>ERROR):\s
        (?P<near>\"[^\"]*\")?
        (?P<message>.*)$
    """


class FakeLinterCaptureNearWithoutQuotes(Linter):
    defaults = {'selector': 'NONE'}
    cmd = 'fake_linter_1'
    regex = r"""(?x)
        ^stdin:(?P<line>\d+):(?P<col>\d+)?\s
        (?P<error>ERROR):\s
        ('(?P<near>[^']*)')?
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


class FakeLinterColMatchesALength(Linter):
    defaults = {'selector': 'NONE'}
    cmd = 'fake_linter_1'
    regex = r"""(?x)
        ^stdin:(?P<line>\d+):(?P<col>x+)?\s
        (?P<error>ERROR):\s
        (?P<near>'[^']+')?
        (?P<message>.*)$
    """


class _BaseTestCase(DeferrableTestCase):
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

    def set_buffer_content(self, content):
        self.view.run_command('append', {'characters': content})


class TestRegexBasedParsing(_BaseTestCase):
    def test_basic_info(self):
        linter = self.create_linter()

        INPUT = "This is the source code."
        OUTPUT = "stdin:1:1 ERROR: The message"
        when(linter)._communicate(['fake_linter_1'], INPUT).thenReturn(OUTPUT)

        result = execute_lint_task(linter, INPUT)
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

        result = execute_lint_task(linter, INPUT)
        drop_info_keys(result)

        self.assertResult(
            [{'line': 0, 'start': 0, 'end': 4, 'region': sublime.Region(0, 4)}],
            result,
        )

    # SublimeLinter is capable of linting portions of a buffer. If you
    # provide an input and an offset, you basically tell SublimeLinter
    # that the input string starts at the position (line, col) in the buffer.
    # If the linter then reports an error on line 1, the error is actually
    # on line (line + 1) in the buffer.
    def test_if_col_and_on_a_word_apply_offset_first_line(self, offset=(5, 10)):
        linter = self.create_linter()

        PREFIX = dedent("""\
        0
        1
        2
        3
        4
        0123456789""")

        INPUT = "This is the extracted source code."
        BUFFER_CONTENT = PREFIX + INPUT
        self.set_buffer_content(BUFFER_CONTENT)

        OUTPUT = "stdin:1:1 ERROR: The message"
        when(linter)._communicate(['fake_linter_1'], INPUT).thenReturn(OUTPUT)

        result = execute_lint_task(linter, INPUT, offset=offset)
        drop_info_keys(result)

        # Whereby the offset is (line, col), regions represent ranges between
        # two points (ints). Basically we shift all points by 20 here.
        # (Note: the '\n' newline char counts!)
        char_offset = len(PREFIX)
        self.assertResult(
            [
                {
                    'line': 5,
                    'start': 10,
                    'end': 14,
                    'region': sublime.Region(char_offset + 0, char_offset + 4),
                }
            ],
            result,
        )

    # See comment above
    def test_if_col_and_on_a_word_apply_offset_next_line(self, offset=(5, 10)):
        linter = self.create_linter()

        PREFIX = dedent("""\
        0
        1
        2
        3
        4
        0123456789""")

        INPUT = "First line\nThis is the extracted source code."
        BUFFER_CONTENT = PREFIX + INPUT
        self.set_buffer_content(BUFFER_CONTENT)

        OUTPUT = "stdin:2:1 ERROR: The message"
        when(linter)._communicate(['fake_linter_1'], INPUT).thenReturn(OUTPUT)

        result = execute_lint_task(linter, INPUT, offset=offset)
        drop_info_keys(result)

        char_offset = len(PREFIX) + len('First line\n')
        self.assertResult(
            [
                {
                    'line': 6,
                    'start': 0,
                    'end': 4,
                    'region': sublime.Region(char_offset + 0, char_offset + 4),
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

    def test_if_no_col_and_no_near_mark_line(self):
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
            (FakeLinterCaptureNearWithSingleQuotes, "stdin:1:2 ERROR: '....' The message"),
            (FakeLinterCaptureNearWithDoubleQuotes, 'stdin:1:2 ERROR: "...." The message'),
            (FakeLinterCaptureNearWithoutQuotes, "stdin:1:2 ERROR: '....' The message"),
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
            (FakeLinterCaptureNearWithSingleQuotes, "stdin:1: ERROR: 'foo' The message"),
            (FakeLinterCaptureNearWithDoubleQuotes, 'stdin:1: ERROR: "foo" The message'),
            (FakeLinterCaptureNearWithoutQuotes, "stdin:1: ERROR: 'foo' The message"),
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
            (FakeLinterCaptureNearWithSingleQuotes, "stdin:1: ERROR: 'foo' The message"),
            (FakeLinterCaptureNearWithDoubleQuotes, 'stdin:1: ERROR: "foo" The message'),
            (FakeLinterCaptureNearWithoutQuotes, "stdin:1: ERROR: 'foo' The message"),
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
            (FakeLinterCaptureNearWithSingleQuotes, "stdin:1: ERROR: 'foo' The message"),
            (FakeLinterCaptureNearWithDoubleQuotes, 'stdin:1: ERROR: "foo" The message'),
            (FakeLinterCaptureNearWithoutQuotes, "stdin:1: ERROR: 'foo' The message"),
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

    # In the following examples you see empty quotes like '' or "".
    # Note that the near matches everything *in* these quotes, so here
    # it actually and in the end captures the empty string.
    # The tests ensure that these empty near's do not mark anything in
    # the buffer. Especially we shouldn't mark quotation punctuation in
    # the source code.
    @p.expand(
        [
            (
                FakeLinterCaptureNearWithSingleQuotes,
                "0123 '' 456789",
                "stdin:1: ERROR: '' The message",
            ),
            (
                FakeLinterCaptureNearWithSingleQuotes,
                "0123 '' 456789",
                "stdin:1:1 ERROR: '' The message",
            ),
            (
                FakeLinterCaptureNearWithDoubleQuotes,
                '0123 "" 456789',
                'stdin:1: ERROR: "" The message',
            ),
            (
                FakeLinterCaptureNearWithDoubleQuotes,
                '0123 "" 456789',
                'stdin:1:1 ERROR: "" The message',
            ),
            (
                FakeLinterCaptureNearWithoutQuotes,
                "0123 '' 456789",
                "stdin:1: ERROR: '' The message",
            ),
            (
                FakeLinterCaptureNearWithoutQuotes,
                "0123 '' 456789",
                "stdin:1:1 ERROR: '' The message",
            ),
        ]
    )
    def test_ensure_empty_near_doesnt_match_anything(
        self, linter_class, INPUT, OUTPUT
    ):
        spy2(persist.settings.get)
        when(persist.settings).get('no_column_highlights_line').thenReturn(False)

        linter = self.create_linter(linter_class)

        when(linter)._communicate(['fake_linter_1'], INPUT).thenReturn(OUTPUT)

        result = execute_lint_task(linter, INPUT)
        drop_info_keys(result)

        self.assertResult(
            [{'line': 0, 'start': 0, 'end': 0, 'region': sublime.Region(0, 1)}],
            result,
        )

    # In the following examples, we capture *foo* as the near value.
    # Note that the source code ('INPUT') contains this value verbatim
    # and quoted ('foo' or "foo").
    # The tests ensure that we mark exactly *foo* in the source code,
    # unquoted.
    @p.expand(
        [
            (
                FakeLinterCaptureNearWithSingleQuotes,
                "0123 'foo' 456789",
                "stdin:1: ERROR: 'foo' The message",
            ),
            (
                FakeLinterCaptureNearWithDoubleQuotes,
                '0123 "foo" 456789',
                'stdin:1: ERROR: "foo" The message',
            ),
            (
                FakeLinterCaptureNearWithoutQuotes,
                "0123 'foo' 456789",
                "stdin:1: ERROR: 'foo' The message",
            ),
        ]
    )
    def test_ensure_correct_mark_when_input_is_quoted(
        self, linter_class, INPUT, OUTPUT
    ):
        linter = self.create_linter(linter_class)

        when(linter)._communicate(['fake_linter_1'], INPUT).thenReturn(OUTPUT)

        result = execute_lint_task(linter, INPUT)
        drop_info_keys(result)

        self.assertResult(
            [{'line': 0, 'start': 6, 'end': 9, 'region': sublime.Region(6, 9)}],
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

    def test_if_col_matches_not_a_digit_evaluate_its_length(self):
        # XXX: BUG?
        """
        This is the source code.
        ^^^^^
        stdin:1:xxxxx ERROR: The message

        In this mode, SL assumes a col base of 0 (it does not apply
        `line_col_base`), but it should (usually) be 1 based bc if you
        visually mark the `is` below, you do something like this

        This is the source code.
        ^^^^^^   (_the 6th_ mark is where the offending code begins)
             ^^  (_after_ 5 space marks the offending code underlining begins)

        See how javac linter works around here:
        https://github.com/SublimeLinter/SublimeLinter-javac/blob/1ec3a052f32dcba2c3d404f1024ff728a84225e7/linter.py#L10
        """
        linter = self.create_linter(FakeLinterColMatchesALength)

        INPUT = "This is the source code."
        OUTPUT = "stdin:1:xxxxx ERROR: The message"
        when(linter)._communicate(['fake_linter_1'], INPUT).thenReturn(OUTPUT)

        result = execute_lint_task(linter, INPUT)
        drop_info_keys(result)

        self.assertResult(
            [{'line': 0, 'start': 5, 'end': 7, 'region': sublime.Region(5, 7)}],
            result,
        )

    def test_if_col_out_of_bounds_set_to_last_char(self):
        linter = self.create_linter()

        INPUT = "0123456789"
        OUTPUT = "stdin:1:100 ERROR: The message"
        when(linter)._communicate(['fake_linter_1'], INPUT).thenReturn(OUTPUT)

        result = execute_lint_task(linter, INPUT)
        drop_info_keys(result)

        self.assertResult(
            [
                {
                    'line': 0,
                    'start': 9,
                    'end': 10,
                    'region': sublime.Region(9, 10),
                }
            ],
            result,
        )

    @p.expand([
        # LINE_COL_BASE, INPUT, OUTPUT, LINE
        ((0, 1), "0123456789", "stdin:0:1 ERROR: The message", 0),
        ((0, 1), "0123456789", "stdin:1:1 ERROR: The message", 0),
        ((0, 1), "0123456789", "stdin:100:1 ERROR: The message", 0),
        ((0, 1), "0123456789\n0123456789", "stdin:1:1 ERROR: The message", 1),
        ((0, 1), "0123456789\n0123456789", "stdin:2:1 ERROR: The message", 1),
        ((0, 1), "0123456789\n0123456789", "stdin:100:1 ERROR: The message", 1),

        ((1, 1), "0123456789", "stdin:0:1 ERROR: The message", 0),
        ((1, 1), "0123456789", "stdin:1:1 ERROR: The message", 0),
        ((1, 1), "0123456789", "stdin:2:1 ERROR: The message", 0),
        ((1, 1), "0123456789", "stdin:100:1 ERROR: The message", 0),
        ((1, 1), "0123456789\n0123456789", "stdin:2:1 ERROR: The message", 1),
        ((1, 1), "0123456789\n0123456789", "stdin:3:1 ERROR: The message", 1),
        ((1, 1), "0123456789\n0123456789", "stdin:100:1 ERROR: The message", 1),
    ])
    def test_if_line_out_of_bounds_set_to_last_line(
        self, LINE_COL_BASE, INPUT, OUTPUT, LINE
    ):
        linter = self.create_linter()
        linter.line_col_base = LINE_COL_BASE

        when(linter)._communicate(['fake_linter_1'], INPUT).thenReturn(OUTPUT)
        when(linter_module.logger).warning(...)

        result = execute_lint_task(linter, INPUT)
        drop_info_keys(result)

        self.assertResult([{
            'line': LINE,
            'start': 0,
            'end': 10,
            'region': sublime.Region(0, 10)
        }], result)

    @p.expand([
        # LINE_COL_BASE, INPUT, OUTPUT, LINE
        ((0, 0), "0\n1", "stdin:2:1 ERROR: The message", 2),
        ((0, 0), "0\n1", "stdin:100:1 ERROR: The message", 100),

        ((1, 0), "1\n2", "stdin:0:1 ERROR: The message", 0),
        ((1, 0), "1\n2", "stdin:3:1 ERROR: The message", 3),
        ((1, 0), "1\n2", "stdin:100:1 ERROR: The message", 100),
    ])
    def test_out_of_bounds_line_produces_warning(
        self, LINE_COL_BASE, INPUT, OUTPUT, LINE
    ):
        linter = self.create_linter()
        linter.line_col_base = LINE_COL_BASE

        when(linter)._communicate(['fake_linter_1'], INPUT).thenReturn(OUTPUT)

        with expect(linter_module.logger, times=1).warning(
            "Reported line '{}' is not within the code we're linting.\n"
            "Maybe the linter reports problems from multiple files "
            "or `line_col_base` is not set correctly."
            .format(LINE)
        ):
            execute_lint_task(linter, INPUT)

            # Looks like we're using an outdated version of mockito,
            # which does not automatically verify on `__exit__`.
            verifyNoUnwantedInteractions(linter_module.logger)

    @p.expand([
        ((0, 0), "0\n1", "stdin:0:1 ERROR: The message"),
        ((0, 0), "0\n1", "stdin:1:1 ERROR: The message"),

        ((1, 0), "1\n2", "stdin:1:1 ERROR: The message"),
        ((1, 0), "1\n2", "stdin:2:1 ERROR: The message"),
    ])
    def test_correct_line_does_not_produce_a_warning(
        self, LINE_COL_BASE, INPUT, OUTPUT
    ):
        linter = self.create_linter()
        linter.line_col_base = LINE_COL_BASE

        when(linter)._communicate(['fake_linter_1'], INPUT).thenReturn(OUTPUT)
        when(linter_module.logger).warning(...)

        execute_lint_task(linter, INPUT)

        verify(linter_module.logger, times=0).warning(...)


class TestSplitMatchContract(_BaseTestCase):
    # Here we execute `linter.lint` bc `backend.execute_lint_task` eats all
    # exceptions by logging them.

    def test_ensure_not_called_with_none(self):
        linter = self.create_linter()

        INPUT = "0123456789"
        OUTPUT = "stdin:foo"
        when(linter)._communicate(['fake_linter_1'], INPUT).thenReturn(OUTPUT)

        with expect(linter, times=0).split_match(None):
            linter.lint(INPUT, VIEW_UNCHANGED)

    def test_super_match_can_be_split(self):
        linter = self.create_linter()

        INPUT = "0123456789"
        OUTPUT = "stdin:1:1 ERROR: The message"
        when(linter)._communicate(['fake_linter_1'], INPUT).thenReturn(OUTPUT)

        assert_equal = self.assertEqual

        def split_match(match):
            m = Linter.split_match(linter, match)
            match_, line, col, error, warning, message, near = m
            assert_equal(match, match_)
            assert_equal(line, m.line)
            assert_equal(col, m.col)
            assert_equal(error, m.error)
            assert_equal(warning, m.warning)
            assert_equal(message, m.message)
            assert_equal(near, m.near)
            return m

        with expect(linter, times=1).split_match(...).thenAnswer(split_match):
            linter.lint(INPUT, VIEW_UNCHANGED)

    def test_allow_tuple_as_result(self):
        linter = self.create_linter()

        INPUT = "0123456789"
        OUTPUT = "stdin:1:1 ERROR: The message"
        when(linter)._communicate(['fake_linter_1'], INPUT).thenReturn(OUTPUT)

        def split_match(match):
            m = Linter.split_match(linter, match)
            match_, line, col, error, warning, message, near = m
            return match_, line, col, error, warning, message, near

        with expect(linter, times=1).split_match(...).thenAnswer(split_match):
            result = linter.lint(INPUT, VIEW_UNCHANGED)

        self.assertEqual(1, len(result))

    @p.expand([('empty_string', ''), ('none', None), ('false', False)])
    def test_do_not_pass_if_falsy_return_value(self, _, FALSY):
        linter = self.create_linter()

        INPUT = "0123456789"
        OUTPUT = "stdin:1:1 ERROR: The message"
        when(linter)._communicate(['fake_linter_1'], INPUT).thenReturn(OUTPUT)

        with expect(linter, times=1).split_match(...).thenReturn(FALSY):
            result = linter.lint(INPUT, VIEW_UNCHANGED)

        self.assertResult([], result)

    @p.expand([('empty_string', ''), ('none', None), ('false', False)])
    def test_do_not_pass_if_1st_item_is_falsy(self, _, FALSY):
        linter = self.create_linter()

        INPUT = "0123456789"
        OUTPUT = "stdin:1:1 ERROR: The message"
        when(linter)._communicate(['fake_linter_1'], INPUT).thenReturn(OUTPUT)

        def split_match(match):
            m = Linter.split_match(linter, match)
            match_, line, col, error, warning, message, near = m
            return FALSY, line, col, error, warning, message, near

        with expect(linter, times=1).split_match(...).thenAnswer(split_match):
            result = linter.lint(INPUT, VIEW_UNCHANGED)

        self.assertEqual(0, len(result))

    def test_do_not_pass_if_2nd_item_is_None(self):
        linter = self.create_linter()

        INPUT = "0123456789"
        OUTPUT = "stdin:1:1 ERROR: The message"
        when(linter)._communicate(['fake_linter_1'], INPUT).thenReturn(OUTPUT)

        def split_match(match):
            m = Linter.split_match(linter, match)
            match_, line, col, error, warning, message, near = m
            return match_, None, col, error, warning, message, near

        with expect(linter, times=1).split_match(...).thenAnswer(split_match):
            result = linter.lint(INPUT, VIEW_UNCHANGED)

        self.assertEqual(0, len(result))

    @p.expand([('empty_string', ''), ('none', None), ('false', False)])
    def test_do_not_pass_if_5th_item_is_falsy(self, _, FALSY):
        linter = self.create_linter()

        INPUT = "0123456789"
        OUTPUT = "stdin:1:1 ERROR: The message"
        when(linter)._communicate(['fake_linter_1'], INPUT).thenReturn(OUTPUT)

        def split_match(match):
            m = Linter.split_match(linter, match)
            match_, line, col, error, warning, message, near = m
            return match_, line, col, error, warning, FALSY, near

        with expect(linter, times=1).split_match(...).thenAnswer(split_match):
            result = linter.lint(INPUT, VIEW_UNCHANGED)

        self.assertEqual(0, len(result))


def drop_keys(keys, array, strict=False):
    for item in array:
        for k in keys:
            item.pop(k) if strict else item.pop(k, None)


drop_info_keys = partial(drop_keys, ['error_type', 'code', 'msg', 'linter'])
drop_position_keys = partial(drop_keys, ['line', 'start', 'end', 'region'])
