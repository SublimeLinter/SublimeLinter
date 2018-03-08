import os
import sublime
import sublime_plugin

from .lint import persist, events

PANEL_NAME = "SublimeLinter"
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
    State.update({
        'active_view': sublime.active_window().active_view()
    })


def plugin_unloaded():
    events.off(on_lint_result)

    for window in sublime.windows():
        window.destroy_output_panel(PANEL_NAME)


@events.on(events.LINT_RESULT)
def on_lint_result(buffer_id, **kwargs):
    for window in sublime.windows():
        if buffer_id in buffer_ids_per_window(window):
            fill_panel(window, update=True)


class UpdateState(sublime_plugin.EventListener):
    def on_activated_async(self, active_view):
        State.update({
            'active_view': active_view,
            'current_pos': get_current_pos(active_view)
        })
        update_panel_selection(**State)

    def on_selection_modified_async(self, _primary_view_):
        active_view = State['active_view']
        current_pos = get_current_pos(active_view)
        if current_pos != State['current_pos']:
            State.update({
                'current_pos': current_pos
            })
            update_panel_selection(**State)

    def on_pre_close(self, view):
        window = view.window()
        # If the user closes the window and not *just* a view, the view is
        # already detached, hence we check.
        if window:
            sublime.set_timeout_async(lambda: fill_panel(window, update=True))

    def on_post_save_async(self, view):
        if persist.settings.get('show_panel_on_save') == 'never':
            return

        window = view.window()
        panel = ensure_panel(window)
        # If we're here and the user actually closed the window in the meantime,
        # we cannot create a panel anymore, and just pass.
        if not panel:
            return

        errors_by_bid = get_window_errors(window, persist.errors)

        if persist.settings.get('show_panel_on_save') == 'window' and errors_by_bid:
            window.run_command('show_panel', {'panel': 'output.' + PANEL_NAME})
        else:
            for bid in errors_by_bid:
                if bid is view.buffer_id():
                    window.run_command('show_panel', {'panel': 'output.' + PANEL_NAME})
                    return


class SublimeLinterPanelToggleCommand(sublime_plugin.WindowCommand):
    def run(self, force_show=False, **kwargs):
        active_panel = self.window.active_panel()
        is_active_panel = (active_panel == "output." + PANEL_NAME)

        if is_active_panel and not force_show:
            self.show_panel(PANEL_NAME, show=False)
        else:
            fill_panel(self.window, **kwargs)
            self.show_panel(PANEL_NAME)

    def show_panel(self, name, show=True):
        """
        Change visibility of panel with given name.

        Panel will be shown by default.
        Pass show=False for hiding.
        """
        if show:
            cmd = "show_panel"
        else:
            cmd = "hide_panel"

        self.window.run_command(cmd, {"panel": "output." + name or ""})


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
            abs_path
            if abs_path.startswith('<untitled')
            else os.path.relpath(abs_path, base_dir)
        )
        for bid, abs_path in file_names_by_bid.items()
    }

    return rel_paths, base_dir


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


def filter_and_sort(buf_errors, panel_filter):
    """Filter errors through white- and blacklisting, then sort them."""
    buf_errors = [e for e in buf_errors if passes_listing(e, panel_filter)]
    return sort_errors(buf_errors)


