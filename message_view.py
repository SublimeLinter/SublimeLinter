import sublime

from .lint.const import ERROR_PANEL_NAME


def plugin_unloaded():
    for window in sublime.windows():
        window.destroy_output_panel(ERROR_PANEL_NAME)
