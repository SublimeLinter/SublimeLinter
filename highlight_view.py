from collections import defaultdict, ChainMap
import html
from itertools import chain
from functools import partial
import re

import sublime
import sublime_plugin

from .lint import persist, events, queue
from .lint import style as style_stores
from .lint.const import PROTECTED_REGIONS_KEY, ERROR, WARNING


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
HIDDEN_STYLE_MARKER = '%HIDDEN%'

highlight_store = style_stores.HighlightStyleStore()
STORAGE_KEY = 'SL.{}.region_keys'


def remember_region_keys(view, keys):
    setting_key = STORAGE_KEY.format(view.id())
    view.settings().set(setting_key, list(keys))


def get_regions_keys(view):
    setting_key = STORAGE_KEY.format(view.id())
    return set(view.settings().get(setting_key) or [])


State = {
    'active_view': None,
    'idle_views': set(),
    'quiet_views': set()
}


def plugin_loaded():
    State.update({
        'active_view': sublime.active_window().active_view(),
        'idle_views': set()
    })


def plugin_unloaded():
    events.off(on_lint_result)
    for window in sublime.windows():
        for view in window.views():
            undraw(view)


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
            idle=(view.id() in State['idle_views']),
            quiet=(view.id() in State['quiet_views'])
        )


def get_demote_predicate():
    setting = persist.settings.get('highlights.demote_while_editing')
    if setting == 'none':
        return demote_nothing

    if setting == 'all':
        return demote_all

    if setting == 'ws_regions':
        return demote_ws_regions

    if setting == 'warnings':
        return demote_warnings


def get_demote_scope():
    return persist.settings.get('highlights.demote_scope')


def demote_nothing(*args, **kwargs):
    return False


def demote_all(*args, **kwargs):
    return True


def demote_ws_regions(selected_text, **kwargs):
    return bool(WS_REGIONS.search(selected_text))


def demote_warnings(selected_text, error_type, **kwargs):
    return error_type == WARNING


class IdleViewController(sublime_plugin.EventListener):
    def on_activated_async(self, active_view):
        previous_view = State['active_view']
        if previous_view and previous_view.id() != active_view.id():
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
    vid = view.id()
    if vid in State['quiet_views']:
        return

    region_keys = get_regions_keys(view)
    for key in region_keys:
        if DEMOTE_WHILE_BUSY_MARKER in key:
            _namespace, scope, flags = key.split('|')
            flags = int(flags)
            if not show:
                scope = get_demote_scope()

            regions = view.get_regions(key)
            view.add_regions(key, regions, scope=scope, flags=flags)


class SublimeLinterToggleHighlights(sublime_plugin.WindowCommand):
    def run(self):
        view = self.window.active_view()
        vid = view.id()
        hidden = vid in State['quiet_views']
        if hidden:
            State['quiet_views'].discard(vid)
        else:
            State['quiet_views'].add(vid)

        toggle_all_regions(view, show=hidden)


HIDDEN_SCOPE = ''


def toggle_all_regions(view, show):
    region_keys = get_regions_keys(view)
    for key in region_keys:
        if '.Highlights.' not in key:
            continue

        _namespace, scope, flags = key.split('|')
        flags = int(flags)
        if not show:
            scope = HIDDEN_SCOPE

        regions = view.get_regions(key)
        view.add_regions(key, regions, scope=scope, flags=flags)


def invalidate_regions_under_cursor(view):
    vid = view.id()
    if vid in State['quiet_views']:
        return

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
        scope = get_scope(**error)
        mark_style = get_mark_style(**error)
        if not mark_style:
            mark_style == 'none'

        line_start = get_line_start(view, error['line'])
        region = sublime.Region(line_start + error['start'], line_start + error['end'])
        # Ensure a region length of 1, otherwise we get visual distortion:
        # outlines are not drawn at all, and underlines get thicker.
        if len(region) == 0:
            region.b = region.b + 1

        selected_text = view.substr(region)
        # Work around Sublime bug, which cannot draw 'underlines' on spaces
        if mark_style in UNDERLINE_STYLES and SOME_WS.search(selected_text):
            mark_style = FALLBACK_MARK_STYLE

        flags = MARK_STYLES[mark_style]
        if not persist.settings.get('show_marks_in_minimap'):
                flags |= sublime.HIDE_ON_MINIMAP

        demote_while_busy = demote_predicate(selected_text, **error)
        hidden = mark_style == 'none' or not scope

        # We group towards the sublime API usage
        #   view.add_regions(uuid(), regions, scope, flags)
        id = (scope, flags, demote_while_busy, hidden)
        by_id[id].append(region)

    # Exchange the `id` with a regular sublime region_id which is a unique
    # string. Generally, uuid() would suffice, but generate an id here for
    # efficient updates.
    by_region_id = {}
    for (scope, flags, demote_while_busy, hidden), regions in by_id.items():
        dwb_marker = DEMOTE_WHILE_BUSY_MARKER if demote_while_busy else ''
        hidden_marker = HIDDEN_STYLE_MARKER if hidden else ''
        region_id = (
            'SL.{}.Highlights.{}{}|{}|{}'
            .format(linter_name, dwb_marker, hidden_marker, scope, flags))
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


