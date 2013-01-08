import os

from lint.linter import Linter
from lint.util import find

class C(Linter):
    language = 'c'
    cmd = ('clang', '-xc', '-fsyntax-only', '-std=c99', '-Werror',
        '-pedantic')
    regex = (
        r'^<stdin>:(?P<line>\d+):(?P<col>\d+):'
        r'(?:(?P<ranges>[{}0-9:\-]+):)?\s+'
        r'(?P<error>.+)'
    )

    def communicate(self, cmd, code):
        includes = []
        if self.filename:
            parent = os.path.dirname(self.filename)
            includes.append('-I' + parent)
            inc = find(parent, 'include')
            if inc:
                includes.append('-I' + inc)

        cmd += ('-',) + tuple(includes)
        return super(C, self).communicate(cmd, code)
