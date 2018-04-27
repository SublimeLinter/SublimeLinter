import sublime
import sublime_plugin

PANEL_NAME = "SublimeLinter Messages"
OUTPUT_PANEL = "output." + PANEL_NAME


def plugin_unloaded():
    for window in sublime.windows():
        window.destroy_output_panel(PANEL_NAME)


class SublimeLinterDisplayPanelCommand(sublime_plugin.WindowCommand):
    def run(self, msg=""):
        panel_view = self.window.create_output_panel(PANEL_NAME, True)
        panel_view.set_read_only(False)
        panel_view.run_command('append', {'characters': msg})
        panel_view.set_read_only(True)
        panel_view.show(0)
        self.window.run_command("show_panel", {"panel": OUTPUT_PANEL})


class SublimeLinterRemovePanelCommand(sublime_plugin.WindowCommand):
    def run(self):
        self.window.destroy_output_panel(PANEL_NAME)
