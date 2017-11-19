import sublime
import sublime_plugin
from .sublime_linter import SublimeLinter
from .lint.persist import settings


class EventListener(sublime_plugin.EventListener):
    def on_hover(self, view, point, hover_zone):
        """Arguments:
            view (View): The view which received the event.
            point (Point): The text position where the mouse hovered
            hover_zone (int): The context the event was triggered in
        """
        if hover_zone != sublime.HOVER_GUTTER:
            return

        # don't let the popup flicker / fight with other packages
        if view.is_popup_visible():
            return

        if not settings.get('show_hover_line_report'):
            return

        lineno, colno = view.rowcol(point)
        from .sublime_linter import SublimeLinter
        SublimeLinter.shared_plugin().open_tooltip(view, lineno)

