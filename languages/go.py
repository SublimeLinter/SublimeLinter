import os
import shlex
from lint.linter import Linter

class Golang(Linter):
	language = 'go'
	cmd = ('go', 'build', '-gcflags', '-e -o ' + os.devnull)
	# can't use this calling method because compiler name changes
	# cmd = ('go', 'tool', '6g', '-e', '-o', os.devnull)
	regex = r'.+?:(?P<line>\d+): (?P<error>.+)'

	def communicate(self, cmd, code):
		posix = (os.name == 'posix')
		if not self.filename:
			tools = self.popen(('go', 'tool')).communicate()[0].split('\n')
			for compiler in ('6g', '8g'):
				if compiler in tools:
					return self.tmpfile(('go', 'tool', compiler, '-e', '-o', os.devnull), code, suffix='.go')

		else:
			path = os.path.split(self.filename)[0]
			cwd = os.getcwd()
			os.chdir(path)
			out = self.popen(('go', 'build', '-n')).communicate()
			# might have an error determining packages, return if so
			if out[1].strip(): return out[1]

			cmds = out[0]
			for line in cmds.split('\n'):
				if line:
					compiler = os.path.splitext(
						os.path.split(
							shlex.split(line, posix=posix)[0]
						)[1]
					)[0]

					if compiler in ('6g', '8g'):
						break
			else:
				return

			args = shlex.split(line, posix=posix)
			files = [arg for arg in args if arg.startswith(('./', '.\\'))]

			answer = self.tmpdir(cmd, files, code)

			os.chdir(cwd)
			return answer
