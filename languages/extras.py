# extras.py - sublimelint plugin for simple external linters

from lint.linter import Linter

class Coffee(Linter):
	language = 'coffeescript'
	cmd = ('coffee', '--compile', '--stdio')
	regex = r'^[A-Za-z]+: (?P<error>.+) on line (?P<line>\d+)'

class Java(Linter):
	language = 'java'
	cmd = ('javac', '-Xlint')
	regex = r'^[^:]+:(?P<line>\d+): (?P<error>.*)$'

	def communicate(self, *args):
		return self.tmpfile(*args, suffix='.java')

	def popen(self, cmd, env=None):
		return super(Java, self).popen(cmd, env)

class JavaScript(Linter):
	language = 'javascript'
	cmd = ('jsl', '-stdin')
	regex = r'^\((?P<line>\d+)\):\s+(?P<error>.+)'

class Perl(Linter):
	language = 'perl'
	cmd = ('perl', '-c')
	regex = r'(?P<error>.+?) at .+? line (?P<line>\d+)(, near "(?P<near>.+?)")?'

class PHP(Linter):
	language = ('php', 'html')
	cmd = ('php', '-l', '-d display_errors=On')
	regex = r'^Parse error:\s*(?P<type>parse|syntax) error,?\s*(?P<error>.+?)?\s+in\s+.+?\s*line\s+(?P<line>\d+)'

	def match_error(self, r, line):
		match, row, col, error, near = super(PHP, self).match_error(r, line)

		if match and match.group('type') == 'parse' and not error:
			error = 'parse error'

		return match, row, col, error, near

class Ruby(Linter):
	language = 'ruby'
	cmd = ('ruby', '-wc')
	regex = r'^.+:(?P<line>\d+):\s+(?P<error>.+)'
