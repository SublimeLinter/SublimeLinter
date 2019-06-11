from collections import defaultdict
import html
from itertools import chain
from functools import partial
import re
import textwrap

import sublime
import sublime_plugin

from .lint import persist, events, style, util, queue
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

SOME_WS = re.compile(r'\s')
FALLBACK_MARK_STYLE = 'outline'

WS_ONLY = re.compile(r'^\s+$')
MULTILINES = re.compile('\n')
DEMOTE_WHILE_BUSY_MARKER = '%DWB%'
HIDDEN_STYLE_MARKER = '%HIDDEN%'

STORAGE_KEY = 'SL.{}.region_keys'


def remember_region_keys(view, keys):
    setting_key = STORAGE_KEY.format(view.id())
    view.settings().set(setting_key, list(keys))


def get_regions_keys(view):
    setting_key = STORAGE_KEY.format(view.id())
    return set(view.settings().get(setting_key) or [])


State = {
    'active_view': None,
    'current_sel': tuple(),
    'idle_views': set(),
    'quiet_views': set(),
    'views': set()
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

    view = views[0]  # to calculate regions we can take any of the views
    protected_regions = prepare_protected_regions(view, errors_for_the_gutter)

    # `prepare_data` returns the state of the view as we would like to draw it.
    # But we cannot *redraw* regions as soon as the buffer changed, in fact
    # Sublime already moved all the regions for us.
    # So for the next step, we filter for errors from the current finished
    # lint, namely from linter_name. All other errors are already UP-TO-DATE.

    errors_for_the_highlights = [error for error in errors_for_the_highlights
                                 if error['linter'] == linter_name]
    errors_for_the_gutter = [error for error in errors_for_the_gutter
                             if error['linter'] == linter_name]

    demote_predicate = get_demote_predicate()
    highlight_regions = prepare_highlights_data(
        view, linter_name, errors_for_the_highlights,
        demote_predicate=demote_predicate)
    gutter_regions = prepare_gutter_data(
        view, linter_name, errors_for_the_gutter)

    for view in views:
        vid = view.id()

        if (
            persist.settings.get('highlights.start_hidden') and
            vid not in State['quiet_views'] and
            vid not in State['views']
        ):
            State['quiet_views'].add(vid)

        if vid not in State['views']:
            State['views'].add(vid)

        draw(
            view,
            linter_name,
            highlight_regions,
            gutter_regions,
            protected_regions,
            idle=(vid in State['idle_views']),
            quiet=(vid in State['quiet_views'])
        )


class ViewListCleanupController(sublime_plugin.EventListener):
    def on_pre_close(self, view):
        vid = view.id()
        State['idle_views'].discard(vid)
        State['quiet_views'].discard(vid)
        State['views'].discard(vid)


class UpdateErrorRegions(sublime_plugin.EventListener):
    @util.distinct_until_buffer_changed
    def on_modified_async(self, view):
        update_error_regions(view)


def update_error_regions(view):
    bid = view.buffer_id()
    errors = persist.errors.get(bid)
    if not errors:
        return

    uid_region_map = {
        extract_uid_from_key(key): head(view.get_regions(key))
        for key in get_regions_keys(view)
        if '.Highlights.' in key
    }

    for error in errors:
        uid = error['uid']
        region = uid_region_map.get(uid, None)
        if region is None:
            continue

        line, start = view.rowcol(region.begin())
        endLine, end = view.rowcol(region.end())
        error.update({
            'region': region,
            'line': line,
            'start': start,
            'endLine': endLine,
            'end': end
        })

    events.broadcast('updated_error_positions', {'view': view, 'bid': bid})


def head(iterable):
    return next(iter(iterable), None)


def extract_uid_from_key(key):
    _namespace, uid, _scope, _flags = key.split('|')
    return uid


def get_demote_predicate():
    setting = persist.settings.get('highlights.demote_while_editing')
    if setting == 'none':
        return demote_nothing

    if setting == 'all':
        return demote_all

    if setting == 'ws_only':
        return demote_ws_only

    if setting in ('some_ws', 'ws_regions'):  # 'ws_regions' is deprecated
        return demote_some_ws

    if setting == 'multilines':
        return demote_multilines

    if setting == 'warnings':
        return demote_warnings


def get_demote_scope():
    return persist.settings.get('highlights.demote_scope')


def demote_nothing(*args, **kwargs):
    return False


def demote_all(*args, **kwargs):
    return True


def demote_ws_only(selected_text, **kwargs):
    return bool(WS_ONLY.search(selected_text))


def demote_some_ws(selected_text, **kwargs):
    return bool(SOME_WS.search(selected_text))


def demote_multilines(selected_text, **kwargs):
    return bool(MULTILINES.search(selected_text))


def demote_warnings(selected_text, error_type, **kwargs):
    return error_type == WARNING


class IdleViewController(sublime_plugin.EventListener):
    def on_activated_async(self, active_view):
        previous_view = State['active_view']
        State.update({
            'active_view': active_view,
            'current_sel': get_current_sel(active_view)
        })

        if previous_view and previous_view.id() != active_view.id():
            set_idle(previous_view, True)

        set_idle(active_view, True)

    @util.distinct_until_buffer_changed
    def on_modified_async(self, view):
        active_view = State['active_view']
        if view.buffer_id() == active_view.buffer_id():
            set_idle(active_view, False)

    @util.distinct_until_buffer_changed
    def on_post_save_async(self, view):
        active_view = State['active_view']
        if view.buffer_id() == active_view.buffer_id():
            set_idle(active_view, True)

    def on_selection_modified_async(self, view):
        active_view = State['active_view']
        # Do not race between `plugin_loaded` and this event handler
        if active_view is None:
            return

        if view.buffer_id() != active_view.buffer_id():
            return

        current_sel = get_current_sel(active_view)
        if current_sel != State['current_sel']:
            State.update({'current_sel': current_sel})

            time_to_idle = persist.settings.get('highlights.time_to_idle')
            queue.debounce(
                partial(set_idle, active_view, True),
                delay=time_to_idle,
                key='highlights.{}'.format(active_view.id())
            )


def get_current_sel(view):
    return tuple(s for s in view.sel())


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
            _namespace, _uid, scope, flags = key.split('|')
            flags = int(flags)
            if not show:
                scope = get_demote_scope()

            regions = view.get_regions(key)
            view.add_regions(key, regions, scope=scope, flags=flags)


class SublimeLinterToggleHighlights(sublime_plugin.WindowCommand):
    def run(self):
        view = self.window.active_view()
        if not view:
            return

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

        _namespace, _uid, scope, flags = key.split('|')
        flags = int(flags)
        if not show:
            scope = HIDDEN_SCOPE

        regions = view.get_regions(key)
        view.add_regions(key, regions, scope=scope, flags=flags)


class InvalidateEditedErrorController(sublime_plugin.EventListener):
    @util.distinct_until_buffer_changed
    def on_modified_async(self, view):
        active_view = State['active_view']
        if view.buffer_id() == active_view.buffer_id():
            invalidate_regions_under_cursor(active_view)


def invalidate_regions_under_cursor(view):
    vid = view.id()
    if vid in State['quiet_views']:
        return

    selections = view.sel()
    region_keys = get_regions_keys(view)
    for key in region_keys:
        if '.Highlights.' in key:
            if any(
                region.contains(selection)
                for region in view.get_regions(key)
                for selection in selections
            ):
                view.erase_regions(key)

        elif '.Gutter.' in key:
            regions = view.get_regions(key)
            filtered_regions = [
                region for region in regions
                if not region.empty()]
            if len(filtered_regions) != len(regions):
                _ns, scope, icon = key.split('|')
                view.add_regions(key, filtered_regions, scope=scope, icon=icon,
                                 flags=sublime.HIDDEN)


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
    # We need to update `prioritiy` here (although a user will rarely change
    # this setting that often) for correctness. Generally, on views with
    # multiple linters running, we compare new lint results from the
    # 'fast' linters with old results from the 'slower' linters. The below
    # `filter_errors` produces wrong results with outdated priorities.
    #
    # ATT: inline, so this change propagates throughout the system
    for error in errors:
        error['priority'] = style.get_value('priority', error, 0)

    # We need to filter the errors, bc we cannot draw multiple regions
    # on the same position. E.g. we can only draw one gutter icon per line,
    # and we can only 'underline' a word once.
    return (
        filter_errors(errors, by_position),  # highlights
        filter_errors(errors, by_line)       # gutter icons
    )


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
        icon = style.get_icon(error)
        if icon == 'none':
            continue

        scope = style.get_icon_scope(error)
        pos = get_line_start(view, error['line'])
        region = view.line(pos)

        # We group towards the optimal sublime API usage:
        #   view.add_regions(uuid(), [region], scope, icon)
        id = (scope, icon)
        by_id[id].append(region)

    # Exchange the `id` with a regular region_id which is a unique string, so
    # uuid() would be candidate here, that can be reused for efficient updates.
    by_region_id = {}
    for (scope, icon), regions in by_id.items():
        region_id = 'SL.{}.Gutter.|{}|{}'.format(linter_name, scope, icon)
        by_region_id[region_id] = (scope, icon, regions)

    return by_region_id


def prepare_highlights_data(view, linter_name, errors, demote_predicate):
    by_id = defaultdict(list)
    for error in errors:
        scope = style.get_value('scope', error)
        mark_style = style.get_value('mark_style', error, 'none')

        region = error['region']

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
        uid = error['uid']
        id = (uid, scope, flags, demote_while_busy, hidden)
        by_id[id].append(region)

    # Exchange the `id` with a regular sublime region_id which is a unique
    # string. Generally, uuid() would suffice, but generate an id here for
    # efficient updates.
    by_region_id = {}
    for (uid, scope, flags, demote_while_busy, hidden), regions in by_id.items():
        dwb_marker = DEMOTE_WHILE_BUSY_MARKER if demote_while_busy else ''
        hidden_marker = HIDDEN_STYLE_MARKER if hidden else ''
        region_id = (
            'SL.{}.Highlights.{}{}|{}|{}|{}'
            .format(linter_name, dwb_marker, hidden_marker, uid, scope, flags))
        by_region_id[region_id] = (scope, flags, regions)

    return by_region_id


def get_line_start(view, line):
    return view.text_point(line, 0)


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

    # overlaying all gutter regions with common invisible one,
    # to create unified handle for GitGutter and other plugins
    if protected_regions:
        view.add_regions(
            PROTECTED_REGIONS_KEY,
            protected_regions
        )
        new_linter_keys.add(PROTECTED_REGIONS_KEY)

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

    for region_id, (scope, icon, regions) in gutter_regions.items():
        view.add_regions(region_id, regions, scope=scope, icon=icon,
                         flags=sublime.HIDDEN)

    # persisting region keys for later clearance
    new_region_keys = other_region_keys | new_linter_keys
    remember_region_keys(view, new_region_keys)
    add_region_keys_to_everstore(view, new_linter_keys)


# --------------- ZOMBIE PROTECTION ---------------- #
#    [¬º°]¬ [¬º°]¬  [¬º˚]¬  [¬º˙]* ─ ─ ─ ─ ─ ─ ─╦╤︻ #

EVERSTORE = defaultdict(set)


def add_region_keys_to_everstore(view, keys):
    bid = view.buffer_id()
    EVERSTORE[bid] |= keys


def restore_from_everstore(view):
    bid = view.buffer_id()
    remember_region_keys(view, EVERSTORE[bid])


class ZombieController(sublime_plugin.EventListener):
    def on_text_command(self, view, cmd, args):
        if cmd in ['undo', 'redo_or_repeat']:
            restore_from_everstore(view)

    def on_pre_close(self, view):
        bid = view.buffer_id()
        views_into_buffer = list(all_views_into_buffer(bid))

        if len(views_into_buffer) <= 1:
            EVERSTORE.pop(bid, None)


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
                open_tooltip(view, point, line_report=True)

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
                    open_tooltip(view, point, line_report=False)


class SublimeLinterLineReportCommand(sublime_plugin.WindowCommand):
    def run(self):
        view = self.window.active_view()
        if not view:
            return

        point = view.sel()[0].begin()
        open_tooltip(view, point, line_report=True)


TOOLTIP_STYLES = '''
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

TOOLTIP_TEMPLATE = '''
    <body id="sublimelinter-tooltip">
        <style>{stylesheet}</style>
        <div>{content}</div>
    </body>
'''


def get_errors_where(view, fn):
    bid = view.buffer_id()
    return [
        error for error in persist.errors[bid]
        if fn(error['region'])
    ]


def open_tooltip(view, point, line_report=False):
    """Show a tooltip containing all linting errors on a given line."""
    # Leave any existing popup open without replacing it
    # don't let the popup flicker / fight with other packages
    if view.is_popup_visible():
        return

    if line_report:
        line = view.full_line(point)
        errors = get_errors_where(
            view, lambda region: region.intersects(line))
    else:
        errors = get_errors_where(
            view, lambda region: region.contains(point))

    if not errors:
        return

    max_width = min(1000, view.viewport_extent()[0])
    max_chars = int(max_width // view.em_width() - 1)
    tooltip_message = join_msgs(errors, show_count=line_report, width=max_chars)
    view.show_popup(
        TOOLTIP_TEMPLATE.format(stylesheet=TOOLTIP_STYLES, content=tooltip_message),
        flags=sublime.HIDE_ON_MOUSE_MOVE_AWAY,
        location=point,
        max_width=max_width
    )


def join_msgs(errors, show_count, width):
    if show_count:
        part = '''
            <div class="{classname}">{count} {heading}</div>
            <div>{messages}</div>
        '''
    else:
        part = '''
            <div>{messages}</div>
        '''

    tmpl_with_code = "{code} - {msg}"
    tmpl_sans_code = "{msg}"

    all_msgs = ""
    for error_type in (WARNING, ERROR):
        errors_by_type = sorted(
            (e for e in errors if e["error_type"] == error_type),
            key=lambda x: (x["start"], x["end"])
        )
        if not errors_by_type:
            continue

        filled_templates = []
        for error in errors_by_type:
            tmpl = tmpl_with_code if error.get('code') else tmpl_sans_code
            prefix_len = len(error['linter']) + 2
            lines = textwrap.wrap(
                tmpl.format(**error),
                width=width,
                initial_indent=" " * prefix_len,
                subsequent_indent=" " * prefix_len
            )
            lines[0] = "{linter}: ".format(**error) + lines[0].lstrip()

            filled_templates.extend([
                html.escape(line, quote=False).replace(' ', '&nbsp;')
                for line in lines
            ])

        heading = error_type
        count = len(errors_by_type)
        if count > 1:  # pluralize
            heading += "s"

        all_msgs += part.format(
            classname=error_type,
            count=count,
            heading=heading,
            messages='<br />'.join(filled_templates)
        )
    return all_msgs
