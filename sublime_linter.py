#
# sublimelinter.py
# Part of SublimeLinter3, a code checking framework for Sublime Text 3
#
# Written by Ryan Hileman and Aparajita Fishman
#
# Project: https://github.com/SublimeLinter/SublimeLinter3
# License: MIT
#

"""This module provides the SublimeLinter plugin class and supporting methods."""

import os
import re

import sublime
import sublime_plugin

from .lint.linter import Linter
from .lint.highlight import HighlightSet, RegionStore
from .lint.queue import queue
from .lint import persist, util, scheme
from .lint.const import SETTINGS_FILE, WARNING, ERROR, WARN_ERR

STATUS_KEY = "sublime_linter_status"


def plugin_loaded():
    """Entry point for SL plugins."""

    persist.plugin_is_loaded = True
    persist.settings.load()

    # remove the two lines below to unlink legacy.py
    from .lint.legacy import legacy_check

    @legacy_check
    def set_scheme():
        return scheme.JsonScheme()

    persist.scheme = set_scheme()
    persist.scheme.generate(from_reload=False)

    persist.printf('debug mode:', 'on' if persist.debug_mode() else 'off')
    util.create_tempdir()

    persist.region_store = RegionStore()

    for linter in persist.linter_classes.values():
        linter.initialize()

    plugin = SublimeLinter.shared_plugin()
    queue.start(plugin.lint)

    persist.settings.on_update_call(SublimeLinter.on_settings_updated)

    # This ensures we lint the active view on a fresh install
    window = sublime.active_window()

    if window:
        plugin.on_activated_async(window.active_view())


