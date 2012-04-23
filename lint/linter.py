import sublime
import re
import persist
import util

from Queue import Queue

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
	
	scope = 'keyword'
	selector = None
	outline = True
	needs_api = False

	languages = {}
	linters = {}
	errors = None
	highlight = None

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
	def lint_view(cls, view_id, filename, code, sections, callback):
		if view_id in cls.linters:
			selectors = Linter.get_selectors(view_id)

			linters = tuple(cls.linters[view_id])
			for linter in linters:
				if not linter.selector:
					linter.filename = filename
					linter.pre_lint(code)

			for sel, linter in selectors:
				if sel in sections:
					highlight = Highlight(code, scope=linter.scope, outline=linter.outline)
					errors = {}

					for line_offset, left, right in sections[sel]:
						highlight.shift(line_offset, left)
						linter.pre_lint(code[left:right], highlight=highlight)

						for line, error in linter.errors.items():
							errors[line+line_offset] = error

					linter.errors = errors

			# merge our result back to the main thread
			sublime.set_timeout(lambda: callback(linters[0].view, linters), 0)

	@classmethod
	def get_view(cls, view_id):
		if view_id in cls.linters:
			return tuple(cls.linters[view_id])[0].view

	@classmethod
	def get_linters(cls, view_id):
		if view_id in cls.linters:
			return tuple(cls.linters[view_id])

		return ()

	@classmethod
	def get_selectors(cls, view_id):
		return [(linter.selector, linter) for linter in cls.get_linters(view_id) if linter.selector]

	def pre_lint(self, code, highlight=None):
		self.errors = {}
		self.highlight = highlight or Highlight(code, scope=self.scope, outline=self.outline)

		if not code: return
		
		# if this linter needs the api, we want to merge back into the main thread
		# but stall this thread until it's done so we still have the return
		if self.needs_api:
			q = Queue()
			def callback():
				q.get()
				self.lint(code)
				q.task_done()

			q.put(1)
			sublime.set_timeout(callback, 1)
			q.join()
		else:
			self.lint(code)

	def lint(self, code):
		if not (self.language and self.cmd and self.regex):
			raise NotImplementedError

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

					self.error(row, message)

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
			elif isinstance(cls.language, (tuple, list)) and language in cls.language:
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

	# popen wrappers
	def communicate(self, cmd, code):
		return util.communicate(cmd, code)

	def tmpfile(self, cmd, code, suffix=''):
		return util.tmpfile(cmd, code, suffix)

	def tmpdir(self, cmd, files, code):
		return util.tmpdir(cmd, files, self.filename, code)

	def popen(self, cmd, env=None):
		return util.popen(cmd, env)
