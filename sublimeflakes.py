import sublime, sublime_plugin
import os, sys, compiler, re
import traceback

from pyflakes import checker, messages

drawType = 4 | 32

class OffsetError(messages.Message):
	message = '%r at offset %r'
	def __init__(self, filename, lineno, text, offset):
		messages.Message.__init__(self, filename, lineno)
		self.offset = offset
		self.message_args = (text, offset)

class PythonError(messages.Message):
	message = '%r'
	def __init__(self, filename, lineno, text):
		messages.Message.__init__(self, filename, lineno)
		self.message_args = (text,)

def check(codeString, filename):
	codeString = codeString.rstrip()
	try:
		try:
			compile(codeString, filename, "exec")
		except MemoryError:
			# Python 2.4 will raise MemoryError if the source can't be
			# decoded.
			if sys.version_info[:2] == (2, 4):
				raise SyntaxError(None)
			raise
	except (SyntaxError, IndentationError), value:
		# print traceback.format_exc() # helps debug new cases
		msg = value.args[0]

		lineno, offset, text = value.lineno, value.offset, value.text

		# If there's an encoding problem with the file, the text is None.
		if text is None:
			# Avoid using msg, since for the only known case, it contains a
			# bogus message that claims the encoding the file declared was
			# unknown.
			if msg.startswith('duplicate argument'):
				arg = msg.split('duplicate argument ',1)[1].split(' ',1)[0].strip('\'"')
				error = messages.DuplicateArgument(filename, lineno, arg)
			else:
				error = PythonError(filename, lineno, msg)
		else:
			line = text.splitlines()[-1]

			if offset is not None:
				offset = offset - (len(text) - len(line))

			if offset is not None:
				error = OffsetError(filename, lineno, msg, offset)
			else:
				error = PythonError(filename, lineno, msg)

		return [error]
	else:
		# Okay, it's syntactically valid.  Now parse it into an ast and check
		# it.
		tree = compiler.parse(codeString)
		w = checker.Checker(tree, filename)
		w.messages.sort(lambda a, b: cmp(a.lineno, b.lineno))
		return w.messages

def printf(*args): print '"' + ' '.join(args) + '"'

