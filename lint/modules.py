# modules.py
# Part of SublimeLinter, a code checking framework for Sublime Text 3
#
# Project: https://github.com/SublimeLinter/sublimelinter
# License: MIT

import importlib.abc
import sys


class LintModule(importlib.abc.SourceLoader):
    '''
    This class inserts the lint package into the module
    search path, so that external linters can import it.
    '''
    @classmethod
    def find_module(cls, fullname, path=None):
        if fullname == 'lint':
            return LintModule

    @classmethod
    def load_module(cls, *args, **kwargs):
        from .. import lint
        sys.modules['lint'] = lint
        return lint

if not LintModule in sys.meta_path:
    sys.meta_path.append(LintModule)
