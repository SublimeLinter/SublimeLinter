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

# diagnostic_severity_names = {
#     DiagnosticSeverity.Error: "error",
#     DiagnosticSeverity.Warning: "warning",
#     DiagnosticSeverity.Information: "info",
#     DiagnosticSeverity.Hint: "hint"
# }

# diagnostic_severity_scopes = {
#     DiagnosticSeverity.Error: 'markup.deleted.lsp sublimelinter.mark.error markup.error.lsp',
#     DiagnosticSeverity.Warning: 'markup.changed.lsp sublimelinter.mark.warning markup.warning.lsp',
#     DiagnosticSeverity.Information: 'markup.inserted.lsp sublimelinter.gutter-mark markup.info.lsp',
#     DiagnosticSeverity.Hint: 'markup.inserted.lsp sublimelinter.gutter-mark markup.info.suggestion.lsp'
# }

stylesheet = '''
            <style>
                div.error-arrow {
                    border-top: 0.4rem solid transparent;
                    border-left: 0.5rem solid color(var(--redish) blend(var(--background) 30%));
                    width: 0;
                    height: 0;
                }
                div.error {
                    padding: 0.4rem 0 0.4rem 0.7rem;
                    margin: 0 0 0.2rem;
                    border-radius: 0 0.2rem 0.2rem 0.2rem;
                }

                div.error span.message {
                    padding-right: 0.7rem;
                }

                div.error a {
                    text-decoration: inherit;
                    padding: 0.35rem 0.7rem 0.45rem 0.8rem;
                    position: relative;
                    bottom: 0.05rem;
                    border-radius: 0 0.2rem 0.2rem 0;
                    font-weight: bold;
                }
                html.dark div.error a {
                    background-color: #00000018;
                }
                html.light div.error a {
                    background-color: #ffffff18;
                }
            </style>
        '''

UNDERLINE_FLAGS = (sublime.DRAW_SQUIGGLY_UNDERLINE
                   | sublime.DRAW_NO_OUTLINE
                   | sublime.DRAW_NO_FILL
                   | sublime.DRAW_EMPTY_AS_OVERWRITE)

BOX_FLAGS = sublime.DRAW_NO_FILL | sublime.DRAW_EMPTY_AS_OVERWRITE


def create_phantom_html(text: str) -> str:
    global stylesheet
    return """<body id=inline-error>{}
                <div class="error-arrow"></div>
                <div class="error">
                    <span class="message">{}</span>
                    <a href="code-actions">Code Actions</a>
                </div>
                </body>""".format(stylesheet, html.escape(text, quote=False))


def on_phantom_navigate(view: sublime.View, href: str, point: int):
    # TODO: don't mess with the user's cursor.
    sel = view.sel()
    sel.clear()
    sel.add(sublime.Region(point))
    view.run_command("lsp_code_actions")


def create_phantom(view, diagnostic):
    region = diagnostic.range.to_region(view)
    # TODO: hook up hide phantom (if keeping them)
    content = create_phantom_html(diagnostic.message)
    return sublime.Phantom(
        region,
        '<p>' + content + '</p>',
        sublime.LAYOUT_BELOW,
        lambda href: on_phantom_navigate(view, href, region.begin())
    )


def format_severity(severity: int) -> str:
    return diagnostic_severity_names.get(severity, "???")


phantom_sets_by_buffer = {}  # type: Dict[int, sublime.PhantomSet]


def dedupe_views(errors):
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



def update_diagnostics_phantoms(view: sublime.View, diagnostics: 'List[Diagnostic]'):
    global phantom_sets_by_buffer

    buffer_id = view.buffer_id()
    if not settings.show_diagnostics_phantoms or view.is_dirty():
        phantoms = None
    else:
        phantoms = list(
            create_phantom(view, diagnostic) for diagnostic in diagnostics)
    if phantoms:
        phantom_set = phantom_sets_by_buffer.get(buffer_id)
        if not phantom_set:
            phantom_set = sublime.PhantomSet(view, "lsp_diagnostics")
            phantom_sets_by_buffer[buffer_id] = phantom_set
        phantom_set.update(phantoms)
    else:
        phantom_sets_by_buffer.pop(buffer_id, None)


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


def update_diagnostics_in_view(view: sublime.View, diagnostics: 'List[Diagnostic]'):
    if view and view.is_valid():
        update_diagnostics_phantoms(view, diagnostics)
        for severity in range(DiagnosticSeverity.Error, DiagnosticSeverity.Information):
            update_diagnostics_regions(view, diagnostics, severity)


# Events.subscribe("document.diagnostics",
#                  lambda update: handle_diagnostics(update))


def handle_diagnostics(update):
    window = sublime.active_window()
    view = window.find_open_file(update.file_path)
    if view:
        update_diagnostics_in_view(view, update.diagnostics)
    update_diagnostics_panel(window)


