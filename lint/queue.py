import threading


# Map from view_id to threading.Timer objects
timers = {}


def debounce(callback, delay, key):
    try:
        timers[key].cancel()
    except KeyError:
        pass

    timers[key] = timer = threading.Timer(delay, callback)
    timer.start()
    return timer


def cleanup(vid):
    try:
        timers.pop(vid).cancel()
    except KeyError:
        pass


def unload():
    while True:
        try:
            _vid, timer = timers.popitem()
        except KeyError:
            return
        else:
            timer.cancel()
