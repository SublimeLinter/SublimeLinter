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

from fnmatch import fnmatch
import json
import os
from threading import Thread

import sublime
import sublime_plugin

from .lint import highlight, linter, persist


def error_command(method):
    """
    A decorator that executes method only if the current view has errors.

    This decorator is meant to be used only with the run method of
    sublime_plugin.TextCommand subclasses.

    A wrapped version of method is returned.

    """

    def run(self, edit, **kwargs):
        vid = self.view.id()

        if vid in persist.errors and persist.errors[vid]:
            method(self, self.view, persist.errors[vid], **kwargs)
        else:
            sublime.message_dialog('No lint errors.')

    return run


def select_line(view, line):
    """Change view's selection to be the given line."""
    point = view.text_point(line, 0)
    sel = view.sel()
    sel.clear()
    sel.add(view.line(point))


class SublimelinterLintCommand(sublime_plugin.TextCommand):

    """A command that lints the current view if it has a linter."""

    def is_enabled(self):
        """Return True if the current view has a linter and the lint mode is not "background"."""
        vid = self.view.id()
        return vid in persist.view_linters and persist.settings.get('lint_mode') != 'background'

    def run(self, edit):
        """Lint the current view."""
        from .sublimelinter import SublimeLinter
        SublimeLinter.shared_plugin().lint(self.view.id())


class HasErrorsCommand:

    """
    A mixin class for sublime_plugin.TextCommand subclasses.

    Inheriting from this class will enable the command only if the current view has errors.

    """

    def is_enabled(self):
        """Return True if the current view has errors."""
        vid = self.view.id()
        return vid in persist.errors and len(persist.errors[vid]) > 0


class GotoErrorCommand(sublime_plugin.TextCommand):

    """A superclass for commands that go to the next/previous error."""

    def goto_error(self, view, errors, direction='next'):
        """Go to the next/previous error in view."""
        sel = view.sel()

        if len(sel) == 0:
            sel.add(sublime.Region(0, 0))

        saved_sel = tuple(sel)
        empty_selection = len(sel) == 1 and sel[0].empty()

        # sublime.Selection() changes the view's selection, get the point first
        point = sel[0].begin() if direction == 'next' else sel[-1].end()

        regions = sublime.Selection(view.id())
        regions.clear()

        for error_type in (highlight.WARNING, highlight.ERROR):
            regions.add_all(view.get_regions(highlight.MARK_KEY_FORMAT.format(error_type)))

        region_to_select = None

        # If going forward, find the first region beginning after the point.
        # If going backward, find the first region ending before the point.
        # If nothing is found in the given direction, wrap to the first/last region.
        if direction == 'next':
            for region in regions:
                if (
                    (point == region.begin() and empty_selection and not region.empty())
                    or (point < region.begin())
                ):
                    region_to_select = region
                    break
        else:
            for region in reversed(regions):
                if (
                    (point == region.end() and empty_selection and not region.empty())
                    or (point > region.end())
                ):
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

    @classmethod
    def select_lint_region(cls, view, region):
        """
        Select the first marked region that contains region.

        If none are found, the cursor is placed at the beginning of region.

        """

        sel = view.sel()
        sel.clear()

        marked_region = cls.find_mark_within(view, region)

        if marked_region is None:
            marked_region = sublime.Region(region.begin(), region.begin())

        sel.add(marked_region)
        view.show_at_center(marked_region)

    @classmethod
    def find_mark_within(cls, view, region):
        """Return the nearest marked region that contains region, or None if none found."""

        marks = view.get_regions(highlight.MARK_KEY_FORMAT.format(highlight.WARNING))
        marks.extend(view.get_regions(highlight.MARK_KEY_FORMAT.format(highlight.ERROR)))
        marks.sort(key=sublime.Region.begin)

        for mark in marks:
            if mark.contains(region):
                return mark

        return None


class SublimelinterGotoErrorCommand(GotoErrorCommand):

    """A command that selects the next/previous error."""

    @error_command
    def run(self, view, errors, **kwargs):
        """Run the command."""
        self.goto_error(view, errors, **kwargs)


