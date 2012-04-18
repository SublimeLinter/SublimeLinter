import subprocess
import os
import shutil
import tempfile

import sublime
import re
import persist

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
	tab_size = 1

	languages = {}
	linters = {}
	scope = 'keyword'

	def __init__(self, view, syntax, filename=None):
		self.view = view
		self.syntax = syntax
		self.filename = filename

		if self.regex:
			self.regex = re.compile(self.regex)

		self.highlight = Highlight(scope=self.scope)

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
		try:
			vid = view.id()
		except RuntimeError:
			pass

		settings = view.settings()
		syn = settings.get('syntax')
		if not syn:
			cls.remove(vid)
			return

		match = syntax_re.search(syn)

		if match:
			syntax, = match.groups()
		else:
			syntax = syn

		if syntax:
			if vid in cls.linters and cls.linters[vid]:
				if tuple(cls.linters[vid])[0].syntax == syntax:
					return

			linters = set()
			for name, entry in cls.languages.items():
				if entry.can_lint(syntax):
					linter = entry(view, syntax, view.file_name())
					linters.add(linter)

			if linters:
				cls.linters[vid] = linters
				return linters

		cls.remove(vid)

	@classmethod
	def remove(cls, vid):
		if vid in cls.linters:
			for linter in cls.linters[vid]:
				linter.clear()

			del cls.linters[vid]

	@classmethod
	def reload(cls, mod):
		'''
		reload all linters originating from a specific module (follows a module reload)
		'''
		for id, linters in cls.linters.items():
			for linter in linters:
				if linter.__module__ == mod:
					linter.clear()
					cls.linters[id].remove(linter)
					linter = cls.languages[linter.name](linter.view, linter.syntax, linter.filename)
					cls.linters[id].add(linter)
					linter.draw()

		return

	@classmethod
	def text(cls, view):
		return view.substr(sublime.Region(0, view.size())).encode('utf-8')

	@classmethod
	def lint_view(cls, view_id, filename, code, callback):
		if view_id in cls.linters:
			linters = tuple(cls.linters[view_id])
			for linter in linters:
				linter.filename = filename
				linter.lint(code)

			# merge our result back to the main thread
			sublime.set_timeout(lambda: callback(linters[0].view, linters), 0)

	@classmethod
	def get_view(self, view_id):
		if view_id in self.linters:
			return tuple(self.linters[view_id])[0].view

	@classmethod
	def get_linters(self, view_id):
		if view_id in self.linters:
			return tuple(self.linters[view_id])

		return ()

	def lint(self, code=None):
		if not (self.language and self.cmd and self.regex):
			raise NotImplementedError

		if code is None:
			code = Linter.text(self.view)

		self.highlight = Highlight(code, scope=self.scope)
		self.errors = errors = {}

		if not code: return

		output = self.communicate(self.cmd, code)
		if output:
			persist.debug('Output:', repr(output))

			for line in output.splitlines():
				line = line.strip()

				match, row, col, message, near = self.match_error(self.regex, line)
				if match:
					if row or row is 0:
						if col or col is 0:
							# adjust column numbers to match the linter's tabs if necessary
							if self.tab_size > 1:
								start, end = self.highlight.full_line(row)
								code_line = code[start:end]
								diff = 0
								for i in xrange(len(code_line)):
									if code_line[i] == '\t':
										diff += (self.tab_size - 1)

									if col - diff <= i:
										col = i
										break

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
		if cls.language:
			if language == cls.language:
				return True
			elif language in cls.language:
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
			if col:
				col = int(col) - 1

			return match, row, col, error, near

		return match, None, None, '', None

	# popen methods
	def communicate(self, cmd, code):
		out = self.popen(cmd)
		if out is not None:
			out = out.communicate(code)
			return (out[0] or '') + (out[1] or '')
		else:
			return ''

	def create_environment(self):
		env = os.environ
		if os.name == 'posix':
			# find PATH using shell --login
			if 'SHELL' in env and env['SHELL'] in ('/bin/bash', ):
				shell = (env['SHELL'], '--login', '-c', 'echo _SUBL_ $PATH')
				path = self.popen(shell, env).communicate()[0]
				env['PATH'] = path.split('_SUBL_ ', 1)[1].split('\n', 1)[0]
			# guess PATH
			else:
				for path in (
					'/usr/bin', '/usr/local/bin',
					'/usr/local/php/bin', '/usr/local/php5/bin'
							):
					if not path in env['PATH']:
						env['PATH'] += (':' + path)

		return env

	def tmpfile(self, cmd, code, suffix=''):
		if isinstance(cmd, basestring):
			cmd = cmd,

		f = tempfile.NamedTemporaryFile(suffix=suffix)
		f.write(code)
		f.flush()

		cmd = tuple(cmd) + (f.name,)
		out = self.popen(cmd)
		if out:
			out = out.communicate('')
			return (out[0] or '') + (out[1] or '')
		else:
			return ''

	def tmpdir(self, cmd, files, code):
		filename = os.path.split(self.filename)[1]
		d = tempfile.mkdtemp()

		for f in files:
			try: os.makedirs(os.path.split(f)[0])
			except: pass

			target = os.path.join(d, f)
			if os.path.split(target)[1] == filename:
				# source file hasn't been saved since change, so update it from our live buffer
				f = open(target, 'wb')
				f.write(code)
				f.close()
			else:
				shutil.copyfile(f, target)

		os.chdir(d)
		out = self.popen(cmd).communicate()
		out = (out[0] or '') + '\n' + (out[1] or '')

		shutil.rmtree(d, True)

		# filter results from build to just this filename
		# no guarantee all languages are as nice about this as Go
		# may need to improve later or just defer to communicate()
		return '\n'.join([
			line for line in out.split('\n') if filename in line.split(':', 1)[0]
		])

	def popen(self, cmd, env=None):
		if isinstance(cmd, basestring):
			cmd = cmd,

		info = None
		if os.name == 'nt':
			info = subprocess.STARTUPINFO()
			info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
			info.wShowWindow = subprocess.SW_HIDE

		if env is None:
			env = self.create_environment()

		try:
			return subprocess.Popen(cmd, stdin=subprocess.PIPE,
				stdout=subprocess.PIPE, stderr=subprocess.PIPE,
				startupinfo=info, env=env)
		except OSError, err:
			persist.debug('SublimeLint: Error launching', repr(cmd))
			persist.debug('Error was:', err.strerror)
