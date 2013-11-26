#
# watcher.py
# Part of SublimeLinter3, a code checking framework for Sublime Text 3
#
# Written by Aparajita Fishman
#
# Project: https://github.com/SublimeLinter/SublimeLinter3
# License: MIT
#

"""This module provides the PathWatcher class."""

import os
from threading import Lock, Thread
import time

from . import persist


class PathWatcher:

    """A class that monitors one or more paths in thread."""

    def __init__(self, interval=10.0):
        self.interval = max(interval, 1.0)  # Minimum interval is 1 second
        self.paths = []
        self.mtimes = []
        self.callbacks = []
        self.lock = Lock()
        self.running = False

    def watch(self, paths, callback):
        """
        Add one or more paths (or groups of paths) to be watched.

        paths is a single path or sequence of paths to watch. If a sequence
        is passed, the callback will be called if any of the paths in the
        sequence is modified.

        callback is a callable to be called when a path is modified. If a path
        is already being watched, the callback is added to the list of callbacks
        for that path.

        """

        if isinstance(paths, str):
            paths_to_watch = [paths]
        else:
            paths_to_watch = paths[:]

        for i, path in enumerate(paths_to_watch):
            path = paths_to_watch[i] = os.path.realpath(path)

            if os.path.exists(path):
                persist.printf('{}.watch: watching \'{}\''.format(self.__class__.__name__, path))
            else:
                persist.printf('{}.watch: invalid path: \'{}\''.format(self.__class__.__name__, path))
                return

        with self.lock:
            found = False

            for i, watched_paths in enumerate(self.paths):
                for path in paths_to_watch:
                    if path in watched_paths:
                        if callback not in self.callbacks[i]:
                            self.callbacks[i].append(callback)
                        else:
                            self.callbacks[i] = [callback]

                        found = True
                        break

                if found:
                    break

            if not found:
                self.paths.append(paths)
                self.mtimes.append([os.stat(path).st_mtime_ns for path in paths])
                self.callbacks.append([callback])

    def loop(self):
        """The main method of the thread. Continuously monitors the paths for changes."""

        while True:
            with self.lock:
                # Iterate in reverse so we can remove entries as we go
                for i in reversed(range(len(self.paths))):
                    modified = False
                    paths = self.paths[i]
                    mtimes = self.mtimes[i]

                    # Iterate in reverse so we can remove entries as we go
                    for ip in reversed(range(len(paths))):
                        path = paths[ip]

                        if not os.path.exists(path):
                            paths.pop(ip)
                            continue

                        mtime = os.stat(path).st_mtime_ns

                        if mtime > mtimes[ip]:
                            modified = True
                            mtimes[ip] = mtime
                            break

                    if modified:
                        for callback in self.callbacks[i]:
                            callback(paths=paths)

                    # If all of the paths in this entry are invalid, remove the entry
                    elif len(paths) == 0:
                        self.paths.pop(i)
                        self.mtimes.pop(i)
                        self.callbacks.pop(i)

            time.sleep(self.interval)

    def start(self):
        """Start the monitor thread."""
        if not self.running:
            Thread(name='watcher', target=self.loop).start()
