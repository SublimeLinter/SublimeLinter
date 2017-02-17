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

import datetime
from fnmatch import fnmatch
from glob import glob
import json
import os
import re
import shutil
import subprocess
import tempfile
from textwrap import TextWrapper
from threading import Thread
import time

import sublime
import sublime_plugin

from .lint import highlight, linter, persist, util


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
            method(self, self.view, persist.errors[vid], persist.highlights[vid], **kwargs)
        else:
            sublime.status_message('No lint errors.')

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
        from .sublimelinter import SublimeLinter
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
                    (point == region.begin() and empty_selection and not region.empty()) or
                    (point < region.begin())
                ):
                    region_to_select = region
                    break
        else:
            for region in reversed(regions):
                if (
                    (point == region.end() and empty_selection and not region.empty()) or
                    (point > region.end())
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
    def run(self, view, errors, highlights, **kwargs):
        """Run the command."""
        self.goto_error(view, errors, **kwargs)


class SublimelinterShowAllErrors(sublime_plugin.TextCommand):
    """A command that shows a quick panel with all of the errors in the current view."""

    @error_command
    def run(self, view, errors, highlights):
        """Run the command."""
        self.errors = errors
        self.highlights = highlights
        self.points = []
        options = []

        for lineno, line_errors in sorted(errors.items()):
            if persist.settings.get("passive_warnings", False):
                if self.highlights.line_type(lineno) != highlight.ERROR:
                    continue

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
            GotoErrorCommand.select_lint_region(self.view, sublime.Region(point, point))
        else:
            self.view.set_viewport_position(self.viewport_pos)
            self.view.sel().clear()
            self.view.sel().add_all(self.selection)


class SublimelinterToggleSettingCommand(sublime_plugin.WindowCommand):
    """Command that toggles a setting."""

    def __init__(self, window):
        """Initialize a new instance."""
        super().__init__(window)

    def is_visible(self, **args):
        """Return True if the opposite of the setting is True."""
        if args.get('checked', False):
            return True

        if persist.settings.has_setting(args['setting']):
            setting = persist.settings.get(args['setting'], None)
            return setting is not None and setting is not args['value']
        else:
            return args['value'] is not None

    def is_checked(self, **args):
        """Return True if the setting should be checked."""
        if args.get('checked', False):
            setting = persist.settings.get(args['setting'], False)
            return setting is True
        else:
            return False

    def run(self, **args):
        """Toggle the setting if value is boolean, or remove it if None."""

        if 'value' in args:
            if args['value'] is None:
                persist.settings.pop(args['setting'])
            else:
                persist.settings.set(args['setting'], args['value'], changed=True)
        else:
            setting = persist.settings.get(args['setting'], False)
            persist.settings.set(args['setting'], not setting, changed=True)

        persist.settings.save()


class ChooseSettingCommand(sublime_plugin.WindowCommand):
    """An abstract base class for commands that choose a setting from a list."""

    def __init__(self, window, setting=None, preview=False):
        """Initialize a new instance."""
        super().__init__(window)
        self.setting = setting
        self._settings = None
        self.preview = preview

    def description(self, **args):
        """Return the visible description of the command, used in menus."""
        return args.get('value', None)

    def is_checked(self, **args):
        """Return whether this command should be checked in a menu."""
        if 'value' not in args:
            return False

        item = self.transform_setting(args['value'], matching=True)
        setting = self.setting_value(matching=True)
        return item == setting

    def _get_settings(self):
        """Return the list of settings."""
        if self._settings is None:
            self._settings = self.get_settings()

        return self._settings

    settings = property(_get_settings)

    def get_settings(self):
        """Return the list of settings. Subclasses must override this."""
        raise NotImplementedError

    def transform_setting(self, setting, matching=False):
        """
        Transform the display text for setting to the form it is stored in.

        By default, returns a lowercased copy of setting.

        """
        return setting.lower()

    def setting_value(self, matching=False):
        """Return the current value of the setting."""
        return self.transform_setting(persist.settings.get(self.setting, ''), matching=matching)

    def on_highlight(self, index):
        """If preview is on, set the selected setting."""
        if self.preview:
            self.set(index)

    def choose(self, **kwargs):
        """
        Choose or set the setting.

        If 'value' is in kwargs, the setting is set to the corresponding value.
        Otherwise the list of available settings is built via get_settings
        and is displayed in a quick panel. The current value of the setting
        is initially selected in the quick panel.

        """

        if 'value' in kwargs:
            setting = self.transform_setting(kwargs['value'])
        else:
            setting = self.setting_value(matching=True)

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
            self.previous_setting = self.setting_value()

            self.window.show_quick_panel(
                self.settings,
                on_select=self.set,
                selected_index=index,
                on_highlight=self.on_highlight)

    def set(self, index):
        """Set the value of the setting."""

        if index == -1:
            if self.settings_differ(self.previous_setting, self.setting_value()):
                self.update_setting(self.previous_setting)

            return

        setting = self.selected_setting(index)

        if isinstance(setting, (tuple, list)):
            setting = setting[0]

        setting = self.transform_setting(setting)

        if not self.settings_differ(persist.settings.get(self.setting, ''), setting):
            return

        self.update_setting(setting)

    def update_setting(self, value):
        """Update the setting with the given value."""
        persist.settings.set(self.setting, value, changed=True)
        self.setting_was_changed(value)
        persist.settings.save()

    def settings_differ(self, old_setting, new_setting):
        """Return whether two setting values differ."""
        if isinstance(new_setting, (tuple, list)):
            new_setting = new_setting[0]

        new_setting = self.transform_setting(new_setting)
        return new_setting != old_setting

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


def choose_setting_command(setting, preview):
    """Return a decorator that provides common methods for concrete subclasses of ChooseSettingCommand."""

    def decorator(cls):
        def init(self, window):
            super(cls, self).__init__(window, setting, preview)

        def run(self, **kwargs):
            """Run the command."""
            self.choose(**kwargs)

        cls.setting = setting
        cls.__init__ = init
        cls.run = run
        return cls

    return decorator


@choose_setting_command('lint_mode', preview=False)
class SublimelinterChooseLintModeCommand(ChooseSettingCommand):
    """A command that selects a lint mode from a list."""

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


@choose_setting_command('mark_style', preview=True)
class SublimelinterChooseMarkStyleCommand(ChooseSettingCommand):
    """A command that selects a mark style from a list."""

    def get_settings(self):
        """Return a list of the mark styles."""
        return highlight.mark_style_names()


@choose_setting_command('gutter_theme', preview=True)
class SublimelinterChooseGutterThemeCommand(ChooseSettingCommand):
    """A command that selects a gutter theme from a list."""

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
        from the "gutter_theme_excludes" setting, return the base name
        of resource and info on whether the theme is a standard theme
        or a user theme, as well as whether it is colorized.

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
        """Return the theme name with the given index."""
        return self.themes[index]

    def transform_setting(self, setting, matching=False):
        """
        Return a transformed version of setting.

        For gutter themes, setting is a Packages-relative path
        to a .gutter-theme file.

        If matching == False, return the original setting text,
        gutter theme settings are not lowercased.

        If matching == True, return the base name of the filename
        without the .gutter-theme extension.

        """

        if matching:
            return os.path.splitext(os.path.basename(setting))[0]
        else:
            return setting


@choose_setting_command('tooltip_theme', preview=True)
class SublimelinterChooseTooltipThemeCommand(ChooseSettingCommand):
    """A command that selects a tooltip theme from a list."""

    def get_settings(self):
        """
        Return a list of all available Tooltip themes, with 'None' at the end.

        Whether the theme is colorized and is a SublimeLinter or user theme
        is indicated below the theme name.

        """

        settings = self.find_tooltip_themes()
        settings.append(['None', 'Do not display tooltip'])
        self.themes.append('none')

        return settings

    def find_tooltip_themes(self):
        """
        Find all SublimeLinter.tooltip-theme resources.

        For each found resource, if it doesn't match one of the patterns
        from the "tooltip_theme_excludes" setting, return the base name
        of resource and info on whether the theme is a standard theme
        or a user theme, as well as whether it is colorized.

        The list of paths to the resources is appended to self.themes.

        """

        self.themes = []
        settings = []
        tooltip_themes = sublime.find_resources('*.tooltip-theme')
        excludes = persist.settings.get('tooltip_theme_excludes', [])

        for theme in tooltip_themes:
            exclude = False
            parent = os.path.dirname(theme)
            htmls = sublime.find_resources('*.html')

            if '{}/tooltip.html'.format(parent) not in htmls:
                continue

            # Now see if the theme name is in tooltip_theme_excludes
            name = os.path.splitext(os.path.basename(theme))[0]

            for pattern in excludes:
                if fnmatch(name, pattern):
                    exclude = True
                    break

            if exclude:
                continue

            self.themes.append(theme)

            std_theme = theme.startswith('Packages/SublimeLinter/tooltip-themes/')

            settings.append([
                name,
                'SublimeLinter theme' if std_theme else 'User theme'
            ])

        # Sort self.themes and settings in parallel using the zip trick
        settings, self.themes = zip(*sorted(zip(settings, self.themes)))

        # zip returns tuples, convert back to lists
        settings = list(settings)
        self.themes = list(self.themes)

        return settings

    def selected_setting(self, index):
        """Return the theme name with the given index."""
        return self.themes[index]

    def transform_setting(self, setting, matching=False):
        """
        Return a transformed version of setting.

        For Tooltip themes, setting is a Packages-relative path
        to a .tooltip-theme file.

        If matching == False, return the original setting text,
        tooltip theme settings are not lowercased.

        If matching == True, return the base name of the filename
        without the .tooltip-theme extension.

        """

        if matching:
            return os.path.splitext(os.path.basename(setting))[0]
        else:
            return setting


class SublimelinterToggleLinterCommand(sublime_plugin.WindowCommand):
    """A command that toggles, enables, or disables linter plugins."""

    def __init__(self, window):
        """Initialize a new instance."""
        super().__init__(window)
        self.linters = {}

    def is_visible(self, **args):
        """Return True if the command would show any linters."""
        which = args['which']

        if self.linters.get(which) is None:
            linters = []
            settings = persist.settings.get('linters', {})

            for instance in persist.linter_classes:
                linter_settings = settings.get(instance, {})
                disabled = linter_settings.get('@disable')

                if which == 'all':
                    include = True
                    instance = [instance, 'disabled' if disabled else 'enabled']
                else:
                    include = (
                        which == 'enabled' and not disabled or
                        which == 'disabled' and disabled
                    )

                if include:
                    linters.append(instance)

            linters.sort()
            self.linters[which] = linters

        return len(self.linters[which]) > 0

    def run(self, **args):
        """Run the command."""
        self.which = args['which']

        if self.linters[self.which]:
            self.window.show_quick_panel(self.linters[self.which], self.on_done)

    def on_done(self, index):
        """Completion handler for quick panel, toggle the enabled state of the chosen linter."""
        if index != -1:
            linter = self.linters[self.which][index]

            if isinstance(linter, list):
                linter = linter[0]

            settings = persist.settings.get('linters', {})
            linter_settings = settings.get(linter, {})
            linter_settings['@disable'] = not linter_settings.get('@disable', False)
            persist.settings.set('linters', settings, changed=True)
            persist.settings.save()

        self.linters = {}


class SublimelinterCreateLinterPluginCommand(sublime_plugin.WindowCommand):
    """A command that creates a new linter plugin."""

    def run(self):
        """Run the command."""
        if not sublime.ok_cancel_dialog(
            'You will be asked for the linter name. Please enter the name '
            'of the linter binary (including dashes), NOT the name of the language being linted. '
            'For example, to lint CSS with csslint, the linter name is '
            '“csslint”, NOT “css”.',
            'I understand'
        ):
            return

        self.window.show_input_panel(
            'Linter name:',
            '',
            on_done=self.copy_linter,
            on_change=None,
            on_cancel=None)

    def copy_linter(self, name):
        """Copy the template linter to a new linter with the given name."""

        self.name = name
        self.fullname = 'SublimeLinter-contrib-{}'.format(name)
        self.dest = os.path.join(sublime.packages_path(), self.fullname)

        if os.path.exists(self.dest):
            sublime.error_message('The plugin “{}” already exists.'.format(self.fullname))
            return

        src = os.path.join(sublime.packages_path(), persist.PLUGIN_DIRECTORY, 'linter-plugin-template')
        self.temp_dir = None

        try:
            self.temp_dir = tempfile.mkdtemp()
            self.temp_dest = os.path.join(self.temp_dir, self.fullname)
            shutil.copytree(src, self.temp_dest)

            self.get_linter_language(name, self.configure_linter)

        except Exception as ex:
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)

            sublime.error_message('An error occurred while copying the template plugin: {}'.format(str(ex)))

    def configure_linter(self, language):
        """Fill out the template and move the linter into Packages."""

        try:
            if language is None:
                return

            if not self.fill_template(self.temp_dir, self.name, self.fullname, language):
                return

            git = util.which('git')

            if git:
                subprocess.call((git, 'init', self.temp_dest))

            shutil.move(self.temp_dest, self.dest)

            util.open_directory(self.dest)
            self.wait_for_open(self.dest)

        except Exception as ex:
            sublime.error_message('An error occurred while configuring the plugin: {}'.format(str(ex)))

        finally:
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)

    def get_linter_language(self, name, callback):
        """Get the language (python, node, etc.) on which the linter is based."""

        languages = ['javascript', 'python', 'ruby', 'other']
        items = ['Select the language on which the linter is based:']

        for language in languages:
            items.append('    ' + language.capitalize())

        def on_done(index):
            language = languages[index - 1] if index > 0 else None
            callback(language)

        self.window.show_quick_panel(items, on_done)

    def fill_template(self, template_dir, name, fullname, language):
        """Replace placeholders and fill template files in template_dir, return success."""

        # Read per-language info
        path = os.path.join(os.path.dirname(__file__), 'create_linter_info.json')

        with open(path, mode='r', encoding='utf-8') as f:
            try:
                info = json.load(f)
            except Exception as err:
                persist.printf(err)
                sublime.error_message('A configuration file could not be opened, the linter cannot be created.')
                return False

        info = info.get(language, {})
        extra_attributes = []
        comment_re = info.get('comment_re', 'None')
        extra_attributes.append('comment_re = ' + comment_re)

        attributes = info.get('attributes', [])

        for attr in attributes:
            extra_attributes.append(attr.format(name))

        extra_attributes = '\n    '.join(extra_attributes)

        if extra_attributes:
            extra_attributes += '\n'

        extra_steps = info.get('extra_steps', '')

        if isinstance(extra_steps, list):
            extra_steps = '\n\n'.join(extra_steps)

        if extra_steps:
            extra_steps = '\n' + extra_steps + '\n'

        platform = info.get('platform', language.capitalize())

        # Replace placeholders
        placeholders = {
            '__linter__': name,
            '__user__': util.get_user_fullname(),
            '__year__': str(datetime.date.today().year),
            '__class__': self.camel_case(name),
            '__superclass__': info.get('superclass', 'Linter'),
            '__cmd__': '{}@python'.format(name) if language == 'python' else name,
            '# __extra_attributes__': extra_attributes,
            '__platform__': platform,
            '__install__': info['installer'].format(name),
            '__extra_install_steps__': extra_steps
        }

        for root, dirs, files in os.walk(template_dir):
            for filename in files:
                extension = os.path.splitext(filename)[1]

                if extension in ('.py', '.md', '.txt'):
                    path = os.path.join(root, filename)

                    with open(path, encoding='utf-8') as f:
                        text = f.read()

                    for placeholder, value in placeholders.items():
                        text = text.replace(placeholder, value)

                    with open(path, mode='w', encoding='utf-8') as f:
                        f.write(text)

        return True

    def camel_case(self, name):
        """Convert and return a name in the form foo-bar to FooBar."""
        camel_name = name[0].capitalize()
        i = 1

        while i < len(name):
            if name[i] == '-' and i < len(name) - 1:
                camel_name += name[i + 1].capitalize()
                i += 1
            else:
                camel_name += name[i]

            i += 1

        return camel_name

    def wait_for_open(self, dest):
        """Wait for new linter window to open in another thread."""

        def open_linter_py():
            """Wait until the new linter window has opened and open linter.py."""

            start = datetime.datetime.now()

            while True:
                time.sleep(0.25)
                delta = datetime.datetime.now() - start

                # Wait a maximum of 5 seconds
                if delta.seconds > 5:
                    break

                window = sublime.active_window()
                folders = window.folders()

                if folders and folders[0] == dest:
                    window.open_file(os.path.join(dest, 'linter.py'))
                    break

        sublime.set_timeout_async(open_linter_py, 0)


