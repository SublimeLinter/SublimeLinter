"""This module provides the SublimeLinter plugin class and supporting methods."""

import os
import html

import sublime
import sublime_plugin

from .lint.linter import Linter
from .lint.highlight import HighlightSet, RegionStore
from .lint.queue import queue
from .lint import persist, util, style
from .lint.error import ErrorStore
from .lint.const import WARN_ERR, STATUS_KEY
from .panel import panel


def backup_old_settings():
    """
        If user settings file in old format exists it is renamed to disable it
        and back it up.
        A message will be displayed to the user.
    """
    usr_dir_abs = os.path.join(sublime.packages_path(), "User")
    settings_file = os.path.join(usr_dir_abs, "SublimeLinter.sublime-settings")
    if os.path.exists(settings_file):
        path = "Packages/User/SublimeLinter.sublime-settings"
        settings = sublime.decode_value(sublime.load_resource(path))

        if "user" in settings:
            msg = "SublimeLinter\n\nYour settings have been backed up to:\nSublimeLinter (old).sublime-settings\nin Packages/User/"  # noqa: 501
            new_name = "SublimeLinter (old).sublime-settings"
            new_path = os.path.join(usr_dir_abs, new_name)
            os.rename(settings_file, new_path)
            sublime.message_dialog(msg)


def plugin_loaded():
    backup_old_settings()

    persist.plugin_is_loaded = True
    persist.settings.load()

    style.StyleParser()()

    persist.debug("debug mode: on")
    util.create_tempdir()

    persist.errors = ErrorStore()
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

    # Load and lint all views on startup
    if persist.settings.get("lint_mode") in ("background", "load_save"):
        for window in sublime.windows():
            for view in window.views():
                plugin.check_syntax(view)
        plugin.lint_all_views()


class Listener:
    """Collection of event handler methods."""

    def on_modified_async(self, view):
        """Ran when view is modified."""

        if util.is_scratch(view):
            return

        if view.id() not in persist.view_linters:
            syntax_changed = self.check_syntax(view)

            if not syntax_changed:
                return
        else:
            syntax_changed = False

        if syntax_changed or persist.settings.get('lint_mode') == 'background':
            self.hit(view)

    def on_activated_async(self, view):
        """Ran when a view gains input focus."""

        if util.is_scratch(view):
            return

        # Reload the plugin settings.
        persist.settings.load()

        self.check_syntax(view)
        view_id = view.id()

        if view_id not in self.linted_views:
            if view_id not in self.loaded_views:
                self.on_new_async(view)

            lint_mode = persist.settings.get('lint_mode')
            if lint_mode in ('background', 'load_save'):
                self.hit(view)

        self.display_errors(view)

    def on_new_async(self, view):
        """Ran when a new buffer is created."""

        if util.is_scratch(view):
            return

        vid = view.id()
        self.loaded_views.add(vid)
        self.view_syntax[vid] = util.get_syntax(view)

    def on_post_save_async(self, view):
        if util.is_scratch(view):
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
            elif filename != "SublimeLinter.sublime-settings":
                self.file_was_saved(view)

    @classmethod
    def on_settings_updated(cls, relint=False):
        """Ran when the settings are updated."""
        if relint:
            cls.lint_all_views()
        else:
            Linter.redraw_all()

    def on_pre_close_async(self, view):
        if util.is_scratch(view):
            return

        vid = view.id()

        dicts = [
            self.loaded_views, self.linted_views, self.view_syntax, persist.errors,
            persist.highlights, persist.view_linters,
            persist.views, persist.last_hit_times
        ]

        for d in dicts:
            d.pop(vid, None)

    def on_selection_modified_async(self, view):
        self.display_errors(view)

    def on_hover(self, view, point, hover_zone):
        """Arguments:
            view (View): The view which received the event.
            point (Point): The text position where the mouse hovered
            hover_zone (int): The context the event was triggered in
        """
        if hover_zone == sublime.HOVER_GUTTER:
            if persist.settings.get('show_hover_line_report'):
                SublimeLinter.shared_plugin().open_tooltip(view, point)

        elif hover_zone == sublime.HOVER_TEXT:
            if persist.settings.get('show_hover_region_report'):
                SublimeLinter.shared_plugin().open_tooltip(view, point, True)


