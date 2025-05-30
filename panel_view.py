from __future__ import annotations
from collections import defaultdict
from functools import lru_cache, partial
from itertools import chain
import os
import sublime
import sublime_plugin
import textwrap
import uuid

from .lint import elect, events, persist, util

from typing import (
    Any, Callable, Collection, Dict, Iterable, List,
    Optional, TypedDict, TypeVar
)


T = TypeVar('T')
U = TypeVar('U')
LintError = persist.LintError
FileName = persist.FileName
LinterName = persist.LinterName
Reason = Optional[str]
Action = Callable[[], None]
ErrorsByFile = Dict[FileName, List[LintError]]


class State_(TypedDict):
    active_view: Optional[sublime.View]
    active_filename: Optional[str]
    cursor: int
    panel_opened_automatically: set[sublime.WindowId]


class DrawInfo(TypedDict, total=False):
    panel: sublime.View
    content: str
    errors_from_active_view: list[LintError]
    nearby_lines: int | list[int]


PANEL_NAME = "SublimeLinter"
OUTPUT_PANEL = "output." + PANEL_NAME
NO_RESULTS_MESSAGE = "  No lint results."
State: State_ = {
    'active_view': None,
    'active_filename': None,
    'cursor': -1,
    'panel_opened_automatically': set()
}


def plugin_loaded():
    active_window = sublime.active_window()
    active_view = active_window.active_view()
    State.update({
        'active_view': active_view,
        'active_filename': util.canonical_filename(active_view) if active_view else None,
    })
    ensure_panel(active_window)


def plugin_unloaded():
    events.off(on_lint_result)
    events.off(on_updated_error_positions)
    events.off(on_renamed_file)

    for window in sublime.windows():
        window.destroy_output_panel(PANEL_NAME)


LINT_RESULT_CACHE: defaultdict[str, list[tuple[FileName, Reason]]] = defaultdict(list)
REQUEST_LINT_RESULT: dict[str, str] = {}


flatten = chain.from_iterable


def unzip(zipped: Iterable[tuple[T, U]]) -> tuple[tuple[T, ...], tuple[U, ...]]:
    return tuple(zip(*zipped))  # type: ignore


def do_intersect(a: set, b: Iterable) -> bool:
    return not a.isdisjoint(b)


@events.on(events.LINT_RESULT)
def on_lint_result(filename: FileName, linter_name: LinterName, reason: Reason = None, **kwargs: Any) -> None:
    LINT_RESULT_CACHE[linter_name].append((filename, reason))

    strategy = (
        run_immediately
        if State['active_filename'] == filename
        else run_on_next_tick
    )
    strategy(
        REQUEST_LINT_RESULT,
        linter_name,
        lambda: execute_on_lint_result_request(linter_name)
    )


def run_immediately(token_cache: dict[T, str], key: T, action: Action) -> None:
    """Invalidate `key` and run `action` immediately."""
    token_cache[key] = uuid.uuid4().hex
    action()


def run_on_next_tick(token_cache: dict[T, str], key: T, action: Action) -> None:
    """Enqueue `action` to be run on next worker tick.

    Subsequent calls with the same `key` in the same tick, t.i.
    before the worker could have emptied the queue, will replace
    the `action`.  (T.i. for n calls to action only 1 will run,
    the other will be erased.)
    """
    token = token_cache[key] = uuid.uuid4().hex
    proposition = lambda: token_cache[key] == token
    sublime.set_timeout_async(lambda: maybe_run(proposition, action))


def maybe_run(prop: Callable[[], bool], action: Action) -> None:
    if prop():
        action()


def execute_on_lint_result_request(linter_name: LinterName) -> None:
    calls = LINT_RESULT_CACHE.pop(linter_name)
    filenames, reasons = unzip(calls)
    _on_lint_result(
        set(filenames),
        do_intersect({'on_save', 'on_user_request'}, reasons)
    )


def _on_lint_result(filenames: Iterable[FileName], maybe_toggle_panel_automatically: bool) -> None:
    for window in sublime.windows():
        panel_open = panel_is_active(window)
        if (
            (panel_open or maybe_toggle_panel_automatically)
            and do_intersect(filenames_per_window(window), filenames)
        ):
            if panel_open:
                fill_panel(window)

            if maybe_toggle_panel_automatically:
                toggle_panel_if_errors(window, filenames)


