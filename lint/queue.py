from . import persist

from collections import defaultdict
import time
import threading


# Map from view_id to threading.Timer objects
timers = {}
running = defaultdict(threading.Lock)


# For compatibility this is a class with unchanged API from SL3.
class Daemon:
    def hit(self, view, callback):
        vid = view.id()
        delay = get_delay()  # [seconds]
        return _queue_lint(vid, delay, callback)

    def cleanup(self, vid):
        _cleanup(vid)


def _queue_lint(vid, delay, callback):  # <-serial execution
    hit_time = time.monotonic()

    def worker():                      # <-concurrent execution
        with running[vid]:  # <- If worker runs long enough
                            #    multiple tasks can wait here!
            callback(vid, hit_time)

    try:
        timers[vid].cancel()
    except KeyError:
        pass

    timers[vid] = timer = threading.Timer(delay, worker)
    timer.start()

    return hit_time


def _cleanup(vid):
    try:
        timers.pop(vid).cancel()
    except KeyError:
        pass

    running.pop(vid, None)


def get_delay():
    """Return the delay between a lint request and when it will be processed.

    If the lint mode is not background, there is no delay. Otherwise, if
    a "delay" setting is not available in any of the settings, MIN_DELAY is used.
    """
    if persist.settings.get('lint_mode') != 'background':
        return 0

    return persist.settings.get('delay')


queue = Daemon()
