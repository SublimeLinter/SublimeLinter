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
flatten = chain.from_iterable


MYPY = False
if MYPY:
    from typing import (
        Callable, DefaultDict, Dict, Iterable, List, Hashable, Optional,
        Protocol, Set, Tuple, TypeVar
    )
    from mypy_extensions import TypedDict
    T = TypeVar('T')
    LintError = persist.LintError
    LinterName = persist.LinterName

    RegionKey = str
    Flags = int
    Icon = str
    Scope = str
    Squiggles = Dict[RegionKey, Tuple[Scope, Flags, List[sublime.Region]]]
    GutterIcons = Dict[RegionKey, Tuple[Scope, Icon, List[sublime.Region]]]
    ProtectedRegions = List[sublime.Region]

    State_ = TypedDict('State_', {
        'active_view': Optional[sublime.View],
        'current_sel': Tuple[sublime.Region, ...],
        'idle_views': Set[sublime.ViewId],
        'quiet_views': Set[sublime.ViewId],
        'views': Set[sublime.ViewId]
    })

    class DemotePredicate(Protocol):
        def __call__(self, selected_text, **error):
            # type: (str, object) -> bool
            ...


UNDERLINE_FLAGS = (
    sublime.DRAW_NO_FILL |
    sublime.DRAW_NO_OUTLINE
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


State = {
    'active_view': None,
    'current_sel': tuple(),
    'idle_views': set(),
    'quiet_views': set(),
    'views': set()
}  # type: State_


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
def on_lint_result(filename, linter_name, **kwargs):
    views = list(all_views_into_file(filename))
    if not views:
        return

    highlight_linter_errors(views, filename, linter_name)


class UpdateOnLoadController(sublime_plugin.EventListener):
    def on_load_async(self, view):
        # update this new view with any errors it currently has
        filename = util.get_filename(view)
        errors = persist.file_errors.get(filename)
        if errors:
            set_idle(view, True)  # show errors immediately
            linter_names = set(error['linter'] for error in errors)
            for linter_name in linter_names:
                highlight_linter_errors([view], filename, linter_name)

    on_clone_async = on_load_async


def highlight_linter_errors(views, filename, linter_name):
    errors = persist.file_errors[filename]
    update_error_priorities_inline(errors)
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


def update_error_priorities_inline(errors):
    # type: (List[LintError]) -> None
    # We need to update `prioritiy` here (although a user will rarely change
    # this setting that often) for correctness. Generally, on views with
    # multiple linters running, we compare new lint results from the
    # 'fast' linters with old results from the 'slower' linters. The below
    # `filter_errors` produces wrong results with outdated priorities.
    #
    # ATT: inline, so this change propagates throughout the system
    for error in errors:
        error['priority'] = style.get_value('priority', error, 0)


def prepare_data(errors):
    # We need to filter the errors, bc we cannot draw multiple regions
    # on the same position. E.g. we can only draw one gutter icon per line,
    # and we can only 'underline' a word once.
    return (
        filter_errors(errors, by_position),  # highlights
        filter_errors(errors, by_line)       # gutter icons
    )


def filter_errors(errors, group_fn):
    # type: (List[LintError], Callable[[LintError], Hashable]) -> List[LintError]
    grouped = defaultdict(list)  # type: DefaultDict[Hashable, List[LintError]]
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
    # type: (LintError) -> Hashable
    return (error['line'], error['start'], error['end'])


def by_line(error):
    # type: (LintError) -> Hashable
    return error['line']


def prepare_protected_regions(view, errors):
    # type: (sublime.View, List[LintError]) -> ProtectedRegions
    return list(
        flatten(
            regions
            for (_, _, regions) in prepare_gutter_data(view, '_', errors).values()
        )
    )


def prepare_gutter_data(
    view,         # type: sublime.View
    linter_name,  # type: LinterName
    errors        # type: List[LintError]
):
    # type: (...) -> GutterIcons
    # Compute the icon and scope for the gutter mark from the error.
    # Drop lines for which we don't get a value or for which the user
    # specified 'none'
    by_id = defaultdict(list)  # type: DefaultDict[Tuple[str, str], List[sublime.Region]]
    for error in errors:
        icon = style.get_icon(error)
        if icon == 'none':
            continue

        scope = style.get_icon_scope(error)
        # We draw gutter icons with `flag=sublime.HIDDEN`. The actual width
        # of the region doesn't matter bc Sublime will draw an icon only
        # on the beginning line, which is exactly what we want.
        region = error['region']

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


def prepare_highlights_data(
    view,             # type: sublime.View
    linter_name,      # type: LinterName
    errors,           # type: List[LintError]
    demote_predicate  # type: DemotePredicate
):
    # type: (...) -> Squiggles
    by_id = defaultdict(list)  # type: DefaultDict[Tuple[str, str, int, bool, bool], List[sublime.Region]]
    for error in errors:
        scope = style.get_value('scope', error)
        mark_style = style.get_value('mark_style', error, 'none')

        region = error['region']
        selected_text = error.get('offending_text') or view.substr(region)
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


def undraw(view):
    for key in get_regions_keys(view):
        view.erase_regions(key)
    remember_region_keys(view, set())


def draw(
    view,               # type: sublime.View
    linter_name,        # type: LinterName
    highlight_regions,  # type: Squiggles
    gutter_regions,     # type: GutterIcons
    protected_regions,  # type: ProtectedRegions
    idle,               # type: bool
    quiet               # type: bool
):
    # type: (...) -> None
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

    # remove unused regions
    for key in current_linter_keys - new_linter_keys:
        view.erase_regions(key)

    # overlaying all gutter regions with common invisible one,
    # to create unified handle for GitGutter and other plugins
    if protected_regions:
        view.add_regions(
            PROTECTED_REGIONS_KEY,
            protected_regions
        )
        new_linter_keys.add(PROTECTED_REGIONS_KEY)

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


def get_demote_scope():
    return persist.settings.get('highlights.demote_scope')


def get_demote_predicate():
    # type: () -> DemotePredicate
    setting = persist.settings.get('highlights.demote_while_editing')
    return getattr(DemotePredicates, setting, DemotePredicates.none)


class DemotePredicates:
    @staticmethod
    def none(*args, **kwargs):
        return False

    @staticmethod
    def all(*args, **kwargs):
        return True

    @staticmethod
    def ws_only(selected_text, **kwargs):
        return bool(WS_ONLY.search(selected_text))

    @staticmethod
    def some_ws(selected_text, **kwargs):
        return bool(SOME_WS.search(selected_text))
    ws_regions = some_ws

    @staticmethod
    def multilines(selected_text, **kwargs):
        return bool(MULTILINES.search(selected_text))

    @staticmethod
    def warnings(selected_text, error_type, **kwargs):
        return error_type == WARNING


# --------------- ZOMBIE PROTECTION ---------------- #
#    [¬º°]¬ [¬º°]¬  [¬º˚]¬  [¬º˙]* ─ ─ ─ ─ ─ ─ ─╦╤︻ #

EVERSTORE = defaultdict(set)  # type: DefaultDict[sublime.BufferId, Set[RegionKey]]
STORAGE_KEY = 'SL.{}.region_keys'


def get_regions_keys(view):
    # type: (sublime.View) -> Set[RegionKey]
    setting_key = STORAGE_KEY.format(view.id())
    return set(view.settings().get(setting_key) or [])


def remember_region_keys(view, keys):
    # type: (sublime.View, Set[RegionKey]) -> None
    setting_key = STORAGE_KEY.format(view.id())
    view.settings().set(setting_key, list(keys))


def add_region_keys_to_everstore(view, keys):
    # type: (sublime.View, Set[RegionKey]) -> None
    bid = view.buffer_id()
    EVERSTORE[bid] |= keys


def restore_from_everstore(view):
    # type: (sublime.View) -> None
    bid = view.buffer_id()
    remember_region_keys(view, EVERSTORE[bid])


class ZombieController(sublime_plugin.EventListener):
    def on_text_command(self, view, cmd, args):
        # type: (sublime.View, str, Dict) -> None
        if cmd in ['undo', 'redo_or_repeat']:
            restore_from_everstore(view)

    def on_pre_close(self, view):
        # type: (sublime.View) -> None
        bid = view.buffer_id()
        views_into_buffer = list(all_views_into_buffer(bid))

        if len(views_into_buffer) <= 1:
            EVERSTORE.pop(bid, None)


# ----------------------------------------------------- #


class ViewListCleanupController(sublime_plugin.EventListener):
    def on_pre_close(self, view):
        vid = view.id()
        State['idle_views'].discard(vid)
        State['quiet_views'].discard(vid)
        State['views'].discard(vid)


class RevisitErrorRegions(sublime_plugin.EventListener):
    @util.distinct_until_buffer_changed
    def on_modified(self, view):
        if not util.is_lintable(view):
            return

        active_view = State['active_view']
        if active_view and view.buffer_id() == active_view.buffer_id():
            view = active_view

        revalidate_regions(view)
        # (Maybe) update the error store on the worker thread which
        # forms a queue so we don't need locks.
        sublime.set_timeout_async(lambda: maybe_update_error_store(view))


def maybe_update_error_store(view):
    # type: (sublime.View) -> None
    filename = util.get_filename(view)
    errors = persist.file_errors.get(filename)
    if not errors:
        return

    region_keys = get_regions_keys(view)
    uid_key_map = {
        extract_uid_from_key(key): key
        for key in region_keys
        if '.Highlights.' in key
    }

    changed = False
    new_errors = []
    discarded_keys = set()
    for error in errors:
        uid = error['uid']
        key = uid_key_map.get(uid, None)
        region = head(view.get_regions(key)) if key else None
        if region is None or region == error['region']:
            new_errors.append(error)
            continue

        changed = True
        line, start = view.rowcol(region.begin())
        if region.empty() and start == 0:
            # Dangle! Sublime has invalidated our region, it has
            # zero length, and moved to a different line at col 0.
            # It is useless now so we remove the error by not
            # copying it.
            view.erase_regions(key)  # type: ignore
            discarded_keys.add(key)
            continue

        endLine, end = view.rowcol(region.end())
        error = error.copy()
        error.update({
            'region': region,
            'line': line,
            'start': start,
            'endLine': endLine,
            'end': end
        })
        new_errors.append(error)

    if changed:
        persist.file_errors[filename] = new_errors
        events.broadcast('updated_error_positions', {'filename': filename})

    if discarded_keys:
        remember_region_keys(view, region_keys - discarded_keys)


def revalidate_regions(view):
    # type: (sublime.View) -> None
    vid = view.id()
    if vid in State['quiet_views']:
        return

    selections = get_current_sel(view)  # frozen sel() for this operation
    region_keys = get_regions_keys(view)
    to_hide = []
    for key in region_keys:
        if '.Highlights.' in key:
            if HIDDEN_STYLE_MARKER in key:
                continue
            region = head(view.get_regions(key))
            if region is None:
                continue

            if any(region.contains(s) for s in selections):
                view.erase_regions(key)
                to_hide.append((key, region))

        elif '.Gutter.' in key:
            regions = view.get_regions(key)
            filtered_regions = list(filter(None, regions))
            if len(filtered_regions) != len(regions):
                _ns, scope, icon = key.split('|')
                view.add_regions(
                    key, filtered_regions, scope=scope, icon=icon,
                    flags=sublime.HIDDEN
                )
    if to_hide:
        sublime.set_timeout_async(lambda: make_regions_hidden(view, to_hide))


def make_regions_hidden(view, key_regions):
    # type: (sublime.View, List[Tuple[RegionKey, sublime.Region]]) -> None
    region_keys = get_regions_keys(view)
    new_drawn_keys = set()
    discarded_keys = set()
    for key, region in key_regions:
        namespace, uid, scope, flags = key.split('|')
        new_key = '|'.join(
            [namespace + HIDDEN_STYLE_MARKER, uid, scope, flags]
        )
        view.add_regions(
            new_key, [region], scope=HIDDEN_SCOPE, flags=int(flags)
        )
        discarded_keys.add(key)
        new_drawn_keys.add(new_key)

    remember_region_keys(
        view, region_keys - discarded_keys | new_drawn_keys
    )
    add_region_keys_to_everstore(view, new_drawn_keys)


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
        if active_view and view.buffer_id() == active_view.buffer_id():
            set_idle(active_view, False)

    @util.distinct_until_buffer_changed
    def on_post_save_async(self, view):
        active_view = State['active_view']
        if active_view and view.buffer_id() == active_view.buffer_id():
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
    # type: (sublime.View, bool) -> None
    vid = view.id()
    if vid in State['quiet_views']:
        return

    region_keys = get_regions_keys(view)
    for key in region_keys:
        if DEMOTE_WHILE_BUSY_MARKER in key:
            _namespace, _uid, scope, flags = key.split('|')
            if not show:
                scope = get_demote_scope()

            regions = view.get_regions(key)
            view.add_regions(key, regions, scope=scope, flags=int(flags))


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
    # type: (sublime.View, bool) -> None
    region_keys = get_regions_keys(view)
    for key in region_keys:
        if '.Highlights.' not in key:
            continue

        _namespace, _uid, scope, flags = key.split('|')
        if not show:
            scope = HIDDEN_SCOPE

        regions = view.get_regions(key)
        view.add_regions(key, regions, scope=scope, flags=int(flags))


# --------------- UTIL FUNCTIONS ------------------- #


def get_current_sel(view):
    # type: (sublime.View) -> Tuple[sublime.Region, ...]
    return tuple(s for s in view.sel())


def head(iterable):
    # type: (Iterable[T]) -> Optional[T]
    return next(iter(iterable), None)


def extract_uid_from_key(key):
    _namespace, uid, _scope, _flags = key.split('|')
    return uid


def all_views_into_buffer(buffer_id):
    for window in sublime.windows():
        for view in window.views():
            if view.buffer_id() == buffer_id:
                yield view


def all_views_into_file(filename):
    for window in sublime.windows():
        for view in window.views():
            if util.get_filename(view) == filename:
                yield view


# --------------- TOOLTIP HANDLING ----------------- #


class TooltipController(sublime_plugin.EventListener):
    def on_hover(self, view, point, hover_zone):
        if hover_zone == sublime.HOVER_GUTTER:
            if persist.settings.get('show_hover_line_report'):
                line_region = view.line(point)
                if any(
                    region.intersects(line_region)
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
    .copy {
        margin-top: 0.5em;
    }
'''

TOOLTIP_TEMPLATE = '''
    <body id="sublimelinter-tooltip">
        <style>{stylesheet}</style>
        <div>{content}</div>
        <div class="copy"><a href="copy">Copy</a></div>
    </body>
'''


def get_errors_where(view, fn):
    filename = util.get_filename(view)
    return [
        error for error in persist.file_errors[filename]
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

    def on_navigate(href: str) -> None:
        if href == "copy":
            sublime.set_clipboard(join_msgs_raw(errors))
            view.window().status_message("SublimeLinter: info copied to clipboard")
            view.hide_popup()

    tooltip_message = join_msgs(errors, show_count=line_report, width=80)
    view.show_popup(
        TOOLTIP_TEMPLATE.format(stylesheet=TOOLTIP_STYLES, content=tooltip_message),
        flags=sublime.HIDE_ON_MOUSE_MOVE_AWAY,
        location=point,
        max_width=1000,
        on_navigate=on_navigate
    )


def join_msgs_raw(errors):
    # Take an `errors` iterable and reduce it to a string without HTML tags.
    sorted_errors = sorted(errors, key=lambda r: (r["linter"], r["error_type"]))
    return "\n\n".join("{}: {}\n{}{}".format(
        e["linter"], e["error_type"], e["code"] + " - " if e["code"] else "", e["msg"]) for e in sorted_errors
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
