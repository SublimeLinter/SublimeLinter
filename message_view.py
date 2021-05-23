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
            panel = window.find_output_panel(PANEL_NAME)
            assert panel
        else:
            panel = window.create_output_panel(PANEL_NAME)
            syntax_path = "Packages/SublimeLinter/panel/message_view.sublime-syntax"
            try:  # Try the resource first, in case we're in the middle of an upgrade
                sublime.load_resource(syntax_path)
            except Exception:
                return

            panel.assign_syntax(syntax_path)

        scroll_to = panel.size()
        msg = msg.rstrip() + '\n\n\n'

        panel.set_read_only(False)
        panel.run_command('append', {'characters': msg})
        panel.set_read_only(True)
        panel.show(scroll_to)
        window.run_command("show_panel", {"panel": OUTPUT_PANEL})


class SublimeLinterRemovePanelCommand(sublime_plugin.WindowCommand):
    def run(self):
        self.window.destroy_output_panel(PANEL_NAME)


def is_panel_active(window):
    return window.active_panel() == OUTPUT_PANEL
