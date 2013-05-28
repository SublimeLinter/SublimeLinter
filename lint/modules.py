# modules.py - loads and reloads plugin scripts from a folder

import glob
import importlib
import importlib.abc
from importlib.machinery import SourceFileLoader
import os
import sys
import traceback

from . import persist

class LintModule(importlib.abc.PyLoader):
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

class Modules:
    def __init__(self, path):
        self.path = path
        self.modules = {}

    def items(self):
        return self.modules.items()

    def load(self, name):
        meta_name = 'linters.{}'.format(name)
        path = os.path.join(self.path, name)
        loader = SourceFileLoader(meta_name, path + '.py')
        persist.debug('loading `{}`'.format(meta_name))
        mod = None
        try:
            mod = loader.load_module(meta_name)
        except:
            persist.debug('error importing `{}`'.format(meta_name))
            persist.debug('-'*20)
            persist.debug(traceback.format_exc())
            persist.debug('-'*20)

        if mod is None:
            return

        self.modules[name] = mod

        # update module's __file__ with the absolute path so we know to reload it if Sublime Text saves that path
        mod.__file__ = os.path.abspath(mod.__file__).rstrip('co') # strip .pyc/.pyo to just .py
        return mod

    def reload(self, mod):
        name = mod.__name__
        if name.startswith('linters.'):
            name = name.split('.', 1)[1]
        if name in self.modules:
            return self.load(name)

    def load_all(self):
        for mod in glob.glob('{}/*.py'.format(self.path)):
            base, name = os.path.split(mod)
            name = name.split('.', 1)[0]
            if name.startswith('_'):
                continue

            self.load(name)

        return self