@events.on('error_positions_changed')
def on_updated_error_positions(filename, **kwargs):
    for window in sublime.windows():
        if panel_is_active(window) and filename in filenames_per_window(window):
            fill_panel(window)


@events.on('file_renamed')
def on_renamed_file(new_filename, **kwargs):
    # update all panels that contain this file
    for window in sublime.windows():
        if new_filename in filenames_per_window(window):
            if panel_is_active(window):
                fill_panel(window)


class UpdateState(sublime_plugin.EventListener):
    def on_activated_async(self, active_view):
        if not util.is_lintable(active_view):
            return

        window = active_view.window()
        if not window:
            return

        State.update({
            'active_view': active_view,
            'active_filename': util.canonical_filename(active_view),
            'cursor': get_current_pos(active_view)
        })
        ensure_panel(window)
        if panel_is_active(window):
            fill_panel(window)
            start_viewport_poller()
        else:
            stop_viewport_poller()

    def on_selection_modified_async(self, view):
        active_view = State['active_view']
        # Do not race between `plugin_loaded` and this event handler
        if active_view is None:
            return

        if view.buffer_id() != active_view.buffer_id():
            return

        cursor = get_current_pos(active_view)
        if cursor != State['cursor']:
            State.update({
                'cursor': cursor
            })
            if panel_is_active(active_view.window()):
                update_panel_selection(**State)  # type: ignore[arg-type]

    def on_pre_close(self, view):
        window = view.window()
        # If the user closes the window and not *just* a view, the view is
        # already detached, hence we check.
        if window and panel_is_active(window):
            sublime.set_timeout_async(lambda: fill_panel(window))

    @util.distinct_until_buffer_changed
    def on_post_save_async(self, view: sublime.View) -> None:
        # In background mode most of the time the errors are already up-to-date
        # on save, so we (maybe) show the panel immediately.
        if view_gets_linted_on_modified_event(view):
            toggle_panel_if_errors(view.window(), [util.canonical_filename(view)])

    def on_post_window_command(self, window, command_name, args):
        if command_name == 'hide_panel':
            State['panel_opened_automatically'].discard(window.id())
            stop_viewport_poller()
            return

        if command_name == 'show_panel':

            if args.get('panel') == OUTPUT_PANEL:
                fill_panel(window)

                # Apply focus fix to ensure `next_result` is bound to our panel.
                active_group = window.active_group()
                active_view = window.active_view()

                panel = get_panel(window)
                window.focus_view(panel)

                window.focus_group(active_group)
                window.focus_view(active_view)
                sublime.set_timeout(start_viewport_poller)
            else:
                stop_viewport_poller()


def view_gets_linted_on_modified_event(view: sublime.View) -> bool:
    return any(elect.runnable_linters_for_view(view, 'on_modified'))


def toggle_panel_if_errors(window: Optional[sublime.Window], filenames: Iterable[FileName]) -> None:
    """Toggle the panel if the view or window has problems, depending on settings."""
    if window is None:
        return

    show_panel_on_save = persist.settings.get('show_panel_on_save')
    if show_panel_on_save == 'never':
        return

    ignored_error_types = persist.settings.get('show_panel_on_save.ignored_error_types')
    errors_by_file = get_window_errors(window, persist.file_errors)

    if show_panel_on_save == 'window':
        has_relevant_errors = any(
            error['error_type'] not in ignored_error_types
            for errors in errors_by_file.values()
            for error in errors
        )
    elif show_panel_on_save == 'view':
        has_relevant_errors = any(
            error["error_type"] not in ignored_error_types
            for filename in filenames
            if filename in errors_by_file
            for error in errors_by_file[filename])
    else:
        return

    if not panel_is_active(window) and has_relevant_errors:
        window.run_command("show_panel", {"panel": OUTPUT_PANEL})
        State['panel_opened_automatically'].add(window.id())

    elif (
        panel_is_active(window) and
        not has_relevant_errors and
        window.id() in State['panel_opened_automatically']
    ):
        window.run_command("hide_panel", {"panel": OUTPUT_PANEL})


