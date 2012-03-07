# sublimelint.py
# SublimeLint is a code linting support framework for Sublime Text 2
#
# Project: https://github.com/lunixbochs/sublimelint
# License: MIT

import sublime_plugin
import os

import thread

from modules import Modules
from linter import Linter
import persist

cwd = os.getcwd()

class SublimeLint(sublime_plugin.EventListener):
	def __init__(self, *args, **kwargs):
		sublime_plugin.EventListener.__init__(self, *args, **kwargs)

		self.loaded = set()
		self.modules = Modules(cwd, 'languages').load_all()
		persist.queue.start(self.lint)

	def lint(self, view_id):
		view = Linter.get_view(view_id)

		if view is not None:
			print 'SublimeLint: running on `%s`' % os.path.split(view.file_name() or 'untitled')[1]
			code = Linter.text(view)
			thread.start_new_thread(Linter.lint_view, (view_id, code, self.finish))

	def finish(self, view, linters):
		errors = {}

		linters[0].clear()
		for linter in linters:
			linter.draw()
			errors.update(linter.errors)

		persist.errors[view.id()] = errors

	# helpers

	def hit(self, view):
		persist.queue.hit(view)

	# callins
	def on_modified(self, view):
		self.hit(view)
	
	def on_load(self, view):
		self.loaded.add(view.id())
		self.on_new(view)

	def on_activated(self, view):
		if view.id() in self.loaded:
			self.loaded.remove(view.id())
			self.hit(view)

	def on_new(self, view):
		Linter.assign(view)
		settings = view.settings()
		syntax = settings.get('syntax')
		def on_change():
			if settings.get('syntax') != syntax:
				Linter.assign(view)

		settings.add_on_change('lint-syntax', on_change)

	def on_post_save(self, view):
		# this will reload submodules if they are saved with sublime text
		for name, module in self.modules.modules.items():
			if module.__file__ == view.file_name():
				self.modules.reload(module)
				Linter.reload(name)
				break

		self.hit(view)
	
	def on_selection_modified(self, view):
		vid = view.id()
		lineno = view.rowcol(view.sel()[0].end())[0]
		if vid in persist.errors and lineno in persist.errors[vid]:
			try: # workaround for issue #18
				view.set_status('sublimelint', '; '.join(persist.errors[vid][lineno]))
			except:
				view.erase_status('sublimelint')
		else:
			view.erase_status('sublimelint')

		persist.queue.delay()
