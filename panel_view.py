import os
import sublime
import sublime_plugin

from .lint import persist, events

PANEL_NAME = "SublimeLinter"
OUTPUT_PANEL = "output." + PANEL_NAME
OUTPUT_PANEL_SETTINGS = {
    "auto_indent": False,
    "draw_indent_guides": False,
    "draw_white_space": "None",
    "gutter": False,
    "is_widget": True,
    "line_numbers": False,
    "match_brackets": False,
    "rulers": False,
    "scroll_past_end": False,
    "spell_check": False,
    "tab_size": 4,
    "translate_tabs_to_spaces": False,
    "word_wrap": False
}


State = {
    'active_view': None,
    'current_pos': (-1, -1)
}


def plugin_loaded():
    active_window = sublime.active_window()
    State.update({
        'active_view': active_window.active_view()
    })
    ensure_panel(active_window)


def plugin_unloaded():
    events.off(on_lint_result)

    for window in sublime.windows():
        window.destroy_output_panel(PANEL_NAME)


@events.on(events.LINT_RESULT)
def on_lint_result(buffer_id, **kwargs):
    for window in sublime.windows():
        if panel_is_active(window) and buffer_id in buffer_ids_per_window(window):
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
            'current_pos': get_current_pos(active_view)
        })
        ensure_panel(window)
        if panel_is_active(window):
            update_panel_selection(**State)

    def on_selection_modified_async(self, view):
        active_view = State['active_view']
        if active_view.buffer_id() != view.buffer_id():
            return

        current_pos = get_current_pos(active_view)
        if current_pos != State['current_pos']:
            State.update({
                'current_pos': current_pos
            })
            if panel_is_active(active_view.window()):
                update_panel_selection(**State)

    def on_pre_close(self, view):
        window = view.window()
        # If the user closes the window and not *just* a view, the view is
        # already detached, hence we check.
        if window and panel_is_active(window):
            sublime.set_timeout_async(lambda: fill_panel(window))

    def on_post_save_async(self, view):
        """Show the panel if the view or window has problems, depending on settings."""
        window = view.window()
        show_panel_on_save = persist.settings.get('show_panel_on_save')
        if not window or show_panel_on_save == 'never' or panel_is_active(window):
            return

        errors_by_bid = get_window_errors(window, persist.errors)

        if show_panel_on_save == 'window' and errors_by_bid:
            window.run_command("show_panel", {"panel": OUTPUT_PANEL})
        elif view.buffer_id() in errors_by_bid:
            window.run_command("show_panel", {"panel": OUTPUT_PANEL})

    def on_post_window_command(self, window, command_name, args):
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


class SublimeLinterPanelToggleCommand(sublime_plugin.WindowCommand):
    def run(self):
        if panel_is_active(self.window):
            self.window.run_command("hide_panel", {"panel": OUTPUT_PANEL})
        else:
            self.window.run_command("show_panel", {"panel": OUTPUT_PANEL})


class SublimeLinterUpdatePanelCommand(sublime_plugin.TextCommand):
    def run(self, edit, text="", clear_sel=False):
        """Replace a view's text entirely and attempt to restore previous selection."""
        sel = self.view.sel()
        # Doesn't make sense to consider multiple selections
        try:
            selected_text = self.view.substr(sel[0])
        except IndexError:
            selected_text = None

        self.view.set_read_only(False)
        self.view.replace(edit, sublime.Region(0, self.view.size()), text)
        self.view.set_read_only(True)

        sel.clear()
        if selected_text and not clear_sel:
            new_selected_region = self.view.find(selected_text, 0, flags=sublime.LITERAL)
            if new_selected_region:
                sel.add(new_selected_region)
                return
        sel.add(0)


def get_current_pos(view):
    try:
        return view.rowcol(view.sel()[0].begin())
    except (AttributeError, IndexError):
        return -1, -1


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
    settings = panel.settings()
    for key, value in OUTPUT_PANEL_SETTINGS.items():
        settings.set(key, value)

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


def format_row(item):
    line = item["line"] + 1
    start = item["start"] + 1
    tmpl = " {LINE:>5}:{START:<4} {error_type:7} {linter:>12}: {code:12} {msg}"
    return tmpl.format(LINE=line, START=start, **item)


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
    for bid, buf_errors in errors_by_bid.items():
        # append header
        to_render.append(format_header(path_dict[bid]))

        # append lines
        base_lineno = len(to_render)
        for i, item in enumerate(buf_errors):
            to_render.append(format_row(item))
            item["panel_line"] = base_lineno + i

        # insert empty line between views sections
        to_render.append("")

    run_update_panel_cmd(panel, text="\n".join(to_render))

    if State['active_view'].window() == window:
        update_panel_selection(**State)


def update_panel_selection(active_view, current_pos, **kwargs):
    """Alter panel selection according to errors belonging to current position.

    If current position is between two errors, place empty panel selection on start of next error's panel line.
    If current position is past last error, place empty selection on the panel line following that of last error.

    """
    panel = get_panel(active_view.window())
    if not panel:
        return

    line, col = current_pos
    if (line, col) == (-1, -1):
        return

    bid = active_view.buffer_id()
    if not persist.errors[bid]:
        return

    # Take only errors under or after the cursor
    all_errors = sort_errors(
        error for error in persist.errors[bid]
        if (
            error['line'] > line or
            error['line'] == line and col <= error['end']
        )
    )

    errors_under_cursor = [
        error for error in all_errors
        if error['line'] == line and error['start'] <= col <= error['end']
    ]

    if errors_under_cursor:
        panel_lines = [error['panel_line'] for error in errors_under_cursor]

        start = panel.text_point(panel_lines[0], 0)
        end = panel.text_point(panel_lines[-1], 0)
        region = panel.line(sublime.Region(start, end))

        clear_position_marker(panel)
        update_selection(panel, region)

    else:
        if all_errors:
            next_error = all_errors[0]
            panel_line = next_error['panel_line']
        else:
            last_error = max(persist.errors[bid], key=lambda e: e['panel_line'])
            panel_line = last_error['panel_line'] + 1

        start = panel.text_point(panel_line, 0)
        region = sublime.Region(start)

        draw_position_marker(panel, panel_line)
        update_selection(panel, region)


def update_selection(panel, region=None):
    panel.run_command(
        '_sublime_linter_update_selection', {'a': region.a, 'b': region.b})


class _sublime_linter_update_selection(sublime_plugin.TextCommand):
    def run(self, edit, a, b):
        region = sublime.Region(a, b)
        self.view.sel().clear()
        self.view.sel().add(region)
        self.view.show_at_center(region)


def draw_position_marker(panel, line):
    line_start = panel.text_point(line - 1, 0)
    region = sublime.Region(line_start, line_start)
    scope = 'region.redish markup.deleted.sublime_linter markup.error.sublime_linter'
    flags = (sublime.DRAW_SOLID_UNDERLINE | sublime.DRAW_NO_FILL |
             sublime.DRAW_NO_OUTLINE | sublime.DRAW_EMPTY_AS_OVERWRITE)
    panel.add_regions('SL.PanelMarker', [region], scope=scope, flags=flags)


def clear_position_marker(panel):
    panel.erase_regions('SL.PanelMarker')
