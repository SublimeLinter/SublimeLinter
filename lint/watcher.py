#
# watch.py
# Part of SublimeLinter3, a code checking framework for Sublime Text 3
#
# Written by Aparajita Fishman
#
# Project: https://github.com/SublimeLinter/SublimeLinter3
# License: MIT
#

import os
from threading import Lock, Thread
import time

from . import persist


class Watcher:
    '''Watches one or more directories for modifications and notifies when they occur.'''
    def __init__(self, interval=5.0):
        self.interval = max(interval, 1.0)  # Minimum interval is 1 second
        self.directories = []
        self.last_mtimes = []
        self.callbacks = []
        self.lock = Lock()
        self.running = False

    def add_directory(self, path, callback):
        if isinstance(path, str):
            paths = [path]
        else:
            paths = path

        for i, path in enumerate(paths):
            path = paths[i] = os.path.realpath(path)

            if not os.path.isdir(path):
                persist.printf('Watcher.watch() was given an invalid path:', path)
                return

        with self.lock:
            found = False

            for i, dirs in enumerate(self.directories):
                for path in paths:
                    if path in dirs:
                        if callback not in self.callbacks[i]:
                            self.callbacks[i].append(callback)
                        else:
                            self.callbacks[i] = [callback]

                        found = True
                        break

                if found:
                    break

            if not found:
                self.directories.append(paths)
                self.last_mtimes.append([os.stat(path).st_mtime_ns for path in paths])
                self.callbacks.append([callback])

    def watch(self):
        while True:
            with self.lock:
                # Iterate in reverse so we can remove entries as we go
                for i in reversed(range(len(self.directories))):
                    modified = False
                    dirs = self.directories[i]
                    mtimes = self.last_mtimes[i]

                    # Iterate in reverse so we can remove entries as we go
                    for di in reversed(range(len(dirs))):
                        d = dirs[di]

                        if not os.path.exists(d) or not os.path.isdir(d):
                            dirs.pop(di)
                            continue

                        mtime = os.stat(d).st_mtime_ns

                        if mtime > mtimes[di]:
                            modified = True
                            mtimes[di] = mtime
                            break

                    if modified:
                        for callback in self.callbacks[i]:
                            if len(dirs) == 1:
                                arg = dirs[0]
                            else:
                                arg = dirs

                            callback(directory=arg)

                    # If all of the directories in this entry are invalid, remove the entry
                    elif len(dirs) == 0:
                        self.directories.pop(i)
                        self.last_mtimes.pop(i)
                        self.callbacks.pop(i)

            time.sleep(self.interval)

    def start(self):
        if not self.running:
            Thread(name='watcher', target=self.watch).start()
