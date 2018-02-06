import sublime
import sublime_plugin

PANEL_NAME = "SublimeLinter Messages"


class SublimeLinterDisplayPanelCommand(sublime_plugin.TextCommand):
    def run(self, edit, msg=""):
        panel_view = sublime.active_window().create_output_panel(PANEL_NAME, True)
        panel_view.set_read_only(False)
        panel_view.erase(edit, sublime.Region(0, panel_view.size()))
        panel_view.insert(edit, 0, msg)
        panel_view.set_read_only(True)
        panel_view.show(0)
        sublime.active_window().run_command("show_panel", {"panel": "output.{}".format(PANEL_NAME)})
