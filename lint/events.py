from __future__ import annotations
from collections import defaultdict
from typing import (
    Any, Callable, Dict, Set, Protocol, Union,
    Literal, overload, TypeVar, TYPE_CHECKING
)
from typing_extensions import TypedDict, Unpack
import traceback

if TYPE_CHECKING:
    from .persist import LintError
    from .settings import Settings


LINT_START: Literal['lint_start'] = 'lint_start'
LINT_RESULT: Literal['lint_result'] = 'lint_result'
LINT_END: Literal['lint_end'] = 'lint_end'
FILE_RENAMED: Literal['file_renamed'] = 'file_renamed'
PLUGIN_LOADED: Literal['plugin_loaded'] = 'plugin_loaded'
ERROR_POSITIONS_UPDATED: Literal['error_positions_updated'] = 'error_positions_updated'
SETTINGS_CHANGED: Literal['settings_changed'] = 'settings_changed'


class LintStartPayload(TypedDict):
    buffer_id: int


class LintResultPayload(TypedDict):
    filename: str
    linter_name: str
    errors: list[LintError]


class LintEndPayload(TypedDict):
    buffer_id: int


class FileRenamedPayload(TypedDict):
    new_filename: str
    old_filename: str


class PluginLoadedPayload(TypedDict, total=False):
    pass


class UpdatedErrorPositionsPayload(TypedDict):
    filename: str


class SettingsChangedPayload(TypedDict):
    settings: Settings


class LintStartHandler(Protocol):
    def __call__(self, **kwargs: Unpack[LintStartPayload]) -> None: ...
class LintResultHandler(Protocol):
    def __call__(self, **kwargs: Unpack[LintResultPayload]) -> None: ...
class LintEndHandler(Protocol):
    def __call__(self, **kwargs: Unpack[LintEndPayload]) -> None: ...
class FileRenamedHandler(Protocol):
    def __call__(self, **kwargs: Unpack[FileRenamedPayload]) -> None: ...
class PluginLoadedHandler(Protocol):
    def __call__(self, **kwargs: Unpack[PluginLoadedPayload]) -> None: ...
class ErrorPositionsUpdatedHandler(Protocol):
    def __call__(self, **kwargs: Unpack[UpdatedErrorPositionsPayload]) -> None: ...
class SettingsChangedHandler(Protocol):
    def __call__(self, **kwargs: Unpack[SettingsChangedPayload]) -> None: ...


F = TypeVar('F', bound=Callable)
Handler = Callable[..., None]
AnyHandler = Union[
    LintStartHandler, LintResultHandler, LintEndHandler, FileRenamedHandler,
    PluginLoadedHandler, ErrorPositionsUpdatedHandler, SettingsChangedHandler
]
map_fn_to_topic: Dict[Handler, str] = {}
listeners: Dict[str, Set[Handler]] = defaultdict(set)


@overload
def subscribe(topic: Literal['lint_start'], fn: LintStartHandler) -> None: ...
@overload
def subscribe(topic: Literal['lint_result'], fn: LintResultHandler) -> None: ...
@overload
def subscribe(topic: Literal['lint_end'], fn: LintEndHandler) -> None: ...
@overload
def subscribe(topic: Literal['file_renamed'], fn: FileRenamedHandler) -> None: ...
@overload
def subscribe(topic: Literal['plugin_loaded'], fn: PluginLoadedHandler) -> None: ...
@overload
def subscribe(topic: Literal['error_positions_updated'], fn: ErrorPositionsUpdatedHandler) -> None: ...
@overload
def subscribe(topic: Literal['settings_changed'], fn: SettingsChangedHandler) -> None: ...
@overload
def subscribe(topic: str, fn: Handler) -> None: ...
def subscribe(topic: str, fn: Callable[..., None]) -> None:
    listeners[topic].add(fn)


@overload
def unsubscribe(topic: Literal['lint_start'], fn: LintStartHandler) -> None: ...
@overload
def unsubscribe(topic: Literal['lint_result'], fn: LintResultHandler) -> None: ...
@overload
def unsubscribe(topic: Literal['lint_end'], fn: LintEndHandler) -> None: ...
@overload
def unsubscribe(topic: Literal['file_renamed'], fn: FileRenamedHandler) -> None: ...
@overload
def unsubscribe(topic: Literal['plugin_loaded'], fn: PluginLoadedHandler) -> None: ...
@overload
def unsubscribe(topic: Literal['error_positions_updated'], fn: ErrorPositionsUpdatedHandler) -> None: ...
@overload
def unsubscribe(topic: Literal['settings_changed'], fn: SettingsChangedHandler) -> None: ...
@overload
def unsubscribe(__fn: AnyHandler) -> None: ...
@overload
def unsubscribe(topic, fn=None) -> None: ...
def unsubscribe(topic, fn=None) -> None:
    if not isinstance(topic, str):
        fn = topic
        topic = map_fn_to_topic.pop(fn, None)
        if topic is None:
            return

    try:
        listeners[topic].remove(fn)
    except KeyError:
        pass


@overload
def broadcast(topic: Literal['lint_start'], payload: LintStartPayload) -> None: ...
@overload
def broadcast(topic: Literal['lint_result'], payload: LintResultPayload) -> None: ...
@overload
def broadcast(topic: Literal['lint_end'], payload: LintEndPayload) -> None: ...
@overload
def broadcast(topic: Literal['file_renamed'], payload: FileRenamedPayload) -> None: ...
@overload
def broadcast(topic: Literal['plugin_loaded'], payload: PluginLoadedPayload = {}) -> None: ...
@overload
def broadcast(topic: Literal['error_positions_updated'], payload: UpdatedErrorPositionsPayload) -> None: ...
@overload
def broadcast(topic: Literal['settings_changed'], payload: SettingsChangedPayload) -> None: ...
@overload
def broadcast(topic: str, payload: Dict[str, Any]) -> None: ...
def broadcast(topic: str, payload={}) -> None:
    for fn in listeners.get(topic, []).copy():
        try:
            fn(**payload)
        except Exception:
            traceback.print_exc()


@overload
def on(topic: Literal['lint_start']) -> Callable[[LintStartHandler], LintStartHandler]: ...
@overload
def on(topic: Literal['lint_result']) -> Callable[[LintResultHandler], LintResultHandler]: ...
@overload
def on(topic: Literal['lint_end']) -> Callable[[LintEndHandler], LintEndHandler]: ...
@overload
def on(topic: Literal['file_renamed']) -> Callable[[FileRenamedHandler], FileRenamedHandler]: ...
@overload
def on(topic: Literal['plugin_loaded']) -> Callable[[PluginLoadedHandler], PluginLoadedHandler]: ...
@overload
def on(topic: Literal['error_positions_updated']) -> Callable[[ErrorPositionsUpdatedHandler], ErrorPositionsUpdatedHandler]: ...
@overload
def on(topic: Literal['settings_changed']) -> Callable[[SettingsChangedHandler], SettingsChangedHandler]: ...
@overload
def on(topic: str) -> Callable[[Handler], Handler]: ...
def on(topic) -> Callable[[F], F]:
    def inner(fn: F) -> F:
        subscribe(topic, fn)
        map_fn_to_topic[fn] = topic
        return fn
    return inner


off = unsubscribe
