# commands.py
# Part of SublimeLinter, a code checking framework for Sublime Text 3
#
# Project: https://github.com/SublimeLinter/sublimelinter
# License: MIT

import sublime
import sublime_plugin

import os
from threading import Thread

from . import sublimelinter
from .lint import persist


def error_command(f):
    '''A decorator that only executes f if the current view has errors.'''
    def run(self, edit, **kwargs):
        vid = self.view.id()

        if vid in persist.errors and persist.errors[vid]:
            f(self, self.view, persist.errors[vid], **kwargs)

    return run


def select_line(view, line):
    sel = view.sel()
    point = view.text_point(line, 0)
    sel.clear()
    sel.add(view.line(point))


class sublimelinter_next_error(sublime_plugin.TextCommand):
    '''Select the next line containing an error.'''
    @error_command
    def run(self, view, errors, direction=1):
        self.view.run_command('single_selection')
        sel = view.sel()

        if len(sel) == 0:
            sel.add((0, 0))

        line = view.rowcol(sel[0].a)[0]
        errors = list(errors)

        if line in errors:
            errors.remove(line)

        errors = sorted(errors + [line])
        i = errors.index(line) + direction

        # Wrap around if we go past the last error
        if i >= len(errors):
            i -= len(errors)

        select_line(view, errors[i])
        view.show_at_center(sel[0])


class sublimelinter_all_errors(sublime_plugin.TextCommand):
    '''Show a quick panel with all of the errors in the current view.'''
    @error_command
    def run(self, view, errors):
        options = []
        option_to_line = []

        for lineno, messages in sorted(errors.items()):
            line = view.substr(
                view.full_line(view.text_point(lineno, 0))
            )

            while messages:
                option_to_line.append(lineno)
                options.append(
                    [("%i| %s" % (lineno + 1, line.strip()))] +
                    [m for m in messages[:2]]
                )

                messages = messages[2:]

        def center_line(i):
            if i != -1:
                select_line(view, option_to_line[i])
                view.show_at_center(view.sel()[0])

        view.window().show_quick_panel(options, center_line, sublime.MONOSPACE_FONT)


class sublimelinter_report(sublime_plugin.WindowCommand):
    '''
    Display a report of all errors in all open files in the current window,
    in all files in all folders in the current window, or both.
    '''
    def run(self, on='files'):
        output = self.window.new_file()
        output.set_name(persist.plugin_name)
        output.set_scratch(True)

        if on == 'files' or on == 'both':
            for view in self.window.views():
                self.report(output, view)

        if on == 'folders' or on == 'both':
            for folder in self.window.folders():
                self.folder(output, folder)

    def folder(self, output, folder):
        for root, dirs, files in os.walk(folder):
            for name in files:
                path = os.path.join(root, name)

                # Ignore files over 256K to speed things up a bit
                if os.stat(path).st_size < 256 * 1024:
                    # TODO: not implemented
                    pass

    def report(self, output, view):
        def finish_lint(view, linters):
            if not linters:
                return

            def insert(edit):
                if not any(l.errors for l in linters):
                    return

                filename = os.path.basename(linters[0].filename or 'untitled')
                out = '\n{}:\n'.format(filename)

                for linter in linters:
                    if linter.errors:
                        for line, errors in sorted(linter.errors.items()):
                            for col, error in errors:
                                out += '  {}: {}\n'.format(line, error)

                output.insert(edit, output.size(), out)

            persist.edits[output.id()].append(insert)
            output.run_command('sublimelinter_edit')

        args = (view.id(), finish_lint)
        Thread(target=sublimelinter.SublimeLinter.lint, args=args).start()
