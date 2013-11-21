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

UNDERLINE_FLAGS = sublime.DRAW_NO_FILL | sublime.DRAW_NO_OUTLINE | sublime.DRAW_EMPTY_AS_OVERWRITE

MARK_STYLES = {
    'outline': sublime.DRAW_NO_FILL,
    'fill': sublime.DRAW_NO_OUTLINE,
    'solid underline': sublime.DRAW_SOLID_UNDERLINE | UNDERLINE_FLAGS,
    'squiggly underline': sublime.DRAW_SQUIGGLY_UNDERLINE | UNDERLINE_FLAGS,
    'stippled underline': sublime.DRAW_STIPPLED_UNDERLINE | UNDERLINE_FLAGS,
    'none': sublime.HIDDEN
}

WORD_RE = re.compile(r'^([-\w]+)')
NEAR_RE_TEMPLATE = r'(?<!"){}({}){}(?!")'


def mark_style_names():
    names = list(MARK_STYLES)
    names.remove('none')
    names.sort()
    names.append('none')
    return [name.capitalize() for name in names]


class HighlightSet:
    """A set of Highlight objects which can perform bulk draw/clear."""
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

    @staticmethod
    def clear(view):
        for error_type in (WARNING, ERROR):
            view.erase_regions(MARK_KEY_FORMAT.format(error_type))
            view.erase_regions(GUTTER_MARK_KEY_FORMAT.format(error_type))

    def redraw(self, view):
        self.clear(view)
        self.draw(view)

    def reset(self, view):
        self.clear(view)

        for highlight in self.all:
            highlight.reset()


class Highlight:
    """A class that represents one or more highlights and knows how to draw itself."""
    def __init__(self, code=''):
        self.code = code
        self.marks = {WARNING: [], ERROR: []}
        self.mark_style = 'outline'
        self.mark_flags = MARK_STYLES[self.mark_style]

        # Every line that has a mark is kept in this dict, so we know which
        # lines to mark in the gutter.
        self.lines = {}

        # These are used when highlighting embedded code, for example JavaScript
        # or CSS within an HTML file. The embedded code is linted as if it begins
        # at (0, 0), but we need to keep track of where the actual start is within the source.
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
        """
        Returns the *real* character positions for the start and end of the given
        *virtual* line (adjusted by the line_offset).
        """
        start, end = self.newlines[line + self.line_offset:line + self.line_offset + 2]
        return start, end

    def range(self, line, pos, length=-1, error_type='error', word_re=None):
        """
        Marks a range of text on the given zero-based line, starting at the given position
        on the line. The length argument can be used to control marking:

            - If length < 0, the nearest word starting at pos is marked, and if
              no word is matched, the character at pos is marked.

            - If length == 0, no text is marked, but a gutter mark will appear on that line.
        """
        start, end = self.full_line(line)

        if length < 0:
            code = self.code[start:end][pos:]
            match = (word_re or WORD_RE).search(code)

            if match:
                length = len(match.group())
            else:
                length = 1

        pos += start
        self.marks[error_type].append(sublime.Region(pos, pos + length))

    def regex(self, line, regex, error_type='error',
              word_match=None, line_match=None, word_re=None):
        offset = 0

        start, end = self.full_line(line)
        lineText = self.code[start:end]

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
            self.range(line, start + offset, end - start, error_type=error_type, word_re=word_re)

    def near(self, line, near, error_type='error', word_re=None):
        start, end = self.full_line(line)
        text = self.code[start:end]

        # Strip enclosing quotes from the text to match.
        first = near[0]

        if first in ('\'', '"') and near[-1] == first:
            near = near[1:-1]

        # Add \b fences around the text if it begins/ends with a word character
        fence = ['', '']

        for i, pos in enumerate((0, -1)):
            if near[pos].isalnum() or near[pos] == '_':
                fence[i] = r'\b'

        match = re.search(NEAR_RE_TEMPLATE.format(fence[0], re.escape(near), fence[1]), text)

        if match:
            start = match.start()
        else:
            start = -1

        if start != -1:
            self.range(line, start, len(near), error_type=error_type, word_re=word_re)
            return start
        else:
            return 0

    def update(self, other):
        for error_type in (WARNING, ERROR):
            self.marks[error_type].extend(other.marks[error_type])

        # Errors override warnings on the same line
        for line, error_type in other.lines.items():
            current_type = self.lines.get(line)

            if current_type is None or current_type == WARNING:
                self.lines[line] = error_type

        self.newlines = other.newlines

    def set_mark_style(self):
        self.mark_style = persist.settings.get('mark_style', 'outline')
        self.mark_flags = MARK_STYLES[self.mark_style]

        if not persist.settings.get('show_marks_in_minimap'):
            self.mark_flags |= sublime.HIDE_ON_MINIMAP

    def draw(self, view):
        self.set_mark_style()

        gutter_regions = {WARNING: [], ERROR: []}
        draw_gutter_marks = persist.settings.get('gutter-theme', 'Default') != 'none'

        if draw_gutter_marks:
            # We use separate regions for the gutter marks so we can use
            # a scope that will not colorize the gutter icon, and to ensure
            # that errors will override warnings.
            for line, error_type in self.lines.items():
                region = sublime.Region(self.newlines[line], self.newlines[line])
                gutter_regions[error_type].append(region)

        for error_type in (WARNING, ERROR):
            if self.marks[error_type]:
                view.add_regions(
                    MARK_KEY_FORMAT.format(error_type),
                    self.marks[error_type],
                    MARK_SCOPE_FORMAT.format(error_type),
                    flags=self.mark_flags
                )

            if draw_gutter_marks and gutter_regions[error_type]:
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

    @staticmethod
    def clear(view):
        for error_type in (WARNING, ERROR):
            view.erase_regions(MARK_KEY_FORMAT.format(error_type))
            view.erase_regions(GUTTER_MARK_KEY_FORMAT.format(error_type))

    def reset(self):
        for error_type in (WARNING, ERROR):
            del self.marks[error_type][:]
            self.lines.clear()

    def line(self, line, error_type):
        line += self.line_offset

        # Errors override warnings, if it's already an error leave it
        if self.lines.get(line) == ERROR:
            return

        self.lines[line] = error_type

    def move_to(self, line, char):
        self.line_offset = line
        self.char_offset = char
