# sublimelint.py
# SublimeLint is a code linting support framework for Sublime Text 2
#
# Project: https://github.com/lunixbochs/sublimelint
# License: MIT

import sublime
import sublime_plugin

import os
import time
import thread

from lint.modules import Modules
from lint.linter import Linter
from lint.highlight import Highlight
import lint.persist as persist

cwd = os.getcwd()

class SublimeLint(sublime_plugin.EventListener):
	def __init__(self, *args, **kwargs):
		sublime_plugin.EventListener.__init__(self, *args, **kwargs)

		self.settings = sublime.load_settings('SublimeLint.sublime-settings')
		self.settings.add_on_change('lint-settings', self.update_settings)
		self.update_settings()

		self.loaded = set()
		self.linted = set()
		self.modules = Modules(cwd, 'languages').load_all()
		self.pending_on_change = set()
		persist.queue.start(self.lint)

		# this gives us a chance to lint the active view on fresh install
		sublime.set_timeout(
			lambda: self.on_activated(sublime.active_window().active_view()), 100
		)

		self.start = time.time()

	def update_settings(self):
		pass

	def lint(self, view_id):
		view = Linter.get_view(view_id)

		if view is not None:
			filename = view.file_name()
			persist.debug('SublimeLint: running on `%s`' % os.path.split(filename or 'untitled')[1])
			code = Linter.text(view)
			thread.start_new_thread(Linter.lint_view, (view_id, filename, code, self.finish))

	def finish(self, view, linters):
		errors = {}
		highlight = Highlight()
		linters[0].clear()

		for linter in linters:
			highlight.update(linter.highlight)
			errors.update(linter.errors)

		highlight.draw(view)
		persist.errors[view.id()] = errors

	# helpers

	def hit(self, view):
		self.linted.add(view.id())
		if view.size() == 0: return
		
		persist.queue.hit(view)

	# callins
	def on_modified(self, view):
		self.hit(view)
	
	def on_load(self, view):
		self.on_new(view)

	def on_activated(self, view):
		view_id = view.id()
		if not view_id in self.linted:
			if not view_id in self.loaded:
				# it seems on_activated can be called before loaded on first start
				if time.time() - self.start < 5: return
				self.on_new(view)

			self.hit(view)

	def on_new(self, view):
		self.loaded.add(view.id())
		
		Linter.assign(view)
		settings = view.settings()
		syntax = settings.get('syntax')
		def on_change():
			# weird, the recursion bug seems to only be happening on one untitled view?
			if view.id() in self.pending_on_change:
				return

			try:
				self.pending_on_change.add(view.id())
				if settings.get('syntax') != syntax:
					Linter.assign(view)

			finally:
				self.pending_on_change.remove(view.id())

		settings.clear_on_change('lint-syntax')
		settings.add_on_change('lint-syntax', on_change)

	def on_post_save(self, view):
		# this will reload submodules if they are saved with sublime text
		for name, module in self.modules.modules.items():
			if os.name == 'posix' and (
				os.stat(module.__file__).st_ino == os.stat(view.file_name()).st_ino
			) or module.__file__ == view.file_name():
				self.modules.reload(module)
				Linter.reload(name)
				break

		# linting here doesn't matter, because we lint on load and on modify
		# self.hit(view)
	
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
