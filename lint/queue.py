import threading


# Map from key to threading.Timer objects
timers = {}


def debounce(callback, delay, key):
    try:
        timers[key].cancel()
    except KeyError:
        pass

    timers[key] = timer = threading.Timer(delay, callback)
    timer.start()
    return timer


def cleanup(key):
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
