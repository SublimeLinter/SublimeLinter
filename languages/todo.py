from lint.linter import Linter

class TODO(Linter):
	scope = 'string'
	selector = 'comment'
	outline = False

	@classmethod
	def can_lint(cls, language):
		return True

	def lint(self, code):
		lines = code.split('\n')
		for i in xrange(len(lines)):
			if 'TODO' in lines[i]:
				todo = lines[i].index('TODO')
				self.highlight.range(i, todo, 4)
				self.error(i,
					lines[i].split('TODO', 1)[1].lstrip(': ') or 'TODO'
				)

# TODO

# TODO