class sublime_linter_panel_toggle(sublime_plugin.WindowCommand):
    def run(self):
        if panel_is_active(self.window):
            self.window.run_command("hide_panel", {"panel": OUTPUT_PANEL})
        else:
            self.window.run_command("show_panel", {"panel": OUTPUT_PANEL})


def get_current_pos(view):
    return next((s.begin() for s in view.sel()), -1)


def panel_is_active(window):
    if not window:
        return False

    if window.active_panel() == OUTPUT_PANEL:
        return True
    else:
        return False


def ensure_panel(window: sublime.Window) -> sublime.View | None:
    return get_panel(window) or create_panel(window)


def get_panel(window: sublime.Window) -> sublime.View | None:
    return window.find_output_panel(PANEL_NAME)


def create_panel(window):
    panel = window.create_output_panel(PANEL_NAME)

    panel.settings().set("result_file_regex", r"^((?::\\|[^:])+):$")
    panel.settings().set("result_line_regex", r"^ +(\d+):(\d+) ")

    syntax_path = "Packages/SublimeLinter/panel/panel.sublime-syntax"
    try:  # Try the resource first, in case we're in the middle of an upgrade
        sublime.load_resource(syntax_path)
    except Exception:
        return

    panel.assign_syntax(syntax_path)
    # Call create_output_panel a second time after assigning the above
    # settings, so that it'll be picked up as a result buffer
    # see: Packages/Default/exec.py#L228-L230
    return window.create_output_panel(PANEL_NAME)


def draw(draw_info: DrawInfo) -> None:
    content = draw_info.get('content')
    if content is None:
        draw_(**draw_info)
    else:
        sublime.set_timeout(lambda: draw_(**draw_info))


def draw_(
    panel: sublime.View,
    content: str = None,
    errors_from_active_view: list[LintError] = [],
    nearby_lines: int | list[int] | None = None
) -> None:
    if content is not None:
        update_panel_content(panel, content)

    if nearby_lines is None:
        mark_lines(panel, None)
        draw_position_marker(panel, None)
        scroll_into_view(panel, None, errors_from_active_view)
    elif isinstance(nearby_lines, list):
        mark_lines(panel, nearby_lines)
        draw_position_marker(panel, None)
        scroll_into_view(panel, nearby_lines, errors_from_active_view)
    else:
        mark_lines(panel, None)
        draw_position_marker(panel, nearby_lines)
        scroll_into_view(panel, [nearby_lines], errors_from_active_view)


def get_window_errors(window: sublime.Window, errors_by_file: ErrorsByFile) -> ErrorsByFile:
    return {
        filename: sorted(
            errors,
            key=lambda e: (e["line"], e["start"], e["linter"], e["region"].end())
        )
        for filename, errors in (
            (filename, errors_by_file.get(filename))
            for filename in filenames_per_window(window)
        )
        if errors
    }


def buffer_ids_per_window(window):
    return {v.buffer_id() for v in window.views()}


def filenames_per_window(window: sublime.Window) -> set[FileName]:
    """Return filenames of all open files plus their dependencies."""
    open_filenames = set(util.canonical_filename(v) for v in window.views())
    return open_filenames | set(
        flatten(
            flatten(persist.affected_filenames_per_filename[filename].values())
            for filename in open_filenames
        )
    )


@lru_cache(maxsize=16)
def create_path_dict(filenames: Collection[FileName]) -> tuple[dict[FileName, str], str]:
    base_dir = get_common_parent([
        path
        for path in filenames
        if not path.startswith('<untitled')
    ])

    rel_paths = {
        filename: (
            os.path.relpath(filename, base_dir)
            if base_dir and not filename.startswith('<untitled')
            else filename
        )
        for filename in filenames
    }

    return rel_paths, base_dir


def get_common_parent(paths):
    """Get the common parent directory of multiple absolute file paths."""
    common_path = os.path.commonprefix(paths)
    return os.path.dirname(common_path)


def format_header(f_path):
    return "{}:".format(f_path)