def get_window_errors(window, all_errors, panel_filter=None):
    bid_error_pairs = (
        (bid, all_errors[bid]) for bid in buffer_ids_per_window(window)
    )
    return {
        bid: filter_and_sort(errors, panel_filter)
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


def passes_listing(error, panel_filter):
    """Check value against white- and blacklisting and return bool."""
    # check whitelisting
    if not panel_filter:
        return True

    COMMAND_ARG_TO_ERROR_KEY = {
        "types": "error_type",
        "codes": "code",
        "linter": "linter"
    }

    for key, check_val in COMMAND_ARG_TO_ERROR_KEY.items():
        # check whitelisting
        if key in panel_filter:
            if error[check_val] not in panel_filter[key]:
                return False

        # check blacklisting
        exclude_key = "exclude_" + key
        if exclude_key in panel_filter:
            if error[check_val] in panel_filter[exclude_key]:
                return False

    # if all checks passed return True
    return True


def fill_panel(window, update=False, **panel_filter):
    errors_by_bid = get_window_errors(window, persist.errors, panel_filter)

    path_dict, base_dir = create_path_dict(window, errors_by_bid.keys())

    panel = ensure_panel(window)
    # If we're here and the user actually closed the window in the meantime,
    # we cannot create a panel anymore, and just pass.
    if not panel:
        return

    settings = panel.settings()
    settings.set("result_base_dir", base_dir)

    if update:
        panel_filter = settings.get("sublime_linter_panel_filter")
    else:
        settings.set("sublime_linter_panel_filter", panel_filter)

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


# logic for updating panel selection

def get_next_panel_line(line, col, errors):
    """Get panel line for next error in buffer.

    If not found this means the current line is past last error's buffer line.
    In that case return last error's panel line incremented by one, which will
    place panel selection in empty space between buffer sections.
    """
    for error in sort_errors(errors):
        if error["line"] == line and error["start"] > col:
            panel_line = error["panel_line"]
            break
        elif error["line"] > line:
            panel_line = error["panel_line"]
            break
    else:
        panel_line = errors[-1]["panel_line"] + 1

    return panel_line, panel_line


def update_selection(panel, region=None):
    selection = panel.sel()
    selection.clear()
    if region is not None:
        selection.add(region)


def get_panel_region(row, panel, is_full_line=False):
    region = sublime.Region(panel.text_point(row, -1))
    if is_full_line:
        region = panel.line(region)
    return region


def update_panel_selection(active_view, current_pos, **kwargs):
    """Alter panel selection according to errors belonging to current position.

    If current position is between two errors, place empty panel selection on start of next error's panel line.

    If current position is past last error, place empty selection on the panel line following that of last error.

    """
    if current_pos == (-1, -1):
        return

    all_errors = persist.errors.get(active_view.buffer_id())
    if not all_errors:
        return
    all_errors = [
        e for e in all_errors
        if "panel_line" in e
    ]
    if not all_errors:
        return

    (line, col) = current_pos

    errors = [
        e for e in all_errors
        if e["line"] == line
    ]

    panel_lines = None
    is_full_line = False

    if errors:
        # we got line dict, now check if current position has errors
        region_panel_lines = [
            e["panel_line"]
            for e in errors
            if e["start"] <= col <= e["end"]
        ]
        if region_panel_lines:
            panel_lines = min(region_panel_lines), max(region_panel_lines)
            is_full_line = True

    if not panel_lines:  # fallback: take next panel line
        panel_lines = get_next_panel_line(line, col, errors or all_errors)

    # logic for changing panel selection
    panel = get_panel(sublime.active_window())
    if not panel:
        return

    if panel_lines[0] == panel_lines[1]:
        draw_position_marker(panel, panel_lines[0], is_full_line)

        region = get_panel_region(panel_lines[0], panel, is_full_line)
    else:  # multiple panel lines
        is_full_line = True
        region_a = get_panel_region(panel_lines[0], panel)
        region_b = get_panel_region(panel_lines[1], panel, is_full_line)
        region = sublime.Region(region_a.begin(), region_b.end())

    update_selection(panel, region)
    panel.show_at_center(region)

    # simulate scrolling to enforce rerendering of panel,
    # otherwise selection is not updated (ST core bug)
    panel.run_command("scroll_lines")


def draw_position_marker(panel, line, error_under_cursor):
    if error_under_cursor:
        panel.erase_regions('SL.PanelMarker')
    else:
        line_start = panel.text_point(line - 1, 0)
        region = sublime.Region(line_start, line_start)
        scope = 'region.redish markup.deleted.sublime_linter markup.error.sublime_linter'
        flags = (sublime.DRAW_SOLID_UNDERLINE | sublime.DRAW_NO_FILL |
                 sublime.DRAW_NO_OUTLINE | sublime.DRAW_EMPTY_AS_OVERWRITE)
        panel.add_regions('SL.PanelMarker', [region], scope=scope, flags=flags)
