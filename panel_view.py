from functools import partial
from itertools import chain
import os
import sublime
import sublime_plugin

from .lint import events, util, persist


if False:
    from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
    from mypy_extensions import TypedDict
    from .lint.persist import LintError

    State_ = TypedDict('State_', {
        'active_view': Optional[sublime.View],
        'cursor': int,
        'just_saved_buffers': Set[sublime.BufferId],
        'panel_opened_automatically': Set[sublime.WindowId]
    })


PANEL_NAME = "SublimeLinter"
OUTPUT_PANEL = "output." + PANEL_NAME

State = {
    'active_view': None,
    'cursor': -1,
    'just_saved_buffers': set(),
    'panel_opened_automatically': set()
}  # type: State_


def plugin_loaded():
    active_window = sublime.active_window()
    State.update({
        'active_view': active_window.active_view()
    })
    ensure_panel(active_window)


def plugin_unloaded():
    events.off(on_lint_result)
    events.off(on_updated_error_positions)

    for window in sublime.windows():
        window.destroy_output_panel(PANEL_NAME)


@events.on(events.LINT_RESULT)
def on_lint_result(buffer_id, **kwargs):
    maybe_toggle_panel_automatically = (
        persist.settings.get('lint_mode') == 'manual' or
        buffer_id in State['just_saved_buffers']
    )
    for window in sublime.windows():
        if buffer_id in buffer_ids_per_window(window):
            if panel_is_active(window):
                fill_panel(window)

            if maybe_toggle_panel_automatically:
                toggle_panel_if_errors(window, buffer_id)


@events.on('updated_error_positions')
def on_updated_error_positions(view, **kwargs):
    bid = view.buffer_id()
    window = view.window()
    if panel_is_active(window) and bid in buffer_ids_per_window(window):
        fill_panel(window)


class UpdateState(sublime_plugin.EventListener):
    def on_activated_async(self, active_view):
        window = active_view.window()
        # Sometimes a view is activated and then destructed before we get here
        # and then it doesn't have a window anymore
        if not window or active_view.settings().get('is_widget'):
            return

        State.update({
            'active_view': active_view,
            'cursor': get_current_pos(active_view)
        })
        ensure_panel(window)
        if panel_is_active(window):
            update_panel_selection(**State)

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
                update_panel_selection(**State)

    def on_pre_close(self, view):
        window = view.window()
        # If the user closes the window and not *just* a view, the view is
        # already detached, hence we check.
        if window and panel_is_active(window):
            sublime.set_timeout_async(lambda: fill_panel(window))

    @util.distinct_until_buffer_changed
    def on_post_save_async(self, view):
        # In background mode most of the time the errors are already up-to-date
        # on save, so we (maybe) show the panel immediately.
        window = view.window()
        bid = view.buffer_id()
        if buffers_effective_lint_mode_is_background(bid):
            toggle_panel_if_errors(window, bid)

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


class JustSavedBufferController(sublime_plugin.EventListener):
    @util.distinct_until_buffer_changed
    def on_post_save_async(self, view):
        bid = view.buffer_id()
        State['just_saved_buffers'].add(bid)

    def on_pre_close(self, view):
        bid = view.buffer_id()
        State['just_saved_buffers'].discard(bid)

    @util.distinct_until_buffer_changed
    def on_modified_async(self, view):
        bid = view.buffer_id()
        State['just_saved_buffers'].discard(bid)


def buffers_effective_lint_mode_is_background(bid):
    return (
        persist.settings.get('lint_mode') == 'background' and
        any(
            True for linter in persist.view_linters.get(bid, [])
            if linter.tempfile_suffix != '-'
        )
    )


