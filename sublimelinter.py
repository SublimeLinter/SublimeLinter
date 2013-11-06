#
# sublimelinter.py
# Part of SublimeLinter3, a code checking framework for Sublime Text 3
#
# Written by Ryan Hileman and Aparajita Fishman
#
# Project: https://github.com/SublimeLinter/SublimeLinter3
# License: MIT
#

import sublime
import sublime_plugin

import os
import re

from .lint.linter import Linter
from .lint.highlight import HighlightSet
from .lint import persist


# In ST3, this is the entry point for a plugin
def plugin_loaded():
    persist.plugin_is_loaded = True
    persist.load_settings()
    persist.update_color_scheme()


class SublimeLinter(sublime_plugin.EventListener):
    '''The main ST3 plugin class.'''

    # We use this to match linter settings filenames.
    LINTER_SETTINGS_RE = re.compile('^SublimeLinter(-.+?)?\.sublime-settings')

    shared_instance = None

    @classmethod
    def shared_plugin(cls):
        return cls.shared_instance

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Keeps track of which views we have assigned linters to
        self.loaded_views = set()

        # Keeps track of which views have actually been linted
        self.linted_views = set()

        # A mapping between view ids and syntax names
        self.view_syntax = {}

        # Every time a view is modified, this is updated and an asynchronous lint is queued.
        # When a lint is done, if the view has been modified since the lint was initiated,
        # marks are not updated because their positions may no longer be valid.
        self.last_hit_times = {}

        self.__class__.shared_instance = self
        persist.queue.start(self.lint)

        # This gives us a chance to lint the active view on fresh install
        window = sublime.active_window()

        if window:
            self.on_activated(window.active_view())

    @classmethod
    def lint_all_views(cls):
        for w in sublime.windows():
            for view in w.views():
                if view.id() in persist.linters:
                    cls.shared_instance.hit(view)

    def lint(self, view_id, hit_time=None, callback=None):
        callback = callback or self.highlight
        view = Linter.get_view(view_id)

        if view is None:
            return

        # Build a list of regions that match the linter's selectors
        sections = {}

        for sel, _ in Linter.get_selectors(view_id):
            sections[sel] = []

            for result in view.find_by_selector(sel):
                sections[sel].append(
                    (view.rowcol(result.a)[0], result.a, result.b)
                )

        filename = view.file_name()
        code = Linter.text(view)
        Linter.lint_view(view_id, filename, code, sections, hit_time, callback)

    def highlight(self, view, linters, hit_time):
        '''Highlight any errors found during a lint.'''
        errors = {}
        vid = view.id()
        highlights = persist.highlights[vid] = HighlightSet()

        for linter in linters:
            if linter.highlight:
                highlights.add(linter.highlight)

            if linter.errors:
                for line, errs in linter.errors.items():
                    errors.setdefault(line, []).extend(errs)

        # If the view has been modified since the lint was triggered, don't draw marks
        if hit_time is not None and self.last_hit_times.get(vid, 0) > hit_time:
            return

        highlights.clear(view)
        highlights.draw(view)
        persist.errors[vid] = errors

        # Update the status
        self.on_selection_modified_async(view)

    def hit(self, view):
        '''Record an activity that could trigger a lint and enqueue a desire to lint.'''
        vid = view.id()
        self.check_syntax(view)
        self.linted_views.add(vid)

        if view.size() == 0:
            for l in Linter.get_linters(vid):
                l.clear()

            return

        self.last_hit_times[vid] = persist.queue.hit(view)

    def check_syntax(self, view):
        vid = view.id()
        syntax = view.settings().get('syntax')

        # Syntax either has never been set or just changed
        if not vid in self.view_syntax or self.view_syntax[vid] != syntax:
            self.view_syntax[vid] = syntax
            Linter.assign(view)

    # sublime_plugin.EventListener event handlers

    def on_modified(self, view):
        '''Called when a view is modified.'''
        if view.id() not in persist.linters:
            return

        if persist.settings.get('lint_mode', 'background') == 'background':
            self.hit(view)

    def on_modified_async(self, view):
        '''Called *after* on_modified, updates the status.'''
        if view.id() not in persist.linters:
            return

        if persist.settings.get('lint_mode') == 'background':
            self.on_selection_modified_async(view)
        else:
            Linter.clear_all()

    def on_load(self, view):
        '''Called when a file is finished loading.'''
        self.on_new(view)

    def on_activated(self, view):
        '''Called when a view gains input focus.'''

        # Reload the plugin settings.
        persist.load_settings()

        self.check_syntax(view)
        view_id = view.id()

        if not view_id in self.linted_views:
            if not view_id in self.loaded_views:
                self.on_new(view)

            if persist.settings.get('lint_mode') in ('background', 'load/save'):
                self.hit(view)

        self.on_selection_modified_async(view)

    def on_open_settings(self, view):
        '''
        Called when any settings file is opened via the Preferences menu.
        view is the view that contains the text of the settings file.
        '''
        filename = view.file_name()

        if not filename:
            return

        dirname, filename = os.path.split(filename)
        dirname = os.path.basename(dirname)

        # We are only interested in the user SublimeLinter settings, not the default settings
        if not self.LINTER_SETTINGS_RE.match(filename) or dirname != 'User':
            return

        persist.update_user_settings(view=view)

    def on_new(self, view):
        '''Called when a new buffer is created.'''
        self.on_open_settings(view)
        vid = view.id()
        self.loaded_views.add(vid)
        self.view_syntax[vid] = view.settings().get('syntax')
        Linter.assign(view)

    def on_selection_modified_async(self, view):
        '''Called when the selection changes (cursor moves or text selected).'''
        vid = view.id()

        # Get the line number of the first line of the first selection.
        try:
            lineno = view.rowcol(view.sel()[0].begin())[0]
        except IndexError:
            lineno = -1

        if vid in persist.errors:
            errors = persist.errors[vid]

            if errors:
                lines = sorted(list(errors))
                counts = [len(errors[line]) for line in lines]
                count = sum(counts)
                plural = 's' if count > 1 else ''

                if lineno in errors:
                    # Sort the errors by column
                    line_errors = sorted(errors[lineno], key=lambda error: error[0])
                    line_errors = [error[1] for error in line_errors]

                    if plural:
                        # Sum the errors before the first error on this line
                        index = lines.index(lineno)
                        first = sum(counts[0:index]) + 1

                        if len(line_errors) > 1:
                            status = '{}-{} of {} errors: '.format(first, first + len(line_errors) - 1, count)
                        else:
                            status = '{} of {} errors: '.format(first, count)
                    else:
                        status = 'Error: '

                    status += '; '.join(line_errors)
                else:
                    status = '%i error%s' % (count, plural)

                view.set_status('sublimelinter', status)
            else:
                view.erase_status('sublimelinter')

    def on_post_save(self, view):
        if persist.settings.get('lint_mode') in ('load/save', 'save only'):
            self.lint(view.id())

        if persist.settings.get('show_errors_on_save') and persist.settings.get('lint_mode') != 'manual':
            view.run_command('sublimelinter_show_all_errors')

    def on_close(self, view):
        vid = view.id()

        if vid in self.loaded_views:
            self.loaded_views.remove(vid)

        if vid in self.linted_views:
            self.linted_views.remove(vid)

        if vid in self.view_syntax:
            del self.view_syntax[vid]

        if vid in self.last_hit_times:
            del self.last_hit_times[vid]

        persist.view_did_close(vid)


class sublimelinter_edit(sublime_plugin.TextCommand):
    '''A plugin command used to generate an edit object for a view.'''
    def run(self, edit):
        persist.edit(self.view.id(), edit)
