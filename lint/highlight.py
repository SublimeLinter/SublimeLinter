# highlight.py
# Part of SublimeLinter, a code checking framework for Sublime Text 3
#
# Project: https://github.com/SublimeLinter/sublimelinter
# License: MIT

import sublime
import re

WORD_RE = re.compile(r'^([0-9a-zA-Z_]+)')

class HighlightSet:
    '''A set of Highlight objects which can perform bulk draw/clear.'''
    def __init__(self):
        self.all = {}

    def add(self, h):
        if not h.scope in self.all:
            self.all[h.scope] = set()

        self.all[h.scope].add(h)

    def draw(self, view, prefix='lint', scope=None):
        for scope in self.all:
            highlight = Highlight(scope=scope)

            for h in self.all[scope]:
                highlight.update(h)

            highlight.draw(view, prefix=prefix, scope=scope)

    def clear(self, view, prefix='lint'):
        for scope in set(self.all):
            view.erase_regions('%s-%s-underline' % (prefix, scope))
            view.erase_regions('%s-%s-outline' % (prefix, scope))

class Highlight:
    '''A class that represents a highlight of an error and knows how to draw itself.'''
    def __init__(self, code='',
            underline_flags=sublime.DRAW_SOLID_UNDERLINE | sublime.DRAW_NO_FILL | sublime.DRAW_NO_OUTLINE,
            line_flags=sublime.HIDDEN, icon='dot',
            scope='keyword', outline=True):

        self.code = code
        self.underline_flags = underline_flags
        self.line_flags = line_flags
        self.scope = scope
        self.outline = outline
        self.underlines = []
        self.lines = set()
        self.icon = icon

        self.line_offset = 0
        self.char_offset = 0

        # Find all the newlines, so we can look for line positions
        # without merging back into the main thread for APIs
        self.newlines = newlines = [0]
        last = -1

        while True:
            last = code.find('\n', last + 1)

            if last == -1:
                break

            newlines.append(last + 1)

        newlines.append(len(code))

    def full_line(self, line):
        a, b = self.newlines[line:line + 2]
        return a, b + 1

    def range(self, line, pos, length=1):
        a, b = self.full_line(line)

        if length == 1:
            code = self.code[a:b][pos:]
            match = WORD_RE.search(code)

            if match:
                length = len(match.group())

        pos += a

        for i in range(length):
            self.underlines.append(sublime.Region(pos + i + self.char_offset))

    def regex(self, line, regex, word_match=None, line_match=None):
        self.line(line)
        offset = 0

        a, b = self.full_line(line)
        lineText = self.code[a:b]

        if line_match:
            match = re.match(line_match, lineText)

            if match:
                lineText = match.group('match')
                offset = match.start('match')
            else:
                return

        iters = re.finditer(regex, lineText)
        results = [(result.start('underline'), result.end('underline'))
                    for result in iters if
                    not word_match or
                    result.group('underline') == word_match]

        for start, end in results:
            self.range(line, start+offset, end-start)

    def near(self, line, near):
        self.line(line)
        a, b = self.full_line(line)
        text = self.code[a:b]
        start = text.find(near)

        if start != -1:
            self.range(line, start, len(near))

    def update(self, other):
        if self.outline:
            self.lines.update(other.lines)

        self.underlines.extend(other.underlines)

    def draw(self, view, prefix='lint', scope=None):
        if scope is None:
            scope = self.scope

        if self.lines and self.outline:
            outlines = [view.full_line(view.text_point(line, 0))
                        for line in self.lines]
            view.add_regions(
                '%s-%s-outline' % (prefix, self.scope),
                outlines, scope, self.icon,
                flags=self.line_flags,
            )

        if self.underlines:
            underlines = [sublime.Region(u.a, u.a+1) for u in self.underlines]
            view.add_regions(
                '%s-%s-underline' % (prefix, self.scope),
                underlines, scope, self.icon,
                flags=self.underline_flags,
            )

    def clear(self, view, prefix='lint', scope=None):
        if scope is None:
            scope = self.scope

        view.erase_regions('%s-%s-underline' % (prefix, scope))
        view.erase_regions('%s-%s-outline' % (prefix, scope))

    def line(self, line):
        if self.outline:
            self.lines.add(line + self.line_offset)

    def move_to(self, line, char):
        self.line_offset = line
        self.char_offset = char
