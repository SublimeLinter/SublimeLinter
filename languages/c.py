import os

from lint.linter import Linter
from lint.util import find

def find_includes(filename):
    includes = []
    if filename:
        parent = os.path.dirname(filename)
        includes.append('-I' + parent)
        inc = find(parent, 'include')
        if inc:
            includes.append('-I' + inc)

    return includes


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
        cmd += ('-',) + tuple(find_includes(self.filename))
        return super(C, self).communicate(cmd, code)

class CPP(C):
    language = 'c++'
    cmd = ('clang++', '-xc++', '-fsyntax-only', '-std=c++11', '-Werror',
        '-pedantic')
