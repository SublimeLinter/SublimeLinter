"""This module provides a threaded queue for lint requests."""

from queue import Queue, Empty
import threading
import traceback
import time

from . import persist, util


class Daemon:
    """
    This class provides a threaded queue that dispatches lints.

    The following operations can be added to the queue:

    hit - Queue a lint for a given view
    delay - Queue a delay for a number of milliseconds
    reload - Indicates the main plugin was reloaded

    """

    MIN_DELAY = 0.1
    running = False
    callback = None
    q = Queue()
    last_runs = {}

    def start(self, callback):
        """Start the daemon thread that runs loop."""
        self.callback = callback

        if self.running:
            self.q.put('reload')
        else:
            self.running = True
            threading.Thread(target=self.loop).start()

    def loop(self):
        """Continually check the queue for new items and process them."""

        last_runs = {}

        while True:
            try:
                try:
                    item = self.q.get(block=True, timeout=self.MIN_DELAY)
                except Empty:
                    pass  # no immediate task to handle
                else:
                    if isinstance(item, tuple):
                        view_id, timestamp, delay = item
                        if view_id in self.last_runs and timestamp < self.last_runs[view_id]:
                            continue
                        last_runs[view_id] = timestamp, delay

                    elif isinstance(item, (int, float)):
                        time.sleep(item)

                    elif isinstance(item, str) and item == 'reload':
                        util.printf('daemon detected a reload')
                        self.last_runs.clear()
                        last_runs.clear()
                    else:
                        util.printf('unknown message sent to daemon:', item)
                    continue

                for view_id, (timestamp, delay) in last_runs.copy().items():
                    # Lint the view if we have gone past the time
                    # at which the lint wants to run.
                    if time.monotonic() > timestamp + delay:
                        self.last_runs[view_id] = time.monotonic()
                        del last_runs[view_id]
                        self.lint(view_id, timestamp)

            except Exception:
                util.printf('error in SublimeLinter daemon:')
                util.printf('-' * 20)
                util.printf(traceback.format_exc())
                util.printf('-' * 20)

    def hit(self, view):
        """Add a lint request to the queue, return the time at which the request was enqueued."""
        timestamp = time.monotonic()
        self.q.put((view.id(), timestamp, self.get_delay(view)))
        return timestamp

    def delay(self, milliseconds=100):
        """Add a millisecond delay to the queue."""
        self.q.put(milliseconds / 1000.0)

    def lint(self, view_id, timestamp):
        """
        Call back into the main plugin to lint the given view.

        timestamp is used to determine if the view has been modified
        since the lint was requested.

        """
        self.callback(view_id, timestamp)

    def get_delay(self, view):
        """
        Return the delay between a lint request and when it will be processed.

        If the lint mode is not background, there is no delay. Otherwise, if
        a "delay" setting is not available in any of the settings, MIN_DELAY is used.

        """

        if persist.settings.get('lint_mode') != 'background':
            return 0

        delay = persist.settings.get('delay', self.MIN_DELAY)

        return delay


queue = Daemon()