def format_error(error: LintError, widths: tuple[tuple[str, int], ...]) -> list[str]:
    error_as_tuple = tuple(
        (k, v)
        for k, v in error.items()
        if k in ("line", "start", "error_type", "linter", "msg", "code", )
    )
    return _format_error(error_as_tuple, widths)


@lru_cache(maxsize=512)
def _format_error(
    error_as_tuple: tuple[tuple[str, object], ...],
    widths_as_tuple: tuple[tuple[str, int], ...]
) -> list[str]:
    error: LintError = dict(error_as_tuple)  # type: ignore
    widths: dict[str, int] = dict(widths_as_tuple)
    info_tmpl = (
        " {{LINE:>{line}}}:{{START:<{col}}}  {{error_type:{error_type}}}  "
        "{{linter:<{linter_name}}}  "
        .format(**widths)
    )

    line = error["line"] + 1
    start = error["start"] + 1
    info = info_tmpl.format(LINE=line, START=start, **error)
    code = " \u200B{}".format(error['code']) if error['code'] else ""
    rv = list(flatten(
        textwrap.wrap(
            msg_line,
            width=widths['viewport'],
            initial_indent=" " * (len(info) + (len(code) if n == 0 else 0)),
            subsequent_indent=" " * len(info)
        )
        for n, msg_line in enumerate(error['msg'].splitlines())
    ))

    spaces_to_fill_viewport = (
        widths['viewport']
        - len(info + rv[0].lstrip() + code)
    )
    rv[0] = info + rv[0].lstrip() + " " * spaces_to_fill_viewport + code
    return rv


