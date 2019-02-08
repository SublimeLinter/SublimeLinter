from itertools import chain
import os
import sublime
import sublime_plugin

from .lint import events, util, persist

PANEL_NAME = "SublimeLinter"
OUTPUT_PANEL = "output." + PANEL_NAME

State = {
    'active_view': None,
    'cursor': -1,
    'just_saved_buffers': set(),
    'panel_opened_automatically': set()
}


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
                # `on_lint_result` runs on the worker thread, we lift
                # `fill_panel` to the main thread to eliminate redraw jank.
                # We just *want* this fast and smooth.
                sublime.set_timeout(lambda: fill_panel(window))

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
            return

        if command_name != 'show_panel':
            return

        panel_name = args.get('panel')
        if panel_name == OUTPUT_PANEL:
            fill_panel(window)

            # Apply focus fix to ensure `next_result` is bound to our panel.
            active_group = window.active_group()
            active_view = window.active_view()

            panel = get_panel(window)
            window.focus_view(panel)

            window.focus_group(active_group)
            window.focus_view(active_view)


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


class SublimeLinterUpdatePanelCommand(sublime_plugin.TextCommand):
    def run(self, edit, text="", clear_sel=False):
        """Replace a view's text entirely and attempt to restore previous selection."""
        view = self.view

        old_sel = [(view.rowcol(s.a), view.rowcol(s.b)) for s in view.sel()]
        x, _ = view.viewport_position()

        view.set_read_only(False)
        view.replace(edit, sublime.Region(0, view.size()), text)
        view.set_read_only(True)

        view.sel().clear()
        for a, b in old_sel:
            view.sel().add(sublime.Region(view.text_point(*a), view.text_point(*b)))

        # We cannot measure the `viewport_position` until right after this
        # command actually finished. So we defer to the next tick/micro-task
        # using `set_timeout`.
        sublime.set_timeout(
            lambda: view.run_command(
                '_sublime_linter_pin_x_axis', {'x': x}
            )
        )


class _sublime_linter_pin_x_axis(sublime_plugin.TextCommand):
    def run(self, edit, x):
        x2, y2 = self.view.viewport_position()
        if x != x2:
            self.view.set_viewport_position((x, y2), False)


def get_current_pos(view):
    return next((s.begin() for s in view.sel()), -1)


def get_common_parent(paths):
    """Get the common parent directory of multiple absolute file paths."""
    common_path = os.path.commonprefix(paths)
    return os.path.dirname(common_path)


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


def panel_is_active(window):
    if not window:
        return False

    if window.active_panel() == OUTPUT_PANEL:
        return True
    else:
        return False


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


def get_panel(window):
    return window.find_output_panel(PANEL_NAME)


def ensure_panel(window: sublime.Window):
    return get_panel(window) or create_panel(window)


def sort_errors(errors):
    return sorted(
        errors, key=lambda e: (e["line"], e["start"], e["end"], e["linter"]))


def get_window_errors(window, all_errors):
    bid_error_pairs = (
        (bid, all_errors[bid]) for bid in buffer_ids_per_window(window)
    )
    return {
        bid: sort_errors(errors)
        for bid, errors in bid_error_pairs
        if errors
    }


def buffer_ids_per_window(window):
    return {v.buffer_id() for v in window.views()}


def format_header(f_path):
    return "{}:".format(f_path)


def run_update_panel_cmd(panel, text=None):
    cmd = "sublime_linter_update_panel"
    clear_sel = False
    if not text:
        text = "No lint results."
        clear_sel = True
    panel.run_command(cmd, {'text': text, 'clear_sel': clear_sel})


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


def fill_panel(window):
    """Create the panel if it doesn't exist, then update its contents."""
    panel = ensure_panel(window)
    # If we're here and the user actually closed the window in the meantime,
    # we cannot create a panel anymore, and just pass.
    if not panel:
        return

    errors_by_bid = get_window_errors(window, persist.errors)
    path_dict, base_dir = create_path_dict(window, errors_by_bid.keys())

    settings = panel.settings()
    settings.set("result_base_dir", base_dir)

    to_render = []
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
    for bid, buf_errors in errors_by_bid.items():
        # append header
        to_render.append(format_header(path_dict[bid]))

        # append lines
        base_lineno = len(to_render)
        for i, item in enumerate(buf_errors):
            to_render.append(format_row(item, widths))
            item["panel_line"] = base_lineno + i

        # insert empty line between views sections
        to_render.append("")

    run_update_panel_cmd(panel, text="\n".join(to_render))

    if State['active_view'].window() == window:
        update_panel_selection(**State)


