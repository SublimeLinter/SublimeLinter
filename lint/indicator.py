import sublime
from itertools import cycle

from .const import STATUS_KEY


class LintIndicator:
    busy = False
    initial_delay = 1000
    cycle_time = 700
    timeout = 20000
    run_time = 0
    phases = cycle(['.', ' '])
    view = None

    def __init__(self, view):
        self.spinner_generator = self.spinning_cursor(self.phases)
        self.view = view

    @staticmethod
    def spinning_cursor(phases):
        for cursor in phases:
            yield "W: {} E: {}".format(cursor, cursor)

    def spinner_task(self):
        if self.busy:
            if self.run_time < self.timeout:
                self.run_time += self.cycle_time
                self.view.set_status(STATUS_KEY, next(self.spinner_generator))
                sublime.set_timeout_async(self.spinner_task, self.cycle_time)
            else:
                self.cleanup()

    def cleanup(self):
        self.view.erase_status(STATUS_KEY)

    def start(self):
        """Initial delay to prevent flickering for short lint times."""
        self.run_time = 0
        self.busy = True
        sublime.set_timeout_async(self.spinner_task, self.initial_delay)

    def stop(self):
        self.busy = False
        self.cleanup()
