from collections import defaultdict, ChainMap
from itertools import chain
from functools import partial
import re

import sublime
import sublime_plugin

from .lint import persist, events, queue
from .lint import style as style_stores
from .lint.const import PROTECTED_REGIONS_KEY, WARNING


UNDERLINE_FLAGS = (
    sublime.DRAW_NO_FILL |
    sublime.DRAW_NO_OUTLINE |
    sublime.DRAW_EMPTY_AS_OVERWRITE
)

MARK_STYLES = {
    'outline': sublime.DRAW_NO_FILL,
    'fill': sublime.DRAW_NO_OUTLINE,
    'solid_underline': sublime.DRAW_SOLID_UNDERLINE | UNDERLINE_FLAGS,
    'squiggly_underline': sublime.DRAW_SQUIGGLY_UNDERLINE | UNDERLINE_FLAGS,
    'stippled_underline': sublime.DRAW_STIPPLED_UNDERLINE | UNDERLINE_FLAGS,
    'none': sublime.HIDDEN
}
UNDERLINE_STYLES = (
    'solid_underline', 'squiggly_underline', 'stippled_underline'
)

SOME_WS = re.compile('\s')
FALLBACK_MARK_STYLE = 'outline'

WS_REGIONS = re.compile('(^\s+$|\n)')
DEMOTE_WHILE_BUSY_MARKER = '%DWB%'

highlight_store = style_stores.HighlightStyleStore()
REGION_KEYS = 'SL.{}.region_keys'


def remember_region_keys(view, keys):
    view.settings().set(REGION_KEYS.format(view.id()), list(keys))


def get_regions_keys(view):
    return set(view.settings().get(REGION_KEYS.format(view.id())) or [])


State = {
    'active_view': None,
    'idle_views': set()
}


def plugin_loaded():
    State.update({
        'active_view': sublime.active_window().active_view(),
        'idle_views': set()
    })


def plugin_unloaded():
    events.off(on_lint_result)


@events.on(events.LINT_RESULT)
def on_lint_result(buffer_id, linter_name, **kwargs):
    views = list(all_views_into_buffer(buffer_id))
    if not views:
        return

    errors = persist.errors[buffer_id]
    errors_for_the_highlights, errors_for_the_gutter = prepare_data(errors)

    # `prepare_data` returns the state of the view as we would like to draw it.
    # But we cannot *redraw* regions as soon as the buffer changed, in fact
    # Sublime already moved all the regions for us.
    # So for the next step, we filter for errors from the current finished
    # lint, namely from linter_name. All other errors are already UP-TO-DATE.

    errors_for_the_highlights = [error for error in errors_for_the_highlights
                                 if error['linter'] == linter_name]
    errors_for_the_gutter = [error for error in errors_for_the_gutter
                             if error['linter'] == linter_name]

    view = views[0]  # to calculate regions we can take any of the views
    demote_predicate = get_demote_predicate()
    highlight_regions = prepare_highlights_data(
        view, linter_name, errors_for_the_highlights,
        demote_predicate=demote_predicate)
    gutter_regions = prepare_gutter_data(
        view, linter_name, errors_for_the_gutter)
    protected_regions = prepare_protected_regions(view, errors_for_the_gutter)

    for view in views:
        draw(
            view,
            linter_name,
            highlight_regions,
            gutter_regions,
            protected_regions,
            idle=(view.id() in State['idle_views'])
        )


def get_demote_predicate():
    setting = persist.settings.get('highlights.demote_while_editing')
    if setting == 'none':
        return demote_nothing

    if setting == 'ws_regions':
        return demote_ws_regions

    if setting == 'warnings':
        return demote_warnings


def get_demote_scope():
    return persist.settings.get('highlights.demote_scope')


def demote_nothing(*args, **kwargs):
    return False


def demote_ws_regions(selected_text, **kwargs):
    return bool(WS_REGIONS.search(selected_text))


def demote_warnings(selected_text, error_type, **kwargs):
    return error_type == WARNING


