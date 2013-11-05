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

from .lint import highlight, linter, persist


def error_command(f):
    '''A decorator that only executes f if the current view has errors.'''
    def run(self, edit, **kwargs):
        vid = self.view.id()

        if vid in persist.errors and persist.errors[vid]:
            f(self, self.view, persist.errors[vid], **kwargs)
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
        # Only show this command in the command palette if the lint mode is manual
        # and the view has an associated linter.
        vid = self.view.id()
        return vid in persist.linters and persist.settings.get('lint_mode') == 'manual'

    def run(self, edit):
        from .sublimelinter import SublimeLinter
        SublimeLinter.shared_plugin().hit(self.view)


class sublimelinter_find_error(sublime_plugin.TextCommand):
    '''This command is just a superclass for other commands, it is never enabled.'''
    def is_enabled(self):
        # Only show this command in the command palette if the view has errors.
        vid = self.view.id()
        return vid in persist.errors and persist.errors[vid]

    def find_error(self, view, errors, forward=True):
        sel = view.sel()
        saved_sel = tuple(sel)

        if len(sel) == 0:
            sel.add((0, 0))

        point = sel[0].begin() if forward else sel[-1].end()
        regions = sublime.Selection(view.id())
        regions.clear()
        regions.add_all(view.get_regions(highlight.MARK_KEY_FORMAT.format(highlight.WARNING)))
        regions.add_all(view.get_regions(highlight.MARK_KEY_FORMAT.format(highlight.ERROR)))
        region_to_select = None

        # If going forward, find the first region beginning after the point.
        # If going backward, find the first region ending before the point.
        # If nothing is found in the given direction, wrap to the first/last region.
        if forward:
            for region in regions:
                if point < region.begin():
                    region_to_select = region
                    break
        else:
            for region in reversed(regions):
                if point > region.end():
                    region_to_select = region
                    break

        # If there is only one error line and the cursor is in that line, we cannot move.
        # Otherwise wrap to the first/last error line unless settings disallow that.
        if region_to_select is None and ((len(regions) > 1 or not regions[0].contains(point))):
            if persist.settings.get('wrap_find', True):
                region_to_select = regions[0] if forward else regions[-1]

        if region_to_select is not None:
            self.select_lint_region(self.view, region_to_select)
        else:
            sel.clear()
            sel.add_all(saved_sel)
            sublime.message_dialog('No {0} lint errors.'.format('next' if forward else 'previous'))

        return region_to_select

    def select_lint_region(self, view, region):
        sel = view.sel()
        sel.clear()

        # Find the first marked region within the region to select.
        # If there are none, put the cursor at the beginning of the line.
        marked_region = self.find_mark_within(view, region)

        if marked_region is None:
            marked_region = sublime.Region(region.begin(), region.begin())

        sel.add(marked_region)
        view.show(marked_region, show_surrounds=True)

    def find_mark_within(self, view, region):
        marks = view.get_regions(highlight.MARK_KEY_FORMAT.format(highlight.WARNING))
        marks.extend(view.get_regions(highlight.MARK_KEY_FORMAT.format(highlight.ERROR)))
        marks.sort(key=lambda x: x.begin())

        for mark in marks:
            if region.contains(mark):
                return mark

        return None


class sublimelinter_next_error(sublimelinter_find_error):
    '''Place the caret at the next error.'''
    @error_command
    def run(self, view, errors):
        self.find_error(view, errors, forward=True)


class sublimelinter_previous_error(sublimelinter_find_error):
    '''Place the caret at the previous error.'''
    @error_command
    def run(self, view, errors):
        self.find_error(view, errors, forward=False)


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


class sublimelinter_choose_lint_mode(sublime_plugin.WindowCommand):
    '''
    Display a list of all available lint modes and set the mode
    if one is selected.
    '''
    def __init__(self, window):
        super().__init__(window)
        self.modes = [[mode[0].capitalize(), mode[1]] for mode in persist.LINT_MODES]

    def run(self):
        mode = persist.settings.get('lint_mode')
        index = 0

        for i, m in enumerate(self.modes):
            if m[0].lower() == mode:
                index = i
                break

        self.window.show_quick_panel(self.modes, self.set_mode, selected_index=index)

    def set_mode(self, index):
        if index == -1:
            return

        old_mode = persist.settings.get('lint_mode')
        mode = self.modes[index][0].lower()

        if mode == old_mode:
            return

        persist.settings['lint_mode'] = mode

        if mode == 'background':
            from .sublimelinter import SublimeLinter
            SublimeLinter.lint_all_views()
        else:
            linter.Linter.clear_all()

        persist.update_user_settings()


class sublimelinter_choose_mark_style(sublime_plugin.WindowCommand):
    '''
    Display a list of all available styles and set the style
    if one is selected.
    '''
    def __init__(self, window):
        super().__init__(window)

        self.styles = [style.capitalize() for style in persist.MARK_STYLES]

        # Put 'None' at the end of the list
        self.styles.remove('None')
        self.styles.sort()
        self.styles.append('None')

    def run(self):
        self.window.show_quick_panel(self.styles, self.set_style)

    def set_style(self, index):
        if index == -1:
            return

        old_style = persist.settings.get('mark_style')
        style = self.styles[index].lower()

        if style != old_style:
            persist.settings['mark_style'] = style
            persist.update_user_settings()


class sublimelinter_choose_gutter_theme(sublime_plugin.WindowCommand):
    '''
    Display a list of all available gutter themes and set the theme
    if one is selected.
    '''
    def run(self):
        self.themes = []
        self.theme_names = []
        self.find_themes(user_themes=True)
        self.find_themes(user_themes=False)
        self.themes.sort()
        self.themes.append(('None', 'Do not display gutter marks'))
        self.window.show_quick_panel(self.themes, self.set_theme)

    def find_themes(self, user_themes):
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
                        relative_path = os.path.relpath(root, full_path)

                        if relative_path not in self.theme_names:
                            self.themes.append([relative_path, 'User theme' if user_themes else 'SublimeLinter theme'])
                            self.theme_names.append(relative_path)

    def set_theme(self, index):
        if index == -1:
            return

        old_theme = persist.settings.get('gutter_theme')
        theme = self.themes[index][0]

        if theme != old_theme:
            persist.settings['gutter_theme'] = theme
            persist.update_gutter_marks()
            persist.update_user_settings()


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