global lineMessages
lineMessages = {}
def validate(view):
	global lineMessages
	vid = view.id()

	text = view.substr(sublime.Region(0, view.size()))

	stripped_lines = []
	good_lines = []
	lines = text.split('\n')
	for i in xrange(len(lines)):
		line = lines[i]
		if not line.strip() or line.strip().startswith('#'):
			stripped_lines.append(i)
		else:
			good_lines.append(line)
	
	text = '\n'.join(good_lines)
	if view.file_name(): filename = os.path.split(view.file_name())[-1]
	else: filename = 'untitled'

	errors = check(text, filename)

	lines = set()
	underline = []

	def underlineRange(lineno, position, length=1):
		line = view.full_line(view.text_point(lineno, 0))
		position += line.begin()

		for i in xrange(length):
			underline.append(sublime.Region(position + i))

	def underlineRegex(lineno, regex, wordmatch=None, linematch=None):
		lines.add(lineno)
		offset = 0

		line = view.full_line(view.text_point(lineno, 0))
		lineText = view.substr(line)
		if linematch:
			match = re.match(linematch, lineText)
			if match:
				lineText = match.group('match')
				offset = match.start('match')
			else:
				return

		iters = re.finditer(regex, lineText)
		results = [(result.start('underline'), result.end('underline')) for result in iters if
											not wordmatch or result.group('underline') == wordmatch]

		for start, end in results:
			underlineRange(lineno, start+offset, end-start)

	def underlineWord(lineno, word):
		regex = '((and|or|not|if|elif|while|in)\s+|[+\-*^%%<>=({[])*\s*(?P<underline>[\w]*%s[\w]*)' % (word)
		underlineRegex(lineno, regex, word)
	
	def underlineImport(lineno, word):
		linematch = 'import\s+(?P<match>[^#;]+)'
		regex = '(^|\s+|,\s*|as\s+)(?P<underline>[\w]*%s[\w]*)' % word
		underlineRegex(lineno, regex, word, linematch)
	
	def underlineForVar(lineno, word):
		regex = 'for\s+(?P<underline>[\w]*%s[\w*])' % word
		underlineRegex(lineno, regex, word)
	
	def underlineDuplicateArgument(lineno, word):
		regex = 'def [\w_]+\(.*?(?P<underline>[\w]*%s[\w]*)' % word
		underlineRegex(lineno, regex, word)
	
	errorMessages = {}
	def addMessage(lineno, message):
		message = str(message)
		if lineno in errorMessages:
			errorMessages[lineno].append(message)
		else:
			errorMessages[lineno] = [message]

	view.erase_regions('pyflakes-syntax')
	view.erase_regions('pyflakes-syntax-underline')
	view.erase_regions('pyflakes-underline')
	for error in errors:
		error.lineno -= 1
		for i in stripped_lines:
			if error.lineno >= i:
				error.lineno += 1
		
		lines.add(error.lineno)
		addMessage(error.lineno, error)
		if isinstance(error, OffsetError):
			underlineRange(error.lineno, error.offset)
			if len(errors) == 1 and False:
				outlines = [view.full_line(view.text_point(error.lineno, 0)) for lineno in lines]
				view.add_regions('pyflakes-syntax', outlines, 'keyword', drawType)#sublime.DRAW_EMPTY_AS_OVERWRITE | sublime.DRAW_OUTLINED)
				view.add_regions('pyflakes-syntax-underline', underline, 'keyword', drawType)#sublime.DRAW_EMPTY_AS_OVERWRITE | sublime.DRAW_OUTLINED)
				return

		elif isinstance(error, PythonError):
			if len(errors) == 1 and False:
				outlines = [view.full_line(view.text_point(error.lineno, 0)) for lineno in lines]
				view.add_regions('pyflakes-syntax', outlines, 'keyword', drawType)#sublime.DRAW_EMPTY_AS_OVERWRITE | sublime.DRAW_OUTLINED)
				return

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
			print 'Oops, we missed an error type!'

	view.erase_regions('pyflakes-outlines')
	if underline or lines:
		outlines = [view.full_line(view.text_point(lineno, 0)) for lineno in lines]

		view.add_regions('pyflakes-underline', underline, 'keyword', drawType)#sublime.DRAW_EMPTY_AS_OVERWRITE | sublime.DRAW_OUTLINED)
		view.add_regions('pyflakes-outlines', outlines, 'keyword', drawType)#sublime.DRAW_EMPTY_AS_OVERWRITE | sublime.DRAW_OUTLINED)

	lineMessages[vid] = errorMessages

import time, thread
global queue, lookup
queue = {}
lookup = {}

def validate_runner(): # this threaded runner keeps it from slowing down UI while you type
	global queue, lookup
	while True:
		time.sleep(0.5)
		for vid in dict(queue):
			if queue[vid] == 0:
				v = lookup[vid]
				def _view():
					try:
						validate(v)
					except RuntimeError, excp:
						print excp
				sublime.set_timeout(_view, 100)
				try: del queue[vid]
				except: pass
				try: del lookup[vid]
				except: pass
			else:
				queue[vid] = 0

def validate_hit(view):
	global lookup
	global queue

	if not 'Python' in view.settings().get("syntax"):
		view.erase_regions('pyflakes-syntax')
		view.erase_regions('pyflakes-syntax-underline')
		view.erase_regions('pyflakes-underline')
		view.erase_regions('pyflakes-outlines')
		return

	vid = view.id()
	lookup[vid] = view
	queue[vid] = 1

thread.start_new_thread(validate_runner, ())

class pyflakes(sublime_plugin.EventListener):
	def __init__(self, *args, **kwargs):
		sublime_plugin.EventListener.__init__(self, *args, **kwargs)
		self.lastCount = {}
	
	def on_modified(self, view):
		validate_hit(view)
		return

		# alternate method which works alright when we don't have threads/set_timeout
		# from when I ported to early X beta :P
		text = view.substr(sublime.Region(0, view.size()))
		count = text.count('\n')
		if count > 500: return
		bid = view.buffer_id()

		if bid in self.lastCount:
			if self.lastCount[bid] != count:
				validate(view)

		self.lastCount[bid] = count
	
	def on_load(self, view):
		validate_hit(view)
	
	def on_post_save(self, view):
		validate_hit(view)
	
	def on_selection_modified(self, view):
		vid = view.id()
		lineno = view.rowcol(view.sel()[0].end())[0]
		if vid in lineMessages and lineno in lineMessages[vid]:
			view.set_status('pyflakes', '; '.join(lineMessages[vid][lineno]))
		else:
			view.erase_status('pyflakes')