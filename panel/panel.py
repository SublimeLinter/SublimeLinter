import os
import sublime

from ..lint import persist

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


def get_common_parent(paths):
    """
    Get the common parent directory of multiple paths.

    Python 3.5+ includes os.path.commonpath which does this, however Sublime
    currently embeds Python 3.3.
    """
    common_path = os.path.commonprefix([path + '/' for path in paths if path])
    if not os.path.exists(common_path):
        common_path = os.path.dirname(common_path)
    return common_path.rstrip('/\\')


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
    base_dir = ""
    file_names_by_bid = get_filenames(window, bids)

    if len(file_names_by_bid) == 1:
        for bid, path in file_names_by_bid.items():
            base_dir, file_name = os.path.split(path)
            rel_paths = {bid: file_name}
    else:
        base_dir = get_common_parent(file_names_by_bid.values())
        if not base_dir:
            rel_paths = file_names_by_bid
        else:
            rel_paths = {
                bid: os.path.relpath(abs_path, base_dir)
                for bid, abs_path in file_names_by_bid.items()
            }

    return rel_paths, base_dir or ""


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
    return sorted(errors, key=lambda x: (x["line"], x["start"], x["end"]))


def filter_and_sort(buf_errors, panel_filter):
    """Filter raw_errors through white- and blacklisting, then sort them."""
    buf_errors = [e for e in buf_errors if passes_listing(e, panel_filter)]
    return sort_errors(buf_errors)


def get_window_raw_errors(window, errors, panel_filter):
    return {
        bid: filter_and_sort(errors[bid], panel_filter)
        for bid in {v.buffer_id()
                    for v in window.views()}
    }


def format_header(f_path):
    return "{}:".format(f_path)


def run_update_panel_cmd(panel, text=None):
    cmd = "sublime_linter_update_panel"
    clear_sel = False
    if not text:
        text = "No lint errors."
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

    errors = persist.raw_errors
    if not errors:
        return

    errors_by_bid = get_window_raw_errors(window, errors, panel_filter)

    path_dict, base_dir = create_path_dict(window, errors_by_bid.keys())
    assert window, "missing window!"

    panel = ensure_panel(window)
    assert panel, "must have a panel now!"

    settings = panel.settings()
    settings.set("result_base_dir", base_dir)

    if update:
        panel_filter = settings.get("sublime_linter_panel_filter")
    else:
        settings.set("sublime_linter_panel_filter", panel_filter)

    to_render = []
    for bid, buf_errors in errors_by_bid.items():
        # do not show headers without errors
        if not buf_errors:
            continue

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


# logic for updating panel selection

def get_next_panel_line(line, errors):
    """Get panel line for next error in buffer.

    If not found this means the current line is past last error's buffer line.
    In that case return last error's panel line incremented by one, which will
    place panel selection in empty space between buffer sections.
    """
    for error in errors:
        if error["line"] > line:
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


def update_panel_selection(active_view, we_count, current_pos, **kwargs):
    """Alter panel selection according to errors belonging to current position.

    If current position is between two errors, place empty panel selection on start of next error's panel line.

    If current position is past last error, place empty selection on the panel line following that of last error.

    """
    if current_pos == (-1, -1):
        return

    all_errors = persist.raw_errors.get(active_view.buffer_id())
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
        panel_lines = get_next_panel_line(line, errors or all_errors)

    # logic for changing panel selection
    panel = get_panel(sublime.active_window())
    if not panel:
        return

    if panel_lines[0] == panel_lines[1]:
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
