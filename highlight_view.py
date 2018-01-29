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

highlight_store = style_stores.HighlightStyleStore()


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
        draw(view, marks, lines)


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

    gutter_regions = prepare_gutter_data(view, errors)
    return highlights.marks, gutter_regions


def prepare_gutter_data(view, errors):
    errors_by_line = defaultdict(list)
    for error in errors:
        priority = highlight_store.get(error['style']).get('priority', 0)
        errors_by_line[error['line']].append(ChainMap({'priority': int(priority)}, error))

    # Since, there can only be one gutter mark per line, we have to select
    # one 'winning' error from all the errors on that line
    error_per_line = {}
    for line, errors in errors_by_line.items():
        # We're lucky here that 'error' comes before 'warning'
        head = sorted(errors, key=lambda e: (e['error_type'], -e['priority']))[0]
        error_per_line[line] = head

    # Compute the icon and scope for the gutter mark from the error.
    # Drop lines for which we don't get a value or for which the user
    # specified 'none'
    by_id = defaultdict(list)
    for line, error in error_per_line.items():

        if not highlight_store.has_style(error['style']):  # really?
            continue

        icon = highlight_store.get_val('icon', error['style'], error['error_type'])
        if not icon or icon == 'none':
            continue

        if style_stores.GUTTER_ICONS.get('colorize', True) or icon in INBUILT_ICONS:
            scope = highlight_store.get_val('scope', error['style'], error['error_type'])
        else:
            scope = " "  # set scope to non-existent one

        pos = get_line_start(view, line)
        region = sublime.Region(pos, pos)

        # We group towards the optimal sublime API usage:
        #   view.add_regions(uuid(), [region], scope, icon)
        id = (scope, icon)
        by_id[id].append(region)

    # Exchange the `id` with a regular region_id which is a unique string, so
    # uuid() would be candidate here, that can be reused for efficient updates.
    by_region_id = {}
    for (scope, icon), regions in by_id.items():
        region_id = 'SL.Gutter.{}.{}'.format(scope, icon)
        by_region_id[region_id] = (scope, icon, regions)

    return by_region_id


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

    def add_error(self, line, start, end, error_type, style, **kwargs):
        line_start = get_line_start(self.view, line)
        region = sublime.Region(line_start + start, line_start + end)

        self.add_mark(error_type, style, region)

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


def draw(view, marks, gutter_regions):
    """
    Draw code and gutter marks in the given view.

    Error, warning and gutter marks are drawn with separate regions,
    since each one potentially needs a different color.

    """
    # `drawn_regions` should be a `set`. We use a list here to
    # assert if we can actually hold this promise
    drawn_regions = []

    for error_type in WARN_ERR:
        if not marks[error_type]:
            continue

        for style, regions in marks[error_type].items():
            if not highlight_store.has_style(style):
                continue

            scope = highlight_store.get_val("scope", style, error_type)
            mark_style = highlight_store.get_val(
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
    if persist.settings.has('gutter_theme'):
        protected_regions = []

        for region_id, (scope, icon, regions) in gutter_regions.items():
            view.add_regions(region_id, regions, scope=scope, icon=icon)
            drawn_regions.append(region_id)
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
