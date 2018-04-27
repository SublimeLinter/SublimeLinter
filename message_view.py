import sublime
import sublime_plugin

PANEL_NAME = "SublimeLinter Messages"
OUTPUT_PANEL = "output." + PANEL_NAME


def plugin_unloaded():
    for window in sublime.windows():
        window.destroy_output_panel(PANEL_NAME)


class SublimeLinterDisplayPanelCommand(sublime_plugin.WindowCommand):
    def run(self, msg=""):
        window = self.window

        if is_panel_active(window):
            panel_view = window.find_output_panel(PANEL_NAME)
        else:
            panel_view = window.create_output_panel(PANEL_NAME)

        scroll_to = panel_view.size()
        msg = msg.rstrip() + '\n\n\n'

        panel_view.set_read_only(False)
        panel_view.run_command('append', {'characters': msg})
        panel_view.set_read_only(True)
        panel_view.show(scroll_to)
        window.run_command("show_panel", {"panel": OUTPUT_PANEL})


class SublimeLinterRemovePanelCommand(sublime_plugin.WindowCommand):
    def run(self):
        self.window.destroy_output_panel(PANEL_NAME)


def is_panel_active(window):
    return window.active_panel() == OUTPUT_PANEL
