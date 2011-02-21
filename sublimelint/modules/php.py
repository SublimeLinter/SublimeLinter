# php.py - sublimelint package for checking php files

import subprocess, os

def check(codeString, filename):
	info = None
	if os.name == 'nt':
		info = subprocess.STARTUPINFO()
		info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
		info.wShowWindow = subprocess.SW_HIDE

	process = subprocess.Popen(('php', '-l', '-d display_errors=On'), stdin=subprocess.PIPE, stdout=subprocess.PIPE, startupinfo=info)
	result = process.communicate(codeString)[0]

	return result

# start sublimelint php plugin
import re
__all__ = ['run', 'language']
language = 'PHP'

def run(code, view, filename='untitled'):
	errors = check(code, filename)
	
	lines = set()
	underline = [] # leave this here for compatibility with original plugin
	
	errorMessages = {}
	def addMessage(lineno, message):
		message = str(message)
		if lineno in errorMessages:
			errorMessages[lineno].append(message)
		else:
			errorMessages[lineno] = [message]
	
	for line in errors.splitlines():
		match = re.match(r'^Parse error:\s*syntax error,\s*(?P<error>.+?)\s+in\s+.+?\s*line\s+(?P<line>\d+)', line)

		if match:
			error, line = match.group('error'), match.group('line')

			lineno = int(line) - 1
			lines.add(lineno)
			addMessage(lineno, error)

	return underline, lines, errorMessages, True
