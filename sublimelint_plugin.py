import sublime, sublime_plugin
import os, sys, glob

## todo:
# * fix lag (was partially caused by multiple worker threads - evaluate if it's still an issue)

## language module loading

# mapping of language name to language module
languages = {}

# import config
basepath = 'sublimelint/modules'
modpath = basepath.replace('/', '.')
ignore = '__init__',
basedir = os.getcwd()

def load_module(name):
	fullmod = '%s.%s' % (modpath, name)

	# make sure the path didn't change on us (this is needed for submodule reload)
	pushd = os.getcwd()
	os.chdir(basedir)

	__import__(fullmod)

	# this following line does two things:
	# first, we get the actual module from sys.modules, not the base mod returned by __import__
	# second, we get an updated version with reload() so module development is easier
	# (save sublimelint_plugin.py to make sublime text reload language submodules)
	mod = sys.modules[fullmod] = reload(sys.modules[fullmod])

	# update module's __file__ to absolute path so we can reload it if saved with sublime text
	mod.__file__ = os.path.abspath(mod.__file__).rstrip('co')

	try:
		language = mod.language
		languages[language] = mod
	except AttributeError:
		print 'SublimeLint: Error loading %s - no language specified' % modf
	except:
		print 'SublimeLint: General error importing %s' % modf
	
	os.chdir(pushd)

def reload_module(module):
	fullmod = module.__name__
	if not fullmod.startswith(modpath):
		return
	
	name = fullmod.replace(modpath+'.', '', 1)
	load_module(name)

for modf in glob.glob('%s/*.py' % basepath):
	base, name = os.path.split(modf)
	name = name.split('.', 1)[0]
	if name in ignore: continue

	load_module(name)

## bulk of the code

# TODO: check to see if the types specified after drawType in the codestill work and replace as necessary
drawType = 4 | 32 # from before ST2 had sublime.DRAW_*

global lineMessages
lineMessages = {}

def run(module, view):
	global lineMessages
	vid = view.id()

	text = view.substr(sublime.Region(0, view.size())).encode('utf-8')
	
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
	for language in languages:
		if language in view.settings().get("syntax"):
			run(languages[language], view)
			break

import time, thread
queue = {}
lookup = {}

def validate_runner(): # this threaded runner keeps it from slowing down UI while you type
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
	for language in languages:
		if language in view.settings().get("syntax"):
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

# only start the thread once - otherwise the plugin will get laggy when saving it often
if not 'already' in globals():
	already = True
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
		text = view.substr(sublime.Region(0, view.size())).encode('utf-8')
		count = text.count('\n')
		if count > 500: return
		bid = view.buffer_id()

		if bid in self.lastCount:
			if self.lastCount[bid] != count:
				validate(view)

		self.lastCount[bid] = count
	
	def on_load(self, view):
		validate(view)
	
	def on_post_save(self, view):
		# this will reload submodules if they are saved with sublime text
		for name, module in languages.items():
			if module.__file__ == view.file_name():
				print 'Sublime Lint - Reloading language:', module.language
				reload_module(module)
				break

		validate_hit(view)
	
	def on_selection_modified(self, view):
		vid = view.id()
		lineno = view.rowcol(view.sel()[0].end())[0]
		if vid in lineMessages and lineno in lineMessages[vid]:
			view.set_status('pyflakes', '; '.join(lineMessages[vid][lineno]))
		else:
			view.erase_status('pyflakes')
