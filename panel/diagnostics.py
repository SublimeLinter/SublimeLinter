import html
import os
import sublime
import sublime_plugin
import copy

try:
    from typing import Any, List, Dict, Tuple, Callable, Optional
    assert Any and List and Dict and Tuple and Callable and Optional
except ImportError:
    pass

# from .core.settings import settings
from ..lint.const import PLUGIN_NAME, WARN_ERR
from ..lint import util, persist

# from .core.events import Events
# from .core.configurations import is_supported_syntax
# from .core.diagnostics import DiagnosticsUpdate, get_window_diagnostics, get_line_diagnostics
# from .core.workspace import get_project_path
from .panels import create_output_panel


PANEL_NAME = "sublime_linter_panel"
OUTPUT_PANEL_SETTINGS = {
    "auto_indent": False,
    "draw_indent_guides": False,
    "draw_white_space": "None",
    "gutter": False,
    'is_widget': True,
    "line_numbers": False,
    "margin": 3,
    "match_brackets": False,
    "scroll_past_end": False,
    "tab_size": 4,
    "translate_tabs_to_spaces": False,
    "word_wrap": False
}


UNDERLINE_FLAGS = (sublime.DRAW_SQUIGGLY_UNDERLINE
                   | sublime.DRAW_NO_OUTLINE
                   | sublime.DRAW_NO_FILL
                   | sublime.DRAW_EMPTY_AS_OVERWRITE)

BOX_FLAGS = sublime.DRAW_NO_FILL | sublime.DRAW_EMPTY_AS_OVERWRITE


def format_severity(severity: int) -> str:
    return diagnostic_severity_names.get(severity, "???")


phantom_sets_by_buffer = {}  # type: Dict[int, sublime.PhantomSet]


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


def get_common_parent(paths: 'List[str]') -> str:
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


def update_diagnostics_regions(view: sublime.View, diagnostics: 'List[Diagnostic]', severity: int):
    region_name = "lsp_" + format_severity(severity)
    if settings.show_diagnostics_phantoms and not view.is_dirty():
        regions = None
    else:
        regions = list(diagnostic.range.to_region(view) for diagnostic in diagnostics
                       if diagnostic.severity == severity)
    if regions:
        scope_name = diagnostic_severity_scopes[severity]
        view.add_regions(
            region_name, regions, scope_name, settings.diagnostics_gutter_marker,
            UNDERLINE_FLAGS if settings.diagnostics_highlight_style == "underline" else BOX_FLAGS)
    else:
        view.erase_regions(region_name)


def create_panel(window):
    panel = create_output_panel(window, PANEL_NAME)
    settings = panel.settings()
    for key, value in OUTPUT_PANEL_SETTINGS.items():
        settings.set(key, value)
    settings().set("result_file_regex", r"^\s*\S\s+(\S.*):$")
    settings().set("result_line_regex", r"^\s+([0-9]+):?([0-9]+).*$")
    syntax_path = "Packages/" + PLUGIN_NAME + \
        "/panel/syntaxes/Diagnostics.sublime-syntax"
    panel.assign_syntax(syntax_path)
    # Call create_output_panel a second time after assigning the above
    # settings, so that it'll be picked up as a result buffer
    # see: Packages/Default/exec.py#L228-L230
    return window.create_output_panel(PANEL_NAME)


def get_panel(window):
    return window.find_output_panel(PANEL_NAME)


def ensure_panel(window: sublime.Window):
    return get_panel(window) or create_panel(window)


def filter_errors(window, select, errors):
    if select == "current":
        vid = window.active_view().id()
        return {vid: errors[vid]}
    elif select == "window":
        vids = [v.id() for v in window.views()]
        return {vid: d for vid, d in errors.items() if vid in vids}
    else:  # == "all"
        return errors


def format_header(f_path):
    return "{}".format(f_path)  # TODO: better using phantom + icon?


def format_row(lineno, err_type, dic):
    prefix = "{LINENO:>6}   {ERR_TYPE:<8} ".format(
        LINENO=int(lineno) + 1 if lineno else lineno, ERR_TYPE=err_type)

    col_tmpl = "{start:>6}:{end:<10}"
    # workaround for not repeating identical cols on consecutive lines
    if "hide_cols" in dic:
        col_tmpl = " " * 17

    tmpl = col_tmpl + "{linter:<15}{code:<6}{msg:>10}"
    return prefix + tmpl.format(**dic)

# TODO:
# - on sublime loaded lint all open views if background or load_save
# - update diagnostics on lint
# - jump to next file in panel (needing symbol defintion?)
# - toggle panel behaviour
# - focus panel upon opening


def update_diagnostics_panel(window, select="window", types=None, codes=None, linter=None):
    print("update diagnostics called")
    errors = persist.errors.data.copy()
    if not errors:
        return

    errors = filter_errors(window, select, errors)
    errors = dedupe_views(errors)
    # base_dir = util.get_project_path(window)
    path_dict, base_dir = create_path_dict(errors)

    assert window, "missing window!"

    panel = ensure_panel(window)
    assert panel, "must have a panel now!"

    panel.settings().set("result_base_dir", base_dir)

    file_regex = (r"^\s*(\S*\.\w+)\s*(\d*)")
    line_regex = (r"(^\s*\d+)")
    panel.settings().set("result_file_regex", file_regex)
    panel.settings().set("result_line_regex", line_regex)

    panel.set_read_only(False)

    to_render = []
    for vid, view_dict in errors.items():
        to_render.append(format_header(path_dict[vid]))
        prev_lineno = None
        for lineno, line_dict in sorted(view_dict["line_dicts"].items()):
            prev_err_type = None
            for err_type in WARN_ERR:
                if types and err_type not in types:
                    continue
                err_dict = line_dict.get(err_type)
                if not err_dict:
                    continue
                items = sorted(err_dict, key=lambda k: k['start'])
                prev_start_end = (None, None)
                prev_linter = None
                for item in items:
                    lineno = "" if lineno == prev_lineno else lineno
                    err_type = "" if err_type == prev_err_type else err_type

                    if prev_start_end == (item['start'], item['end']):
                        item['hide_cols'] = True

                        # new filter function
                        if linter and item['linter'] not in linter:
                            continue

                        if codes and item['code'] not in codes:
                            continue

                        if item['linter'] == prev_linter:
                            item["linter"] = ""

                    line_msg = format_row(lineno, err_type, item)
                    to_render.append(line_msg)
                    prev_lineno = lineno
                    prev_err_type = err_type
                    prev_start_end = (item['start'], item['end'])
                    prev_linter = item['linter']
        to_render.append("\n")  # empty lines between views

    panel.run_command("sublime_linter_panel_update", {
                      "characters": "\n".join(to_render)})
    panel.set_read_only(True)
    window.run_command("sublime_linter_panel_toggle", {"ensure_panel": True})
