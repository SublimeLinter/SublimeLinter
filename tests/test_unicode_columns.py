import os
import tempfile
import unittest

import sublime
from SublimeLinter.lint import Linter, LintMatch
from SublimeLinter.lint.linter import VirtualView
from SublimeLinter.tests.test_regex_parsing import (
    FakeLinter, _BaseTestCase, execute_lint_task,
)
from SublimeLinter.tests.mockito import when


class UnicodeLinter(Linter):
    cmd = 'fake_linter_1'
    defaults = {'selector': 'NONE'}
    regex = r'(?P<line>\d+):(?P<col>\d+)?:(?P<end_line>\d+)?:(?P<end_col>\d+)? (?P<message>.+)'


class TestUnicodeColumns(unittest.TestCase):
    def assertMatch(self, cls, output, source, start, end, text, line=0):
        linter = cls(sublime.View(0), {})
        match = next(linter.find_errors(output))
        error = linter.process_match(match, VirtualView(source))
        self.assertIsNotNone(error)
        begin = VirtualView(source).full_line(line)[0] + start
        self.assertEqual({k: error[k] for k in ('line', 'start', 'region', 'offending_text')}, {
            'line': line,
            'start': start,
            'region': sublime.Region(begin, end),
            'offending_text': text
        })

    def test_class_default_with_unchanged_numeric_groups(self):
        for unit, col in [('codepoint', 7), ('utf8', 20), ('utf16', 11)]:
            with self.subTest(unit=unit):
                class Encoded(UnicodeLinter):
                    column_unit = unit
                self.assertMatch(Encoded, '{}:{}:: Hi'.format(1, col), 'é😀😀😀😀 foo', 6, 9, 'foo')

    def test_ascii_defaults_and_zero_or_one_based_numeric_columns(self):
        for unit in ('codepoint', 'utf8', 'utf16'):
            for base in (0, 1):
                with self.subTest(unit=unit, base=base):
                    class Encoded(UnicodeLinter):
                        column_unit = unit
                        line_col_base = (base, base)
                    self.assertMatch(Encoded, '{}:{}:: Hi'.format(base, base + 2), 'a foo', 2, 5, 'foo')
                    self.assertMatch(Encoded, '{}:{}:: Hi'.format(base, base), 'abc', 0, 3, 'abc')

    def test_caret_prefix_keeps_its_zero_based_length(self):
        class Caret(UnicodeLinter):
            column_unit = 'utf16'
            regex = r'(?P<line>\d+):(?P<col>[ \t]*)\^ (?P<message>.+)'
        self.assertMatch(Caret, '1:\t    ^ Hi', '\té😀 foo', 4, 7, 'foo')
        # Empty caret-prefix captures retain the legacy missing-column behavior.
        self.assertIsNone(next(Caret(sublime.View(0), {}).find_errors('1:^ Hi')).col)

    def test_both_endpoints_same_line(self):
        for unit, col, end in [('codepoint', 4, 7), ('utf8', 8, 11), ('utf16', 5, 8)]:
            for base in (0, 1):
                with self.subTest(unit=unit, base=base):
                    class Encoded(UnicodeLinter):
                        column_unit = unit
                        line_col_base = (base, base)
                    output = f'{base}:{col - 1 + base}:{base}:{end - 1 + base} Hi'
                    self.assertMatch(Encoded, output, 'é😀 foo!', 3, 6, 'foo')

    def test_multiline_endpoints_use_different_source_lines(self):
        class Encoded(UnicodeLinter):
            column_unit = 'utf8'
        self.assertMatch(Encoded, '1:8:2:10 Hi', 'é😀 foo\n😀é bar', 3, 12, 'foo\n😀é ba')

    def test_positioning_preserves_raw_match_without_copying(self):
        class NoCopyMatch(LintMatch):
            def copy(self):
                raise AssertionError('Positioning must not copy the match')

        class Encoded(UnicodeLinter):
            column_unit = 'utf8'

            def convert_column(self, line, col, m, vv):
                assert m is match
                return super().convert_column(line, col, m, vv)

        match = NoCopyMatch(object(), 0, 7, None, None, 'Hi', None)
        match.update(end_col=10, extra='kept')
        before = dict(match)
        self.assertEqual(len(tuple(match)), 7)
        self.assertEqual(match[2], 7)
        error = Encoded(sublime.View(0), {}).process_match(match, VirtualView('é😀 foo!'))
        self.assertEqual(error['start'], 3)
        self.assertEqual(error['region'], sublime.Region(3, 6))
        self.assertEqual(error['offending_text'], 'foo')
        self.assertEqual(match.col, 7)
        self.assertEqual(match.end_col, 10)
        self.assertEqual(match, before)

    def test_custom_parser_uses_source_aware_column_hook(self):
        calls = []

        class Custom(UnicodeLinter):
            def find_errors(self, output):
                yield LintMatch(line=0, col=7, end_col=10, message=output)

            def convert_column(self, line, col, m, vv):
                calls.append((line, col, m.col, m.end_col))
                return vv.col_from_utf8(line, col)
        self.assertMatch(Custom, 'Hi', 'é😀 foo!', 3, 6, 'foo')
        self.assertEqual(calls, [(0, 7, 7, 10), (0, 10, 7, 10)])

    def test_selective_source_aware_conversion_precedes_repositioning(self):
        class Mixed(UnicodeLinter):
            column_unit = 'utf16'

            def convert_column(self, line, col, m, vv):
                return col if m.message == 'characters' else vv.col_from_utf8(line, col)

            def reposition_match(self, line, col, m, vv):
                assert col == 3  # converted and clamped
                assert m.col == (3 if m.message == 'characters' else 7)  # raw
                return super().reposition_match(line, col, m, vv)
        self.assertMatch(Mixed, '1:4:: characters', 'é😀 foo', 3, 6, 'foo')
        self.assertMatch(Mixed, '1:8:: bytes', 'é😀 foo', 3, 6, 'foo')

    def test_original_match_can_be_processed_twice_without_double_conversion(self):
        class Encoded(UnicodeLinter):
            column_unit = 'utf8'
        linter = Encoded(sublime.View(0), {})
        vv = VirtualView('é😀 foo')
        for output in ('1:8:: Hi', '1:8:1:11 Hi'):
            match = next(linter.find_errors(output))
            before = dict(match)
            first = linter.process_match(match, vv)
            second = linter.process_match(match, vv)
            self.assertEqual(first, second)
            self.assertEqual(first['start'], 3)
            self.assertEqual(first['offending_text'], 'foo')
            self.assertEqual(match.col, 7)
            self.assertEqual(match, before)

    def test_missing_columns_unchanged(self):
        class Encoded(UnicodeLinter):
            column_unit = 'utf8'

            def convert_column(self, line, col, m, vv):
                raise AssertionError('Missing columns must not be converted')
        linter = Encoded(sublime.View(0), {})
        match = next(linter.find_errors('1::: Hi'))
        self.assertIsNone(match.col)
        self.assertIsNone(match.end_col)
        # Both use exactly the same existing no-column highlight policy.
        expected = UnicodeLinter(sublime.View(0), {}).process_match(match, VirtualView('é😀 foo'))
        self.assertEqual(linter.process_match(match, VirtualView('é😀 foo')), expected)

    def test_helper_boundaries_round_down_and_saturate(self):
        vv = VirtualView('é😀x')
        for col, expected in [(-1, 0), (0, 0), (1, 0), (2, 1), (3, 1), (5, 1), (6, 2), (7, 3), (100, 3)]:
            self.assertEqual(vv.col_from_utf8(0, col), expected)
        for col, expected in [(-1, 0), (0, 0), (1, 1), (2, 1), (3, 2), (4, 3), (100, 3)]:
            self.assertEqual(vv.col_from_utf16(0, col), expected)
        self.assertEqual(VirtualView('').col_from_utf8(0, 99), 0)

    def test_positions_before_and_after_non_ascii_characters(self):
        for unit, positions in [('utf8', [0, 1, 3, 7, 8]), ('utf16', [0, 1, 2, 4, 5])]:
            vv = VirtualView('aé😀b!')
            for expected, position in enumerate(positions):
                self.assertEqual(getattr(vv, 'col_from_' + unit)(0, position), expected)

    def test_encoded_out_of_bounds_lines_and_columns_follow_legacy_clamping(self):
        class Encoded(UnicodeLinter):
            column_unit = 'utf8'
        self.assertMatch(Encoded, '99:8:: Hi', 'abc\né😀 foo', 3, 10, 'foo', line=1)
        self.assertMatch(Encoded, '0:0:: Hi', 'foo', 0, 3, 'foo')
        self.assertMatch(Encoded, '1:99:1:99 Hi', 'é😀 foo', 5, 6, 'o')
        self.assertMatch(Encoded, '1:8:1:3 Hi', 'é😀 foo', 3, 4, 'f')
        self.assertMatch(Encoded, '1:8:99:99 Hi', 'é😀 foo\né😀 bar', 3, 13, 'foo\né😀 bar')
        self.assertMatch(Encoded, '2:8:1:11 Hi', 'abc\né😀 foo', 3, 10, 'foo', line=1)
        self.assertMatch(Encoded, '2:99:: Hi', 'é😀\n', 0, 3, '', line=1)

    def test_invalid_class_unit_disables_linter_and_inheritance_works(self):
        class Invalid(UnicodeLinter):
            column_unit = 'bytes'
        self.assertTrue(Invalid.disabled)

        class Parent(UnicodeLinter):
            column_unit = 'utf8'

        class Child(Parent):
            pass
        self.assertFalse(Child.disabled)
        self.assertMatch(Child, '1:8:: Hi', 'é😀 foo', 3, 6, 'foo')

    def test_external_source_is_resolved_before_conversion(self):
        fd, filename = tempfile.mkstemp()
        os.close(fd)
        self.addCleanup(os.unlink, filename)
        with open(filename, 'w', encoding='utf8') as f:
            f.write('é😀 foo')

        class External(UnicodeLinter):
            column_unit = 'utf8'
            regex = r'(?P<filename>.+):(?P<line>\d+):(?P<col>\d+) (?P<message>.+)'

            def convert_column(self, line, col, m, vv):
                assert vv.select_line(0) == 'é😀 foo'
                return super().convert_column(line, col, m, vv)
        self.assertMatch(External, filename + ':1:8 Hi', 'wrong source', 3, 6, 'foo')


class TestUnicodeSnapshots(_BaseTestCase):
    def test_partial_buffer_uses_snapshot_before_backend_offsets(self):
        class Encoded(FakeLinter):
            column_unit = 'utf8'
        source = 'é😀 foo'
        prefix = 'header\n😀prefix '
        self.set_buffer_content(prefix + source)
        linter = self.create_linter(Encoded)
        when(linter)._communicate(['fake_linter_1'], source).thenReturn('stdin:1:8 ERROR: Hi')
        result = execute_lint_task(linter, source, offsets=(1, 8, len(prefix)))
        self.assertEqual(result[0]['start'], 11)
        self.assertEqual(result[0]['line'], 1)
        self.assertEqual(result[0]['region'], sublime.Region(len(prefix) + 3, len(prefix) + 6))
        self.assertEqual(result[0]['offending_text'], 'foo')
