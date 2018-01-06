from collections import defaultdict
import re
import sublime

from . import persist, util
from .style import HighlightStyleStore
from .const import PROTECTED_REGIONS_KEY, WARNING, ERROR, WARN_ERR, INBUILT_ICONS


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


# Dict[view_id, region_keys]
regions = defaultdict(set)


def remember_drawn_regions(view, regions_keys):
    """Remember draw regions for later clearance."""
    view_id = view.id()
    regions[view_id].update(regions_keys)


def clear_view(view):
    """Clear all marks in the given view."""
    view_id = view.id()
    region_keys = regions.pop(view_id, [])
    for key in region_keys:
        view.erase_regions(key)


class HighlightSet:
    """This class maintains a set of Highlight objects and performs bulk operations on them."""

    def __init__(self):
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

    def __init__(self, code=''):
        self.code = code
        self.marks = util.get_new_dict()
        self.mark_style = 'outline'
        self.style_store = HighlightStyleStore()

        # Every line that has a mark is kept in this dict, so we know which
        # lines to mark in the gutter.
        self.lines = util.get_new_dict()

        # These are used when highlighting embedded code
        # The embedded code is linted as if it begins
        # at (0, 0), but we need to keep track of where
        # the actual start is within the source.
        self.line_offset = 0
        self.char_offset = 0

        # Linting runs asynchronously on a snapshot of the code.
        # Marks are added to the code during that asynchronous linting,
        # and the markup code needs to calculate character positions given
        # a line + column. By the time marks are added, the actual buffer
        # may have changed, so we can't reliably use the plugin API to
        # calculate character positions.
        # The solution is to calculate and store the character positions for
        # every line when this object is created, then reference that
        # when needed.
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

        This returns *real* character positions (relative to the beginning
        of self.code) base on the *virtual* line number (adjusted by the
        self.line_offset).
        """
        if line == 0:
            char_offset = self.char_offset
        else:
            char_offset = 0

        line += self.line_offset
        start = self.newlines[line] + char_offset

        end = self.newlines[min(line + 1, len(self.newlines) - 1)]

        return start, end

    def range(
        self,
        line,
        pos,
        length=-1,
        near=None,
        error_type=ERROR,
        word_re=None,
        style=None
    ):
        """
        Mark a range of text.

        line and pos should be zero-based. The pos and length argument can be
        used to control marking:

        - If pos < 0, the entire line is marked and length is ignored.

        - If near is not None, it is stripped of quotes and length = len(near)

        - If length < 0, the nearest word starting at pos is marked, and if
          no word is matched, the character at pos is marked.

        - If length == 0, no text is marked,
          but a gutter mark will appear on that line.

        error_type determines what type mark will be drawn (ERROR or WARNING).

        When length < 0, this method attempts to mark the closest word at
        pos on the given line.
        If you want to customize the word matching regex, pass it in word_re.

        If the error_type is WARNING and an identical ERROR region exists,
        it is not added.
        If the error_type is ERROR and an identical WARNING region exists,
        the warning region is removed and the error region is added.
        """
        start, end = self.full_line(line)

        if pos < 0:
            pos = 0
            length = (end - start) - 1
        elif near:
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

        for scope, marks in self.marks[other_type].items():
            i_offset = 0
            for i, mark in enumerate(marks):
                if (mark.a, mark.b) == (region.a, region.b):
                    if error_type == WARNING:
                        return length
                    else:
                        self.marks[other_type][scope].pop(i - i_offset)
                        i_offset += 1

        self.marks[error_type].setdefault(style, []).append(region)
        return length

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
            self.range(
                line,
                start,
                length=len(near),
                error_type=error_type,
                word_re=word_re,
                style=style
            )
            return start, len(near)
        else:
            return 0, 0  # Probably a bug. Why should we fall through here?

    def update(self, other):
        """
        Update this object with another Highlight.

        It is assumed that other.code == self.code.

        other's marks and error positions are merged, and this
        object takes the newlines array from other.

        """
        for error_type in WARN_ERR:
            self.marks[error_type].update(other.marks[error_type])

            for line, style in other.lines[error_type].items():
                self.overwrite_line(line, error_type, style)

        self.newlines = other.newlines

    def draw(self, view):
        """
        Draw code and gutter marks in the given view.

        Error, warning and gutter marks are drawn with separate regions,
        since each one potentially needs a different color.

        """
        from .style import GUTTER_ICONS

        # `drawn_regions` should be a `set`. We use a list here to
        # assert if we can actually hold this promise
        drawn_regions = []
        protected_regions = []

        for error_type in WARN_ERR:
            if not self.marks[error_type]:
                continue

            for style, regions in self.marks[error_type].items():
                if not self.style_store.has_style(style):
                    continue

                scope = self.style_store.get_val("scope", style, error_type)
                mark_style = self.style_store.get_val(
                    "mark_style",
                    style,
                    error_type
                )

                flags = MARK_STYLES[mark_style]
                if not persist.settings.get('show_marks_in_minimap'):
                    flags |= sublime.HIDE_ON_MINIMAP

                view.add_regions(style, regions, scope=scope, flags=flags)
                drawn_regions.append(style)

            # gutter marks
            if not persist.settings.has('gutter_theme'):
                continue

            gutter_regions = {}
            # collect regions of error type
            for line, style in self.lines[error_type].items():
                if not self.style_store.has_style(style):
                    continue
                pos = self.newlines[line]
                region = sublime.Region(pos, pos)
                gutter_regions.setdefault(style, []).append(region)

            # draw gutter marks for
            for style, regions in gutter_regions.items():
                icon = self.style_store.get_val("icon", style, error_type)
                if not icon or icon == "none":  # do not draw icon
                    continue

                if GUTTER_ICONS.get('colorize', True) or icon in INBUILT_ICONS:
                    scope = self.style_store.get_val("scope", style, error_type)
                else:
                    scope = " "  # set scope to non-existent one

                k = style.rfind(".")
                gutter_key = style[:k] + ".gutter." + style[k + 1:]

                view.add_regions(
                    gutter_key,
                    regions,
                    scope=scope,
                    icon=icon
                )
                drawn_regions.append(gutter_key)
                protected_regions.extend(regions)

        # overlaying all gutter regions with common invisible one,
        # to create unified handle for GitGutter and other plugins
        # flag might not be neccessary
        if protected_regions:
            view.add_regions(
                PROTECTED_REGIONS_KEY,
                protected_regions,
                flags=sublime.HIDDEN
            )
            drawn_regions.append(PROTECTED_REGIONS_KEY)

        assert len(drawn_regions) == len(set(drawn_regions)), \
            "region keys not unique {}".format(drawn_regions)

        # persisting region keys for later clearance
        remember_drawn_regions(view, drawn_regions)

    def line(self, line, error_type, style=None):
        """Record the given line as having the given error type."""
        line += self.line_offset
        self.overwrite_line(line, error_type, style)

    def overwrite_line(self, line, error_type, style):
        # Errors override warnings on the same line
        if error_type == WARNING:
            if line in self.lines[ERROR]:
                return
        else:  # ensure no warning icons on same line as error
            self.lines[WARNING].pop(line, None)

        # Styles with higher priority override those of lower one
        # on the same line
        existing = self.lines[error_type].get(line)
        if existing:
            scope_ex = self.style_store.get(existing).get("priority", 0)
            scope_new = self.style_store.get(style).get("priority", 0)
            if scope_ex > scope_new:
                return

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