class SublimelinterPackageControlCommand(sublime_plugin.WindowCommand):
    """
    Abstract superclass for Package Control utility commands.

    Only works if git is installed.

    """

    TAG_RE = re.compile(r'(?P<major>\d+)\.(?P<minor>\d+)\.(?P<release>\d+)(?:\+\d+)?')

    def __init__(self, window):
        """Initialize a new instance."""
        super().__init__(window)
        self.git = ''

    def is_visible(self, paths=[]):
        """Return True if any eligible plugin directories are selected."""

        if self.git == '':
            self.git = util.which('git')

        if self.git:
            for path in paths:
                if self.is_eligible_path(path):
                    return True

        return False

    def is_eligible_path(self, path):
        """
        Return True if path is an eligible directory.

        A directory is eligible if it has a messages subdirectory
        and has messages.json.

        """
        return (
            os.path.isdir(path) and
            os.path.isdir(os.path.join(path, 'messages')) and
            os.path.isfile(os.path.join(path, 'messages.json'))
        )

    def get_current_tag(self):
        """
        Return the most recent tag components.

        A tuple of (major, minor, release) is returned, or (1, 0, 0) if there are no tags.
        If the most recent tag does not conform to semver, return (None, None, None).

        """

        tag = util.communicate(['git', 'describe', '--tags', '--abbrev=0']).strip()

        if not tag:
            return (1, 0, 0)

        match = self.TAG_RE.match(tag)

        if match:
            return (int(match.group('major')), int(match.group('minor')), int(match.group('release')))
        else:
            return None


