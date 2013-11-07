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

import sublime
import sublime_plugin

import os
from threading import Thread

from .lint import highlight, linter, persist, util


def error_command(f):
    '''A decorator that only executes f if the current view has errors.'''
    def run(self, edit, **args):
        vid = self.view.id()

        if vid in persist.errors and persist.errors[vid]:
            f(self, self.view, persist.errors[vid], **args)
        else:
            sublime.message_dialog('No lint errors.')

    return run


def select_line(view, line):
    sel = view.sel()
    point = view.text_point(line, 0)
    sel.clear()
    sel.add(view.line(point))


class sublimelinter_lint(sublime_plugin.TextCommand):
    '''Lints the current view if it has a linter.'''
    def is_enabled(self):
        vid = self.view.id()
        return vid in persist.linters and persist.settings.get('lint_mode') != 'background'

    def run(self, edit):
        from .sublimelinter import SublimeLinter
        SublimeLinter.shared_plugin().lint(self.view.id())


class has_errors_command(object):
    '''A mixin class for text commands that should only be enabled if the current view has errors.'''
    def is_enabled(self):
        # Only show this command in the command palette if the view has errors.
        vid = self.view.id()
        return vid in persist.errors and len(persist.errors[vid]) > 0


class goto_error_command(has_errors_command, sublime_plugin.TextCommand):
    '''This command is just a superclass for other commands, it is never enabled.'''
    def goto_error(self, view, errors, point=None, direction='next'):
        sel = view.sel()

        if len(sel) == 0:
            sel.add(sublime.Region(0, 0))

        saved_sel = tuple(sel)
        empty_selection = len(sel) == 1 and sel[0].empty()

        # sublime.Selection() changes the view's selection, get the point first
        if point is None:
            point = sel[0].begin() if direction == 'next' else sel[-1].end()

        regions = sublime.Selection(view.id())
        regions.clear()
        regions.add_all(view.get_regions(highlight.MARK_KEY_FORMAT.format(highlight.WARNING)))
        regions.add_all(view.get_regions(highlight.MARK_KEY_FORMAT.format(highlight.ERROR)))
        region_to_select = None

        # If going forward, find the first region beginning after the point.
        # If going backward, find the first region ending before the point.
        # If nothing is found in the given direction, wrap to the first/last region.
        if direction == 'next':
            for region in regions:
                if (point == region.begin() and empty_selection) or (point < region.begin()):
                    region_to_select = region
                    break
        else:
            for region in reversed(regions):
                if (point == region.end() and empty_selection) or (point > region.end()):
                    region_to_select = region
                    break

        # If there is only one error line and the cursor is in that line, we cannot move.
        # Otherwise wrap to the first/last error line unless settings disallow that.
        if region_to_select is None and ((len(regions) > 1 or not regions[0].contains(point))):
            if persist.settings.get('wrap_find', True):
                region_to_select = regions[0] if direction == 'next' else regions[-1]

        if region_to_select is not None:
            self.select_lint_region(self.view, region_to_select)
        else:
            sel.clear()
            sel.add_all(saved_sel)
            sublime.message_dialog('No {0} lint error.'.format(direction))

        return region_to_select

    @classmethod
    def select_lint_region(cls, view, region):
        sel = view.sel()
        sel.clear()

        # Find the first marked region within the region to select.
        # If there are none, put the cursor at the beginning of the line.
        marked_region = cls.find_mark_within(view, region)

        if marked_region is None:
            marked_region = sublime.Region(region.begin(), region.begin())

        sel.add(marked_region)
        view.show(marked_region, show_surrounds=True)

    @classmethod
    def find_mark_within(cls, view, region):
        marks = view.get_regions(highlight.MARK_KEY_FORMAT.format(highlight.WARNING))
        marks.extend(view.get_regions(highlight.MARK_KEY_FORMAT.format(highlight.ERROR)))
        marks.sort(key=lambda x: x.begin())

        for mark in marks:
            if region.contains(mark):
                return mark

        return None


class sublimelinter_goto_error(goto_error_command):
    '''Place the caret at the next/previous error.'''
    @error_command
    def run(self, view, errors, **args):
        self.goto_error(view, errors, **args)


class sublimelinter_show_all_errors(goto_error_command):
    '''Show a quick panel with all of the errors in the current view.'''
    @error_command
    def run(self, view, errors):
        self.errors = errors
        self.error_info = []
        options = []

        for lineno, messages in sorted(errors.items()):
            line = view.substr(view.full_line(view.text_point(lineno, 0))).rstrip('\n\r')

            # Strip whitespace from the front of the line, but keep track of how much was
            # stripped so we can adjust the column.
            space = len(line)
            line = line.lstrip()
            space -= len(line)

            for message in sorted(messages):
                # Keep track of the line and column
                column = message[0]
                self.error_info.append((lineno, column))

                # Insert an arrow at the column in the stripped line
                code = line[:column - space] + '➜' + line[column - space:]
                options.append(['{}  {}'.format(lineno, message[1]), code])

        view.window().show_quick_panel(options, self.select_error)

    def select_error(self, index):
        if index != -1:
            selection = self.view.sel()
            selection.clear()
            point = self.view.text_point(*self.error_info[index])
            self.goto_error(self.view, self.errors, point=point)