def toggle_panel_if_errors(window, bid):
    """Toggle the panel if the view or window has problems, depending on settings."""
    if window is None:
        return

    show_panel_on_save = persist.settings.get('show_panel_on_save')
    if show_panel_on_save == 'never':
        return

    errors_by_bid = get_window_errors(window, persist.errors)
    has_relevant_errors = (
        show_panel_on_save == 'window' and errors_by_bid or
        bid in errors_by_bid)

    if not panel_is_active(window) and has_relevant_errors:
        window.run_command("show_panel", {"panel": OUTPUT_PANEL})
        State['panel_opened_automatically'].add(window.id())

    elif (
        panel_is_active(window) and
        not has_relevant_errors and
        window.id() in State['panel_opened_automatically']
    ):
        window.run_command("hide_panel", {"panel": OUTPUT_PANEL})


class SublimeLinterPanelToggleCommand(sublime_plugin.WindowCommand):
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


def ensure_panel(window: sublime.Window):
    return get_panel(window) or create_panel(window)


def get_panel(window):
    # type: (sublime.Window) -> Optional[sublime.View]
    return window.find_output_panel(PANEL_NAME)


def create_panel(window):
    panel = window.create_output_panel(PANEL_NAME)

    panel.settings().set("result_file_regex", r"^(.*):$")
    # row:col   type   linter: code   message
    # where code is optional
    # r"^ +(\d+)(?::(\d+))? +\w+ +\w+:(?: \w+)? +(.*)$"
    panel.settings().set("result_line_regex", r"^ +(\d+)(?::(\d+))?.*")

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


def draw(panel, content=None, errors_from_active_view=[], nearby_lines=None):
    # type: (sublime.View, str, List[LintError], Tuple[int, int]) -> None
    if content is not None:
        update_panel_content(panel, content)

    if nearby_lines is None:
        mark_lines(panel, None)
        draw_position_marker(panel, None)
        scroll_into_view(panel, None, errors_from_active_view)
    elif isinstance(nearby_lines, tuple):
        mark_lines(panel, nearby_lines)
        draw_position_marker(panel, None)
        scroll_into_view(panel, nearby_lines, errors_from_active_view)
    else:
        mark_lines(panel, None)
        draw_position_marker(panel, nearby_lines)
        scroll_into_view(panel, (nearby_lines, nearby_lines), errors_from_active_view)


def draw_on_main_thread(*args, **kwargs):
    sublime.set_timeout(lambda: draw(*args, **kwargs))


def get_window_errors(window, errors_by_bid):
    return {
        bid: sorted(
            errors,
            key=lambda e: (e["line"], e["start"], e["end"], e["linter"])
        )
        for bid, errors in (
            (bid, errors_by_bid.get(bid))
            for bid in buffer_ids_per_window(window)
        )
        if errors
    }


def buffer_ids_per_window(window):
    return {v.buffer_id() for v in window.views()}


def create_path_dict(window, bids):
    file_names_by_bid = get_filenames(window, bids)

    base_dir = get_common_parent([
        path
        for path in file_names_by_bid.values()
        if not path.startswith('<untitled')
    ])

    rel_paths = {
        bid: (
            os.path.relpath(abs_path, base_dir)
            if base_dir and not abs_path.startswith('<untitled')
            else abs_path
        )
        for bid, abs_path in file_names_by_bid.items()
    }

    return rel_paths, base_dir


def get_filenames(window, bids):
    """
    Return dict of buffer_id: file_name for all views in window.

    Assign a substitute name to untitled buffers: <untitled buffer_id>
    """
    return {
        v.buffer_id(): v.file_name() or "<untitled {}>".format(v.buffer_id())
        for v in window.views()
        if v.buffer_id() in bids
    }


def get_common_parent(paths):
    """Get the common parent directory of multiple absolute file paths."""
    common_path = os.path.commonprefix(paths)
    return os.path.dirname(common_path)


def format_header(f_path):
    return "{}:".format(f_path)


