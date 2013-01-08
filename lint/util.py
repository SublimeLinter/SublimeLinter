import os
import shutil
import tempfile
import subprocess

import persist

def memoize(f):
	rets = {}

	def wrap(*args):
		if not args in rets:
			rets[args] = f(*args)

		return rets[args]

	wrap.__name__ = f.__name__
	return wrap

def climb(top):
    right = True
    while right:
        top, right = os.path.split(top)
        yield top

@memoize
def find(top, name, parent=False):
    for d in climb(top):
        target = os.path.join(d, name)
        if os.path.exists(target):
            if parent:
                return d

            return target

def extract_path(cmd, delim=':'):
	path = popen(cmd, os.environ).communicate()[0]
	path = path.split('__SUBL__', 1)[1].strip('\r\n')
	return ':'.join(path.split(delim))

def find_path(env):
	# find PATH using shell --login
	if 'SHELL' in env:
		shell_path = env['SHELL']
		shell = os.path.basename(shell_path)

		if shell in ('bash', 'zsh'):
			return extract_path(
				(shell_path, '--login', '-c', 'echo __SUBL__$PATH')
			)
		elif shell == 'fish':
			return extract_path(
				(shell_path, '--login', '-c', 'echo __SUBL__; for p in $PATH; echo $p; end'),
				'\n'
			)

	# guess PATH if we haven't returned yet
	split = env['PATH'].split(':')
	p = env['PATH']
	for path in (
		'/usr/bin', '/usr/local/bin',
		'/usr/local/php/bin', '/usr/local/php5/bin'
				):
		if not path in split:
			p += (':' + path)

	return p

@memoize
def create_environment():
	if os.name == 'posix':
		os.environ['PATH'] = find_path(os.environ)

	return os.environ

# popen methods
def communicate(cmd, code):
	out = popen(cmd)
	if out is not None:
		out = out.communicate(code)
		return (out[0] or '') + (out[1] or '')
	else:
		return ''


def tmpfile(cmd, code, suffix=''):
	if isinstance(cmd, basestring):
		cmd = cmd,

	f = tempfile.NamedTemporaryFile(suffix=suffix)
	f.write(code)
	f.flush()

	cmd = tuple(cmd) + (f.name,)
	out = popen(cmd)
	if out:
		out = out.communicate()
		return (out[0] or '') + (out[1] or '')
	else:
		return ''

def tmpdir(cmd, files, filename, code):
	filename = os.path.split(filename)[1]
	d = tempfile.mkdtemp()

	for f in files:
		try: os.makedirs(os.path.split(f)[0])
		except: pass

		target = os.path.join(d, f)
		if os.path.split(target)[1] == filename:
			# source file hasn't been saved since change, so update it from our live buffer
			f = open(target, 'wb')
			f.write(code)
			f.close()
		else:
			shutil.copyfile(f, target)

	os.chdir(d)
	out = popen(cmd)
	if out:
		out = out.communicate()
		out = (out[0] or '') + '\n' + (out[1] or '')
		
		# filter results from build to just this filename
		# no guarantee all languages are as nice about this as Go
		# may need to improve later or just defer to communicate()
		out = '\n'.join([
			line for line in out.split('\n') if filename in line.split(':', 1)[0]
		])
	else:
		out = ''

	shutil.rmtree(d, True)
	return out

def popen(cmd, env=None):
	if isinstance(cmd, basestring):
		cmd = cmd,

	info = None
	if os.name == 'nt':
		info = subprocess.STARTUPINFO()
		info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
		info.wShowWindow = subprocess.SW_HIDE

	if env is None:
		env = create_environment()

	try:
		return subprocess.Popen(cmd, stdin=subprocess.PIPE,
			stdout=subprocess.PIPE, stderr=subprocess.PIPE,
			startupinfo=info, env=env)
	except OSError, err:
		persist.debug('SublimeLint: Error launching', repr(cmd))
		persist.debug('Error was:', err.strerror)