class show_errors_on_save(sublime_plugin.WindowCommand):
    def __init__(self, window, show_on_save=True):
        super().__init__(window)
        self.show_on_save = show_on_save

    def is_enabled(self):
        return persist.settings.get('show_errors_on_save') is not self.show_on_save

    def set(self):
        persist.settings['show_errors_on_save'] = self.show_on_save
        persist.update_user_settings()


class sublimelinter_show_errors_on_save(show_errors_on_save):
    def __init__(self, window):
        super().__init__(window, show_on_save=True)

    def run(self):
        self.set()


class sublimelinter_dont_show_errors_on_save(show_errors_on_save):
    def __init__(self, window):
        super().__init__(window, show_on_save=False)

    def run(self):
        self.set()


class choose_setting_command(sublime_plugin.WindowCommand):
    '''
    Abstract base class for commands that choose a setting from a list.
    '''
    def __init__(self, window, setting=None):
        super().__init__(window)
        self.setting = setting

    def get_settings(self):
        return []

    def choose(self, **args):
        self.settings = self.get_settings()

        if 'value' in args:
            setting = args['value']
        else:
            setting = persist.settings.get(self.setting)

        index = 0

        for i, s in enumerate(self.settings):
            if isinstance(s, (tuple, list)):
                s = s[0].lower()
            else:
                s = s.lower()

            if s == setting:
                index = i
                break

        if 'value' in args:
            self.set(index)
        else:
            self.window.show_quick_panel(self.settings, self.set, selected_index=index)

    def set(self, index):
        if index == -1:
            return

        old_setting = persist.settings.get(self.setting)
        setting = self.settings[index]

        if isinstance(setting, (tuple, list)):
            setting = setting[0]

        setting = setting.lower()

        if setting == old_setting:
            return

        persist.settings[self.setting] = setting
        self.setting_was_changed(setting)
        persist.update_user_settings()

    def setting_was_changed(self, setting):
        pass


class sublimelinter_choose_lint_mode(choose_setting_command):
    '''Select a lint mode from a list.'''
    def __init__(self, window):
        super().__init__(window, 'lint_mode')

    def run(self, **args):
        self.choose(**args)

    def get_settings(self):
        return [[mode[0].capitalize(), mode[1]] for mode in persist.LINT_MODES]

    def setting_was_changed(self, setting):
        if setting == 'background':
            from .sublimelinter import SublimeLinter
            SublimeLinter.lint_all_views()
        else:
            linter.Linter.clear_all()


class sublimelinter_choose_mark_style(choose_setting_command):
    '''Select a mark style from a list.'''
    def __init__(self, window):
        super().__init__(window, 'mark_style')

    def run(self, **args):
        self.choose(**args)

    def get_settings(self):
        return highlight.mark_style_names()


class sublimelinter_choose_gutter_theme(choose_setting_command):
    '''Select a gutter theme from a list.'''
    def __init__(self, window):
        super().__init__(window, 'gutter_theme')

    def run(self, **args):
        self.choose(**args)

    def get_settings(self):
        settings = []
        themes = []
        self.find_themes(settings, themes, user_themes=True)
        self.find_themes(settings, themes, user_themes=False)
        settings.sort()
        settings.append(('None', 'Do not display gutter marks'))

        return settings

    def find_themes(self, settings, themes, user_themes):
        if user_themes:
            theme_path = os.path.join('User', 'SublimeLinter-gutter-themes')
        else:
            theme_path = os.path.join(os.path.basename(persist.PLUGIN_DIRECTORY), 'gutter-themes')

        full_path = os.path.join(sublime.packages_path(), theme_path)

        if os.path.isdir(full_path):
            dirs = os.listdir(full_path)

            for d in dirs:
                for root, dirs, files in os.walk(os.path.join(full_path, d)):
                    if 'warning.png' in files and 'error.png' in files:
                        relative_path = util.package_relative_path(os.path.relpath(root, full_path), prefix_packages=False)

                        if relative_path not in themes:
                            settings.append([relative_path, 'User theme' if user_themes else 'SublimeLinter theme'])
                            themes.append(relative_path)


class sublimelinter_report(sublime_plugin.WindowCommand):
    '''
    Display a report of all errors in all open files in the current window,
    in all files in all folders in the current window, or both.
    '''
    def run(self, on='files'):
        output = self.window.new_file()
        output.set_name(persist.PLUGIN_NAME)
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

        from .sublimelinter import SublimeLinter
        Thread(target=SublimeLinter.lint, args=args).start()