class PanelCursorListener(sublime_plugin.ViewEventListener):
    def __init__(self, view):
        self.view = view
        self.has_status = False
        print(self.view)

    @classmethod
    def is_applicable(cls, view_settings):
        syntax = view_settings.get('syntax')
        return settings.show_diagnostics_in_view_status and syntax and is_supported_syntax(syntax)

    def on_selection_modified_async(self):
        print("selection modified in panel")
    #     selections = self.view.sel()
    #     if len(selections) > 0:
    #         pos = selections[0].begin()
    #         line_diagnostics = get_line_diagnostics(self.view, pos)
    #         if len(line_diagnostics) > 0:
    #             self.show_diagnostics_status(line_diagnostics)
    #         elif self.has_status:
    #             self.clear_diagnostics_status()

    # def show_diagnostics_status(self, line_diagnostics):
    #     self.has_status = True
    #     self.view.set_status('lsp_diagnostics', line_diagnostics[0].message)

    # def clear_diagnostics_status(self):
    #     self.view.set_status('lsp_diagnostics', "")
    #     self.has_status = False




PANEL_NAME = "sublime_linter_panel"

def create_panel(window):
    panel = create_output_panel(window, PANEL_NAME)
    panel.settings().set("result_file_regex", r"^\s*\S\s+(\S.*):$")
    panel.settings().set("result_line_regex", r"^\s+([0-9]+):?([0-9]+).*$")
    syntax_path = "Packages/" + PLUGIN_NAME + \
        "/panel/syntaxes/Diagnostics.sublime-syntax"
    panel.assign_syntax(syntax_path)
    # Call create_output_panel a second time after assigning the above
    # settings, so that it'll be picked up as a result buffer
    # see: Packages/Default/exec.py#L228-L230
    PanelCursorListener(panel)
    return window.create_output_panel(PANEL_NAME)

def get_panel(window):
    return window.find_output_panel(PANEL_NAME)

def ensure_panel(window: sublime.Window):
    return get_panel(window) or create_panel(window)


# def format_diagnostic(diagnostic) -> str:
#     # location = "{:>8}:{:<4}".format(
#     #     diagnostic.range.start.row + 1, diagnostic.range.start.col + 1)
#     # message = diagnostic.message.replace("\n", " ").replace("\r", "")
#     # return " {}\t{:<12}\t{:<10}\t{}".format(
#     #     location, diagnostic.source, format_severity(diagnostic.severity), message)
#     return " {}\t{:<12}\t{:<10}\t{}".format(
#         "AAA", "BBB", "CCC", "DDD")


# def format_diagnostics(file_path, item, err_type):
#     content = " ◌ {}:\n".format(file_path)
#     f_item = " {}\t{:<12}\t{:<10}\t{}".format(
#         item["col"], item["linter"], err_type, item["msg"])
#     content += f_item + "\n"
#     return content

def format_header(vid):
    f_path = vid
    return " ◌ {}".format(f_path)  # TODO: better using phantom + icon?

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
# - allow command to filter by active,view | type, linter, code
# - on sublime loaded lint all open views if background or load_save
# - update diagnostics on lint
# - jump to next file in panel (needing symbol defintion?)
# - toggle panel behaviour
# - remove old commands
def update_diagnostics_panel(window, linter):
    print("update diagnostics called")
    errors = persist.errors.data.copy()
    if not errors:
        return

    print("linter in update_diagnostics_panel:", linter)

    errors = dedupe_views(errors)
    # base_dir = util.get_project_path(window)
    path_dict, base_dir = create_path_dict(errors)

    assert window, "missing window!"

    panel = ensure_panel(window)
    assert panel, "must have a panel now!"

    active_panel = window.active_panel()
    is_active_panel = (active_panel == "output." + PANEL_NAME)
    panel.settings().set("result_base_dir", base_dir)

    # file_regex = (r"^\s*(\S*\.\w+)\s*(\d*)")
    file_regex = (r"◌\s*(\S*\.\w+)\s*(\d*)")  # TODO: clean up regex

    line_regex = (r"(^\s*\d+)")
    panel.settings().set("result_file_regex", file_regex)
    panel.settings().set("result_line_regex", line_regex)

    panel.set_read_only(False)

    # import json
    # print(json.dumps(errors, indent=4, sort_keys=True))

    to_render = []
    for vid, view_dict in errors.items():
        to_render.append(format_header(path_dict[vid]))
        prev_lineno = None
        for lineno, line_dict in sorted(view_dict["line_dicts"].items()):
            prev_err_type = None
            for err_type in WARN_ERR:
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
                        if linter and item['linter'] not in [linter]:
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
    # if not active_panel:
    #     window.run_command("show_panel",
    #                        {"panel": "output." + PANEL_NAME})
    # else:
    #     panel.run_command("sublime_linter_panel_clear")
    #     if is_active_panel:
    #         window.run_command("hide_panel",
    #                            {"panel": "output." + PANEL_NAME})

            # window.destroy_output_panel(PANEL_NAME)  ## added by me

    panel.set_read_only(True)