class IdleViewController(sublime_plugin.EventListener):
    def on_activated_async(self, active_view):
        previous_view = State['active_view']
        if previous_view.id() != active_view.id():
            set_idle(previous_view, True)

        State.update({'active_view': active_view})

    # Called multiple times (once per buffer) but provided *view* is always
    # the same, the primary one.
    def on_modified_async(self, view):
        active_view = State['active_view']
        if view.buffer_id() == active_view.buffer_id():
            invalidate_regions_under_cursor(active_view)
            set_idle(active_view, False)

    def on_post_save_async(self, view):
        active_view = State['active_view']
        if view.buffer_id() == active_view.buffer_id():
            set_idle(active_view, True)

    def on_selection_modified_async(self, view):
        active_view = State['active_view']
        time_to_idle = persist.settings.get('highlights.time_to_idle')
        if view.buffer_id() == active_view.buffer_id():
            queue.debounce(
                partial(set_idle, active_view, True),
                delay=time_to_idle,
                key='highlights.{}'.format(view.id()))


def set_idle(view, idle):
    vid = view.id()
    current_idle = vid in State['idle_views']
    if idle != current_idle:
        if idle:
            State['idle_views'].add(vid)
        else:
            State['idle_views'].discard(vid)

        toggle_demoted_regions(view, idle)


def toggle_demoted_regions(view, show):
    region_keys = get_regions_keys(view)
    for key in region_keys:
        if DEMOTE_WHILE_BUSY_MARKER in key:
            _namespace, scope, flags = key.split('|')
            flags = int(flags)
            if not show:
                scope = get_demote_scope()

            regions = view.get_regions(key)
            view.add_regions(key, regions, scope=scope, flags=flags)


def invalidate_regions_under_cursor(view):
    selections = view.sel()
    region_keys = get_regions_keys(view)
    for key in region_keys:
        if '.Highlights.' not in key:
            continue

        regions = view.get_regions(key)
        filtered = {
            (region.a, region.b)
            for region in regions
            if not any(region.contains(selection) for selection in selections)
        }
        if len(filtered) != len(regions):
            _namespace, scope, flags = key.split('|')
            flags = int(flags)

            filtered_regions = [sublime.Region(a, b) for a, b in filtered]
            view.add_regions(key, filtered_regions, scope=scope, flags=flags)


def prepare_protected_regions(view, errors):
    return list(chain.from_iterable(
        regions for (_, _, regions) in
        prepare_gutter_data(view, 'PROTECTED_REGIONS', errors).values()))


def all_views_into_buffer(buffer_id):
    for window in sublime.windows():
        for view in window.views():
            if view.buffer_id() == buffer_id:
                yield view


def prepare_data(errors):
    errors_augmented = []
    for error in errors:
        style = get_base_error_style(**error)

        priority = int(highlight_store.get(style).get('priority', 0))
        errors_augmented.append(
            ChainMap({'style': style, 'priority': priority}, error))

    # We need to filter the errors, bc we cannot draw multiple regions
    # on the same position. E.g. we can only draw one gutter icon per line,
    # and we can only 'underline' a word once.
    return (
        filter_errors(errors_augmented, by_position),  # highlights
        filter_errors(errors_augmented, by_line)       # gutter icons
    )


def get_base_error_style(linter, code, error_type, **kwargs):
    store = style_stores.get_linter_style_store(linter)
    return store.get_style(code, error_type)


def filter_errors(errors, group_fn):
    grouped = defaultdict(list)
    for error in errors:
        grouped[group_fn(error)].append(error)

    filtered_errors = []
    for errors in grouped.values():
        head = sorted(
            errors,
            key=lambda e: (-e['priority'], e['error_type'], e['linter'])
        )[0]
        filtered_errors.append(head)

    return filtered_errors


def by_position(error):
    return (error['line'], error['start'], error['end'])


def by_line(error):
    return error['line']


def prepare_gutter_data(view, linter_name, errors):
    # Compute the icon and scope for the gutter mark from the error.
    # Drop lines for which we don't get a value or for which the user
    # specified 'none'
    by_id = defaultdict(list)
    for error in errors:
        icon = get_icon(**error)
        if not icon or icon == 'none':
            continue

        scope = get_icon_scope(icon, error)
        pos = get_line_start(view, error['line'])
        region = sublime.Region(pos, pos)

        # We group towards the optimal sublime API usage:
        #   view.add_regions(uuid(), [region], scope, icon)
        id = (scope, icon)
        by_id[id].append(region)

    # Exchange the `id` with a regular region_id which is a unique string, so
    # uuid() would be candidate here, that can be reused for efficient updates.
    by_region_id = {}
    for (scope, icon), regions in by_id.items():
        region_id = 'SL.{}.Gutter.{}.{}'.format(linter_name, scope, icon)
        by_region_id[region_id] = (scope, icon, regions)

    return by_region_id


