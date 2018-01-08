from collections import defaultdict
import re
import sublime

from . import persist
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


class VirtualView:
    def __init__(self, code=''):
        self._code = code
        self._newlines = newlines = [0]
        last = -1

        while True:
            last = code.find('\n', last + 1)

            if last == -1:
                break

            newlines.append(last + 1)

        newlines.append(len(code))

    def full_line(self, line):
        """Return the start/end character positions for the given line."""
        start = self._newlines[line]
        end = self._newlines[min(line + 1, len(self._newlines) - 1)]

        return start, end

    def select_line(self, line):
        """Return code for the given line."""
        start, end = self.full_line(line)
        return self._code[start:end]

    # Actual Sublime API would look like:
    # def full_line(self, region)
    # def full_line(self, point) => Region
    # def substr(self, region)
    # def text_point(self, row, col) => Point
    # def rowcol(self, point) => (row, col)


class Highlight:
    """This class maintains error marks and knows how to draw them."""

    def __init__(self, code=''):
        self.vv = VirtualView(code)

        # Dict[error_type, Dict[style, List[region]]]
        self.marks = defaultdict(lambda: defaultdict(list))
        self.style_store = HighlightStyleStore()

        # Every line that has a mark is kept in this dict, so we know which
        # lines to mark in the gutter.
        # Dict[error_type, Dict[lineno, style]]
        self.lines = defaultdict(dict)

    def range(self, line, pos, length=-1, near=None, error_type=ERROR, word_re=None, style=None):
        """Mark a range of text."""
        raise Exception('`range` has been removed')

    def near(self, line, near, error_type=ERROR, word_re=None, style=None):
        """Mark a range of text near a given word."""
        raise Exception('`near` has been removed')

    def add_error(self, line, start, end, error_type, style):
        a, b = self.vv.full_line(line)
        region = sublime.Region(a + start, a + end)
        self.add_mark(error_type, style, region)
        self.line(line, error_type, style)
        return region

    def add_mark(self, error_type, style, region):
        other_type = ERROR if error_type == WARNING else WARNING

        for scope, marks in self.marks[other_type].items():
            i_offset = 0
            for i, mark in enumerate(marks):
                if (mark.a, mark.b) == (region.a, region.b):
                    if error_type == WARNING:
                        # ABORT! We found an error on the exact same position
                        return
                    else:
                        self.marks[other_type][scope].pop(i - i_offset)
                        i_offset += 1

        self.marks[error_type][style].append(region)

    def line(self, line, error_type, style=None):
        """Record the given line as having the given error type."""
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
                pos, _ = self.vv.full_line(line)
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
