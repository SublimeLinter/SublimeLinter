import sublime

import math

from .lint import events


DEFAULT_TIMEOUT = 2500  # [ms]
INFO = 'info'
ERROR = 'error'

STYLES = {
    INFO: {
        'background': 'transparent',
        'foreground': 'var(--foreground)'
    },
    ERROR: {
        'background': 'var(--redish)',
        'foreground': '#fff'
    }
}


def plugin_unloaded():
    events.off(on_toast)


@events.on(events.TOAST)
def on_toast(message, type=INFO, timeout=DEFAULT_TIMEOUT, **kwargs):
    active_view = sublime.active_window().active_view()
    show_toast(active_view, message, timeout=timeout, style=STYLES[type])


def show_toast(view, message, timeout=DEFAULT_TIMEOUT, style=STYLES[INFO]):
    width, _ = view.viewport_extent()
    max_chars = math.floor(width // view.em_width())
    content = style_message(center(message, cols=max_chars), style)

    visible_region = view.visible_region()
    first_row, _ = view.rowcol(visible_region.begin())
    line_start = view.text_point(first_row, 0)

    flags = (
        sublime.COOPERATE_WITH_AUTO_COMPLETE |
        sublime.HIDE_ON_MOUSE_MOVE_AWAY
    )
    view.show_popup(content, flags,
                    max_width=width, location=line_start)

    sublime.set_timeout_async(lambda: hide_popup(view), timeout)


def hide_popup(view):
    if view.is_popup_visible():
        view.hide_popup()


def center(text, cols=80, char='&nbsp;'):
    fill_len = (cols - len(text)) // 2 - 1
    fill = fill_len * char
    return fill + text + fill


def style_message(message, style):
    return """
        <div
            style="padding: 1em 0;
                   background-color: {background};
                   color: {foreground}"
        >{message}</div>
    """.format(message=message, **style)
