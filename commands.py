# coding: utf-8
#
# commands.py
# Part of SublimeLinter3, a code checking framework for Sublime Text 3
#
# Written by Ryan Hileman and Aparajita Fishman
#
# Project: https://github.com/SublimeLinter/SublimeLinter3
# License: MIT
#

"""This module implements the Sublime Text commands provided by SublimeLinter."""

import os
from threading import Thread
from itertools import cycle

import sublime
import sublime_plugin

from .lint import highlight, linter, persist, util
from .lint.const import WARNING, ERROR


def error_command(method):
    """
    Execute method only if the current view has errors.

    This is a decorator and is meant to be used only with the run method of
    sublime_plugin.TextCommand subclasses.

    A wrapped version of method is returned.

    """

    def run(self, edit, **kwargs):
        vid = self.view.id()

        if vid in persist.errors and persist.errors[vid]:
            method(self, self.view,
                   persist.errors[vid], persist.highlights[vid], **kwargs)
        else:
            sublime.status_message('No lint errors.')

    return run


def select_line(view, line):
    """Change view's selection to be the given line."""
    point = view.text_point(line, 0)
    sel = view.sel()
    sel.clear()
    sel.add(view.line(point))


class SublimeLinterLintCommand(sublime_plugin.TextCommand):
    """A command that lints the current view if it has a linter."""

    def is_enabled(self):
        """
        Return True if the current view can be linted.

        If the view has *only* file-only linters, it can be linted
        only if the view is not dirty.

        Otherwise it can be linted.

        """

        has_non_file_only_linter = False

        vid = self.view.id()
        linters = persist.view_linters.get(vid, [])

        for lint in linters:
            if lint.tempfile_suffix != '-':
                has_non_file_only_linter = True
                break

        if not has_non_file_only_linter:
            return not self.view.is_dirty()

        return True

    def run(self, edit):
        """Lint the current view."""
        from .sublime_linter import SublimeLinter
        SublimeLinter.shared_plugin().hit(self.view)


class HasErrorsCommand:
    """
    A mixin class for sublime_plugin.TextCommand subclasses.

    Inheriting from this class will enable the command only if the current view has errors.

    """

    def is_enabled(self):
        """Return True if the current view has errors."""
        vid = self.view.id()
        return vid in persist.errors and len(persist.errors[vid]) > 0


def get_neighbours(num, l):
    cyc = cycle(l)
    prev_num = next(cyc)
    next_num = None
    while True:
        next_num = next(cyc)
        if next_num == num:
            next_num = next(cyc)
            break
        elif prev_num < num < next_num:
            break
        prev_num = next_num
    return prev_num, next_num


class GotoErrorCommand(sublime_plugin.TextCommand):
    """A superclass for commands that go to the next/previous error."""

    def goto_error(self, view, errors, direction='next'):
        """Go to the next/previous error in view."""
        sel = view.sel()

        if len(sel) == 0:
            sel.add(sublime.Region(0, 0))

        # sublime.Selection() changes the view's selection, get the point first
        point = sel[0].begin() if direction == 'next' else sel[-1].end()

        regions = sublime.Selection(view.id())
        regions.clear()

        from .lint.persist import region_store
        mark_points = region_store.get_mark_regions(view)

        if not mark_points:
            return

        prev_mark, next_mark = get_neighbours(point, mark_points)

        if direction == 'next':
            region_to_select = sublime.Region(next_mark, next_mark)
        else:
            region_to_select = sublime.Region(prev_mark, prev_mark)

        self.select_lint_region(view, region_to_select)

    @classmethod
    def select_lint_region(cls, view, region):
        """
        Select and scroll to the first marked region that contains region.

        If none are found, the beginning of region is used. The view is
        centered on the calculated region and the region is selected.

        """

        marked_region = cls.find_mark_within(view, region)

        if marked_region is None:
            marked_region = sublime.Region(region.begin(), region.begin())

        sel = view.sel()
        sel.clear()
        sel.add(marked_region)

        # There is a bug in ST3 that prevents the selection from changing
        # when a quick panel is open and the viewport does not change position,
        # so we call our own custom method that works around that.
        util.center_region_in_view(marked_region, view)

    @classmethod
    def find_mark_within(cls, view, region):
        """Return the nearest marked region that contains region, or None if none found."""

        marks = view.get_regions(
            highlight.MARK_KEY_FORMAT.format(WARNING))
        marks.extend(view.get_regions(
            highlight.MARK_KEY_FORMAT.format(ERROR)))
        marks.sort(key=sublime.Region.begin)

        for mark in marks:
            if mark.contains(region):
                return mark

        return None


