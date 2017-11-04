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
    'solid_underline': sublime.DRAW_SOLID_UNDERLINE | UNDERLINE_FLAGS,
    'squiggly_underline': sublime.DRAW_SQUIGGLY_UNDERLINE | UNDERLINE_FLAGS,
    'stippled_underline': sublime.DRAW_STIPPLED_UNDERLINE | UNDERLINE_FLAGS,
    'none': sublime.HIDDEN
}

WORD_RE = re.compile(r'^([-\w]+)')
NEAR_RE_TEMPLATE = r'(?<!"){}({}){}(?!")'

SAVED_REGIONS = sublime.load_settings('sl_regions.sublime-settings')
SAVED_REGIONS.set("regions", [])


# def mark_style_names():
#     """Return the keys from MARK_STYLES, sorted and capitalized, with None at the end."""
#     names = list(MARK_STYLES)
#     names.remove('none')
#     names.sort()
#     names.append('none')
#     return [name.capitalize() for name in names]


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
        # for error_type in (WARNING, ERROR):
        # view.erase_regions(MARK_KEY_FORMAT.format(error_type))
        # view.erase_regions(GUTTER_MARK_KEY_FORMAT.format(error_type))
        # print("SAVED_REGIONS: ", SAVED_REGIONS)
        all_regions = SAVED_REGIONS.get('regions', [])
        # print("all_regions: ", all_regions)
        if not all_regions:
            return  # workaround as get does not seem to return []
        for region in all_regions:
            view.erase_regions(region)

    def redraw(self, view):
        """Redraw all marks in the given view."""
        self.clear(view)
        self.draw(view)

    def reset(self, view):
        """Clear all marks in the given view and reset the list of marks in our Highlights."""
        self.clear(view)

        for highlight in self.all:
            highlight.reset()

    def line_type(self, line):
        """Return the primary error type for the given line number."""
        if not self.all:
            return None

        line_type = None
        for highlight in self.all:
            if line_type == ERROR:
                continue
            _line_type = highlight.lines.get(line)
            if _line_type != WARNING and line_type == WARNING:
                continue
            line_type = _line_type
        return line_type


