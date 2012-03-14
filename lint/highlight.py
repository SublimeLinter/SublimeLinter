import sublime
import re

class Highlight:
	def __init__(self, code='',
			draw_type=sublime.DRAW_EMPTY_AS_OVERWRITE|sublime.DRAW_OUTLINED):

		self.code = code
		self.draw_type = draw_type
		self.underlines = []
		self.lines = set()

		# find all the newlines, so we can look for line positions
		# without merging back into the main thread for APIs
		self.newlines = newlines = [0]
		last = -1
		while True:
			last = code.find('\n', last+1)
			if last == -1: break
			newlines.append(last+1)

		newlines.append(len(code))

	def full_line(self, line):
		a, b = self.newlines[line:line+2]
		return a, b

	def range(self, line, pos, length=1):
		a, b = self.full_line(line)
		pos += a

		for i in xrange(length):
			self.underlines.append(sublime.Region(pos + i))

	def regex(self, line, regex, word_match=None, line_match=None):
		self.lines.add(line)
		offset = 0

		a, b = self.full_line(line)
		lineText = self.code[a:b]
		if line_match:
			match = re.match(line_match, lineText)
			if match:
				lineText = match.group('match')
				offset = match.start('match')
			else:
				return

		iters = re.finditer(regex, lineText)
		results = [(result.start('underline'), result.end('underline')) 
					for result in iters if
					not word_match or
					result.group('underline') == word_match]

		for start, end in results:
			self.range(line, start+offset, end-start)

	def near(self, line, near):
		self.lines.add(line)
		a, b = self.full_line(line)
		text = self.code[a:b]

		start = text.find(near)
		if start != -1:
			self.range(line, start, len(near))

	def update(self, other):
		self.lines.update(other.lines)
		self.underlines.extend(other.underlines)

	def draw(self, view, prefix='lint'):
		if self.underlines:
			view.add_regions('%s-underline' % prefix, self.underlines, 'keyword', self.draw_type)
		
		if self.lines:
			outlines = [view.full_line(view.text_point(line, 0)) for line in self.lines]
			view.add_regions('%s-outline' % prefix, outlines, 'keyword', self.draw_type)

	def clear(self, view, prefix='lint'):
		view.erase_regions('%s-underline' % prefix)
		view.erase_regions('%s-outline' % prefix)

	def line(self, line):
		self.lines.add(line)
