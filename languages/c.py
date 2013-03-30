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
    cmd = ('clang',)
    args = ('-xc', '-fsyntax-only', '-std=c99', '-Werror', '-pedantic')
    regex = (
        r'^<stdin>:(?P<line>\d+):(?P<col>\d+):'
        r'(?:(?P<ranges>[{}0-9:\-]+):)?\s+'
        r'(?P<error>.+)'
    )
    defaults = {
        'cmd': cmd,
        'args': args,
        'include': [],
    }

    def communicate(self, cmd, code):
        cmd = tuple(self.settings.get('cmd'),) or self.cmd
        cmd += tuple(self.settings.get('args', []))
        for include in self.settings.get('include', []):
            cmd += ('-I{}'.format(include),)
        cmd += ('-',) + tuple(find_includes(self.filename))
        return super().communicate(cmd, code)

class CPP(C):
    language = 'c++'
    cmd = ('clang++',)
    args = ('-xc++', '-fsyntax-only', '-std=c++11', '-Werror', '-pedantic')
    defaults = {
        'cmd': cmd,
        'args': args,
        'include': [],
    }
