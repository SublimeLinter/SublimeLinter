import sublime
import sublime_plugin

from .lint import persist
from .panel.panel import fill_panel, PANEL_NAME


class SublimeLinterLintCommand(sublime_plugin.TextCommand):
    """A command that lints the current view if it has a linter."""

    def is_enabled(self):
        """
        Return True if the current view can be linted.

        If the view has *only* file-only linters, it can be linted
        only if the view is not dirty.

        Otherwise it can be linted.

        """

        has_non_file_only_linter = False

        vid = self.view.id()
        linters = persist.view_linters.get(vid, [])

        for lint in linters:
            if lint.tempfile_suffix != '-':
                has_non_file_only_linter = True
                break

        if not has_non_file_only_linter:
            return not self.view.is_dirty()

        return True

    def run(self, edit):
        """Lint the current view."""
        from .sublime_linter import SublimeLinter
        SublimeLinter.shared_plugin().hit(self.view)


class SublimeLinterLineReportCommand(sublime_plugin.WindowCommand):
    def run(self):
        from .sublime_linter import SublimeLinter
        SublimeLinter.shared_plugin().open_tooltip()


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
        Changes visibility of panel with given name.
        Panel will be shown by default.
        Pass show=False for hiding.
        """
        if show:
            cmd = "show_panel"
        else:
            cmd = "hide_panel"

        self.window.run_command(cmd, {"panel": "output." + name or ""})


class SublimeLinterReplaceAllCommand(sublime_plugin.TextCommand):
    def run(self, edit, characters):
        self.view.replace(edit, sublime.Region(0, self.view.size()), characters)
