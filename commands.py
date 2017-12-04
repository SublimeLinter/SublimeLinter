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

from .panel.diagnostics import PANEL_NAME


def error_command(method):
    """
    Execute method only if the current view has errors.

    This is a decorator and is meant to be used only with the run method of
    sublime_plugin.TextCommand subclasses.

    A wrapped version of method is returned.

    """

    def run(self, edit, **kwargs):
        vid = self.view.id()

        if not vid:
            return

        if vid in persist.errors.data and persist.errors.data[vid]:
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


# TODO: any function? is it used internally? -> check correct snak_case
class SublimeLinterClearCachesCommand(sublime_plugin.WindowCommand):
    """A command that clears all of SublimeLinter's internal caches."""

    def run(self):
        util.clear_path_caches()
        util.get_rc_settings.cache_clear()
        util.find_file.cache_clear()
        linter.Linter.clear_settings_caches()


# TODO: does this command serve any function?
class SublimeLinterEditCommand(sublime_plugin.TextCommand):
    """A plugin command used to generate an edit object for a view."""

    def run(self, edit):
        persist.edit(self.view.id(), edit)


class SublimeLinterLineReportCommand(sublime_plugin.WindowCommand):
    def run(self):
        from .sublime_linter import SublimeLinter
        SublimeLinter.shared_plugin().open_tooltip()


class SublimeLinterShowPanelCommand(sublime_plugin.WindowCommand):
    def run(self, select, types, codes, linter):
        from .sublime_linter import SublimeLinter
        SublimeLinter.shared_plugin().open_panel_report(select, types, codes, linter)


# TODO: make it a true toggle, allow spec of state via arg
class SublimeLinterPanelToggleCommand(sublime_plugin.WindowCommand):
    """
    A update_panel command to update the error panel with new text.
    """

    def run(self, ensure_panel=False):
        print("panel toggle called")
        window = self.window
        active_panel = window.active_panel()
        is_active_panel = (active_panel == "output." + PANEL_NAME)
        if not active_panel or ensure_panel:
            window.run_command("show_panel",
                               {"panel": "output." + PANEL_NAME})

            panel_view = window.find_output_panel(PANEL_NAME)
            # panel focus does not work as of 3156, due to ST bug
            window.focus_view(panel_view)
        else:
            # panel.run_command("sublime_linter_panel_clear")
            if is_active_panel:
                window.run_command("hide_panel",
                                   {"panel": "output." + PANEL_NAME})



class SublimeLinterPanelUpdateCommand(sublime_plugin.TextCommand):
    """
    A update_panel command to update the error panel with new text.
    """

    def run(self, edit, characters):
        self.view.replace(edit, sublime.Region(
            0, self.view.size()), characters)
        # Move cursor to the end
        selection = self.view.sel()
        selection.clear()
        selection.add(sublime.Region(self.view.size(), self.view.size()))



class SublimeLinterPanelClearCommand(sublime_plugin.TextCommand):
    """
    A clear_panel command to clear the error panel.
    """

    def run(self, edit):
        self.view.erase(edit, sublime.Region(0, self.view.size()))
