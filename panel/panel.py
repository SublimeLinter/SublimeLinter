import html
import os
import sublime
import sublime_plugin
import copy


from ..lint.const import PLUGIN_NAME, WARN_ERR, WARNING, ERROR
from ..lint import util, persist
from difflib import SequenceMatcher


PANEL_NAME = "sublime_linter_panel"
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

STEALTH_KEY = "panel_stealth"
STEALTH_SCOPE = """ invisible scope: output.lsp.diagnostics meta.diagnostic.body.lsp markup.changed.lsp sublimelinter.mark.warning markup.warning.lsp """
# current compare cut-off should be at 52 chars


def visual_grouping(view, lines):
    """Applies invisibility scope to region to those lines overlapping with content from the previous one. Anchored to the start.
    Minimal length ensures line number and columns are not minced. Errors are always displayed."""

    regions = []
    cut_off = 45
    min_len = 8

    for i, line in enumerate(lines):
        if i == 0:
            continue
        prev = lines[i - 1]

        min_line_len = min(len(prev), len(line))
        cut_off = min_line_len if min_line_len < cut_off else cut_off

        s = SequenceMatcher(lambda x: x == ERROR, prev, line)

        match = s.find_longest_match(0, cut_off, 0, cut_off)

        if match.a == 0 and match.size >= min_len:
            start = view.text_point(i, 0)
            end = view.text_point(i, match.size)
            region = sublime.Region(start, end)
            regions.append(region)

    view.add_regions(STEALTH_KEY, regions, STEALTH_SCOPE)


def dedupe_views(errors):
    if len(errors) == 1:
        return errors
    else:
        return {
            vid: dic
            for vid, dic in errors.items()
            if sublime.View(vid).is_primary()
        }


def get_file_path(vid):
    return sublime.View(vid).file_name()


def get_common_parent(paths):
    """
    Get the common parent directory of multiple paths.
    Python 3.5+ includes os.path.commonpath which does this, however Sublime
    currently embeds Python 3.3.
    """
    return os.path.commonprefix([path + '/' for path in paths]).rstrip('/')


def create_path_dict(x):
    abs_dict = {vid: get_file_path(vid) for vid in x}

    if len(abs_dict) == 1:
        for vid, path in abs_dict.items():
            base_dir, file_name = os.path.split(path)
            rel_paths = {vid: file_name}
    else:
        base_dir = get_common_parent(abs_dict.values())

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

    panel.settings().set("result_file_regex", r"^\s*(\S*\.\w+)\s*(\d*)")
    panel.settings().set("result_line_regex", r"(^\s*\d+)")

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
    return "{}".format(f_path)  # TODO: better using phantom + icon?


def format_row(lineno, err_type, dic):
    lineno = int(lineno) + 1  # if lineno else lineno
    tmpl = "{LINENO:>7}:{start:<7}{ERR_TYPE:15}{linter:<16}{code:<9}{msg:>10}"
    return tmpl.format(LINENO=lineno, ERR_TYPE=err_type, **dic)


def fill_panel(window, types=None, codes=None, linter=None, update=False):

    errors = persist.errors.data.copy()
    if not errors:
        return

    errors = filter_errors(window, errors)
    errors = dedupe_views(errors)
    # base_dir = util.get_project_path(window)
    path_dict, base_dir = create_path_dict(errors)

    assert window, "missing window!"

    panel = ensure_panel(window)
    assert panel, "must have a panel now!"

    settings = panel.settings()
    settings.set("result_base_dir", base_dir)

    if update:
        panel.run_command("sublime_linter_panel_clear")
        types = settings.get("types")
        codes = settings.get("codes")
        linter = settings.get("linter")
    else:
        settings.set("types", types)
        settings.set("codes", codes)
        settings.set("linter", linter)

    panel.set_read_only(False)
    to_render = []
    for vid, view_dict in errors.items():

        if util.is_none_or_zero(view_dict["we_count_view"]):
            continue

        to_render.append(format_header(path_dict[vid]))

        for lineno, line_dict in sorted(view_dict["line_dicts"].items()):
            for err_type in WARN_ERR:
                if types and err_type not in types:
                    continue
                err_dict = line_dict.get(err_type)
                if not err_dict:
                    continue
                items = sorted(err_dict, key=lambda k: k['start'])

                for item in items:
                    # new filter function
                    if linter and item['linter'] not in linter:
                        continue

                    if codes and item['code'] not in codes:
                        continue

                    line_msg = format_row(lineno, err_type, item)
                    to_render.append(line_msg)

        to_render.append("\n")  # empty lines between views

    panel.erase_regions(STEALTH_KEY)
    panel.run_command("sublime_linter_panel_update", {
                      "characters": "\n".join(to_render)})
    panel.set_read_only(True)
    visual_grouping(panel, to_render)
