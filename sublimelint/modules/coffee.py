# coffee.py - sublimelint package for checking coffee-script files

import subprocess, os

def check(codeString, filename):
    info = None
    if os.name == 'nt':
        info = subprocess.STARTUPINFO()
        info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        info.wShowWindow = subprocess.SW_HIDE

    process = subprocess.Popen(
        ('coffee', '--compile', '--stdio'), 
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
        startupinfo=info
    )
    result = process.communicate(codeString)[1]
    return result

import re
__all__ = ['run', 'language']
language = 'CoffeeScript'

compile_err = re.compile('^[A-Za-z]+: (.+) on line ([0-9]+)')

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
        match = compile_err.match(line)
        if match:
            error, line = match.groups()
        else:
            continue

        lineno = int(line) - 1
        lines.add(lineno)
        addMessage(lineno, error)

    return underline, lines, errorMessages, True

if __name__ == '__main__':
    import sys
    print run(open(sys.argv[1]).read(), 'bah')