class SublimeLinter(sublime_plugin.EventListener, Listener):
    """The main ST3 plugin class."""

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

                    if not window_views.get(wid):
                        window_views[wid] = other_view

            panel.fill_panel(window, update=True)

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
        syntax = util.get_syntax(view)

        # Syntax either has never been set or just changed
        if vid not in self.view_syntax or self.view_syntax[vid] != syntax:
            self.view_syntax[vid] = syntax
            Linter.assign(view, reset=True)
            self.clear(view)
            return True
        else:
            return False

    def clear(self, view):
        Linter.clear_view(view)

    def view_has_file_only_linter(self, vid):
        """Return True if any linters for the given view are file-only."""
        for lint in persist.view_linters.get(vid, []):
            if lint.tempfile_suffix == '-':
                return True

        return False

    def get_line_and_col(self, view):
        try:
            lineno, colno = view.rowcol(view.sel()[0].begin())
        except IndexError:
            lineno, colno = -1, -1

        return lineno, colno

    def display_errors(self, view):
        """
        Display lint errors in the statusbar of the current view
        """

        if not view:  # handling of panel
            return

        view = util.get_focused_view(view)
        if not view:  # handling of panel
            return

        lineno, colno = self.get_line_and_col(view)
        vid = view.id()

        view_dict = persist.errors.get_view_dict(vid)
        if not view_dict:
            view.erase_status(STATUS_KEY)
            return

        we_count = view_dict["we_count_view"]
        status = "W: {warning} E: {error}".format(**we_count)

        msgs = []
        region_dict = persist.errors.get_region_dict(vid, lineno, colno)
        for error_type, dc in region_dict.items():
            for d in dc:
                msgs.append(d["msg"])
        if msgs:
            status += " - {}".format("; ".join(msgs))

        if status != view.get_status(STATUS_KEY):
            view.set_status(STATUS_KEY, status)

    @classmethod
    def join_msgs(cls, line_dict, we_count):
        part = '''
            <div class="{classname}">{count} {heading}</div>
            <div>{messages}</div>
        '''

        template = "{linter}: {code} - {escaped_msg}"
        template_no_code = "{linter}: {escaped_msg}"

        all_msgs = ""
        for error_type in WARN_ERR:
            count = we_count[error_type]
            heading = error_type
            error_type_msgs = []
            msg_list = line_dict.get(error_type)

            if not msg_list:
                continue
            for item in msg_list:
                item["escaped_msg"] = html.escape(item["msg"], quote=False)
                template_to_fill = template if item.get('code') else template_no_code
                error_type_msgs.append(template_to_fill.format(**item))

            if count > 1:  # pluralize
                heading += "s"

            all_msgs += part.format(
                classname=error_type,
                count=count,
                heading=heading,
                messages='<br />'.join(error_type_msgs)
            )
        return all_msgs

    def open_tooltip(self, active_view=None, point=None, is_inline=False):
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

        if not active_view:
            active_view = util.get_active_view()

        # Leave any existing popup open without replacing it
        # don't let the popup flicker / fight with other packages
        if active_view.is_popup_visible():
            return

        if point:  # provided from hover
            lineno, colno = active_view.rowcol(point)
        else:
            lineno, colno = self.get_line_and_col(active_view)

        vid = active_view.id()

        line_dict = persist.errors.get_line_dict(vid, lineno)
        if not line_dict:
            return

        if is_inline:  # do not show tooltip on hovering empty gutter
            line_dict = persist.errors.get_region_dict(vid, lineno, colno)

        if not line_dict:
            return

        tooltip_message = ""
        we_count = persist.errors.get_we_count_line(vid, lineno)

        if util.is_none_or_zero(we_count):
            return

        tooltip_message = self.join_msgs(line_dict, we_count)
        if not tooltip_message:
            return

        colno = 0 if not is_inline else colno
        location = active_view.text_point(lineno, colno)
        active_view.show_popup(
            template.format(stylesheet=stylesheet, message=tooltip_message),
            flags=sublime.HIDE_ON_MOUSE_MOVE_AWAY,
            location=location,
            max_width=1000)

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