class SublimeLinter(sublime_plugin.EventListener):
    """The main ST3 plugin class."""

    # We use this to match linter settings filenames.
    LINTER_SETTINGS_RE = re.compile(r'^SublimeLinter(-.+?)?\.sublime-settings')

    shared_instance = None

    @classmethod
    def shared_plugin(cls):
        """Return the plugin instance."""
        return cls.shared_instance

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Keeps track of which views we have assigned linters to
        self.loaded_views = set()

        # Keeps track of which views have actually been linted
        self.linted_views = set()

        # A mapping between view ids and syntax names
        self.view_syntax = {}

        self.__class__.shared_instance = self

    @classmethod
    def lint_all_views(cls):
        """Simulate a modification of all views, which will trigger a relint."""

        def apply(view):
            if view.id() in persist.view_linters:
                cls.shared_instance.hit(view)

        util.apply_to_all_views(apply)

    def lint(self, view_id, hit_time=None, callback=None):
        """
        Lint the view with the given id.

        This method is called asynchronously by queue.Daemon when a lint
        request is pulled off the queue.

        If provided, hit_time is the time at which the lint request was added
        to the queue. It is used to determine if the view has been modified
        since the lint request was queued. If so, the lint is aborted, since
        another lint request is already in the queue.

        callback is the method to call when the lint is finished. If not
        provided, it defaults to highlight().

        """

        # If the view has been modified since the lint was triggered,
        # don't lint again.
        if hit_time and persist.last_hit_times.get(view_id, 0) > hit_time:
            return

        view = Linter.get_view(view_id)

        if not view:
            return

        filename = view.file_name()
        code = Linter.text(view)
        callback = callback or self.highlight
        Linter.lint_view(view, filename, code, hit_time, callback)

    def highlight(self, view, linters, hit_time):
        """
        Highlight any errors found during a lint of the given view.

        This method is called by Linter.lint_view after linting is finished.

        linters is a list of the linters that ran. hit_time has the same meaning
        as in lint(), and if the view was modified since the lint request was
        made, this method aborts drawing marks.

        If the view has not been modified since hit_time, all of the marks and
        errors from the list of linters are aggregated and drawn, and the status is updated.

        """

        if not view:
            return

        vid = view.id()

        # If the view has been modified since the lint was triggered,
        # don't draw marks.
        if hit_time and persist.last_hit_times.get(vid, 0) > hit_time:
            return

        errors = {}
        highlights = persist.highlights[vid] = HighlightSet()
        persist.warn_err_count = {}

        for linter in linters:
            if linter.highlight:
                highlights.add(linter.highlight)

            if linter.errors:
                for line, errs in linter.errors.items():
                    l_err = errors.setdefault(line, {})
                    for err_t in WARN_ERR:
                        l_err.setdefault(err_t, []).extend(errs.get(err_t, []))

        # Keep track of one view in each window that shares view's buffer
        window_views = {}
        buffer_id = view.buffer_id()

        for window in sublime.windows():
            wid = window.id()

            for other_view in window.views():
                if other_view.buffer_id() == buffer_id:
                    vid = other_view.id()
                    persist.highlights[vid] = highlights
                    highlights.clear(other_view)
                    highlights.draw(other_view)
                    persist.errors[vid] = errors
                    persist.warn_err_count[vid] = self.count_we(errors)

                    if not window_views.get(wid):
                        window_views[wid] = other_view

        for view in window_views.values():
            self.display_errors(view)

    def hit(self, view):
        """Record an activity that could trigger a lint and enqueue a desire to lint."""

        if not view:
            return

        vid = view.id()
        self.check_syntax(view)
        self.linted_views.add(vid)

        if view.size() == 0:
            for linter in Linter.get_linters(vid):
                linter.clear()
            return

        persist.last_hit_times[vid] = queue.hit(view)

    def check_syntax(self, view):
        """
        Check and return if view's syntax has changed.

        If the syntax has changed, a new linter is assigned.

        """

        if not view:
            return

        vid = view.id()
        syntax = persist.get_syntax(view)

        # Syntax either has never been set or just changed
        if vid not in self.view_syntax or self.view_syntax[vid] != syntax:
            self.view_syntax[vid] = syntax
            Linter.assign(view, reset=True)
            self.clear(view)
            return True
        else:
            return False

    def clear(self, view):
        if not view:
            return

        Linter.clear_view(view)

    def is_scratch(self, view):
        """
        Return whether a view is effectively scratch.

        There is a bug (or feature) in the current ST3 where the Find panel
        is not marked scratch but has no window.

        There is also a bug where settings files opened from within .sublime-package
        files are not marked scratch during the initial on_modified event, so we have
        to check that a view with a filename actually exists on disk if the file
        being opened is in the Sublime Text packages directory.

        """

        if view.is_scratch() or view.is_read_only() or not view.window() or view.settings().get("repl"):
            return True
        elif (
            view.file_name() and
            view.file_name().startswith(sublime.packages_path() + os.path.sep) and
            not os.path.exists(view.file_name())
        ):
            return True
        else:
            return False

    def view_has_file_only_linter(self, vid):
        """Return True if any linters for the given view are file-only."""
        for lint in persist.view_linters.get(vid, []):
            if lint.tempfile_suffix == '-':
                return True

        return False

    # sublime_plugin.EventListener event handlers

    def on_modified_async(self, view):
        """Ran when view is motified."""

        if self.is_scratch(view):
            return

        if view.id() not in persist.view_linters:
            syntax_changed = self.check_syntax(view)

            if not syntax_changed:
                return
        else:
            syntax_changed = False

        if syntax_changed or persist.settings.get('lint_mode') == 'background':
            self.hit(view)
        # else:
        #     self.clear(view)

    def on_activated_async(self, view):
        """Ran when a view gains input focus."""

        if self.is_scratch(view):
            return

        # Reload the plugin settings.
        persist.settings.load()

        self.check_syntax(view)
        view_id = view.id()

        if view_id not in self.linted_views:
            if view_id not in self.loaded_views:
                self.on_new_async(view)

            if persist.settings.get('lint_mode') in ('background', 'load_save'):
                self.hit(view)

        self.display_errors(view)

    def on_open_settings(self, view):
        """
        Ran when any settings file is opened.

        view is the view that contains the text of the settings file.

        """
        if self.is_settings_file(view, user_only=True):
            persist.settings.save(view=view)

    def is_settings_file(self, view, user_only=False):
        """Return True if view is a SublimeLinter settings file."""

        filename = view.file_name()

        if not filename:
            return False

        if not filename.startswith(sublime.packages_path()):
            return False

        dirname, filename = os.path.split(filename)
        dirname = os.path.basename(dirname)

        if self.LINTER_SETTINGS_RE.match(filename):
            if user_only:
                return dirname == 'User'
            else:
                return dirname in (persist.PLUGIN_DIRECTORY, 'User')

    @classmethod
    def on_settings_updated(cls, relint=False):
        """Ran when the settings are updated."""
        if relint:
            cls.lint_all_views()
        else:
            Linter.redraw_all()

    def on_new_async(self, view):
        """Ran when a new buffer is created."""
        self.on_open_settings(view)

        if self.is_scratch(view):
            return

        vid = view.id()
        self.loaded_views.add(vid)
        self.view_syntax[vid] = persist.get_syntax(view)

    def get_focused_view_id(self, view):
        """
        Return the focused view which shares view's buffer.

        When updating the status, we want to make sure we get
        the selection of the focused view, since multiple views
        into the same buffer may be open.

        """
        active_view = self.get_active_view(view)
        if not active_view:
            return

        for view in view.window().views():
            if view == active_view:
                return view

    def get_line_and_col(self, view):
        try:
            lineno, colno = view.rowcol(view.sel()[0].begin())
        except IndexError:
            lineno, colno = -1, -1

        return lineno, colno

    def get_view_dict(self, view):
        if self.is_scratch(view):
            return

        view = self.get_focused_view_id(view)

        if not view:
            return

        return persist.errors.get(view.id())

    def msg_count(self, l_dict):
        w_count = len(l_dict.get("warning", []))
        e_count = len(l_dict.get("error", []))
        return w_count, e_count

    def count_we(self, v_dict):
        tups = [self.msg_count(v) for v in v_dict.values()]
        we = [sum(x) for x in zip(*tups)]
        if not we:
            return
        return {WARNING: we[0], ERROR: we[1]}

    def on_selection_modified_async(self, view):
        self.display_errors(view)

    def display_errors(self, view):
        """
        Display lint errors in the statusbar of the current view
        """

        lineno, colno = self.get_line_and_col(view)

        view_dict = self.get_view_dict(view)
        if not view_dict:
            view.erase_status(STATUS_KEY)
            return

        we_count = persist.warn_err_count.get(view.id())
        if not we_count:
            view.erase_status(STATUS_KEY)
            return

        status = "W: {warning} E: {error}".format(**we_count)

        line_dict = view_dict.get(lineno)
        if not line_dict:
            view.set_status(STATUS_KEY, status)
            return

        msgs = []
        point = view.text_point(lineno, colno)

        for error_type, dc in line_dict.items():
            for d in dc:
                region = d.get("region")
                if region:
                    if region.contains(point):
                        msgs.append(d["msg"])
                elif colno == 0:
                    msgs.append(d["msg"])

        if msgs:
            status += " - {}".format("; ".join(msgs))

        if status != view.get_status(STATUS_KEY):
            view.set_status(STATUS_KEY, status)

    def get_active_view(self, view=None):
        if view:
            return view.window().active_view()

        return sublime.active_window().active_view()

    def open_tooltip(self, active_view=None, lineno=None, show_clean=True):
        """ Show a tooltip containing all linting errors on a given line. """

        stylesheet = '''
            body {
                word-wrap: break-word;
            }
            .error {
                color: var(--redish);
                font-weight: bold;
            }
            .warning {
                color: var(--yellowish);
                font-weight: bold;
            }
        '''

        template = '''
            <body id="sublimelinter-tooltip">
                <style>{stylesheet}</style>
                <div>{message}</div>
            </body>
        '''

        part = '''
            <div class="{classname}">{count} {heading}</div>
            <div>{messages}</div>
        '''

        if not active_view:
            active_view = self.get_active_view()

        # Leave any existing popup open without replacing it
        if active_view.is_popup_visible():
            return

        if not lineno:
            lineno, colno = self.get_line_and_col(active_view)

        view_dict = self.get_view_dict(active_view)
        if not view_dict:
            return

        line_dict = view_dict.get(lineno)

        if not line_dict:
            if not show_clean:  # do not show tooltip on hovering empty gutter
                return
            tooltip_message = "No errors"

        else:
            w_count, e_count = self.msg_count(line_dict)

            def join_msgs(error_type, count, heading):
                combined_msg_tmpl = "{linter}: {code} - {msg}"
                msgs = []
                msg_list = line_dict.get(error_type)

                if not msg_list:
                    return ""
                for item in msg_list:
                    msgs.append(combined_msg_tmpl.format(**item))

                return part.format(
                    classname=error_type,
                    count=count,
                    messages='<br />'.join(msgs),
                    heading=heading
                )

            if w_count > 1:
                tooltip_message = join_msgs("warning", w_count, "Warnings")
            else:
                tooltip_message = join_msgs("warning", w_count, "Warning")
            if e_count > 1:
                tooltip_message += join_msgs("error", e_count, "Errors")
            else:
                tooltip_message += join_msgs("error", e_count, "Error")

        # place at beginning of line
        location = active_view.text_point(lineno, 0)
        active_view.show_popup(
            template.format(stylesheet=stylesheet, message=tooltip_message),
            flags=sublime.HIDE_ON_MOUSE_MOVE_AWAY,
            location=location,
            max_width=1000)

    def on_post_save_async(self, view):
        if self.is_scratch(view):
            return

        # First check to see if the project settings changed
        if view.window().project_file_name() == view.file_name():
            self.lint_all_views()
        else:
            # Now see if a .sublimelinterrc has changed
            filename = os.path.basename(view.file_name())

            if filename == '.sublimelinterrc':
                # If a .sublimelinterrc has changed, to be safe
                # clear the rc cache and relint.
                util.get_rc_settings.cache_clear()
                self.lint_all_views()

            # If a file other than one of our settings files changed,
            # check if the syntax changed or if we need to show errors.
            elif filename != SETTINGS_FILE:
                self.file_was_saved(view)

    def file_was_saved(self, view):
        """Check if the syntax changed or if we need to show errors."""
        syntax_changed = self.check_syntax(view)
        vid = view.id()
        mode = persist.settings.get('lint_mode')
        show_errors = persist.settings.get('show_errors_on_save')

        if syntax_changed:
            self.clear(view)

            if vid in persist.view_linters:
                if mode != 'manual':
                    self.hit(view)
                else:
                    show_errors = False
            else:
                show_errors = False
        else:
            if show_errors:
                # if showing errors on save, linting must be synchronized.
                self.lint(vid)
            elif (
                mode == 'load_save' or
                mode == 'background' and self.view_has_file_only_linter(vid)
            ):
                self.hit(view)
            elif mode == 'manual':
                show_errors = False

        if show_errors and vid in persist.errors and persist.errors[vid]:
            view.run_command('sublimelinter_show_all_errors')

    def on_pre_close_async(self, view):
        if self.is_scratch(view):
            return

        vid = view.id()

        dicts = [
            self.loaded_views, self.linted_views, self.view_syntax, persist.errors,
            persist.warn_err_count, persist.highlights, persist.view_linters,
            persist.views, persist.last_hit_times
        ]

        for d in dicts:
            d.pop(vid, None)

    def on_hover(self, view, point, hover_zone):
        """Arguments:
            view (View): The view which received the event.
            point (Point): The text position where the mouse hovered
            hover_zone (int): The context the event was triggered in
        """
        if hover_zone != sublime.HOVER_GUTTER:
            return

        # don't let the popup flicker / fight with other packages
        if view.is_popup_visible():
            return

        if not persist.settings.get('show_hover_line_report'):
            return

        lineno, colno = view.rowcol(point)
        SublimeLinter.shared_plugin().open_tooltip(view, lineno, show_clean=False)


class SublimelinterEditCommand(sublime_plugin.TextCommand):
    """A plugin command used to generate an edit object for a view."""

    def run(self, edit):
        persist.edit(self.view.id(), edit)
