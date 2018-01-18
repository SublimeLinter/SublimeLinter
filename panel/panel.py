import os
import sublime
import bisect

from ..lint import util, persist

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
    """Return dict of buffer_id: file_name for all views in window.

       Untitled buffers are file names are substituded by:
       <untitled buffer_id>
    """

    return {
        v.buffer_id(): v.file_name() or "<untitled {}>".format(v.buffer_id())
        for v in window.views()
        if v.buffer_id() in bids
    }


def create_path_dict(window, bids):
    base_dir = ""
    abs_dict = get_filenames(window, bids)

    if len(abs_dict) == 1:
        for vid, path in abs_dict.items():
            base_dir, file_name = os.path.split(path)
            rel_paths = {vid: file_name}
    else:
        base_dir = get_common_parent(abs_dict.values())
        if not base_dir:
            rel_paths = abs_dict
        else:
            rel_paths = {
                vid: os.path.relpath(abs_path, base_dir)
                for vid, abs_path in abs_dict.items()
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


def get_window_raw_errors(window, errors):
    bids = {v.buffer_id() for v in window.views()}
    return {bid: d for bid, d in errors.items() if bid in bids}


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
    line = int(item["line"]) + 1
    start = item['start'] + 1
    tmpl = " {LINE:>5}:{START:<4} {error_type:7} {linter:>12}: {code:12} {msg}"
    return tmpl.format(LINE=line, START=start, **item)


def passes_listing(buf_d, panel_filter):
    """Check value against white- and blacklisting and return bool."""
    # check whitelisting
    if not panel_filter:
        return True

    x = {"types": "error_type", "codes": "code", "linter": "linter"}
    for key, check_val in x.items():
        # check whitelisting
        if key in panel_filter:
            if buf_d[check_val] not in panel_filter[key]:
                return False

        # check blacklisting
        exclude_key = "exclude_" + key
        if exclude_key in panel_filter:
            if buf_d[check_val] in panel_filter[exclude_key]:
                return False

    # if all checks passed return True
    return True


def get_buf_lines(buf_dicts, panel_filter):
    return [d for d in buf_dicts if passes_listing(d, panel_filter)]


def fill_panel(window, update=False, **panel_filter):

    errors = persist.raw_errors
    if not errors:
        return

    errors = get_window_raw_errors(window, errors)

    path_dict, base_dir = create_path_dict(window, errors)
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
    for bid, buf_dict in errors.items():
        buf_lines = get_buf_lines(buf_dict, panel_filter)
        if buf_lines:
            # append header
            to_render.append(format_header(path_dict[bid]))

            # append lines
            base_lineno = len(to_render)
            for i, item in enumerate(buf_lines):
                to_render.append(format_row(item))
                item["panel_line"] = base_lineno + i

            # insert empty line between views sections
            to_render.append("")

    run_update_panel_cmd(panel, text="\n".join(to_render))


# logic for updating panel selection

def get_next_panel_line(buf_line, buf_dict):
    """Get panel line for next error in buffer.

    If not found this means the current line is past last error's buffer line.
    In that case return last error's panel line incremented by one, which will
    place panel selection in empty space between buffer sections.
    """
    for d in buf_dict:
        if d["line"] > buf_line:
            panel_line = d["panel_line"]
            break
    else:
        panel_line = buf_dict[-1]["panel_line"] + 1

    return panel_line, panel_line


def update_selection(panel, region=None):
    selection = panel.sel()
    selection.clear()
    if region is not None:
        selection.add(region)


def get_panel_region(row, panel, is_full_line=False):
    region = sublime.Region(panel.text_point(row - 1, -1))
    if is_full_line:
        region = panel.line(region)
    return region


def update_panel_selection(active_view, we_count, current_pos, **kwargs):
    if current_pos == (-1, -1):
        return

    buf_dicts = persist.raw_errors.get(active_view.buffer_id())
    if not buf_dicts:  # None type error with default dict??
        return
    buf_dicts = [d for d in buf_dicts if "panel_line" in d]
    if not buf_dicts:
        return

    (buf_line, col) = current_pos
    line_dicts = [d for d in buf_dicts if d["line"] == buf_line]

    is_full_line = False
    if line_dicts:
        region_panel_lines = [
            d["panel_line"]
            for d in line_dicts
            if d["start"] <= col <= d["end"]
        ]
        if region_panel_lines:
            panel_lines = min(region_panel_lines), max(region_panel_lines)
            is_full_line = True

    panel_lines = get_next_panel_line(buf_line, line_dicts or buf_dicts)

    # logic for actually changing panel
    panel = get_panel(sublime.active_window())
    if not panel:
        return

    if panel_lines[0] == panel_lines[1]:
        region = get_panel_region(panel_lines[0], panel, is_full_line)
    else:
        region_a = get_panel_region(panel_lines[0], panel)
        region_b = get_panel_region(panel_lines[1], panel, is_full_line=True)
        region = sublime.Region(region_a.begin(), region_b.end())

    update_selection(panel, region)

    # scroll selection into panel
    if not panel.visible_region().contains(region):
        panel.show(region)

    # simulate scrolling to enforce rerendering of panel,
    # otherwise selection is not updated (ST core bug)
    panel.run_command("scroll_lines")