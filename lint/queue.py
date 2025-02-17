from __future__ import annotations
import threading


from typing import Callable, Hashable

Key = Hashable


# Map from key to threading.Timer objects
timers: dict[Key, threading.Timer] = {}


def debounce(callback: Callable[[], None], delay: float, key: Key) -> threading.Timer:
    try:
        timers[key].cancel()
    except KeyError:
        pass

    timers[key] = timer = threading.Timer(delay, callback)
    timer.start()
    return timer


def cleanup(key: Key) -> None:
    try:
        timers.pop(key).cancel()
    except KeyError:
        pass


def unload():
    while True:
        try:
            _key, timer = timers.popitem()
        except KeyError:
            return
        else:
            timer.cancel()
