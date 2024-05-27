# Stubs for sublime_plugin (Python 3.5)
#
# NOTE: This dynamically typed stub was automatically generated by stubgen.

import sublime
from typing import Any, List, Dict, Optional, Tuple

WindowCommandR = Optional[Tuple[str, Optional[Dict[str, Any]]]]
Args = Optional[Dict[str, object]]

api_ready = ...  # type: bool
application_command_classes = ...  # type: Any
window_command_classes = ...  # type: Any
text_command_classes = ...  # type: Any
view_event_listener_classes = ...  # type: Any
view_event_listeners = ...  # type: Any
all_command_classes = ...  # type: Any
all_callbacks = ...  # type: Any
profile = ...  # type: Any
def unload_module(module): ...
def unload_plugin(modulename): ...
def reload_plugin(modulename): ...
def create_application_commands(): ...
def create_window_commands(window_id): ...
def create_text_commands(view_id): ...
def on_api_ready(): ...
def is_view_event_listener_applicable(cls, view): ...
def create_view_event_listeners(classes, view): ...
def check_view_event_listeners(view): ...
def attach_view(view): ...

check_all_view_event_listeners_scheduled = ...  # type: bool
def check_all_view_event_listeners(): ...
def detach_view(view): ...
def event_listeners_for_view(view): ...
def find_view_event_listener(view, cls): ...
def on_new(view_id): ...
def on_new_async(view_id): ...
def on_clone(view_id): ...
def on_clone_async(view_id): ...

class Summary:
    max = ...  # type: float
    sum = ...  # type: float
    count = ...  # type: int
    def __init__(self) -> None: ...
    def record(self, x): ...

def run_callback(event, callback, expr): ...
def run_view_listener_callback(view, name): ...
def run_async_view_listener_callback(view, name): ...
def on_load(view_id): ...
def on_load_async(view_id): ...
def on_pre_close(view_id): ...
def on_close(view_id): ...
def on_pre_save(view_id): ...
def on_pre_save_async(view_id): ...
def on_post_save(view_id): ...
def on_post_save_async(view_id): ...
def on_modified(view_id): ...
def on_modified_async(view_id): ...
def on_selection_modified(view_id): ...
def on_selection_modified_async(view_id): ...
def on_activated(view_id): ...
def on_activated_async(view_id): ...
def on_deactivated(view_id): ...
def on_deactivated_async(view_id): ...
def on_query_context(view_id, key, operator, operand, match_all): ...
def normalise_completion(c): ...
def on_query_completions(view_id, prefix, locations): ...
def on_hover(view_id, point, hover_zone): ...
def on_text_command(view_id, name, args): ...
def on_window_command(window_id, name: str, args: Dict[str, Any]) -> WindowCommandR: ...
def on_post_text_command(view_id, name, args): ...
def on_post_window_command(window_id, name, args): ...

class ListInputHandler:
    def list_items(self) -> Tuple[List[str], int] | List[str]: ...

class Command:
    def name(self): ...
    def is_enabled_(self, args: Args): ...
    def is_enabled(self) -> bool: ...
    def is_visible_(self, args: Args): ...
    def is_visible(self): ...
    def is_checked_(self, args: Args): ...
    def is_checked(self): ...
    def description_(self, args: Args): ...
    def description(self): ...
    def filter_args(self, args: Args) -> Args: ...
    def want_event(self): ...
    def run_(self, edit_token, args: Args): ...
    def run(self, *args, **kwargs) -> None: ...

class ApplicationCommand(Command): ...

class WindowCommand(Command):
    window = ...  # type: sublime.Window
    def __init__(self, window) -> None: ...

class TextCommand(Command):
    view = ...  # type: sublime.View
    def __init__(self, view) -> None: ...

class EventListener:
    def on_activated_async(self, view: sublime.View): ...
    def on_load_async(self, view: sublime.View): ...

class ViewEventListener:
    view = ...  # type: sublime.View
    @classmethod
    def is_applicable(cls, settings: sublime.Settings) -> bool: ...
    @classmethod
    def applies_to_primary_view_only(cls) -> bool: ...
    def __init__(self, view: sublime.View) -> None: ...

class MultizipImporter:
    loaders = ...  # type: Any
    file_loaders = ...  # type: Any
    def __init__(self) -> None: ...
    def find_module(self, fullname, path: Optional[Any] = ...): ...

class ZipLoader:
    zippath = ...  # type: Any
    name = ...  # type: Any
    def __init__(self, zippath) -> None: ...
    def has(self, fullname): ...
    def load_module(self, fullname): ...

override_path = ...  # type: Any
multi_importer = ...  # type: Any
def update_compressed_packages(pkgs): ...
def set_override_path(path): ...
