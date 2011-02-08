import sublime, sublime_plugin
import os

# todo:
# * fix lag
# * glob modules subfolder for languages and dynamically load - remove the current ugly hardcodedness

import sublimelint.modules.python as python

drawType = 4 | 32

languages = [python]

global lineMessages
lineMessages = {}

def run(module, view):
	global lineMessages
	vid = view.id()

	text = view.substr(sublime.Region(0, view.size()))
	
	if view.file_name():
		filename = os.path.split(view.file_name())[-1]
	else:
		filename = 'untitled'
	
	underline, lines, errorMessages, clearOutlines = module.run(text, view, filename)
	lineMessages[vid] = errorMessages

	view.erase_regions('lint-syntax')
	view.erase_regions('lint-syntax-underline')
	view.erase_regions('lint-underline')

	if clearOutlines:
		view.erase_regions('lint-outlines')
	
	if underline:
		view.add_regions('lint-underline', underline, 'keyword', drawType)#sublime.DRAW_EMPTY_AS_OVERWRITE | sublime.DRAW_OUTLINED)
		
	if lines:
		outlines = [view.full_line(view.text_point(lineno, 0)) for lineno in lines]
		view.add_regions('lint-outlines', outlines, 'keyword', drawType)#sublime.DRAW_EMPTY_AS_OVERWRITE | sublime.DRAW_OUTLINED)
	

def validate(view):
	for module in languages:
		if module.language in view.settings().get("syntax"):
			run(module, view)
			break

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

	for module in languages:
		if module.language in view.settings().get("syntax"):
			break
	else:
		view.erase_regions('lint-syntax')
		view.erase_regions('lint-syntax-underline')
		view.erase_regions('lint-underline')
		view.erase_regions('lint-outlines')
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
