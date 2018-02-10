from . import persist

import threading


# Map from view_id to threading.Timer objects
timers = {}


def hit(view, callback):
    delay = get_delay()  # [seconds]
    debounce(callback, delay, key=view.id())


def debounce(callback, delay, key=None):
    key = key or callback
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


def get_delay():
    """Return the delay between a lint request and when it will be processed.

    If the lint mode is not background, there is no delay. Otherwise, if
    a "delay" setting is not available in any of the settings, MIN_DELAY is used.
    """
    if persist.settings.get('lint_mode') != 'background':
        return 0

    return persist.settings.get('delay')
