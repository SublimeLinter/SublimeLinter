#
# highlight.py
# Part of SublimeLinter3, a code checking framework for Sublime Text 3
#
# Written by Ryan Hileman and Aparajita Fishman
#
# Project: https://github.com/SublimeLinter/SublimeLinter3
# License: MIT
#

import re
import sublime
from . import persist

#
# Error types
#
WARNING = 'warning'
ERROR = 'error'

MARK_KEY_FORMAT = 'sublimelinter-{}-marks'
GUTTER_MARK_KEY_FORMAT = 'sublimelinter-{}-gutter-marks'
MARK_SCOPE_FORMAT = 'sublimelinter.mark.{}'

WORD_RE = re.compile(r'^(\w+)')


class HighlightSet:
    '''A set of Highlight objects which can perform bulk draw/clear.'''
    def __init__(self):
        self.all = set()

    def add(self, highlight):
        self.all.add(highlight)

    def draw(self, view):
        if not self.all:
            return

        all = Highlight()

        for highlight in self.all:
            all.update(highlight)

        all.draw(view)

    def clear(self, view):
        for error_type in (WARNING, ERROR):
            view.erase_regions(MARK_KEY_FORMAT.format(error_type))
            view.erase_regions(GUTTER_MARK_KEY_FORMAT.format(error_type))


class Highlight:
    '''A class that represents one or more highlights and knows how to draw itself.'''
    def __init__(self, code='', mark_flags=sublime.DRAW_NO_FILL):
        self.code = code
        self.mark_flags = mark_flags
        self.marks = {WARNING: [], ERROR: []}

        # Every line that has a mark is kept in this dict, so we know which
        # lines to mark in the gutter.
        self.lines = {}

        # These are used when highlighting embedded code, for example PHP.
        # The embedded code is linted as if it begins at (0, 0), but we
        # need to keep track of where the actual start is within the source.
        self.line_offset = 0
        self.char_offset = 0

        # Find all the newlines, so we can look for line positions
        # without merging back into the main thread for APIs
        self.newlines = newlines = [0]
        last = -1

        while True:
            last = code.find('\n', last + 1)

            if last == -1:
                break

            newlines.append(last + 1)

        newlines.append(len(code))

    def full_line(self, line):
        a, b = self.newlines[line:line + 2]
        return a, b + 1

    def range(self, line, pos, length=1, error_type='error'):
        a, b = self.full_line(line)

        if length == 1:
            code = self.code[a:b][pos:]
            match = WORD_RE.search(code)

            if match:
                length = len(match.group())

        pos += a + self.char_offset
        self.marks[error_type].append(sublime.Region(pos, pos + length))

    def regex(self, line, regex, word_match=None, line_match=None, error_type='error'):
        offset = 0

        a, b = self.full_line(line)
        lineText = self.code[a:b]

        if line_match:
            match = re.match(line_match, lineText)

            if match:
                lineText = match.group('match')
                offset = match.start('match')
            else:
                return

        it = re.finditer(regex, lineText)
        results = [
            (result.start('mark'), result.end('mark'))
            for result in it
            if not word_match or result.group('mark') == word_match
        ]

        for start, end in results:
            self.range(line, start + offset, end - start, error_type=error_type)

    def near(self, line, near, error_type='error'):
        a, b = self.full_line(line)
        text = self.code[a:b]
        start = text.find(near)

        if start != -1:
            self.range(line, start, len(near), error_type=error_type)

    def update(self, other):
        for error_type in (WARNING, ERROR):
            self.marks[error_type].extend(other.marks[error_type])

        # Errors override warnings on the same line
        for line, error_type in other.lines.items():
            current_type = self.lines.get(line)

            if current_type is None or current_type == WARNING:
                self.lines[line] = error_type

        self.newlines = other.newlines

    def draw(self, view):
        gutter_regions = {WARNING: [], ERROR: []}

        # We use separate regions for the gutter marks so we can use
        # a scope that will not colorize the gutter icon, and to ensure
        # that errors will override warnings.
        for line, error_type in self.lines.items():
            gutter_regions[error_type].append(sublime.Region(self.newlines[line], self.newlines[line]))

        for error_type in (WARNING, ERROR):
            if self.marks[error_type]:
                view.add_regions(
                    MARK_KEY_FORMAT.format(error_type),
                    self.marks[error_type],
                    MARK_SCOPE_FORMAT.format(error_type),
                    flags=self.mark_flags
                )

            if gutter_regions[error_type]:
                if persist.gutter_marks['colorize']:
                    scope = MARK_SCOPE_FORMAT.format(error_type)
                else:
                    scope = 'sublimelinter.gutter-mark'

                view.add_regions(
                    GUTTER_MARK_KEY_FORMAT.format(error_type),
                    gutter_regions[error_type],
                    scope,
                    icon=persist.gutter_marks[error_type]
                )

    def clear(self, view):
        for error_type in (WARNING, ERROR):
            view.erase_regions(MARK_KEY_FORMAT.format(error_type))
            view.erase_regions(GUTTER_MARK_KEY_FORMAT.format(error_type))

    def line(self, line, error_type):
        line += self.line_offset

        # Errors override warnings, if it's already an error leave it
        if self.lines.get(line) == ERROR:
            return

        self.lines[line] = error_type

    def move_to(self, line, char):
        self.line_offset = line
        self.char_offset = char
