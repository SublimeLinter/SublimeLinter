import sublime
import sublime_plugin
from itertools import cycle

from .const import STATUS_KEY

class LintIndicator:
    busy = False
    delay = 700
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
            self.view.set_status(STATUS_KEY, next(self.spinner_generator))
            sublime.set_timeout_async(self.spinner_task, self.delay)

    def start(self):
        """Initial delay to prevent flickering for short lint times."""
        self.busy = True
        sublime.set_timeout_async(self.spinner_task, 1000)

    def stop(self):
        self.busy = False
        self.view.erase_status(STATUS_KEY)



