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
from lint.highlight import HighlightSet
import lint.persist as persist

default_user_settings = '''{
	"debug": false
}
'''
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
		self.last_syntax = {}
		persist.queue.start(self.lint)

		# this gives us a chance to lint the active view on fresh install
		window = sublime.active_window()
		if window:
			sublime.set_timeout(
				lambda: self.on_activated(window.active_view()), 100
			)

		self.start = time.time()

	def update_settings(self):
		pass

	def lint(self, view_id):
		view = Linter.get_view(view_id)

		sections = {}
		for sel, _ in Linter.get_selectors(view_id):
			sections[sel] = []
			for result in view.find_by_selector(sel):
				sections[sel].append(
					(view.rowcol(result.a)[0], result.a, result.b)
				)

		if view is not None:
			filename = view.file_name()
			persist.debug('SublimeLint: running on `%s`' % os.path.split(filename or 'untitled')[1])
			code = Linter.text(view)
			thread.start_new_thread(Linter.lint_view, (view_id, filename, code, sections, self.finish))

	def finish(self, view, linters):
		errors = {}
		highlights = HighlightSet()

		for linter in linters:
			if linter.highlight:
				highlights.add(linter.highlight)
				
			if linter.errors:
				errors.update(linter.errors)

		highlights.clear(view)
		highlights.draw(view)
		persist.errors[view.id()] = errors
		self.on_selection_modified(view)

	# helpers

	def hit(self, view):
		self.linted.add(view.id())
		if view.size() == 0:
			for l in Linter.get_linters(view.id()):
				l.clear()
			
			return
		
		persist.queue.hit(view)

	def check_syntax(self, view, lint=False):
		vid = view.id()
		syntax = view.settings().get('syntax')

		# syntax either has never been set or just changed
		if not vid in self.last_syntax or self.last_syntax[vid] != syntax:
			self.last_syntax[vid] = syntax

			# assign a linter, then maybe trigger a lint if we get one
			if Linter.assign(view) and lint:
				self.hit(view)

	# callins
	def on_modified(self, view):
		self.check_syntax(view)
		self.hit(view)
	
	def on_load(self, view):
		self.on_new(view)

	def on_activated(self, view):
		sublime.set_timeout(lambda: self.check_syntax(view, True), 50)
		
		view_id = view.id()
		if not view_id in self.linted:
			if not view_id in self.loaded:
				# it seems on_activated can be called before loaded on first start
				if time.time() - self.start < 5: return
				self.on_new(view)

			self.hit(view)

	def on_new(self, view):
		# handle new user preferences file
		if view.file_name() and os.path.split(view.file_name())[1] == 'SublimeLint.sublime-settings':
			if view.size() == 0:
				edit = view.begin_edit()
				view.insert(edit, 0, default_user_settings)
				view.end_edit(edit)

		vid = view.id()
		self.loaded.add(vid)
		self.last_syntax[vid] = view.settings().get('syntax')
		Linter.assign(view)

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

		view.erase_status('sublimelint')
		if vid in persist.errors:
			errors = persist.errors[vid]
			if errors:
				plural = 's' if len(errors) > 1 else ''
				if lineno in errors:
					status = ''
					if plural:
						num = sorted(list(errors)).index(lineno) + 1
						status += '%i/%i errors: ' % (num, len(errors))

					# sublime statusbar can't hold unicode
					status += '; '.join(errors[lineno]).encode('ascii', 'replace')
				else:
					status = '%i error%s' % (len(errors), plural)

				view.set_status('sublimelint', status)

		persist.queue.delay()