class SublimelinterNewPackageControlMessageCommand(SublimelinterPackageControlCommand):
    """
    This command automates the process of creating new Package Control release messages.

    It creates a new entry in messages.json for the next version
    and creates a new file named messages/<version>.txt.

    """

    COMMIT_MSG_RE = re.compile(r'{{{{(.+?)}}}}')

    def __init__(self, window):
        """Initialize a new instance."""
        super().__init__(window)

    def run(self, paths=[]):
        """Run the command."""

        for path in paths:
            if self.is_eligible_path(path):
                self.make_new_version_message(path)

    def make_new_version_message(self, path):
        """Make a new version message for the repo at the given path."""

        try:
            cwd = os.getcwd()
            os.chdir(path)

            version = self.get_current_tag()

            if version[0] is None:
                return

            messages_path = os.path.join(path, 'messages.json')
            message_path = self.rewrite_messages_json(messages_path, version)

            if os.path.exists(message_path):
                os.remove(message_path)

            with open(message_path, mode='w', encoding='utf-8') as f:
                header = '{} {}'.format(
                    os.path.basename(path),
                    os.path.splitext(os.path.basename(message_path))[0])
                f.write('{}\n{}\n'.format(header, '-' * (len(header) + 1)))
                f.write(self.get_commit_messages_since(version))

            self.window.run_command('open_file', args={'file': message_path})

        except Exception:
            import traceback
            traceback.print_exc()
        finally:
            os.chdir(cwd)

    def rewrite_messages_json(self, messages_path, tag):
        """Add an entry in messages.json for tag, return relative path to the file."""

        with open(messages_path, encoding='utf-8') as f:
            messages = json.load(f)

        major, minor, release = tag
        release += 1
        tag = '{}.{}.{}'.format(major, minor, release)
        message_path = os.path.join('messages', '{}.txt'.format(tag))
        messages[tag] = message_path
        message_path = os.path.join(os.path.dirname(messages_path), message_path)

        with open(messages_path, mode='w', encoding='utf-8') as f:
            messages_json = '{\n'
            sorted_messages = []

            if 'install' in messages:
                install_message = messages.pop('install')
                sorted_messages.append('    "install": "{}"'.format(install_message))

            keys = sorted(map(self.sortable_tag, messages.keys()))

            for _, key in keys:
                sorted_messages.append('    "{}": "{}"'.format(key, messages[key]))

            messages_json += ',\n'.join(sorted_messages)
            messages_json += '\n}\n'
            f.write(messages_json)

        return message_path

    def sortable_tag(self, tag):
        """Return a version tag in a sortable form."""

        if tag == 'install':
            return (tag, tag)

        major, minor, release = tag.split('.')

        if '+' in release:
            release, update = release.split('+')
            update = '+{:04}'.format(int(update))
        else:
            update = ''

        return ('{:04}.{:04}.{:04}{}'.format(int(major), int(minor), int(release), update), tag)

    def get_commit_messages_since(self, version):
        """Return a formatted list of commit messages since the given tagged version."""

        tag = '{}.{}.{}'.format(*version)
        output = util.communicate([
            'git', 'log',
            '--pretty=format:{{{{%w(0,0,0)%s %b}}}}',
            '--reverse', tag + '..'
        ])

        # Split the messages, they are bounded by {{{{ }}}}
        messages = []

        for match in self.COMMIT_MSG_RE.finditer(output):
            messages.append(match.group(1).strip())

        # Wrap the messages
        wrapper = TextWrapper(initial_indent='- ', subsequent_indent='  ')
        messages = list(map(lambda msg: '\n'.join(wrapper.wrap(msg)), messages))
        return '\n\n'.join(messages) + '\n'