class SublimelinterShowAllErrors(sublime_plugin.TextCommand):

    """A command that shows a quick panel with all of the errors in the current view."""

    @error_command
    def run(self, view, errors):
        """Run the command."""
        self.errors = errors
        self.points = []
        options = []

        for lineno, line_errors in sorted(errors.items()):
            line = view.substr(view.full_line(view.text_point(lineno, 0))).rstrip('\n\r')

            # Strip whitespace from the front of the line, but keep track of how much was
            # stripped so we can adjust the column.
            diff = len(line)
            line = line.lstrip()
            diff -= len(line)

            max_prefix_len = 40

            for column, message in sorted(line_errors):
                # Keep track of the line and column
                point = view.text_point(lineno, column)
                self.points.append(point)

                # If there are more than max_prefix_len characters before the adjusted column,
                # lop off the excess and insert an ellipsis.
                column = max(column - diff, 0)

                if column > max_prefix_len:
                    visible_line = '...' + line[column - max_prefix_len:]
                    column = max_prefix_len + 3  # 3 for ...
                else:
                    visible_line = line

                # Insert an arrow at the column in the stripped line
                code = visible_line[:column] + '➜' + visible_line[column:]
                options.append(['{}  {}'.format(lineno + 1, message), code])

        view.window().show_quick_panel(options, self.select_error)

    def select_error(self, index):
        """Completion handler for the quick panel. Selects the indexed error."""
        if index != -1:
            point = self.points[index]
            GotoErrorCommand.select_lint_region(self.view, sublime.Region(point, point))


class ToggleSettingCommand(sublime_plugin.WindowCommand):

    """Abstract base class for commands that toggle a setting."""

    def __init__(self, window, setting=None, value=True):
        super().__init__(window)
        self.setting = setting
        self.value = value

    def is_enabled(self):
        """Return True if the opposite of self.setting is True."""
        return persist.settings.get(self.setting) is not self.value

    def set(self):
        """Toggle the setting if self.value is boolean, or remove it if None."""

        if self.value is None:
            persist.settings.pop(self.setting)
        else:
            persist.settings.set(self.setting, self.value)

        persist.settings.save()


class SublimelinterShowErrorsOnSaveCommand(ToggleSettingCommand):

    """A command that sets the "show_errors_on_save" setting to True."""

    def __init__(self, window):
        super().__init__(window, setting='show_errors_on_save', value=True)

    def run(self):
        """Run the command."""
        self.set()


class SublimelinterDontShowErrorsOnSaveCommand(ToggleSettingCommand):

    """A command that sets the "show_errors_on_save" setting to False."""

    def __init__(self, window):
        super().__init__(window, setting='show_errors_on_save', value=False)

    def run(self):
        """Run the command."""
        self.set()


class SublimelinterDisableLintingCommand(ToggleSettingCommand):

    """A command that sets the "@disable" setting to True."""

    def __init__(self, window):
        super().__init__(window, setting='@disable', value=True)

    def run(self):
        """Run the command."""
        self.set()


class SublimelinterDontDisableLintingCommand(ToggleSettingCommand):

    """A command that remove the "@disable" setting."""

    def __init__(self, window):
        super().__init__(window, setting='@disable', value=None)

    def run(self):
        """Run the command."""
        self.set()


class ChooseSettingCommand(sublime_plugin.WindowCommand):

    """An abstract base class for commands that choose a setting from a list."""

    def __init__(self, window, setting=None):
        super().__init__(window)
        self.setting = setting

    def get_settings(self):
        """Return the list of settings. Subclasses must override this."""
        raise NotImplementedError

    def transform_setting(self, setting):
        """
        Transform the display text for setting to the form it is stored in.

        By default, returns a lowercased copy of setting.

        """
        return setting.lower()

    def choose(self, **kwargs):
        """
        Choose or set the setting.

        If 'value' is in kwargs, the setting is set to the corresponding value.
        Otherwise the list of available settings is built via get_settings
        and is displayed in a quick panel. The current value of the setting
        is initially selected in the quick panel.

        """

        self.settings = self.get_settings()

        if 'value' in kwargs:
            setting = self.transform_setting(kwargs['value'])
        else:
            setting = self.transform_setting(persist.settings.get(self.setting))

        index = 0

        for i, s in enumerate(self.settings):
            if isinstance(s, (tuple, list)):
                s = self.transform_setting(s[0])
            else:
                s = self.transform_setting(s)

            if s == setting:
                index = i
                break

        if 'value' in kwargs:
            self.set(index)
        else:
            self.window.show_quick_panel(self.settings, self.set, selected_index=index)

    def set(self, index):
        """Set the value of the setting."""

        if index == -1:
            return

        old_setting = persist.settings.get(self.setting)
        setting = self.selected_setting(index)

        if isinstance(setting, (tuple, list)):
            setting = setting[0]

        setting = self.transform_setting(setting)

        if setting == old_setting:
            return

        persist.settings.set(self.setting, setting)
        self.setting_was_changed(setting)
        persist.settings.save()

    def selected_setting(self, index):
        """
        Return the selected setting by index.

        Subclasses may override this if they want to return something other
        than the indexed value from self.settings.

        """

        return self.settings[index]

    def setting_was_changed(self, setting):
        """
        Do something after the setting value is changed but before settings are saved.

        Subclasses may override this if further action is necessary after
        the setting's value is changed.

        """
        pass


