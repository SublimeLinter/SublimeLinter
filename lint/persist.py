import threading
import traceback
import time
import sublime

from queue import Queue, Empty

class Daemon:
	running = False
	callback = None
	q = Queue()
	last_run = {}

	def __init__(self):
		print('init persist!')
		self.settings = {}
		self.sub_settings = sublime.load_settings('SublimeLint.sublime-settings')
		self.sub_settings.add_on_change('lint-persist-settings', self.update_settings)

	def update_settings(self):
		settings = self.sub_settings.get('default') or {}
		user = self.sub_settings.get('user') or {}
		if user:
			settings.update(user)

		self.settings.clear()
		self.settings.update(settings)

		# reattach settings objects to linters
		import sys
		linter = sys.modules.get('lint.linter')
		if linter and hasattr(linter, 'persist'):
			linter.Linter.reload()

	def start(self, callback):
		self.callback = callback

		if self.running:
			self.q.put('reload')
			return
		else:
			self.running = True
			threading.Thread(target=self.loop).start()

	def reenter(self, view_id):
		self.callback(view_id)

	def loop(self):
		views = {}

		while True:
			try:
				try:
					item = self.q.get(True, 0.5)
				except Empty:
					for view_id, ts in views.copy().items():
						if ts < time.time() - 0.5:
							self.last_run[view_id] = time.time()
							del views[view_id]
							self.reenter(view_id)
					
					continue

				if isinstance(item, tuple):
					view_id, ts = item
					if view_id in self.last_run and ts < self.last_run[view_id]:
						continue

					views[view_id] = ts

				elif isinstance(item, (int, float)):
					time.sleep(item)

				elif isinstance(item, basestring):
					if item == 'reload':
						self.printf('SublimeLint daemon detected a reload')
				else:
					self.printf('SublimeLint: Unknown message sent to daemon:', item)
			except:
				self.printf('Error in SublimeLint daemon:')
				self.printf('-'*20)
				self.printf(traceback.format_exc())
				self.printf('-'*20)

	def hit(self, view):
		self.q.put((view.id(), time.time()))

	def delay(self):
		self.q.put(0.01)

	def printf(self, *args):
		if not self.settings.get('debug'): return

		for arg in args:
			print(arg, end=' ')
		print()

if not 'already' in globals():
	queue = Daemon()
	debug = queue.printf
	settings = queue.settings
	queue.update_settings()

	errors = {}
	languages = {}
	linters = {}
	already = True

def add_language(sub, name, attrs):
	if name:
		plugins = settings.get('plugins', {})
		sub.lint_settings = plugins.get(name, {})
		sub.name = name
		languages[name] = sub