def format_row(item, widths):
    code_width = widths['code']
    code_tmpl = ":{{code:<{}}}".format(code_width)
    tmpl = (
        " {{LINE:>{line}}}:{{START:<{col}}}  {{error_type:{error_type}}}  "
        "{{linter:<{linter_name}}}{{CODE}}  {{msg}}"
        .format(**widths)
    )

    line = item["line"] + 1
    start = item["start"] + 1
    code = (
        code_tmpl.format(**item)
        if item['code']
        else ' ' * (code_width + (1 if code_width else 0))  # + 1 for the ':'
    )
    return tmpl.format(LINE=line, START=start, CODE=code, **item)


def fill_panel(window, then=draw_on_main_thread):
    """Create the panel if it doesn't exist, then update its contents."""
    panel = ensure_panel(window)
    # If we're here and the user actually closed the window in the meantime,
    # we cannot create a panel anymore, and just pass.
    if not panel:
        return

    errors_by_bid = get_window_errors(window, persist.errors)
    fpath_by_bid, base_dir = create_path_dict(window, errors_by_bid.keys())

    settings = panel.settings()
    settings.set("result_base_dir", base_dir)

    widths = dict(
        zip(
            ('line', 'col', 'error_type', 'linter_name', 'code'),
            map(
                max,
                zip(*[
                    (
                        len(str(error['line'])),
                        len(str(error['start'])),
                        len(error['error_type']),
                        len(error['linter']),
                        len(str(error['code'])),
                    )
                    for error in chain(*errors_by_bid.values())
                ])
            )
        )
    )

    to_render = []
    for fpath, errors in sorted(
        (fpath_by_bid[bid], errors) for bid, errors in errors_by_bid.items()
    ):
        to_render.append(format_header(fpath))

        base_lineno = len(to_render)
        for i, item in enumerate(errors):
            to_render.append(format_row(item, widths))
            item["panel_line"] = base_lineno + i

        # insert empty line between views sections
        to_render.append("")

    content = '\n'.join(to_render)
    draw_info = {
        'panel': panel,
        'content': content
    }

    if State['active_view'].window() == window:
        update_panel_selection(draw_info=draw_info, then=then, **State)
    else:
        then(**draw_info)


def update_panel_selection(active_view, cursor, draw_info=None, then=draw, **kwargs):
    """Alter panel highlighting according to the current cursor position."""
    if draw_info is None:
        draw_info = {}

    panel = get_panel(active_view.window())
    if not panel:
        return

    if cursor == -1:
        return

    bid = active_view.buffer_id()

    try:
        # Rarely, and if so only on hot-reload, `update_panel_selection` runs
        # before `fill_panel`, thus 'panel_line' has not been set.
        all_errors = sorted(persist.errors[bid], key=lambda e: e['panel_line'])
    except KeyError:
        all_errors = []

    draw_info.update(
        panel=panel,
        errors_from_active_view=all_errors
    )  # type: Dict[str, Any]

    row, _ = active_view.rowcol(cursor)
    errors_with_position = (
        (
            error,
            (
                abs(error['line'] - row),
                min(
                    abs(error['region'].begin() - cursor),
                    abs(error['region'].end() - cursor)
                )
            )
        )
        for error in all_errors
    )  # type: Iterable[Tuple[LintError, Tuple[int, int]]]

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
        nearest_errors = [
            e
            for e in all_errors
            if nearest_error['region'].contains(e['region'])
        ]
        start = nearest_errors[0]['panel_line']
        end = nearest_errors[-1]['panel_line']

        draw_info.update(nearby_lines=(start, end))

    elif all_errors:
        try:
            next_error = next(
                error
                for error in all_errors
                if error['region'].begin() > cursor
            )
        except StopIteration:
            last_error = all_errors[-1]
            panel_line = last_error['panel_line'] + 1
        else:
            panel_line = next_error['panel_line']

        draw_info.update(nearby_lines=panel_line)

    then(**draw_info)


#   Visual side-effects   #