def fill_panel(window: sublime.Window) -> None:
    """Create the panel if it doesn't exist, then update its contents."""
    panel = ensure_panel(window)
    # If we're here and the user actually closed the *window* in the meantime,
    # we cannot create a panel anymore, and just pass.
    if not panel:
        return

    # If the user closed the *panel* (or switched to another one), the panel
    # has no extent anymore and we don't need to fill it.
    vx, _ = panel.viewport_extent()
    if vx == 0:
        return

    active_view = State['active_view']
    if active_view and active_view.window() == window:
        active_filename = State['active_filename']
    else:
        active_view = None
        active_filename = None

    errors_by_file = get_window_errors(window, persist.file_errors)
    if active_filename and active_filename not in errors_by_file:
        errors_by_file[active_filename] = []

    fpath_by_file, base_dir = create_path_dict(tuple(errors_by_file.keys()))

    settings = panel.settings()
    settings.set("result_base_dir", base_dir)

    widths: tuple[tuple[str, int], ...] = tuple(
        zip(
            ('line', 'col', 'error_type', 'linter_name'),
            map(
                max,
                zip(*[
                    (
                        len(str(error['line'] + 1)),
                        len(str(error['start'] + 1)),
                        len(error['error_type']),
                        len(error['linter']),
                    )
                    for error in flatten(errors_by_file.values())
                ])
            )
        )
    )
    widths += (('viewport', int(vx // panel.em_width()) - 1), )

    def sorted_by_path(active_filename, items):
        active_filename_parts = len(fpath_by_file[active_filename].split(os.sep))

        def by_path(item):
            fpath, filename, errors = item
            parts = fpath.split(os.sep)
            return (abs(len(parts) - active_filename_parts), len(parts), parts)
        return sorted(items, key=by_path)

    to_render = []
    if active_filename:
        affected_filenames = set(flatten(
            persist.affected_filenames_per_filename.get(active_filename, {}).values()
        ))

        sorted_errors = (
            # Unrelated errors surprisingly come first. The scroller
            # will scroll past them, often showing empty space below
            # the current file to reduce visual noise.
            sorted(
                (fpath_by_file[filename], filename, errors_by_file[filename])
                for filename in (
                    errors_by_file.keys()
                    - affected_filenames
                    - {active_filename}
                )
            )

            # For the current active file, always show something.
            # The scroller will try to show this file at the top of the
            # view.
            + [(
                fpath_by_file[active_filename],
                active_filename,
                errors_by_file.get(active_filename, [])
            )]

            # Affected files can be clean, just omit those
            + sorted_by_path(
                active_filename,
                (
                    (fpath_by_file[filename], filename, errors_by_file[filename])
                    for filename in affected_filenames
                    if filename in errors_by_file
                )
            )
        )

    else:
        sorted_errors = sorted(
            (fpath_by_file[filename], filename, errors)
            for filename, errors in errors_by_file.items()
        )

    for fpath, filename, errors in sorted_errors:
        to_render.append(format_header(fpath))

        if errors:
            for error in errors:
                lines = format_error(error, widths)
                to_render.extend(lines)
                error["panel_line"] = (len(to_render) - len(lines), len(to_render) - 1)
        else:
            actual_linter_names = ', '.join(sorted(
                persist.actual_linters.get(filename, set())
            ))
            if actual_linter_names:
                to_render.append(
                    NO_RESULTS_MESSAGE
                    + " Running {}.".format(actual_linter_names)
                )
            else:
                to_render.append(NO_RESULTS_MESSAGE)

        # Insert empty line between files
        to_render.append("")

    content = '\n'.join(to_render)
    draw_info: DrawInfo = {
        'panel': panel,
        'content': content
    }

    if active_view:
        update_panel_selection(draw_info=draw_info, **State)  # type: ignore[arg-type]
    else:
        draw(draw_info)


def update_panel_selection(
    active_view: sublime.View,
    cursor: int,
    draw_info: DrawInfo | None = None,
    **kwargs: Any
) -> None:
    """Alter panel highlighting according to the current cursor position."""
    if draw_info is None:
        draw_info = {}

    window = active_view.window()
    assert window
    panel = get_panel(window)
    if not panel:
        return

    if cursor == -1:
        return

    filename = util.canonical_filename(active_view)

    try:
        # Rarely, and if so only on hot-reload, `update_panel_selection` runs
        # before `fill_panel`, thus 'panel_line' has not been set.
        all_errors = sorted(persist.file_errors[filename],
                            key=lambda e: e['panel_line'])
    except KeyError:
        all_errors = []

    draw_info.update({
        'panel': panel,
        'errors_from_active_view': all_errors
    })

    row, _ = active_view.rowcol(cursor)
    errors_with_position: Iterable[tuple[LintError, tuple[int, int, int, int]]] = (
        (
            error,
            (
                abs(error['line'] - row),
                -error['region'].contains(cursor),
                min(
                    abs(error['region'].begin() - cursor),
                    abs(error['region'].end() - cursor)
                ),
                error['region'].end() - error['region'].begin()
            )
        )
        for error in all_errors
    )

    SNAP = (3, )  # [lines]
    nearest_error = None
    try:
        nearest_error, _ = min(
            (
                e_p
                for e_p in errors_with_position
                if e_p[1] < SNAP
            ),
            key=lambda e_p: e_p[1]
        )
    except ValueError:
        nearest_error = None

    if nearest_error:
        panel_lines = [
            error['panel_line'][0]
            for error in all_errors
            if error['region'].contains(nearest_error['region'])
        ]
        draw_info.update({'nearby_lines': panel_lines})

    elif all_errors:
        try:
            next_error = next(
                error
                for error in all_errors
                if error['region'].begin() > cursor
            )
        except StopIteration:
            last_error = all_errors[-1]
            panel_line = last_error['panel_line'][1] + 1
        else:
            panel_line = next_error['panel_line'][0]

        draw_info.update({'nearby_lines': panel_line})

    draw(draw_info)


#   Visual side-effects   #


def update_panel_content(panel, text):
    if not text:
        text = NO_RESULTS_MESSAGE
    panel.run_command('sublime_linter_replace_panel_content', {'text': text})


class sublime_linter_replace_panel_content(sublime_plugin.TextCommand):
    def run(self, edit, text):
        view = self.view
        _, y = view.viewport_position()
        view.set_read_only(False)
        view.replace(edit, sublime.Region(0, view.size()), text)
        view.set_read_only(True)
        # Avoid https://github.com/SublimeTextIssues/Core/issues/2560
        # Force setting the viewport synchronous by setting it twice.
        view.set_viewport_position((0, 0), False)
        view.set_viewport_position((0, y), False)


INNER_MARGIN = 2  # [lines]
JUMP_COEFFICIENT = 3


def scroll_into_view(panel: sublime.View, wanted_lines: Optional[list[int]], errors: list[LintError]) -> None:
    """Compute and then scroll the view so that `wanted_lines` appear.

    Basically an optimized, do-it-yourself version of `view.show()`. If
    possible shows the start of this file section (the filename) at the top
    of the viewport. Generally tries to scroll as little as possible.
    """
    if not errors or not wanted_lines:
        # For clean files, we know that we have exactly two rows: the
        # filename itself, followed by the "No lint results." message.
        match = panel.find(NO_RESULTS_MESSAGE, 0, sublime.LITERAL)
        if match:
            r, _ = panel.rowcol(match.begin())
            scroll_to_line(panel, r - 1, animate=False)
        return

    # We would like to use just `view.visible_region()` but that doesn't count
    # lines past the content. E.g. if you're at the eof it - for our purpose
    # wrongly - tells you that the visible region is only 2 lines height.
    # So we compute the values basically using `viewport_extent()`. This
    # unfortunately leads to rounding errors bc we must convert from pixels
    # to lines. See below.
    _, vy = panel.viewport_position()
    vtop = panel.rowcol(panel.layout_to_text((0.0, vy)))[0]
    vheight = int(panel.viewport_extent()[1] // panel.line_height())
    vbottom = vtop + vheight

    # Before the first error comes the filename
    ftop = errors[0]['panel_line'][0] - 1
    # After the last error comes the empty line
    fbottom = errors[-1]['panel_line'][1] + 1
    fheight = fbottom - ftop + 1

    if fheight <= vheight:
        scroll_to_line(panel, ftop, animate=False)
        return

    wtop, wbottom = wanted_lines[0], wanted_lines[-1]
    out_of_bounds = False
    jump_position = int(vheight // JUMP_COEFFICIENT)

    if fbottom < vbottom:
        out_of_bounds = True
        vtop = max(ftop, fbottom - vheight)
    elif ftop > vtop:
        out_of_bounds = True
        vtop = ftop

    if vtop + INNER_MARGIN < wbottom < vbottom - INNER_MARGIN:
        if not out_of_bounds:
            return  # Do nothing bc `vtop` likely has rounding errors
    elif wtop < vtop + INNER_MARGIN:
        vtop = max(ftop, wtop - jump_position)
    elif vbottom - INNER_MARGIN < wbottom:
        next_bottom = min(fbottom, wbottom + jump_position)
        vtop = max(ftop, next_bottom - vheight)

    scroll_to_line(panel, vtop, animate=not out_of_bounds)


def scroll_to_line(view, line, animate):
    """Scroll y-axis so that `line` appears at the top of the viewport."""
    x, y = view.text_to_layout(view.text_point(line, 0))
    view.run_command('sublime_linter_scroll_y', {'y': y, 'animate': animate})


class sublime_linter_scroll_y(sublime_plugin.TextCommand):
    def run(self, edit, y, animate):
        x, _ = self.view.viewport_position()
        self.view.set_viewport_position((x, y), animate)


def mark_lines(panel: sublime.View, lines: Optional[list[int]]) -> None:
    """Select/Highlight given lines."""
    if lines is None:
        panel.sel().clear()
        return

    regions = [panel.line(panel.text_point(line, 0)) for line in lines]
    panel.sel().clear()
    panel.sel().add_all(regions)


CURSOR_MARKER_KEY = 'SL.PanelMarker'
CURSOR_MARKER_SCOPE = 'region.yellowish.panel_cursor.sublime_linter'


def draw_position_marker(panel: sublime.View, line: Optional[int]) -> None:
    """Draw a visual cursor 'below' given line.

    We draw a region 'dangle' (a region of length 0 at the start of a line)
    *at* the given `line` which usually appears as if it were slightly below
    the current line, or between this and the next line.

    Basically a visual hack.
    """
    if line is None:
        panel.erase_regions(CURSOR_MARKER_KEY)
        return

    line_start = panel.text_point(line - 1, 0)
    region = sublime.Region(line_start, line_start)
    draw_region_dangle(panel, CURSOR_MARKER_KEY, CURSOR_MARKER_SCOPE, [region])


CONFUSION_THRESHOLD = 5
VIEWPORT_MARKER_KEY = 'SL.Panel.ViewportMarker'
VIEWPORT_MARKER_SCOPE = 'region.bluish.visible_viewport.sublime_linter'
VIEWPORT_BACKGROUND_KEY = 'SL.Panel.ViewportBackground'

_RUNNING = False


def get_viewport_background_scope():
    return persist.settings.get('xperiments', {}).get('viewport_background_scope')


def start_viewport_poller():
    global _RUNNING
    if _RUNNING:
        return

    _RUNNING = True
    update_viewport()


def stop_viewport_poller():
    global _RUNNING
    _RUNNING = False


def update_viewport(token1=None, token2=None):
    global _RUNNING
    if not _RUNNING:
        return

    next_token1 = mayby_rerender_panel(token1)
    next_token2 = maybe_render_viewport(token2)
    sublime.set_timeout(partial(update_viewport, next_token1, next_token2), 16)


def mayby_rerender_panel(previous_token):
    view = State['active_view']
    if not view:
        return

    token = (view.viewport_extent(),)
    if previous_token and token != previous_token:
        window = view.window()
        if not window:
            return

        fill_panel(window)

    return token


def maybe_render_viewport(previous_token):
    view = State['active_view']
    if not view:
        return

    window = view.window()
    if not window:
        return
    panel = get_panel(window)
    if not panel:
        return

    token = (
        view.buffer_id(),
        view.visible_region(),
        panel.change_count(),
        panel.get_regions(CURSOR_MARKER_KEY)
    )
    if token != previous_token:
        render_visible_viewport(panel, view)
    return token


def render_visible_viewport(panel: sublime.View, view: sublime.View) -> None:
    """Compute and draw a fancy scrollbar like region on the left...

    ... indicating the current viewport into that file or error(s) list.
    """
    errors = persist.file_errors.get(util.canonical_filename(view), [])
    if len(errors) > CONFUSION_THRESHOLD:
        viewport = view.visible_region()
        visible_errors = [
            error
            for error in errors
            if viewport.contains(error['region'])
        ]
        if visible_errors and len(visible_errors) != len(errors):
            try:
                visible_errors = sorted(
                    visible_errors, key=lambda error: error['panel_line'])
            except KeyError:
                return
            head, end = visible_errors[0], visible_errors[-1]
            head_line = panel.text_point(head['panel_line'][0] - 1, 0)
            end_line = panel.text_point(end['panel_line'][1], 0)

            regions = [
                sublime.Region(head_line, head_line),
                sublime.Region(end_line, end_line)
            ]
            cursor = panel.get_regions(CURSOR_MARKER_KEY)
            regions = [r for r in regions if r not in cursor]
            draw_region_dangle(
                panel, VIEWPORT_MARKER_KEY, VIEWPORT_MARKER_SCOPE, regions)

            viewport_background_scope = get_viewport_background_scope()
            if viewport_background_scope:
                head_line = panel.text_point(head['panel_line'][0], 0)
                end_line = panel.text_point(end['panel_line'][1] + 1, 0)
                regions = [
                    sublime.Region(r.a, r.a + 1)
                    for r in panel.lines(sublime.Region(head_line, end_line))
                ]
                flags = sublime.DRAW_NO_OUTLINE
                panel.add_regions(
                    VIEWPORT_BACKGROUND_KEY, regions,
                    scope=viewport_background_scope, flags=flags)
            return

    panel.erase_regions(VIEWPORT_MARKER_KEY)
    panel.erase_regions(VIEWPORT_BACKGROUND_KEY)


DANGLE_FLAGS = (
    sublime.DRAW_SOLID_UNDERLINE | sublime.DRAW_NO_FILL |
    sublime.DRAW_NO_OUTLINE | sublime.DRAW_EMPTY_AS_OVERWRITE)


def draw_region_dangle(view: sublime.View, key: str, scope: str, regions: list[sublime.Region]) -> None:
    view.add_regions(key, regions, scope=scope, flags=DANGLE_FLAGS)
