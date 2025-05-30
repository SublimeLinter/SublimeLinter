from typing import (
    Any, Callable, Protocol, Union,
    Literal, overload, TYPE_CHECKING
)
from typing_extensions import TypedDict, Unpack

if TYPE_CHECKING:
    from .persist import LintError
    from .settings import Settings


LINT_START: Literal['lint_start']
LINT_RESULT: Literal['lint_result']
LINT_END: Literal['lint_end']
FILE_RENAMED: Literal['file_renamed']
PLUGIN_LOADED: Literal['plugin_loaded']
ERROR_POSITIONS_CHANGED: Literal['error_positions_changed']
SETTINGS_CHANGED: Literal['settings_changed']
LINTER_ASSIGNED: Literal['linter_assigned']


class LintStartPayload(TypedDict):
    filename: str
    linter_name: str

class LintResultPayload(TypedDict):
    filename: str
    linter_name: str
    errors: list[LintError]

class LintEndPayload(TypedDict):
    filename: str
    linter_name: str

class FileRenamedPayload(TypedDict):
    new_filename: str
    old_filename: str

class PluginLoadedPayload(TypedDict, total=False):
    ...

class ErrorPositionsChangedPayload(TypedDict):
    filename: str

class SettingsChangedPayload(TypedDict):
    settings: Settings

class LinterAssignedPayload(TypedDict):
    filename: str
    linter_names: set[str]


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

class ErrorPositionsChangedHandler(Protocol):
    def __call__(self, **kwargs: Unpack[ErrorPositionsChangedPayload]) -> None: ...

class SettingsChangedHandler(Protocol):
    def __call__(self, **kwargs: Unpack[SettingsChangedPayload]) -> None: ...

class LinterAssignedHandler(Protocol):
    def __call__(self, **kwargs: Unpack[LinterAssignedPayload]) -> None: ...


Handler = Callable[..., None]
AnyHandler = Union[
    LintStartHandler, LintResultHandler, LintEndHandler, FileRenamedHandler,
    PluginLoadedHandler, ErrorPositionsChangedHandler, SettingsChangedHandler,
    LinterAssignedHandler,
]

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
def subscribe(topic: Literal['error_positions_changed'], fn: ErrorPositionsChangedHandler) -> None: ...
@overload
def subscribe(topic: Literal['settings_changed'], fn: SettingsChangedHandler) -> None: ...
@overload
def subscribe(topic: Literal['linter_assigned'], fn: LinterAssignedHandler) -> None: ...
@overload
def subscribe(topic: str, fn: Handler) -> None: ...

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
def unsubscribe(topic: Literal['error_positions_changed'], fn: ErrorPositionsChangedHandler) -> None: ...
@overload
def unsubscribe(topic: Literal['settings_changed'], fn: SettingsChangedHandler) -> None: ...
@overload
def unsubscribe(topic: Literal['linter_assigned'], fn: LinterAssignedHandler) -> None: ...
@overload
def unsubscribe(topic: str, fn: Handler) -> None: ...
@overload
def unsubscribe(__fn: Handler) -> None: ...

@overload
def broadcast(topic: Literal['lint_start'], payload: LintStartPayload) -> None: ...
@overload
def broadcast(topic: Literal['lint_result'], payload: LintResultPayload) -> None: ...
@overload
def broadcast(topic: Literal['lint_end'], payload: LintEndPayload) -> None: ...
@overload
def broadcast(topic: Literal['file_renamed'], payload: FileRenamedPayload) -> None: ...
@overload
def broadcast(topic: Literal['plugin_loaded'], payload: PluginLoadedPayload = ...) -> None: ...
@overload
def broadcast(topic: Literal['error_positions_changed'], payload: ErrorPositionsChangedPayload) -> None: ...
@overload
def broadcast(topic: Literal['settings_changed'], payload: SettingsChangedPayload) -> None: ...
@overload
def broadcast(topic: Literal['linter_assigned'], payload: LinterAssignedPayload) -> None: ...
@overload
def broadcast(topic: str, payload: dict[str, Any]) -> None: ...

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
def on(topic: Literal['error_positions_changed']) -> Callable[[ErrorPositionsChangedHandler], ErrorPositionsChangedHandler]: ...
@overload
def on(topic: Literal['settings_changed']) -> Callable[[SettingsChangedHandler], SettingsChangedHandler]: ...
@overload
def on(topic: Literal['linter_assigned']) -> Callable[[LinterAssignedHandler], LinterAssignedHandler]: ...
@overload
def on(topic: str) -> Callable[[Handler], Handler]: ...

off: Callable[[Handler], None]
