import sublime

from . import persist

import time


# Map from view_id to timestamp of last 'hit' (e.g. an edit)
last_seen = {}


# For compatibility this is a class with unchanged API from SL3.
class Daemon:
    def start(self, callback):
        self._callback = callback

    def hit(self, view):
        assert self._callback, "Queue: Can't hit before start."

        vid = view.id()
        delay = get_delay()  # [seconds]
        return queue_lint(vid, delay, self._callback)


def queue_lint(vid, delay, callback):
    hit_time = time.monotonic()

    def worker():
        last_hit = last_seen[vid]
        del last_seen[vid]

        # If we have a newer hit than this one, we debounce
        if last_hit > hit_time:
            queue_lint(vid, last_hit - hit_time, callback)
            return

        callback(vid, hit_time)

    # We cannot fire rapidly `set_timeout_async` or Sublime will miss some
    # events eventually. So we use a membership test `vid in last_seen` to tell
    # if we already queued an async worker or not.
    if vid not in last_seen:
        sublime.set_timeout_async(worker, delay * 1000)

    # We store the last hit_time in any case. This will invalidate the worker
    # if we have an old one running. The worker needs to debounce and schedule
    # a new task with a fixed delay accordingly.
    last_seen[vid] = hit_time
    return hit_time


MIN_DELAY = 0.1


def get_delay():
    """Return the delay between a lint request and when it will be processed.

    If the lint mode is not background, there is no delay. Otherwise, if
    a "delay" setting is not available in any of the settings, MIN_DELAY is used.
    """
    if persist.settings.get('lint_mode') != 'background':
        return 0

    return persist.settings.get('delay', MIN_DELAY)


queue = Daemon()
