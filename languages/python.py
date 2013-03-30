from lint.linter import Linter

class Python(Linter):
    language = 'python'
    cmd = 'pyflakes'
    regex = r'^.+:(?P<line>\d+):\s*(?P<error>.+)'