class SublimeLinterGotoErrorCommand(GotoErrorCommand):
    """A command that selects the next/previous error."""

    @error_command
    def run(self, view, errors, highlights, **kwargs):
        self.goto_error(view, errors, **kwargs)


class SublimeLinterShowAllErrors(sublime_plugin.TextCommand):

    @error_command
    def run(self, view, errors, highlights):
        self.errors = errors
        self.highlights = highlights
        self.points = []
        options = []

        for lineno, line_errors in sorted(errors.items()):
            line = view.substr(
                view.full_line(view.text_point(lineno, 0))
            ).rstrip('\n\r')

            line = line.lstrip()

            we_count = util.msg_count(line_errors)
            msg = "W: {} E: {}".format(we_count[0], we_count[1])

            point = view.text_point(lineno, 0)
            self.points.append(point)

            options.append(['{}  {}'.format(lineno + 1, msg), line])

        self.viewport_pos = view.viewport_position()
        self.selection = list(view.sel())

        view.window().show_quick_panel(
            options,
            on_select=self.select_error,
            on_highlight=self.select_error
        )

    def select_error(self, index):
        """Completion handler for the quick panel. Selects the indexed error."""
        if index != -1:
            point = self.points[index]
            GotoErrorCommand.select_lint_region(
                self.view, sublime.Region(point, point))
        else:
            self.view.set_viewport_position(self.viewport_pos)
            self.view.sel().clear()
            self.view.sel().add_all(self.selection)


class SublimeLinterClearCachesCommand(sublime_plugin.WindowCommand):
    """A command that clears all of SublimeLinter's internal caches."""

    def run(self):
        util.clear_path_caches()
        util.get_rc_settings.cache_clear()
        util.find_file.cache_clear()
        linter.Linter.clear_settings_caches()


class SublimeLinterReportCommand(sublime_plugin.WindowCommand):
    """
    A command that displays a report of all errors.

    The scope of the report is all open files in the current window,
    all files in all folders in the current window, or both.

    """

    def run(self, on='files'):
        """Run the command. on determines the scope of the report."""

        output = self.window.new_file()
        output.set_name('{} Error Report'.format(persist.PLUGIN_NAME))
        output.set_scratch(True)

        from .sublime_linter import SublimeLinter
        self.plugin = SublimeLinter.shared_plugin()

        if on == 'files' or on == 'both':
            for view in self.window.views():
                self.report(output, view)

        if on == 'folders' or on == 'both':
            for folder in self.window.folders():
                self.folder(output, folder)

    def folder(self, output, folder):
        """Report on all files in a folder."""

        for root, dirs, files in os.walk(folder):
            for name in files:
                path = os.path.join(root, name)

                # Ignore files over 256K to speed things up a bit
                if os.stat(path).st_size < 256 * 1024:
                    pass

    def report(self, output, view):
        """Write a report on the given view to output."""

        def finish_lint(view, linters, hit_time):
            if not linters:
                return

            def insert(edit):
                if not any(l.errors for l in linters):
                    return

                filename = os.path.basename(linters[0].filename or 'untitled')
                out = '\n{}:\n'.format(filename)

                for lint in sorted(linters, key=lambda lint: lint.name):
                    if lint.errors:
                        out += '\n  {}:\n'.format(lint.name)
                        items = sorted(lint.errors.items())

                        # Get the highest line number so we know how much padding numbers need
                        highest_line = items[-1][0]
                        width = 1

                        while highest_line >= 10:
                            highest_line /= 10
                            width += 1

                        for line, messages in items:
                            for e_t, ds in messages.items():
                                for d in ds:
                                    msg = e_t + " - {code}: {msg}".format(**d)
                                    out += '    {:>{width}}: {}\n'.format(
                                        line + 1, msg, width=width)

                output.insert(edit, output.size(), out)

            persist.edits[output.id()].append(insert)
            output.run_command('sublime_linter_edit')

        kwargs = {'self': self.plugin,
                  'view_id': view.id(), 'callback': finish_lint}

        from .sublime_linter import SublimeLinter
        Thread(target=SublimeLinter.lint, kwargs=kwargs).start()


class SublimeLinterLineReportCommand(sublime_plugin.WindowCommand):
    def run(self):
        from .sublime_linter import SublimeLinter
        SublimeLinter.shared_plugin().open_tooltip()


class SublimeLinterShowPanelCommand(sublime_plugin.WindowCommand):
    def run(self):
        from .sublime_linter import SublimeLinter
        SublimeLinter.shared_plugin().open_panel_report()
