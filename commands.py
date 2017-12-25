import sublime
import sublime_plugin

from .panel.panel import fill_panel, PANEL_NAME


class SublimeLinterLintCommand(sublime_plugin.TextCommand):
    """A command that lints the current view if it has a linter."""

    def run(self, edit, lint_all_views=False):
        """Lint the current view."""
        from .sublime_linter import SublimeLinter

        plugin = SublimeLinter.shared_plugin()
        if not lint_all_views:
            plugin.hit(self.view)
        else:
            for window in sublime.windows():
                for view in window.views():
                    plugin.check_syntax(view)
            plugin.lint_all_views()

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


class SublimeLinterUpdatePanelCommand(sublime_plugin.TextCommand):
    def run(self, edit, text="", clear_sel=False):
        """Replace a view's text entirely and attempt to restore previous selection."""
        sel = self.view.sel()
        # Doesn't make sense to consider multiple selections
        selected_region = sel[0] if sel else None
        selected_text = self.view.substr(selected_region) if sel else None

        self.view.set_read_only(False)
        self.view.replace(edit, sublime.Region(0, self.view.size()), text)
        self.view.set_read_only(True)

        sel.clear()
        if selected_text and not clear_sel:
            new_selected_region = self.view.find(selected_text, 0, flags=sublime.LITERAL)
            if new_selected_region:
                sel.add(new_selected_region)
                return

        sel.add(0)
