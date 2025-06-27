from __future__ import annotations
from collections import defaultdict
import traceback

from typing import Callable, TypeVar

# Note the fancy types in `events.pyi`!
LINT_START = 'lint_start'
LINT_RESULT = 'lint_result'
LINT_END = 'lint_end'
FILE_RENAMED = 'file_renamed'
PLUGIN_LOADED = 'plugin_loaded'
ERROR_POSITIONS_CHANGED = 'error_positions_changed'
SETTINGS_CHANGED = 'settings_changed'
LINTER_ASSIGNED = 'linter_assigned'
LINTER_UNASSIGNED = 'linter_unassigned'
LINTER_FAILED = 'linter_failed'


Handler = Callable[..., None]
F = TypeVar('F', bound=Handler)
map_fn_to_topic: dict[Handler, str] = {}
listeners: dict[str, set[Handler]] = defaultdict(set)


def subscribe(topic: str, fn: Handler) -> None:
    listeners[topic].add(fn)


def unsubscribe(topic_or_fn: str | Handler, fn: Handler | None = None) -> None:
    if isinstance(topic_or_fn, str):
        topic = topic_or_fn
        if not fn:
            raise ValueError("second argument must be given")
    else:
        fn = topic_or_fn
        try:
            topic = map_fn_to_topic.pop(fn)
        except KeyError:
            return

    try:
        listeners[topic].remove(fn)
    except KeyError:
        pass


def broadcast(topic: str, payload: dict = {}):
    for fn in listeners.get(topic, []).copy():
        try:
            fn(**payload)
        except Exception:
            traceback.print_exc()


def on(topic: str) -> Callable[[F], F]:
    def inner(fn):
        subscribe(topic, fn)
        map_fn_to_topic[fn] = topic
        return fn
    return inner


off = unsubscribe
