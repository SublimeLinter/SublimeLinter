from lint.linter import Linter

class TODO(Linter):
	scope = 'string'
	outline = False
	needs_api = True

	@classmethod
	def can_lint(cls, language):
		return True

	def lint(self, code=None):
		view = self.view
		for comment in view.find_by_selector('comment'):
			todo = view.substr(comment)
			if 'TODO' in todo:
				todo = todo.index('TODO')
			else:
				continue

			if todo > -1:
				line = view.rowcol(comment.a)[0]
				self.highlight.range(line, todo, 4)
				self.error(line,
					view.substr(comment).split('TODO', 1)[1].lstrip(': ')
				)