def prepare_highlights_data(view, linter_name, errors, demote_predicate):

    by_id = defaultdict(list)
    for error in errors:
        line_start = get_line_start(view, error['line'])
        region = sublime.Region(line_start + error['start'], line_start + error['end'])

        scope = get_scope(**error)
        mark_style = get_mark_style(**error)
        selected_text = view.substr(region)

        demote_while_busy = demote_predicate(selected_text, **error)

        # Work around Sublime bug, which cannot draw 'underlines' on spaces
        if mark_style in UNDERLINE_STYLES and SOME_WS.search(selected_text):
            mark_style = FALLBACK_MARK_STYLE

        flags = MARK_STYLES[mark_style]
        if not persist.settings.get('show_marks_in_minimap'):
                flags |= sublime.HIDE_ON_MINIMAP

        # We group towards the sublime API usage
        #   view.add_regions(uuid(), regions, scope, flags)
        id = (scope, flags, demote_while_busy)
        by_id[id].append(region)

    # Exchange the `id` with a regular sublime region_id which is a unique
    # string. Generally, uuid() would suffice, but generate an id here for
    # efficient updates.
    by_region_id = {}
    for (scope, flags, demote_while_busy), regions in by_id.items():
        dwb_marker = DEMOTE_WHILE_BUSY_MARKER if demote_while_busy else ''
        region_id = (
            'SL.{}.Highlights.{}|{}|{}'
            .format(linter_name, dwb_marker, scope, flags))
        by_region_id[region_id] = (scope, flags, regions)

    return by_region_id


def get_line_start(view, line):
    return view.text_point(line, 0)


def get_icon(style, error_type, **kwargs):
    return highlight_store.get_val('icon', style, error_type)


def get_scope(style, error_type, **kwargs):
    return highlight_store.get_val('scope', style, error_type)


def get_mark_style(style, error_type, **kwargs):
    return highlight_store.get_val('mark_style', style, error_type)


def get_icon_scope(icon, error):
    if style_stores.COLORIZE:
        return get_scope(**error)
    else:
        return "region.whitish"  # hopefully a white color


def draw(view, linter_name, highlight_regions, gutter_regions,
         protected_regions, idle):
    """
    Draw code and gutter marks in the given view.

    Error, warning and gutter marks are drawn with separate regions,
    since each one potentially needs a different color.

    """
    current_region_keys = get_regions_keys(view)
    current_linter_keys = {key for key in current_region_keys
                           if key.startswith('SL.{}.'.format(linter_name))}
    other_region_keys = current_region_keys - current_linter_keys

    new_linter_keys = set(highlight_regions.keys()) | set(gutter_regions.keys())
    if len(gutter_regions):
        new_linter_keys.add(PROTECTED_REGIONS_KEY)

    # overlaying all gutter regions with common invisible one,
    # to create unified handle for GitGutter and other plugins
    # flag might not be neccessary
    view.add_regions(
        PROTECTED_REGIONS_KEY,
        protected_regions
    )

    # remove unused regions
    for key in current_linter_keys - new_linter_keys:
        view.erase_regions(key)

    # otherwise update (or create) regions
    for region_id, (scope, flags, regions) in highlight_regions.items():
        if not idle and DEMOTE_WHILE_BUSY_MARKER in region_id:
            scope = get_demote_scope()
        view.add_regions(region_id, regions, scope=scope, flags=flags)

    if persist.settings.has('gutter_theme'):
        for region_id, (scope, icon, regions) in gutter_regions.items():
            view.add_regions(region_id, regions, scope=scope, icon=icon)

    # persisting region keys for later clearance
    new_region_keys = other_region_keys | new_linter_keys
    remember_region_keys(view, new_region_keys)