def undraw(view):
    for key in get_regions_keys(view):
        view.erase_regions(key)
    remember_region_keys(view, set())


def draw(view, linter_name, highlight_regions, gutter_regions,
         protected_regions, idle, quiet):
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
        if quiet:
            scope = HIDDEN_SCOPE
        elif not idle and DEMOTE_WHILE_BUSY_MARKER in region_id:
            scope = get_demote_scope()
        view.add_regions(region_id, regions, scope=scope, flags=flags)

    if persist.settings.has('gutter_theme'):
        for region_id, (scope, icon, regions) in gutter_regions.items():
            view.add_regions(region_id, regions, scope=scope, icon=icon)

    # persisting region keys for later clearance
    new_region_keys = other_region_keys | new_linter_keys
    remember_region_keys(view, new_region_keys)


# --------------- TOOLTIP HANDLING ----------------- #


class TooltipController(sublime_plugin.EventListener):
    def on_hover(self, view, point, hover_zone):
        """On mouse hover event hook.

        Arguments:
            view (View): The view which received the event.
            point (Point): The text position where the mouse hovered
            hover_zone (int): The context the event was triggered in
        """
        if hover_zone == sublime.HOVER_GUTTER:
            if persist.settings.get('show_hover_line_report') and any(
                region.contains(point)
                for key in get_regions_keys(view) if '.Gutter.' in key
                for region in view.get_regions(key)
            ):
                open_tooltip(view, point, True)

        elif hover_zone == sublime.HOVER_TEXT:
            if (
                persist.settings.get('show_hover_region_report') and
                view.id() not in State['quiet_views']
            ):
                idle = view.id() in State['idle_views']
                if any(
                    region.contains(point)
                    for key in get_regions_keys(view)
                    if (
                        '.Highlights.' in key and
                        HIDDEN_STYLE_MARKER not in key and
                        # Select visible highlights; when `idle` all regions
                        # are visible, otherwise all *not* demoted regions.
                        (idle or DEMOTE_WHILE_BUSY_MARKER not in key)
                    )
                    for region in view.get_regions(key)
                ):
                    open_tooltip(view, point)


class SublimeLinterLineReportCommand(sublime_plugin.WindowCommand):
    def run(self):
        open_tooltip(self.window.active_view(), line_report=True)


def open_tooltip(active_view, point=None, line_report=False):
    """Show a tooltip containing all linting errors on a given line."""
    stylesheet = '''
        body {
            word-wrap: break-word;
        }
        .error {
            color: var(--redish);
            font-weight: bold;
        }
        .warning {
            color: var(--yellowish);
            font-weight: bold;
        }
    '''

    template = '''
        <body id="sublimelinter-tooltip">
            <style>{stylesheet}</style>
            <div>{message}</div>
        </body>
    '''

    # Leave any existing popup open without replacing it
    # don't let the popup flicker / fight with other packages
    if active_view.is_popup_visible():
        return

    if point is None:
        line, col = get_current_pos(active_view)
    else:  # provided by hover
        line, col = active_view.rowcol(point)

    bid = active_view.buffer_id()

    errors = persist.errors[bid]
    errors = [e for e in errors if e["line"] == line]
    if not line_report:
        errors = [e for e in errors if e["start"] <= col <= e["end"]]
    if not errors:
        return

    tooltip_message = join_msgs(errors, line_report)
    if not tooltip_message:
        return

    location = active_view.text_point(line, col)
    active_view.show_popup(
        template.format(stylesheet=stylesheet, message=tooltip_message),
        flags=sublime.HIDE_ON_MOUSE_MOVE_AWAY,
        location=location,
        max_width=1000
    )


def join_msgs(errors, show_count=False):

    if show_count:
        part = '''
            <div class="{classname}">{count} {heading}</div>
            <div>{messages}</div>
        '''
    else:
        part = '''
            <div>{messages}</div>
        '''

    tmpl_with_code = "{linter}: {code} - {escaped_msg}"
    tmpl_sans_code = "{linter}: {escaped_msg}"

    all_msgs = ""
    for error_type in (WARNING, ERROR):
        heading = error_type
        filled_templates = []
        msg_list = [e for e in errors if e["error_type"] == error_type]

        if not msg_list:
            continue

        msg_list = sorted(msg_list, key=lambda x: (x["start"], x["end"]))
        count = len(msg_list)

        for item in msg_list:
            msg = html.escape(item["msg"], quote=False)
            tmpl = tmpl_with_code if item.get('code') else tmpl_sans_code
            filled_templates.append(tmpl.format(escaped_msg=msg, **item))

        if count > 1:  # pluralize
            heading += "s"

        all_msgs += part.format(
            classname=error_type,
            count=count,
            heading=heading,
            messages='<br />'.join(filled_templates)
        )
    return all_msgs


def get_current_pos(view):
    try:
        return view.rowcol(view.sel()[0].begin())
    except (AttributeError, IndexError):
        return -1, -1
