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


class RegionStore:
    def __init__(self):
        """structure: {"view.id": [region_keys ... ]}"""
        self.memory = sublime.load_settings("sl_regions.sublime-settings")
        views = self.memory.get("views")
        if not views:
            self.memory.set("views", {})

    def add_region_keys(self, view, new_keys):
        view_id = view.id()
        saved_keys = self._get_views(view_id)
        saved_keys.extend(new_keys)
        self._set_views(view_id, saved_keys)

    def del_regions(self, view):
        view_id = view.id()
        saved_keys = self._get_views(view_id)
        for key in saved_keys:
            view.erase_regions(key)
        self._set_views(view_id)

    def get_mark_regions(self, view):
        saved_keys = self._get_views(view.id())
        regions = [
            view.get_regions(key)
            for key in saved_keys
            if "gutter" not in key
        ]
        regions = [y for x in regions for y in x]  # flatten
        points = [r.a for r in regions]
        points = sorted(list(set(points)))
        return points

    def _get_views(self, view_id):
        return self.memory.get("views").get(str(view_id), [])

    def _set_views(self, view_id, region_keys=None):
        view_id = str(view_id)
        views = self.memory.get("views")

        if not region_keys:
            if view_id in views:
                del views[view_id]
        else:
            views[view_id] = region_keys
        self.memory.set("views", views)


class HighlightSet:
    """
    This class maintains a set of Highlight objects
    and performs bulk operations on them.
    """

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

    @staticmethod
    def clear(view):
        """Clear all marks in the given view."""
        persist.region_store.del_regions(view)

    def redraw(self, view):
        """Redraw all marks in the given view."""
        self.clear(view)
        self.draw(view)

    def reset(self, view):
        """
        Clear all marks in the given view
        and reset the list of marks in our Highlights.
        """
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

        # The first line of the code needs the character offset
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
        err_type=ERROR,
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

        err_type determines what type mark will be drawn (ERROR or WARNING).

        When length < 0, this method attempts to mark the closest word at
        pos on the given line.
        If you want to customize the word matching regex, pass it in word_re.

        If the err_type is WARNING and an identical ERROR region exists,
        it is not added.
        If the err_type is ERROR and an identical WARNING region exists,
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
        other_type = ERROR if err_type == WARNING else WARNING

        for scope, marks in self.marks[other_type].items():
            i_offset = 0
            for i, mark in enumerate(marks):
                if (mark.a, mark.b) == (region.a, region.b):
                    if err_type == WARNING:
                        return length
                    else:
                        self.marks[other_type][scope].pop(i - i_offset)
                        i_offset += 1

        self.marks[err_type].setdefault(style, []).append(region)
        return length

    def regex(self, line, regex, err_type=ERROR,
              line_match=None, word_match=None, word_re=None):
        """
        Mark a range of text that matches a regex.

        line, err_type and word_re are the same as in range().

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
                       start, err_type=err_type)

    def near(self, line, near, err_type=ERROR, word_re=None, style=None):
        """
        Mark a range of text near a given word.

        line, err_type and word_re are the same as in range().

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

        if near == '':
            return 0

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
            length = self.range(
                line,
                start,
                len(near),
                err_type=err_type,
                word_re=word_re,
                style=style
            )
            return start, length
        else:
            return 0, 0

    def update(self, other):
        """
        Update this object with another Highlight.

        It is assumed that other.code == self.code.

        other's marks and error positions are merged, and this
        object takes the newlines array from other.

        """
        for err_type in WARN_ERR:
            self.marks[err_type].update(other.marks[err_type])

            for line, style in other.lines[err_type].items():
                self.overwrite_line(line, err_type, style)

        self.newlines = other.newlines

    def draw(self, view):
        """
        Draw code and gutter marks in the given view.

        Error, warning and gutter marks are drawn with separate regions,
        since each one potentially needs a different color.

        """
        from .style import GUTTER_ICONS

        drawn_regions = []
        protected_regions = []

        for err_type in WARN_ERR:
            if not self.marks[err_type]:
                continue

            for style, regions in self.marks[err_type].items():
                if not self.style_store.has_style(style):
                    continue

                scope = self.style_store.get_val("scope", style, err_type)
                mark_style = self.style_store.get_val(
                    "mark_style", style, err_type)

                flags = MARK_STYLES[mark_style]
                view.add_regions(style, regions, scope=scope, flags=flags)
                drawn_regions.append(style)

            # gutter marks
            if not persist.settings.has('gutter_theme'):
                continue

            gutter_regions = {}
            # collect regions of error type
            for line, style in self.lines[err_type].items():
                pos = self.newlines[line]
                region = sublime.Region(pos, pos)
                gutter_regions.setdefault(style, []).append(region)

            # draw gutter marks for
            for style, regions in gutter_regions.items():
                icon = self.style_store.get_val("icon", style, err_type)
                if icon == "none":  # do not draw icon
                    continue

                # colorize icon

                if GUTTER_ICONS.get('colorize', True) or icon in INBUILT_ICONS:
                    scope = self.style_store.get_val("scope", style, err_type)
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
            view.add_regions(PROTECTED_REGIONS_KEY,
                             protected_regions, flags=sublime.HIDDEN)
            drawn_regions.append(PROTECTED_REGIONS_KEY)

        # persisting region keys for later clearance
        persist.region_store.add_region_keys(view, drawn_regions)

    @staticmethod
    def clear(view):
        """Clear all marks in the given view."""
        persist.region_store.del_regions(view)

    def reset(self):
        """
        Clear the list of marks maintained by this object.

        This method does not clear the marks, only the list.
        The next time this object is used to draw, the marks will be cleared.

        """

        self.marks = util.get_new_dict()
        self.lines = util.get_new_dict()

    def line(self, line, err_type, style=None):
        """Record the given line as having the given error type."""
        line += self.line_offset
        self.overwrite_line(line, err_type, style)

    def overwrite_line(self, line, err_type, style):
        # Errors override warnings on the same line
        if err_type == WARNING:
            if line in self.lines[ERROR]:
                return
        else:  # ensure no warning icons on same line as error
            self.lines[WARNING].pop(line, None)

        # Styles with higher priority override those of lower one
        # on the same line
        existing = self.lines[err_type].get(line)
        if existing:
            scope_ex = self.style_store.get(existing).get("priority", 0)
            scope_new = self.style_store.get(style).get("priority", 0)
            if scope_ex > scope_new:
                return

        self.lines[err_type][line] = style

    def move_to(self, line, char_offset):
        """
        Move the highlight to the given line and character offset.

        The character offset is relative to the start of the line.
        This method is used to create virtual line numbers
        and character positions when linting embedded code.

        """
        self.line_offset = line
        self.char_offset = char_offset
