import subprocess
import os
import tempfile

import sublime
import re

from highlight import Highlight

syntax_re = re.compile(r'/([^/]+)\.tmLanguage$')

class Tracker(type):
	def __init__(cls, name, bases, attrs):
		if bases:
			bases[-1].add_subclass(cls, name, attrs)

class Linter:
	__metaclass__ = Tracker
	language = ''
	cmd = ()
	regex = ''

	languages = {}
	linters = {}

	def __init__(self, view, syntax, filename='untitled'):
		self.view = view
		self.syntax = syntax
		self.filename = filename
		if self.regex:
			self.regex = re.compile(self.regex)

	@classmethod
	def add_subclass(cls, sub, name, attrs):
		if name:
			sub.name = name
			cls.languages[name] = sub

	@classmethod
	def assign(cls, view):
		'''
		find a linter for a specified view if possible, then add it to our mapping of view <--> lint class and return it
		each view has its own linter to make it feasible for linters to store persistent data about a view
		'''
		id = view.id()

		settings = view.settings()
		syn = settings.get('syntax')
		if not syn: return
		
		match = syntax_re.search(syn)

		if match:
			syntax, = match.groups()
		else:
			syntax = syn

		if syntax:
			if id in cls.linters and cls.linters[id]:
				if tuple(cls.linters[id])[0].syntax == syntax:
					return

			linters = set()
			for entry in cls.languages.values():
				if entry.can_lint(syntax):
					linter = entry(view, syntax)
					linters.add(linter)

			if linters:
				cls.linters[id] = linters
			else:
				if id in cls.linters:
					del cls.linters[id]
					
			return linters

	@classmethod
	def reload(cls, mod):
		'''
		reload all linters originating from a specific module (follows a module reload)
		'''
		for id, linters in cls.linters.items():
			for linter in linters:
				if linter.__module__ == mod:
					cls.linters[id].remove(linter)
					linter = cls.languages[linter.name](linter.view, linter.syntax)
					cls.linters[id].add(linter)

		return

	@classmethod
	def text(cls, view):
		return view.substr(sublime.Region(0, view.size())).encode('utf-8')

	@classmethod
	def lint_view(cls, view_id, code, callback):
		if view_id in cls.linters:
			linters = tuple(cls.linters[view_id])
			for linter in linters:
				linter.lint(code)

			# merge our result back to the main thread
			sublime.set_timeout(lambda: callback(linters[0].view, linters), 0)

	@classmethod
	def get_view(self, view_id):
		if view_id in self.linters:
			return tuple(self.linters[view_id])[0].view


	def lint(self, code=None):
		if not (self.language and self.cmd and self.regex):
			raise NotImplementedError

		if code is None:
			code = Linter.text(self.view)

		self.highlight = Highlight(code)
		self.errors = errors = {}

		if not code: return

		output = self.communicate(self.cmd, code)
		print repr(output)

		for line in output.splitlines():
			line = line.strip()

			match, row, col, message, near = self.match_error(self.regex, line)
			if match:
				if row or row is 0:
					if col or col is 0:
						self.highlight.range(row, col)
					elif near:
						self.highlight.near(row, near)
					else:
						self.highlight.line(row)

				if row in errors:
					errors[row].append(message)
				else:
					errors[row] = [message]

	def draw(self, prefix='lint'):
		self.highlight.draw(self.view, prefix)

	def clear(self, prefix='lint'):
		self.highlight.clear(self.view, prefix)

	# helper methods

	@classmethod
	def can_lint(cls, language):
		language = language.lower()
		if isinstance(cls.language, basestring) and language == cls.language:
			return True
		elif isinstance(cls.language, (list, tuple, set)) and language in cls.language:
			return True
		else:
			return False

	def error(self, line, error):
		self.highlight.line(line)
		
		error = str(error)
		if line in self.errors:
			self.errors[line].append(error)
		else:
			self.errors[line] = [error]

	def match_error(self, r, line):
		match = r.match(line)

		if match:
			items = {'row':None, 'col':None, 'error':'', 'near':None}
			items.update(match.groupdict())
			error, row, col, near = [items[k] for k in ('error', 'line', 'col', 'near')]

			row = int(row) - 1
			return match, row, col, error, near

		return match, None, None, '', None

	# popen methods

	def communicate(self, cmd, code):
		out = self.popen(cmd).communicate(code)
		return (out[0] or '') + (out[1] or '')

	def tmpfile(self, cmd, code, suffix=''):
		f = tempfile.NamedTemporaryFile(suffix=suffix)
		f.write(code)
		f.flush()

		cmd = tuple(cmd) + (f.name,)
		out = self.popen(cmd).communicate('')
		return (out[0] or '') + (out[1] or '')

	def popen(self, cmd):
		if isinstance(cmd, basestring):
			cmd = cmd,

		info = None
		if os.name == 'nt':
			info = subprocess.STARTUPINFO()
			info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
			info.wShowWindow = subprocess.SW_HIDE

		env = os.environ
		if os.name == 'posix':
			for path in (
				'/usr/bin', '/usr/local/bin',
				'/usr/local/php/bin', '/usr/local/php5/bin'
						):
				if not path in env['PATH']:
					env['PATH'] += (':' + path)

		return subprocess.Popen(cmd, stdin=subprocess.PIPE,
			stdout=subprocess.PIPE, stderr=subprocess.PIPE,
			startupinfo=info, env=env)
