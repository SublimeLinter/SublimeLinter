from __future__ import annotations

import sublime

from typing import Callable, Hashable

Key = Hashable
storage: dict[Key, object] = {}


def debounce(callback: Callable[[], None], delay: float, key: Key) -> Callable[[], None]:
    global storage

    token = object()

    def setup():
        storage[key] = token

    def run():
        if storage.get(key) == token:
            callback()

    def clear():
        if storage.get(key) == token:
            storage.pop(key)

    sublime.set_timeout_async(setup)
    sublime.set_timeout_async(run, int(delay * 1000))
    return lambda: sublime.set_timeout_async(clear)


def cleanup(key: Key) -> None:
    try:
        storage.pop(key)
    except KeyError:
        pass


def unload():
    storage.clear()