if False:
    from typing import Any, Dict, List, Tuple, Iterable
    LintError = Dict[str, Any]


def update_panel_selection(active_view, cursor, **kwargs):
    """Alter panel selection according to errors belonging to current position.

    If current position is between two errors, place empty panel selection on start of next error's panel line.
    If current position is past last error, place empty selection on the panel line following that of last error.

    """
    panel = get_panel(active_view.window())
    if not panel:
        return

    if cursor == -1:
        return

    bid = active_view.buffer_id()
    if not persist.errors[bid]:
        return

    try:
        # Rarely, and if so only on hot-reload, `update_panel_selection` runs
        # before `fill_panel`, thus 'panel_line' has not been set.
        all_errors = sorted(persist.errors[bid], key=lambda e: e['panel_line'])
    except KeyError:
        all_errors = []

    mark_visible_viewport(panel, active_view, all_errors)

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
        start = panel.text_point(nearest_errors[0]['panel_line'], 0)
        end = panel.text_point(nearest_errors[-1]['panel_line'], 0)
        region = panel.line(sublime.Region(start, end))

        clear_position_marker(panel)
        update_selection(panel, region)

    else:
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

        start = panel.text_point(panel_line, 0)
        region = sublime.Region(start)

        draw_position_marker(panel, panel_line)
        update_selection(panel, region)


def mark_visible_viewport(panel, view, errors):
    # type: (sublime.View, sublime.View, List[Dict[str, Any]]) -> None
    KEY = 'SL.Panel.ViewportMarker'
    KEY2 = 'SL.Panel.ViewportMarker2'

    viewport = view.visible_region()

    visible_errors = [e for e in errors if viewport.contains(e['region'])]
    if visible_errors:
        head, end = visible_errors[0], visible_errors[-1]
        head_line = panel.text_point(head['panel_line'] - 1, 0)
        end_line = panel.text_point(end['panel_line'], 0)

        regions = [
            sublime.Region(head_line, head_line),
            sublime.Region(end_line, end_line)
        ]
        scope = 'region.bluish.visible_viewport.sublime_linter'
        flags = (sublime.DRAW_SOLID_UNDERLINE | sublime.DRAW_NO_FILL |
                 sublime.DRAW_NO_OUTLINE | sublime.DRAW_EMPTY_AS_OVERWRITE)
        panel.add_regions(KEY, regions, scope=scope, flags=flags)

        scope = 'region.bluish.visible_viewport.sublime_linter'
        flags = sublime.DRAW_NO_OUTLINE
        head_line = panel.text_point(head['panel_line'], 0)
        end_line = panel.text_point(end['panel_line'] + 1, 0)
        regions = [sublime.Region(r.a, r.a + 1) for r in panel.lines(sublime.Region(head_line, end_line))]
        panel.add_regions(KEY2, regions, scope=scope, flags=flags)
    else:
        panel.erase_regions(KEY)
        panel.erase_regions(KEY2)


def update_selection(panel, region=None):
    panel.run_command(
        '_sublime_linter_update_selection', {'a': region.a, 'b': region.b})


class _sublime_linter_update_selection(sublime_plugin.TextCommand):
    def run(self, edit, a, b):
        x1, y1 = self.view.viewport_position()

        region = sublime.Region(a, b)
        self.view.sel().clear()
        self.view.sel().add(region)
        self.view.show_at_center(region)

        # `show_at_center` will scroll the `b` part into the viewport. If
        # we have long lines that means we scroll on the x-axis as well.
        # But we don't want that, so we maybe halfway undo and pin the x-axis
        # to the previous value.
        x2, y2 = self.view.viewport_position()
        if x1 != x2:
            self.view.set_viewport_position((x1, y2))


def draw_position_marker(panel, line):  # type: (sublime.View, int) -> None
    line_start = panel.text_point(line - 1, 0)
    region = sublime.Region(line_start, line_start)
    # scope = 'region.redish markup.deleted.sublime_linter markup.error.sublime_linter'
    scope = 'region.yellowish'
    flags = (sublime.DRAW_SOLID_UNDERLINE | sublime.DRAW_NO_FILL |
             sublime.DRAW_NO_OUTLINE | sublime.DRAW_EMPTY_AS_OVERWRITE)
    panel.add_regions('SL.PanelMarker', [region], scope=scope, flags=flags)


def clear_position_marker(panel):
    panel.erase_regions('SL.PanelMarker')
