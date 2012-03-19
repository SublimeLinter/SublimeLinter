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
						print 'SublimeLint daemon detected a reload'
				else:
					print 'SublimeLint: Unknown message sent to daemon:', item
			except:
				print 'Error in SublimeLint daemon:'
				print '-'*20
				print traceback.format_exc()
				print '-'*20

	def hit(self, view):
		self.q.put((view.id(), time.time()))

	def delay(self):
		self.q.put(0.01)

if not 'already' in globals():
	queue = Daemon()
	errors = {}
	already = True