def update_panel_content(panel, text):
    if not text:
        text = "No lint results."
    panel.run_command('_sublime_linter_update_panel_content', {'text': text})


class _sublime_linter_update_panel_content(sublime_plugin.TextCommand):
    def run(self, edit, text):
        """Replace a view's text entirely and try to hold the viewport stable."""
        view = self.view
        x, _ = view.viewport_position()

        view.set_read_only(False)
        view.replace(edit, sublime.Region(0, view.size()), text)
        view.set_read_only(True)

        # We cannot measure the `viewport_position` until right after this
        # command actually finished. So we defer to the next tick/micro-task
        # using `set_timeout`.
        sublime.set_timeout(
            lambda: view.run_command('_sublime_linter_pin_x_axis', {'x': x})
        )


class _sublime_linter_pin_x_axis(sublime_plugin.TextCommand):
    def run(self, edit, x):
        x2, y2 = self.view.viewport_position()
        if x != x2:
            self.view.set_viewport_position((x, y2), False)


INNER_MARGIN = 2  # [lines]
JUMP_COEFFICIENT = 3


def scroll_into_view(panel, wanted_lines, errors):
    # type: (sublime.View, Optional[Tuple[int, int]], List[LintError]) -> None
    """Compute and then scroll the view so that `wanted_lines` appear.

    Basically an optimized, do-it-yourself version of `view.show()`. If
    possible shows the start of this file section (the filename) at the top
    of the viewport. Otherwise tries to not 'overscroll' so that errors from a
    possible next file are essentially hidden. Inbetween tries to scroll as
    little as possible.
    """
    if not errors or not wanted_lines:
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
    ftop = errors[0]['panel_line'] - 1
    # After the last error comes the empty line
    fbottom = errors[-1]['panel_line'] + 1
    fheight = fbottom - ftop + 1

    if fheight <= vheight:
        scroll_to_line(panel, ftop, animate=False)
        return

    wtop, wbottom = wanted_lines
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
    view.run_command('_sublime_linter_scroll_y', {'y': y, 'animate': animate})


class _sublime_linter_scroll_y(sublime_plugin.TextCommand):
    def run(self, edit, y, animate):
        x, _ = self.view.viewport_position()
        self.view.set_viewport_position((x, y), animate)


def mark_lines(panel, lines):
    # type: (sublime.View, Optional[Tuple[int, int]]) -> None
    """Select/Highlight given lines."""
    if lines is None:
        panel.sel().clear()
        return

    start, end = lines
    start = panel.text_point(start, 0)
    end = panel.text_point(end, 0)
    region = panel.line(sublime.Region(start, end))

    panel.sel().clear()
    panel.sel().add(region)


CURSOR_MARKER_KEY = 'SL.PanelMarker'
CURSOR_MARKER_SCOPE = 'region.yellowish.panel_cursor.sublime_linter'


def draw_position_marker(panel, line):
    # type: (sublime.View, Optional[int]) -> None
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


def update_viewport(token=None):
    global _RUNNING
    if not _RUNNING:
        return

    next_token = maybe_render_viewport(token)
    sublime.set_timeout(partial(update_viewport, next_token), 16)


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


def render_visible_viewport(panel, view):
    # type: (sublime.View, sublime.View) -> None
    """Compute and draw a fancy scrollbar like region on the left...

    ... indicating the current viewport into that file or error(s) list.
    """
    errors = persist.errors.get(view.buffer_id(), [])
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
            head_line = panel.text_point(head['panel_line'] - 1, 0)
            end_line = panel.text_point(end['panel_line'], 0)

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
                head_line = panel.text_point(head['panel_line'], 0)
                end_line = panel.text_point(end['panel_line'] + 1, 0)
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


def draw_region_dangle(view, key, scope, regions):
    # type: (sublime.View, str, str, List[sublime.Region]) -> None
    view.add_regions(key, regions, scope=scope, flags=DANGLE_FLAGS)
