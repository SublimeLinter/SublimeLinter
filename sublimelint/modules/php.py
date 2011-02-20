# php.py - sublimelint package for checking php files

# start code to actually work with PHP and lint check input
import subprocess, os, tempfile

def check(codeString, filename):
	info = None
	if os.name == 'nt':
		info = subprocess.STARTUPINFO()
		info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
		info.wShowWindow = subprocess.SW_HIDE
	tmpFile = tempfile.NamedTemporaryFile(delete=False)
	tmpFileName = tmpFile.name
	tmpFile.write(codeString)
	tmpFile.close()
	result = subprocess.Popen(['php', '-l', tmpFileName], stdout=subprocess.PIPE, startupinfo=info).communicate()[0]	
	os.unlink(tmpFileName)
	return result, tmpFileName

# start sublimelint php plugin
import re
__all__ = ['run', 'language']
language = 'PHP'

def run(code, view, filename='untitled'):
	errors, tmpFile = check(code, filename)
		
	lines = set()
	underline = [] # leave this here for compatibility with original plugin
	
	errorMessages = {}
	def addMessage(lineno, message):
		message = str(message)
		if lineno in errorMessages:
			errorMessages[lineno].append(message)
		else:
			errorMessages[lineno] = [message]
	
	m = re.search(r"on line (\d+)", errors);
	if m:
		lineno = int(m.group(1))
		lineno -= 1
		lines.add(lineno)		
		errorLines = errors.splitlines();
		tmpFile = tmpFile.replace("\\", "\\\\")
		m2 = re.search(r"(.*) in " + tmpFile + " on line \d+", errorLines[1])		
		addMessage(lineno, m2.group(1))

	return underline, lines, errorMessages, True
