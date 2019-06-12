import threading


MYPY = False
if MYPY:
    from typing import Callable, Dict, Hashable

    Key = Hashable


# Map from key to threading.Timer objects
timers = {}  # type: Dict[Key, threading.Timer]


def debounce(callback, delay, key):
    # type: (Callable[[], None], float, Key) -> threading.Timer
    try:
        timers[key].cancel()
    except KeyError:
        pass

    timers[key] = timer = threading.Timer(delay, callback)
    timer.start()
    return timer


def cleanup(key):
    # type: (Key) -> None
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
