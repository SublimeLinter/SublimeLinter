# modules.py - loads and reloads plugin scripts from a folder

import os
import sys
import glob

import traceback

class Modules:
	def __init__(self, cwd, path):
		self.base = cwd
		self.path = path
		self.abspath = os.path.abspath(path)
		self.modules = {}

	def load(self, name):
		print 'SublimeLint: loading `%s`' % name
		pushd = os.getcwd()
		os.chdir(self.base)
		path = list(sys.path)

		sys.path.insert(0, self.path)

		try:
			__import__(name)

			# first, we get the actual module from sys.modules, not the base mod returned by __import__
			# second, we get an updated version of the module with reload() so development is easier
			mod = sys.modules[name] = reload(sys.modules[name])
		except:
			print 'SublimeLint: Error importing `%s`' % name
			print '-'*20
			print traceback.format_exc()
			print '-'*20

		self.modules[name] = mod

		# update module's __file__ with the absolute path so we know to reload it if Sublime Text saves that path
		mod.__file__ = os.path.abspath(mod.__file__).rstrip('co') # strip .pyc/.pyo to just .py

		sys.path = path
		os.chdir(pushd)

		return mod

	def reload(self, mod):
		name = mod.__name__
		print 'SublimeLint: reloading `%s`' % name
		if name in self.modules:
			return self.load(name)

	def load_all(self):
		pushd = os.getcwd()
		os.chdir(self.base)
		for mod in glob.glob('%s/*.py' % self.path):
			base, name = os.path.split(mod)
			name = name.split('.', 1)[0]
			if name.startswith('_'):
				continue

			self.load(name)

		os.chdir(pushd)
		return self
