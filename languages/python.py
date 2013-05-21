import sublime
import sys

from lint.linter import Linter
from lint.util import which

class Python(Linter):
    language = 'python'
    cmd = 'pyflakes'
    regex = r'^.+:(?P<line>\d+):\s*(?P<error>.+)'

    def run(self, cmd, code):
        python3 = False
        if (self.filename or '').startswith(sublime.packages_path()):
            if sys.version_info >= (3, 0) and which('python3'):
                python3 = True

        if python3:
            # python 3
            pyflakes = which('pyflakes')
            cmd = ('python3', pyflakes)
            return self.communicate(cmd, code)
        else:
            return self.communicate(cmd, code)
