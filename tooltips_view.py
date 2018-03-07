import html

import sublime
import sublime_plugin

from .lint import persist
from .lint.const import WARNING, ERROR


class TooltipController(sublime_plugin.EventListener):
    def on_hover(self, view, point, hover_zone):
        """On mouse hover event hook.

        Arguments:
            view (View): The view which received the event.
            point (Point): The text position where the mouse hovered
            hover_zone (int): The context the event was triggered in
        """
        if hover_zone == sublime.HOVER_GUTTER:
            if persist.settings.get('show_hover_line_report'):
                open_tooltip(view, point, True)

        elif hover_zone == sublime.HOVER_TEXT:
            if persist.settings.get('show_hover_region_report'):
                open_tooltip(view, point)


class SublimeLinterLineReportCommand(sublime_plugin.WindowCommand):
    def run(self):
        open_tooltip(self.window.active_view(), line_report=True)


def open_tooltip(active_view, point=None, line_report=False):
    """Show a tooltip containing all linting errors on a given line."""
    stylesheet = '''
        body {
            word-wrap: break-word;
        }
        .error {
            color: var(--redish);
            font-weight: bold;
        }
        .warning {
            color: var(--yellowish);
            font-weight: bold;
        }
    '''

    template = '''
        <body id="sublimelinter-tooltip">
            <style>{stylesheet}</style>
            <div>{message}</div>
        </body>
    '''

    # Leave any existing popup open without replacing it
    # don't let the popup flicker / fight with other packages
    if active_view.is_popup_visible():
        return

    if point is None:
        line, col = get_current_pos(active_view)
    else:  # provided by hover
        line, col = active_view.rowcol(point)

    bid = active_view.buffer_id()

    errors = persist.errors[bid]
    errors = [e for e in errors if e["line"] == line]
    if not line_report:
        errors = [e for e in errors if e["start"] <= col <= e["end"]]
    if not errors:
        return

    tooltip_message = join_msgs(errors, line_report)
    if not tooltip_message:
        return

    location = active_view.text_point(line, col)
    active_view.show_popup(
        template.format(stylesheet=stylesheet, message=tooltip_message),
        flags=sublime.HIDE_ON_MOUSE_MOVE_AWAY,
        location=location,
        max_width=1000
    )


def join_msgs(errors, show_count=False):

    if show_count:
        part = '''
            <div class="{classname}">{count} {heading}</div>
            <div>{messages}</div>
        '''
    else:
        part = '''
            <div>{messages}</div>
        '''

    tmpl_with_code = "{linter}: {code} - {escaped_msg}"
    tmpl_sans_code = "{linter}: {escaped_msg}"

    all_msgs = ""
    for error_type in (WARNING, ERROR):
        heading = error_type
        filled_templates = []
        msg_list = [e for e in errors if e["error_type"] == error_type]

        if not msg_list:
            continue

        msg_list = sorted(msg_list, key=lambda x: (x["start"], x["end"]))
        count = len(msg_list)

        for item in msg_list:
            msg = html.escape(item["msg"], quote=False)
            tmpl = tmpl_with_code if item.get('code') else tmpl_sans_code
            filled_templates.append(tmpl.format(escaped_msg=msg, **item))

        if count > 1:  # pluralize
            heading += "s"

        all_msgs += part.format(
            classname=error_type,
            count=count,
            heading=heading,
            messages='<br />'.join(filled_templates)
        )
    return all_msgs


def get_current_pos(view):
    try:
        return view.rowcol(view.sel()[0].begin())
    except (AttributeError, IndexError):
        return -1, -1
