import os
from lint.linter import Linter

def find_files(root, ext):
	root = root.rstrip(os.sep) + os.sep
	ret = []
	for base, dirs, names in os.walk(root):
		for name in names:
			if name.endswith(ext):
				base = base.replace(root, '', 1)
				ret.append(os.path.join(base, name))
	return ret

class Golang(Linter):
	language = 'go'
	cmd = ('go', 'build', '-gcflags', '-eN')
	regex = r'.+?:(?P<line>\d+): (?P<error>.+)'

	def run(self, cmd, code):
		code = code.encode('utf8')
		if not self.filename:
			tools = self.popen(('go', 'tool')).communicate()[0].split('\n')
			for compiler in ('6g', '8g'):
				if compiler in tools:
					return self.tmpfile(('go', 'tool', compiler, '-e', '-o', os.devnull), code, suffix='.go')
		else:
			path = os.path.split(self.filename)[0]
			os.chdir(path)
			files = find_files(path, '.go')
			answer = self.tmpdir(cmd, files, code)
			return answer