class Highlight:
    """This class maintains error marks and knows how to draw them."""
    styles = {}  # TODO: add comment here

    def __init__(self, code=''):
        """Initialize a new instance."""
        self.code = code
        self.marks = {WARNING: {}, ERROR: {}}
        self.mark_style = 'outline'
        self.mark_flags = MARK_STYLES[self.mark_style]

        # Every line that has a mark is kept in this dict, so we know which
        # lines to mark in the gutter.
        self.lines = {WARNING: {}, ERROR: {}}

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
        try:
            start = self.newlines[line] + char_offset
        except IndexError as e:
            print("line: ", line)
            print("self.newlines: ", self.newlines)
            raise e

        end = self.newlines[min(line + 1, len(self.newlines) - 1)]

        return start, end

    def range(self, line, pos, length=-1, near=None, error_type=ERROR, word_re=None, style=None):
        """
        Mark a range of text.

        line and pos should be zero-based. The pos and length argument can be used to control marking:

            - If pos < 0, the entire line is marked and length is ignored.

            - If near is not None, it is stripped of quotes and length = len(near)

            - If length < 0, the nearest word starting at pos is marked, and if
              no word is matched, the character at pos is marked.

            - If length == 0, no text is marked, but a gutter mark will appear on that line.

        error_type determines what type of error mark will be drawn (ERROR or WARNING).

        When length < 0, this method attempts to mark the closest word at pos on the given line.
        If you want to customize the word matching regex, pass it in word_re.

        If the error_type is WARNING and an identical ERROR region exists, it is not added.
        If the error_type is ERROR and an identical WARNING region exists, the warning region
        is removed and the error region is added.

        """

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
        other_type = ERROR if error_type == WARNING else WARNING


        if not style:
            style = error_type

        if style not in self.marks[error_type]:  # TODO: None handling
            self.marks[error_type][style] = []

        for scope, marks in self.marks[other_type].items():
            i_offset = 0
            for i, mark in enumerate(marks):
                if mark.a == region.a and mark.b == region.b:
                    if error_type == WARNING:
                        return
                    else:
                        self.marks[other_type][scope].pop(i - i_offset)
                        # marks.pop(i - i_offset)

                        i_offset += 1

        self.marks[error_type][style].append(region)

    def regex(self, line, regex, error_type=ERROR,
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
            self.range(line, start + offset, end -
                       start, error_type=error_type)

    def near(self, line, near, error_type=ERROR, word_re=None, style=None):
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
            self.range(line, start, len(near), error_type=error_type,
                       word_re=word_re, style=style)
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
        for error_type in (WARNING, ERROR):
            self.marks[error_type].update(other.marks[error_type])

            for line, style in other.lines[error_type].items():

                # Errors override warnings on the same line
                if error_type != ERROR and self.lines[ERROR].get(line):
                    continue

                # Styles with higher priority override those of lower one
                # on the sameline
                existing = self.lines[error_type].get(line)
                if existing:
                    scope_ex = self.styles[existing].get("priority", 0)
                    scope_new = self.styles[style].get("priority", 0)

                    print(line)
                    print(style)
                    print(existing)
                    print(self.styles)

                    print(scope_ex)
                    print(scope_new)
                    print("___ "*4)


                    # if prio_ex > prio_new:
                    #     continue

                self.lines[error_type][line] = style

        self.newlines = other.newlines

    def set_mark_style(self):
        """Configure the mark style and flags based on settings."""
        self.mark_style = persist.settings.get('mark_style', 'outline')
        self.mark_flags = MARK_STYLES[self.mark_style]

        if not persist.settings.get('show_marks_in_minimap'):
            self.mark_flags |= sublime.HIDE_ON_MINIMAP

    def draw(self, view):
        """
        Draw code and gutter marks in the given view.

        Error, warning and gutter marks are drawn with separate regions,
        since each one potentially needs a different color.

        """
        self.set_mark_style()
        drawn_regions = []  # to collect drawn regions

        gutter_regions = {WARNING: {}, ERROR: {}}

        if persist.has_gutter_theme:
            # We use separate regions for the gutter marks so we can use
            # a scope that will not colorize the gutter icon, and to ensure
            # that errors will override warnings.
            for error_type in (WARNING, ERROR):
                for line, style in self.lines[error_type].items():
                    pos = self.newlines[line]
                    region = sublime.Region(pos, pos)
                    # gutter_regions[error_type][line] = region
                    gutter_regions[error_type].setdefault(style, []).append(region)

        for error_type in (WARNING, ERROR):
            # print("self.marks: ", self.marks)
            if not self.marks[error_type]:
                # TODO: check whether this makes sense
                continue

            for style, regions in self.marks[error_type].items():

                # TODO: implement default handling
                # print("style: ", style)
                # print("self.marks: ", self.marks)
                # print("self.styles: ", self.styles)
                # print("-"*10)

                styl_def = self.styles.get(style)

                # print("style_def: ", self.styles.get(style))
                # print("-"*10)
                if not styl_def:
                    continue

                scope_name = styl_def["scope"]
                mark_style = styl_def.get("mark_style", "squiggly underline")

                flags = MARK_STYLES[mark_style]
                view.add_regions(style, regions, scope=scope_name, flags=flags)

                drawn_regions.append(style)

            if not persist.has_gutter_theme:
                continue

            for line, style in self.lines[error_type].items():
                this_style = self.styles[style]
                # print("this_style: ", this_style)
                # print("style: ", style)
                # print("#"*8)

                icon = this_style.get("icon", "dot")  # TOOO: implement def handling

                if persist.gutter_marks['colorize']:
                    scope = this_style["scope"]
                else:
                    scope = " "  # set scope to non-existent one

                gutter_style = "gutter_" + style

                # GUTTER_MARK_KEY_FORMAT.format(error_type)
                view.add_regions(
                    gutter_style,
                    gutter_regions[error_type][style],
                    scope=scope,
                    icon=icon
                )
                drawn_regions.append(gutter_style)

            # persisting region keys for later clearance
            SAVED_REGIONS.set("regions", drawn_regions)

    @staticmethod
    def clear(view):
        """Clear all marks in the given view."""
        # # TODO: clear all regions
        # for error_type in (WARNING, ERROR):
        #     view.erase_regions(MARK_KEY_FORMAT.format(error_type))
        #     view.erase_regions(GUTTER_MARK_KEY_FORMAT.format(error_type))
        regions = SAVED_REGIONS.get("regions", [])
        if regions:
            for r in regions:
                view.erase_regions(r)

    def reset(self):
        """
        Clear the list of marks maintained by this object.

        This method does not clear the marks, only the list.
        The next time this object is used to draw, the marks will be cleared.

        """
        # TODO: centralize dic creation via deepcopy
        # TODO: check if it works
        self.marks = {WARNING: {}, ERROR: {}}
        self.lines = {WARNING: {}, ERROR: {}}

    def line(self, line, error_type, style=None):
        """Record the given line as having the given error type."""
        line += self.line_offset

        # Errors override warnings, if it's already an error leave it
        if self.lines.get(ERROR).get(line):
            return

        # TODO: implement gutter priority here

        if style:
            self.lines[error_type][line] = style

    def move_to(self, line, char_offset):
        """
        Move the highlight to the given line and character offset.

        The character offset is relative to the start of the line.
        This method is used to create virtual line numbers
        and character positions when linting embedded code.

        """
        self.line_offset = line
        self.char_offset = char_offset
