import os
import sublime
import bisect

from ..lint.const import WARN_ERR
from ..lint import util, persist

PANEL_NAME = "SublimeLinter"
OUTPUT_PANEL_SETTINGS = {
    "auto_indent": False,
    "draw_indent_guides": False,
    "draw_white_space": "None",
    "gutter": False,
    "is_widget": True,
    "line_numbers": False,
    "margin": 3,
    "match_brackets": False,
    "scroll_past_end": False,
    "tab_size": 4,
    "translate_tabs_to_spaces": False,
    "word_wrap": False
}


class RenderLines:
    def __init__(self):
        self.lines = []
        self._line_counter = 0

    def append(self, str):
        self.lines.append(str)
        self._line_counter += 1

    def current_lineno(self):
        return self._line_counter

    def render(self):
        return "\n".join(self.lines)


def dedupe_views(errors):
    if len(errors) == 1:
        return errors
    else:
        return {
            vid: dic
            for vid, dic in errors.items()
            if sublime.View(vid).is_primary()
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


def create_path_dict(x):
    abs_dict = {}
    base_dir = ""
    for vid in x:
        view = sublime.View(vid)
        if view.file_name():
            abs_dict[vid] = view.file_name()
        else:
            abs_dict[vid] = "<untitled " + str(view.buffer_id()) + ">"

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


def filter_errors(window, errors):
    vids = [v.id() for v in window.views()]
    return {vid: d for vid, d in errors.items() if vid in vids}


def format_header(f_path):
    return "{}:".format(f_path)


def run_update_panel_cmd(panel, text=None):
    cmd = "sublime_linter_update_panel"
    clear_sel = False
    if not text:
        text = "No lint errors."
        clear_sel = True
    panel.run_command(cmd, {'text': text, 'clear_sel': clear_sel})


def format_row(lineno, error_type, dic):
    lineno = int(lineno) + 1
    start = dic['start'] + 1
    msg = dic['msg'].rstrip()
    tmpl = " {LINENO:>5}:{START:<4} {ERR_TYPE:7} {linter:>12}: {code:12} {MSG}"
    return tmpl.format(
        LINENO=lineno, START=start, ERR_TYPE=error_type, MSG=msg, **dic)


def fill_panel(window, types=None, codes=None, linter=None, update=False):
    errors = persist.errors.data
    if not errors:
        return

    errors = filter_errors(window, errors)
    errors = dedupe_views(errors)

    path_dict, base_dir = create_path_dict(errors)
    assert window, "missing window!"

    panel = ensure_panel(window)
    assert panel, "must have a panel now!"

    settings = panel.settings()
    settings.set("result_base_dir", base_dir)

    if update:
        types = settings.get("types")
        codes = settings.get("codes")
        linter = settings.get("linter")
    else:
        settings.set("types", types)
        settings.set("codes", codes)
        settings.set("linter", linter)

    to_render = RenderLines()
    for vid, view_dict in errors.items():
        if util.is_none_or_zero(view_dict["we_count_view"]):
            continue

        to_render.append(format_header(path_dict[vid]))

        for lineno, line_dict in sorted(view_dict["line_dicts"].items()):
            for error_type in WARN_ERR:
                if types and error_type not in types:
                    continue
                err_dict = line_dict.get(error_type)
                if not err_dict:
                    continue
                items = sorted(err_dict, key=lambda k: k['start'])

                for item in items:
                    item["panel_lineno"] = None
                    # new filter function
                    if linter and item['linter'] not in linter:
                        continue

                    if codes and item['code'] not in codes:
                        continue

                    line_msg = format_row(lineno, error_type, item)
                    to_render.append(line_msg)
                    item["panel_lineno"] = to_render.current_lineno()

        to_render.append("")  # empty lines between views

    rendered_text = to_render.render() if to_render else None
    run_update_panel_cmd(panel, text=rendered_text)


# logic for updating panel selection

def get_closest_region_dict(dic, colno):
    dics = [
        d
        for error_dict in dic.values() for d in error_dict
        if d.get("panel_lineno")
        # if d["start"] <= colno <= d["end"]  # problematic line
    ]
    if not dics:
        return
    return min(dics, key=lambda x: abs(x["start"] - colno))


def get_next_lineno(num, interval):
    interval = set(interval)
    interval.discard(num)
    interval = list(interval)
    interval.sort()

    if num < interval[0] or interval[-1] < num:
        return interval[0]
    else:
        i = bisect.bisect_right(interval, num)
        neighbours = interval[i - 1:i + 1]
        return neighbours[1]


def change_selection(panel_lineno, full_line=False, window=None):
    panel = get_panel(window or sublime.active_window())
    if not panel:
        return

    region = sublime.Region(panel.text_point(panel_lineno - 1, -1))
    if full_line:
        region = panel.line(region)

    selection = panel.sel()
    selection.clear()
    selection.add(region)

    # scroll selection into panel
    if not panel.visible_region().contains(region):
        panel.show(region)

    # simulate scrolling to enforce rerendering of panel,
    # otherwise selection is not updated (ST core bug)
    panel.run_command("scroll_lines")


def update_panel_selection(vid, lineno=None, colno=None, window=None):
    if lineno < 0:
        lineno = None
    if colno <= 0:
        colno = None

    full_line = False
    view_dict = persist.errors.get_view_dict(vid)
    if not view_dict or util.is_none_or_zero(view_dict["we_count_view"]):
        return

    line_dicts = view_dict["line_dicts"]

    if lineno:
        if lineno in line_dicts:
            full_line = True
        else:
            lineno = get_next_lineno(lineno, line_dicts)

    lineno = 0 if lineno is None else lineno

    line_dict = line_dicts[lineno]
    region_dict = get_closest_region_dict(line_dict, colno or 0)

    if not region_dict:
        return

    if full_line and colno is not None:
        full_line = region_dict["start"] <= colno <= region_dict["end"]

    panel_lineno = region_dict.get("panel_lineno")

    if panel_lineno:
        change_selection(panel_lineno, full_line=full_line)
