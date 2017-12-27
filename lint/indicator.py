import sublime
from itertools import cycle

from .const import STATUS_KEY


class LintIndicator:
    _view_dict = {}
    initial_delay = 700
    cycle_time = 400
    timeout = 20000

    def __init__(self, view):
        """Conditional Borg pattern. Ensures same state for all
        instances associated with a view."""
        vid = view.id()
        if vid in self._view_dict:
            self.__dict__ = self._view_dict[vid]
        else:
            self._view_dict[vid] = self.__dict__
            self.view = view
            self.reset_internals()

    def reset_internals(self):
        self.busy = False  # stop has not been called
        self.run_time = 0
        self.dirty = False  # status bar has been touched

    @staticmethod
    def spinning_cursor():
        phases = cycle(['.', ' '])
        for cursor in phases:
            yield "W: {} E: {}".format(cursor, cursor)

    def spinner_task(self):
        if self.busy:
            self.dirty = True
            if self.run_time < self.timeout:
                self.run_time += self.cycle_time
                self.view.set_status(STATUS_KEY, next(self.spinning_cursor()))
                sublime.set_timeout_async(self.spinner_task, self.cycle_time)
            else:
                self.cleanup()

    def cleanup(self):
        self.reset_internals()
        if self.dirty:
            self.view.erase_status(STATUS_KEY)

    def start(self):
        """Initial delay to prevent flickering for short lint times."""
        if not self.busy:
            self.busy = True
            sublime.set_timeout_async(self.spinner_task, self.initial_delay)

    def stop(self):
        self.busy = False
        self.cleanup()
