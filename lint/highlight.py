#
# highlight.py
# Part of SublimeLinter3, a code checking framework for Sublime Text 3
#
# Written by Ryan Hileman and Aparajita Fishman
#
# Project: https://github.com/SublimeLinter/SublimeLinter3
# License: MIT
#

"""
This module implements highlighting code with marks.

The following classes are exported:

HighlightSet
Highlight


The following constants are exported:

WARNING - name of warning type
ERROR   - name of error type

MARK_KEY_FORMAT         - format string for key used to mark code regions
GUTTER_MARK_KEY_FORMAT  - format string for key used to mark gutter mark regions
MARK_SCOPE_FORMAT       - format string used for color scheme scope names

"""
# TODO - used in the icon fixer only, remove if it becomes superfluous
import shutil
import os


import re
import sublime
from collections import defaultdict
from . import persist

#
# Error types
#
WARNING = 'warning'
ERROR = 'error'

DEFAULT_MARK = ERROR

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
    """Return the keys from MARK_STYLES, sorted and capitalized, with None at the end."""
    names = list(MARK_STYLES)
    names.remove('none')
    names.sort()
    names.append('none')
    return [name.capitalize() for name in names]


def decrease_specificity(mark_type):
    """Generate less-specific versions of a mark_type scope, left to right."""
    parts = mark_type.split(".")

    for i in range(0, len(parts)):
        yield ".".join(parts[i:])


def more_important(new_type, current_type):
    """Return True if the new type is more important than the current one."""
    pecking_order = persist.settings.get("precedence", [])

    # We care if new_type is here because if not we keep the first mark.
    if new_type in pecking_order:
        try:
            return pecking_order.index(new_type) < pecking_order.index(current_type)
        except ValueError:
            # current_type has _no_ precedence; new_type wins.
            return True

    return False


class HighlightSet:

    """This class maintains a set of Highlight objects and performs bulk operations on them."""

    def __init__(self):
        """Initialize a new instance."""
        self.all = set()

    def add(self, highlight):
        """Add a Highlight to the set."""
        self.all.add(highlight)

    def draw(self, view):
        """
        Draw all of the Highlight objects in our set.

        Rather than draw each Highlight object individually, the marks in each
        object are aggregated into a new Highlight object, and that object
        is then drawn for the given view.

        """

        if not self.all:
            return

        all = Highlight()

        for highlight in self.all:
            all.update(highlight)

        all.draw(view)

    @staticmethod
    def clear(view):
        """Clear all marks in the given view."""
        try:
            highlights = persist.highlights[view.id()]
        except KeyError:
            return

        for highlight in highlights.all:
            highlight.clear(view)

    def redraw(self, view):
        """Redraw all marks in the given view."""
        self.clear(view)
        self.draw(view)

    def reset(self, view):
        """Clear all marks in the given view and reset the list of marks in our Highlights."""
        self.clear(view)

        for highlight in self.all:
            highlight.reset()