class SublimelinterChooseLintModeCommand(ChooseSettingCommand):

    """A command that selects a lint mode from a list."""

    def __init__(self, window):
        super().__init__(window, 'lint_mode')

    def run(self, **kwargs):
        """Run the command."""
        self.choose(**kwargs)

    def get_settings(self):
        """Return a list of the lint modes."""
        return [[name.capitalize(), description] for name, description in persist.LINT_MODES]

    def setting_was_changed(self, setting):
        """Update all views when the lint mode changes."""
        if setting == 'background':
            from .sublimelinter import SublimeLinter
            SublimeLinter.lint_all_views()
        else:
            linter.Linter.clear_all()


class SublimelinterChooseMarkStyleCommand(ChooseSettingCommand):

    """A command that selects a mark style from a list."""

    def __init__(self, window):
        super().__init__(window, 'mark_style')

    def run(self, **kwargs):
        """Run the command."""
        self.choose(**kwargs)

    def get_settings(self):
        """Return a list of the mark styles."""
        return highlight.mark_style_names()


class SublimelinterChooseGutterThemeCommand(ChooseSettingCommand):

    """A command that selects a gutter theme from a list."""

    def __init__(self, window):
        super().__init__(window, 'gutter_theme')

    def run(self, **kwargs):
        """Run the command."""
        self.choose(**kwargs)

    def get_settings(self):
        """
        Return a list of all available gutter themes, with 'None' at the end.

        Whether the theme is colorized and is a SublimeLinter or user theme
        is indicated below the theme name.

        """

        settings = self.find_gutter_themes()
        settings.append(['None', 'Do not display gutter marks'])
        self.themes.append('none')

        return settings

    def find_gutter_themes(self):
        """
        Find all SublimeLinter.gutter-theme resources.

        For each found resource, if it doesn't match one of the patterns
        from the "gutter_theme_excludes" setting, append to settings the
        base name of resource and info on whether the theme is a standard
        theme or a user theme, as well as whether it is colorized.

        The list of paths to the resources is appended to self.themes.

        """

        self.themes = []
        settings = []
        gutter_themes = sublime.find_resources('*.gutter-theme')
        excludes = persist.settings.get('gutter_theme_excludes', [])
        pngs = sublime.find_resources('*.png')

        for theme in gutter_themes:
            # Make sure the theme has error.png and warning.png
            exclude = False
            parent = os.path.dirname(theme)

            for name in ('error', 'warning'):
                if '{}/{}.png'.format(parent, name) not in pngs:
                    exclude = True

            if exclude:
                continue

            # Now see if the theme name is in gutter_theme_excludes
            name = os.path.splitext(os.path.basename(theme))[0]

            for pattern in excludes:
                if fnmatch(name, pattern):
                    exclude = True
                    break

            if exclude:
                continue

            self.themes.append(theme)

            try:
                info = json.loads(sublime.load_resource(theme))
                colorize = info.get('colorize', False)
            except ValueError:
                colorize = False

            std_theme = theme.startswith('Packages/SublimeLinter/gutter-themes/')

            settings.append([
                name,
                '{}{}'.format(
                    'SublimeLinter theme' if std_theme else 'User theme',
                    ' (colorized)' if colorize else ''
                )
            ])

        # Sort self.themes and settings in parallel using the zip trick
        settings, self.themes = zip(*sorted(zip(settings, self.themes)))

        # zip returns tuples, convert back to lists
        settings = list(settings)
        self.themes = list(self.themes)

        return settings

    def selected_setting(self, index):
        return self.themes[index]

    def transform_setting(self, setting):
        """Return the original setting text, gutter theme settings are not lowercased."""
        return setting


class SublimelinterReportCommand(sublime_plugin.WindowCommand):

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
                    # TODO: not implemented
                    pass

    def report(self, output, view):
        """Write a report on the given view to output."""

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
                            for col, error_type, error in errors:
                                out += '  {}: {}\n'.format(line, error)

                output.insert(edit, output.size(), out)

            persist.edits[output.id()].append(insert)
            output.run_command('sublimelinter_edit')

        args = (view.id(), finish_lint)

        from .sublimelinter import SublimeLinter
        Thread(target=SublimeLinter.lint, args=args).start()