class SublimelinterClearColorSchemeFolderCommand(sublime_plugin.WindowCommand):
    """A command that clears all of SublimeLinter made color schemes."""

    def run(self):
        """Run the command."""
        base_path = os.path.join(sublime.packages_path(), 'User', '*.tmTheme')
        sublime_path = os.path.join(sublime.packages_path(), 'User', 'SublimeLinter', '*.tmTheme')
        themes = glob(base_path) + glob(sublime_path)
        prefs = sublime.load_settings('Preferences.sublime-settings')
        scheme = prefs.get('color_scheme')

        for theme in themes:
            # Ensure it is a (SL) theme and it is not current current scheme
            if re.search(r'\(SL\)', theme) and os.path.normpath(scheme) not in theme:
                persist.debug('deleting {}'.format(os.path.split(theme)[1]))
                os.remove(theme)


class SublimelinterClearCachesCommand(sublime_plugin.WindowCommand):
    """A command that clears all of SublimeLinter's internal caches."""

    def run(self):
        """Run the command."""
        util.clear_path_caches()
        util.get_rc_settings.cache_clear()
        util.find_file.cache_clear()
        linter.Linter.clear_settings_caches()


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

        from .sublimelinter import SublimeLinter
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
                    # TODO: not implemented
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
                            for col, message in messages:
                                out += '    {:>{width}}: {}\n'.format(line + 1, message, width=width)

                output.insert(edit, output.size(), out)

            persist.edits[output.id()].append(insert)
            output.run_command('sublimelinter_edit')

        kwargs = {'self': self.plugin, 'view_id': view.id(), 'callback': finish_lint}

        from .sublimelinter import SublimeLinter
        Thread(target=SublimeLinter.lint, kwargs=kwargs).start()