class Highlight:

    """This class maintains error marks and knows how to draw them."""

    def __init__(self, code='', linter_name=None):
        """Initialize a new instance."""
        self.linter_name = linter_name
        self.code = code
        self.marks = defaultdict(list)
        self.coordinates = {}
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

        # Linting runs asynchronously on a snapshot of the code. Marks are added to the code
        # during that asynchronous linting, and the markup code needs to calculate character
        # positions given a line + column. By the time marks are added, the actual buffer
        # may have changed, so we can't reliably use the plugin API to calculate character
        # positions. The solution is to calculate and store the character positions for
        # every line when this object is created, then reference that when needed.
        self.newlines = newlines = [0]
        last = -1

        while True:
            last = code.find('\n', last + 1)

            if last == -1:
                break

            newlines.append(last + 1)

        newlines.append(len(code))

    @staticmethod
    def strip_quotes(text):
        """Return text stripped of enclosing single/double quotes."""
        first = text[0]

        if first in ('\'', '"') and text[-1] == first:
            text = text[1:-1]

        return text

    def full_line(self, line):
        """
        Return the start/end character positions for the given line.

        This returns *real* character positions (relative to the beginning of self.code)
        base on the *virtual* line number (adjusted by the self.line_offset).

        """
        # The first line of the code needs the character offset
        if line == 0:
            char_offset = self.char_offset
        else:
            char_offset = 0

        line += self.line_offset
        start = self.newlines[line] + char_offset

        end = self.newlines[min(line + 1, len(self.newlines) - 1)]

        return start, end

    def localize_mark_type(self, mark_type):
        """
        Return a linter-specific mark_type.

        For example, 'warning' becomes '<linter_name>.warning'.
        """
        if self.linter_name:
            colors = persist.settings.colors()
            parts = decrease_specificity(mark_type)
            subtype = next(parts)

            while subtype:
                if subtype in colors:
                    specific_type = '{}.{}'.format(self.linter_name, subtype)

                    if specific_type in colors[mark_type]:
                        return specific_type

                    return subtype

                subtype = next(parts)

        return mark_type

    def range(self, line, pos, length=-1, near=None, error_type=DEFAULT_MARK, word_re=None):
        """
        Mark a range of text.

        line and pos should be zero-based. The pos and length argument can be used to control marking:

            - If pos < 0, the entire line is marked and length is ignored.

            - If near is not None, it is stripped of quotes and length = len(near)

            - If length < 0, the nearest word starting at pos is marked, and if
              no word is matched, the character at pos is marked.

            - If length == 0, no text is marked, but a gutter mark will appear on that line.

        error_type determines what type of error/warning mark will be drawn.

        When length < 0, this method attempts to mark the closest word at pos on the given line.
        If you want to customize the word matching regex, pass it in word_re.

        If attempting to add a mark region identical to an existing mark, conflicts
        will be disambiguated first by the precedence setting, and then
        on a first-come basis; less important marks will be replaced or ignored.

        """
        error_type = self.localize_mark_type(error_type)
        start, end = self.full_line(line)

        if pos < 0:
            pos = 0
            length = (end - start) - 1
        elif near is not None:
            near = self.strip_quotes(near)
            length = len(near)
        elif length < 0:
            code = self.code[start:end][pos:]
            match = (word_re or WORD_RE).search(code)

            if match:
                length = len(match.group())
            else:
                length = 1

        pos += start
        region = sublime.Region(pos, pos + length)
        region_coords = (region.a, region.b)

        try:
            current_type = self.coordinates[region_coords]

            if more_important(error_type, current_type):
                self.marks[current_type].remove(region)
            else:
                return

        except KeyError:
            pass

        self.coordinates[region_coords] = error_type
        self.marks[error_type].append(region)

    def regex(self, line, regex, error_type=DEFAULT_MARK,
              line_match=None, word_match=None, word_re=None):
        """
        Mark a range of text that matches a regex.

        line, error_type and word_re are the same as in range().

        line_match may be a string pattern or a compiled regex.
        If provided, it must have a named group called 'match' that
        determines which part of the source line will be considered
        for marking.

        word_match may be a string pattern or a compiled regex.
        If provided, it must have a named group called 'mark' that
        determines which part of the source line will actually be marked.
        Multiple portions of the source line may match.

        """
        offset = 0

        start, end = self.full_line(line)
        line_text = self.code[start:end]

        if line_match:
            match = re.match(line_match, line_text)

            if match:
                line_text = match.group('match')
                offset = match.start('match')
            else:
                return

        it = re.finditer(regex, line_text)
        results = [
            result.span('mark')
            for result in it
            if word_match is None or result.group('mark') == word_match
        ]

        for start, end in results:
            self.range(line, start + offset, end - start, error_type=error_type)

    def near(self, line, near, error_type=DEFAULT_MARK, word_re=None):
        """
        Mark a range of text near a given word.

        line, error_type and word_re are the same as in range().

        If near is enclosed by quotes, they are stripped. The first occurrence
        of near in the given line of code is matched. If the first and last
        characters of near are word characters, a match occurs only if near
        is a complete word.

        The position at which near is found is returned, or zero if there
        is no match.

        """
        if not near:
            return

        start, end = self.full_line(line)
        text = self.code[start:end]
        near = self.strip_quotes(near)

        # Add \b fences around the text if it begins/ends with a word character
        fence = ['', '']

        for i, pos in enumerate((0, -1)):
            if near[pos].isalnum() or near[pos] == '_':
                fence[i] = r'\b'

        pattern = NEAR_RE_TEMPLATE.format(fence[0], re.escape(near), fence[1])
        match = re.search(pattern, text)

        if match:
            start = match.start(1)
        else:
            start = -1

        if start != -1:
            self.range(line, start, len(near), error_type=error_type, word_re=word_re)
            return start
        else:
            return 0

    def update(self, other):
        """
        Update this object with another Highlight.

        It is assumed that other.code == self.code.

        other's marks and error positions are merged, and this
        object takes the newlines array from other.

        """
        # merge following precedence rules
        for mark_type in other.marks:
            for mark in other.marks[mark_type]:
                new_coord = (mark.a, mark.b)
                existing_type = self.coordinates.get(new_coord)

                if existing_type:
                    if more_important(mark_type, existing_type):
                        self.marks[existing_type].remove(mark)
                    else:
                        continue

                self.marks[mark_type].append(mark)
                self.coordinates[new_coord] = mark_type

        # Some mark types override others based on precedence settings
        for line, mark_type in other.lines.items():
            current_type = self.lines.get(line)

            if current_type:
                if more_important(mark_type, current_type):
                    self.lines[line] = mark_type
            else:
                self.lines[line] = mark_type

        self.newlines = other.newlines

    def set_mark_style(self):
        """Setup the mark style and flags based on settings."""
        self.mark_style = persist.settings.get('mark_style', 'outline')
        self.mark_flags = MARK_STYLES[self.mark_style]

        if not persist.settings.get('show_marks_in_minimap'):
            self.mark_flags |= sublime.HIDE_ON_MINIMAP

    # This will hopefully be a temporary function/generator.
    # (https://github.com/SublimeText/Issues/issues/270) prevents us from re-using
    # one icon file for multiple scopes, so we use this patch to write a new file
    # if necessary and return a safe icon path.
    icon_generators = {}
    icon_counters = {}

    def fix_icon(self, mark_type):
        """Return appropriate icon file path--generating the file if necessary."""
        try:
            return next(self.icon_generators[mark_type])
        except KeyError:

            def iconerator(mark_type):
                """Return an icon generator for a given mark_type."""
                theme = persist.settings.get(
                    'gutter_theme', persist.DEFAULT_GUTTER_THEME_PATH
                    )
                icon_dir = os.path.dirname(os.path.join(
                    os.path.dirname(sublime.packages_path()), theme))
                icon_path = None
                parts = decrease_specificity(mark_type)
                subtype = next(parts)

                # if no icon for this mark type, fall back to lower specificity or defaults
                while subtype:
                    subtype_path = os.path.join(icon_dir, "{}.png".format(subtype))

                    if os.path.isfile(subtype_path):
                        icon_path = subtype_path
                        mark_type = subtype
                        break

                    subtype = next(parts)
                else:
                    mark_type = 'warning'
                    icon_path = os.path.join(icon_dir, "{}.png".format(mark_type))

                if mark_type not in self.icon_counters:
                    self.icon_counters[mark_type] = 0
                else:
                    self.icon_counters[mark_type] += 1

                while True:
                    icon = os.path.join(
                        icon_dir,
                        "{}{}.png".format(mark_type, self.icon_counters[mark_type])
                        )

                    if not os.path.isfile(icon):
                        shutil.copy(icon_path, icon)

                    yield os.path.join(
                        os.path.dirname(theme),
                        "{}{}.png".format(mark_type, self.icon_counters[mark_type])
                        )

            self.icon_generators[mark_type] = iconerator(mark_type)
            return next(self.icon_generators[mark_type])

    def draw(self, view):
        """
        Draw code and gutter marks in the given view.

        Error, warning and gutter marks are drawn with separate regions,
        since each one potentially needs a different color.

        """
        self.set_mark_style()

        gutter_regions = defaultdict(list)
        draw_gutter_marks = persist.settings.get('gutter_theme') != 'None'

        if draw_gutter_marks:
            # We use separate regions for the gutter marks so we can use
            # a scope that will not colorize the gutter icon, and to ensure
            # that errors will override warnings.
            for line, error_type in self.lines.items():
                error_type = self.localize_mark_type(error_type)
                region = sublime.Region(self.newlines[line], self.newlines[line])
                gutter_regions[error_type].append(region)

        for mark_type in self.marks:
            if self.marks[mark_type]:
                view.add_regions(
                    MARK_KEY_FORMAT.format(mark_type),
                    self.marks[mark_type],
                    MARK_SCOPE_FORMAT.format(mark_type),
                    flags=self.mark_flags
                )

            if draw_gutter_marks and mark_type in gutter_regions:
                icon = self.fix_icon(mark_type)

                if persist.gutter_marks['colorize']:
                    scope = MARK_SCOPE_FORMAT.format(mark_type)
                else:
                    scope = 'sublimelinter.gutter-mark'

                view.add_regions(
                    GUTTER_MARK_KEY_FORMAT.format(mark_type),
                    gutter_regions[mark_type],
                    scope,
                    icon=icon
                )

    def clear(self, view):
        """Clear all marks in the given view."""
        for mark_type in self.marks:
            view.erase_regions(MARK_KEY_FORMAT.format(mark_type))
            view.erase_regions(GUTTER_MARK_KEY_FORMAT.format(mark_type))

    def reset(self):
        """
        Clear the list of marks maintained by this object.

        This method does not clear the marks, only the list.
        The next time this object is used to draw, the marks will be cleared.

        """
        for mark_type in self.marks.keys():
            del self.marks[mark_type][:]
        self.lines.clear()

    def line(self, line, error_type):
        """Record the given line as having the given error type."""
        error_type = self.localize_mark_type(error_type)
        line += self.line_offset
        current_type = self.lines.get(line)

        # more important mark types, per precedence settings, prevail
        if current_type and not more_important(error_type, current_type):
            return

        self.lines[line] = error_type

    def move_to(self, line, char_offset):
        """
        Move the highlight to the given line and character offset.

        The character offset is relative to the start of the line.
        This method is used to create virtual line numbers
        and character positions when linting embedded code.

        """
        self.line_offset = line
        self.char_offset = char_offset
