from collections import defaultdict, ChainMap
import sublime

from .lint import persist, events
from .lint import style as style_stores
from .lint.const import PROTECTED_REGIONS_KEY, WARNING, ERROR, WARN_ERR, INBUILT_ICONS


UNDERLINE_FLAGS = sublime.DRAW_NO_FILL | sublime.DRAW_NO_OUTLINE | sublime.DRAW_EMPTY_AS_OVERWRITE

MARK_STYLES = {
    'outline': sublime.DRAW_NO_FILL,
    'fill': sublime.DRAW_NO_OUTLINE,
    'solid_underline': sublime.DRAW_SOLID_UNDERLINE | UNDERLINE_FLAGS,
    'squiggly_underline': sublime.DRAW_SQUIGGLY_UNDERLINE | UNDERLINE_FLAGS,
    'stippled_underline': sublime.DRAW_STIPPLED_UNDERLINE | UNDERLINE_FLAGS,
    'none': sublime.HIDDEN
}


def plugin_unloaded():
    events.off(on_finished_linting)


@events.on(events.FINISHED_LINTING)
def on_finished_linting(buffer_id):
    views = list(all_views_into_buffer(buffer_id))
    if not views:
        return

    errors = persist.errors[buffer_id]
    marks, lines = prepare_data(views[0], errors)

    for view in views:
        clear_view(view)
        draw(view, style_stores.HighlightStyleStore(), marks, lines)


def all_views_into_buffer(buffer_id):
    for window in sublime.windows():
        for view in window.views():
            if view.buffer_id() == buffer_id:
                yield view


def prepare_data(view, errors):
    errors = [
        ChainMap({
            'style': (
                style_stores.get_linter_style_store(error['linter'])
                            .get_style(error['code'], error['error_type']))
        }, error)
        for error in errors]

    highlights = Highlight(view)
    for error in errors:
        highlights.add_error(**error)

    return highlights.marks, highlights.lines


REGION_KEYS = 'SL.{}.region_keys'


def remember_region_keys(view, keys):
    view.settings().set(REGION_KEYS.format(view.id()), keys)


def get_regions_keys(view):
    return set(view.settings().get(REGION_KEYS.format(view.id()), []))


def clear_view(view):
    for key in get_regions_keys(view):
        view.erase_regions(key)

    remember_region_keys(view, [])


def get_line_start(view, line):
    return view.text_point(line, 0)


class Highlight:
    """This class maintains error marks and knows how to draw them."""

    def __init__(self, view):
        self.view = view

        # Dict[error_type, Dict[style, List[region]]]
        self.marks = defaultdict(lambda: defaultdict(list))
        self.style_store = style_stores.HighlightStyleStore()

        # Every line that has a mark is kept in this dict, so we know which
        # lines to mark in the gutter.
        # Dict[error_type, Dict[lineno, style]]
        self.lines = defaultdict(dict)

    def add_error(self, line, start, end, error_type, style, **kwargs):
        line_start = get_line_start(self.view, line)
        region = sublime.Region(line_start + start, line_start + end)

        self.add_mark(error_type, style, region)
        line_region = sublime.Region(line_start, line_start)
        self.line(line, error_type, style, line_region)

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

    def line(self, line, error_type, style, region):
        """Record the given line as having the given error type."""
        # Errors override warnings on the same line
        if error_type == WARNING:
            if line in self.lines[ERROR]:
                return
        else:  # ensure no warning icons on same line as error
            self.lines[WARNING].pop(line, None)

        # Styles with higher priority override those of lower one
        # on the same line
        existing, _ = self.lines[error_type].get(line, (None, None))
        if existing:
            scope_ex = self.style_store.get(existing).get("priority", 0)
            scope_new = self.style_store.get(style).get("priority", 0)
            if scope_ex > scope_new:
                return

        self.lines[error_type][line] = (style, region)


def draw(view, style_store, marks, lines):
    """
    Draw code and gutter marks in the given view.

    Error, warning and gutter marks are drawn with separate regions,
    since each one potentially needs a different color.

    """
    # `drawn_regions` should be a `set`. We use a list here to
    # assert if we can actually hold this promise
    drawn_regions = []
    protected_regions = []

    for error_type in WARN_ERR:
        if not marks[error_type]:
            continue

        for style, regions in marks[error_type].items():
            if not style_store.has_style(style):
                continue

            scope = style_store.get_val("scope", style, error_type)
            mark_style = style_store.get_val(
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
        for line, (style, region) in lines[error_type].items():
            if not style_store.has_style(style):
                continue
            gutter_regions.setdefault(style, []).append(region)

        # draw gutter marks for
        for style, regions in gutter_regions.items():
            icon = style_store.get_val("icon", style, error_type)
            if not icon or icon == "none":  # do not draw icon
                continue

            if style_stores.GUTTER_ICONS.get('colorize', True) or icon in INBUILT_ICONS:
                scope = style_store.get_val("scope", style, error_type)
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
    remember_region_keys(view, drawn_regions)
