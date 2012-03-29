import thread
import traceback
import time
import sublime

from Queue import Queue, Empty

class Daemon:
	running = False
	callback = None
	q = Queue()
	views = {}
	last_run = {}

	def __init__(self):
		self.settings = sublime.load_settings('SublimeLint.sublime-settings')
		self.settings.add_on_change('lint-persist-settings', self.update_settings)
		self.update_settings()

	def update_settings(self):
		self.debug = self.settings.get('debug', False)

	def start(self, callback):
		self.callback = callback

		if self.running:
			self.q.put('reload')
			return
		else:
			self.running = True
			thread.start_new_thread(self.loop, ())

	def reenter(self, view_id):
		sublime.set_timeout(lambda: self.callback(view_id), 0)

	def loop(self):
		while True:
			try:
				try:
					item = self.q.get(True, 0.5)
				except Empty:
					for view_id, ts in self.views.items():
						if ts < time.time() - 0.5:
							self.last_run[view_id] = time.time()
							del self.views[view_id]
							self.reenter(view_id)
					
					continue

				if isinstance(item, tuple):
					view_id, ts = item
					if view_id in self.last_run and ts < self.last_run[view_id]:
						continue

					self.views[view_id] = ts

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
		if not self.debug: return

		for arg in args:
			print arg,
		print

if not 'already' in globals():
	queue = Daemon()
	debug = queue.printf
	
	errors = {}
	already = True
