import sublime
import sublime_plugin

PANEL_NAME = "SublimeLinter Messages"
OUTPUT_PANEL = "output." + PANEL_NAME
OUTPUT_PANEL_SETTINGS = {
    "auto_indent": False,
    "draw_indent_guides": False,
    "draw_white_space": "None",
    "gutter": False,
    "is_widget": True,
    "line_numbers": False,
    "rulers": False,
    "scroll_past_end": False,
    "spell_check": False,
    "translate_tabs_to_spaces": False,
    "word_wrap": False
}


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
            settings = panel_view.settings()
            for key, value in OUTPUT_PANEL_SETTINGS.items():
                settings.set(key, value)

            syntax_path = "Packages/SublimeLinter/panel/message_view.sublime-syntax"
            try:  # Try the resource first, in case we're in the middle of an upgrade
                sublime.load_resource(syntax_path)
            except Exception:
                return

            panel_view.assign_syntax(syntax_path)

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
