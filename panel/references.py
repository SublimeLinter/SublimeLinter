import os
import sublime
import sublime_plugin

from .core.panels import create_output_panel
from .core.settings import PLUGIN_NAME
from .core.clients import client_for_view
from .core.documents import is_at_word, get_position, get_document_position
from .core.configurations import is_supported_view
from .core.workspace import get_project_path
from .core.protocol import Request, Point
from .core.url import uri_to_filename


def ensure_references_panel(window: sublime.Window):
    return window.find_output_panel("references") or create_references_panel(window)


def create_references_panel(window: sublime.Window):
    panel = create_output_panel(window, "references")
    panel.settings().set("result_file_regex",
                         r"^\s+\S\s+(\S.+)\s+(\d+):?(\d+)$")
    panel.assign_syntax("Packages/" + PLUGIN_NAME +
                        "/Syntaxes/References.sublime-syntax")
    # Call create_output_panel a second time after assigning the above
    # settings, so that it'll be picked up as a result buffer
    # see: Packages/Default/exec.py#L228-L230
    panel = window.create_output_panel("references")
    return panel


class LspSymbolReferencesCommand(sublime_plugin.TextCommand):
    def is_enabled(self, event=None):
        if is_supported_view(self.view):
            client = client_for_view(self.view)
            if client and client.has_capability('referencesProvider'):
                return is_at_word(self.view, event)
        return False

    def run(self, edit, event=None):
        client = client_for_view(self.view)
        if client:
            pos = get_position(self.view, event)
            document_position = get_document_position(self.view, pos)
            if document_position:
                document_position['context'] = {
                    "includeDeclaration": False
                }
                request = Request.references(document_position)
                client.send_request(
                    request, lambda response: self.handle_response(response, pos))

    def handle_response(self, response, pos):
        window = self.view.window()
        word = self.view.substr(self.view.word(pos))
        base_dir = get_project_path(window)
        file_path = self.view.file_name()
        relative_file_path = os.path.relpath(file_path, base_dir) if base_dir else file_path

        references = list(format_reference(item, base_dir) for item in response)

        if (len(references)) > 0:
            panel = ensure_references_panel(window)
            panel.settings().set("result_base_dir", base_dir)
            panel.set_read_only(False)
            panel.run_command("lsp_clear_panel")
            panel.run_command('append', {
                'characters': 'References to "' + word + '" at ' + relative_file_path + ':\n'
            })
            window.run_command("show_panel", {"panel": "output.references"})
            for reference in references:
                panel.run_command('append', {
                    'characters': reference + "\n",
                    'force': True,
                    'scroll_to_end': True
                })
            panel.set_read_only(True)

        else:
            window.run_command("hide_panel", {"panel": "output.references"})
            window.status_message("No references found")

    def want_event(self):
        return True


def format_reference(reference, base_dir):
    start = Point.from_lsp(reference.get('range').get('start'))
    file_path = uri_to_filename(reference.get("uri"))
    relative_file_path = os.path.relpath(file_path, base_dir)
    return " ◌ {} {}:{}".format(relative_file_path, start.row + 1, start.col + 1)
