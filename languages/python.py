# python.py - Lint checking for Python
# input: a filename and the contents of a Python source file
# output: a list of line numbers to outline, offsets to highlight, and error messages
#
# todo:
# * fix regex for variable names inside strings (quotes)
#

from _pyflakes import check, messages, OffsetError, PythonError
from linter import Linter
from highlight import Highlight

class Python(Linter):
	language = 'python'

	def lint(self, code=None):
		self.highlight = Highlight(code)
		self.errors = {}

		if code is None:
			code = Linter.text(self.view)

		if code:
			self.check(code)

	def check(self, code, filename='untitled'):
		stripped_lines = []
		good_lines = []
		lines = code.split('\n')
		for i in xrange(len(lines)):
			line = lines[i]
			if not line.strip() or line.strip().startswith('#'):
				stripped_lines.append(i)
			else:
				good_lines.append(line)
			
		text = '\n'.join(good_lines)
		errors = check(text, filename)

		def underlineWord(lineno, word):
			regex = r'((and|or|not|if|elif|while|in)\s+|[+\-*^%%<>=\(\{])*\s*(?P<underline>[\w\.]*%s[\w]*)' % (word)
			self.highlight.regex(lineno, regex, word)
		
		def underlineImport(lineno, word):
			linematch = '(from\s+[\w_\.]+\s+)?import\s+(?P<match>[^#;]+)'
			regex = '(^|\s+|,\s*|as\s+)(?P<underline>[\w]*%s[\w]*)' % word
			self.highlight.regex(lineno, regex, word, linematch)
		
		def underlineForVar(lineno, word):
			regex = 'for\s+(?P<underline>[\w]*%s[\w*])' % word
			self.highlight.regex(lineno, regex, word)
		
		def underlineDuplicateArgument(lineno, word):
			regex = 'def [\w_]+\(.*?(?P<underline>[\w]*%s[\w]*)' % word
			self.highlight.regex(lineno, regex, word)

		for error in errors:
			error.lineno -= 1
			for i in stripped_lines:
				if error.lineno >= i:
					error.lineno += 1
			
			self.error(error.lineno, error)
			if isinstance(error, OffsetError):
				self.highlight.range(error.lineno, error.offset)

			elif isinstance(error, PythonError):
				pass

			elif isinstance(error, messages.UnusedImport):
				underlineImport(error.lineno, error.name)
			
			elif isinstance(error, messages.RedefinedWhileUnused):
				underlineWord(error.lineno, error.name)

			elif isinstance(error, messages.ImportShadowedByLoopVar):
				underlineForVar(error.lineno, error.name)

			elif isinstance(error, messages.ImportStarUsed):
				underlineImport(error.lineno, '\*')

			elif isinstance(error, messages.UndefinedName):
				underlineWord(error.lineno, error.name)

			elif isinstance(error, messages.UndefinedExport):
				underlineWord(error.lineno, error.name)

			elif isinstance(error, messages.UndefinedLocal):
				underlineWord(error.lineno, error.name)

			elif isinstance(error, messages.DuplicateArgument):
				underlineDuplicateArgument(error.lineno, error.name)

			elif isinstance(error, messages.RedefinedFunction):
				underlineWord(error.lineno, error.name)

			elif isinstance(error, messages.LateFutureImport):
				pass

			elif isinstance(error, messages.UnusedVariable):
				underlineWord(error.lineno, error.name)

			else:
				print 'SublimeLint (Python): Oops, we missed an error type!'
