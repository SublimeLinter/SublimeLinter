"""This module provides the SublimeLinter plugin class and supporting methods."""

from collections import defaultdict
import os
import html

import sublime
import sublime_plugin

from .lint import events
from .lint.linter import Linter
from .lint import highlight
from .lint.queue import queue
from .lint import persist, util, style
from .lint.error import ErrorStore
from .lint.const import WARN_ERR
from .lint import backend
from .panel import panel


def backup_old_settings():
    """
    Backup old settings.

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
            new_name = "SublimeLinter (old).sublime-settings"
            new_path = os.path.join(usr_dir_abs, new_name)
            os.rename(settings_file, new_path)
            msg = "SublimeLinter\n\nYour settings have been backed up to:\n{}\nin Packages/User/".format(new_name)  # noqa: 501
            sublime.message_dialog(msg)


def plugin_loaded():
    backup_old_settings()

    persist.plugin_is_loaded = True
    persist.settings.load()
    persist.debug("debug mode: on")

    style.StyleParser()()

    util.create_tempdir()

    persist.errors = ErrorStore()

    for linter in persist.linter_classes.values():
        linter.initialize()

    plugin = SublimeLinter.shared_plugin()
    queue.start(plugin.lint)

    # Lint the visible views from the active window on startup
    if persist.settings.get("lint_mode") in ("background", "load_save"):
        for view in visible_views():
            plugin.hit(view)


def visible_views():
    """Yield all visible views of the active window."""
    window = sublime.active_window()

    # Priority for the active view
    active_view = window.active_view()
    yield active_view

    num_groups = window.num_groups()
    for group_id in range(num_groups):
        view = window.active_view_in_group(group_id)
        if view != active_view:
            yield view


class Listener:

    def on_modified_async(self, view):
        if not util.is_lintable(view):
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
        if not util.is_lintable(view):
            return

        self.check_syntax(view)

        view_id = view.id()
        if view_id not in self.linted_views:
            if view_id not in self.loaded_views:
                self.on_new_async(view)

            lint_mode = persist.settings.get('lint_mode')
            if lint_mode in ('background', 'load_save'):
                self.hit(view)

    def on_new_async(self, view):
        if not util.is_lintable(view):
            return

        vid = view.id()
        self.loaded_views.add(vid)
        self.view_syntax[vid] = util.get_syntax(view)

    def on_post_save_async(self, view):
        if not util.is_lintable(view):
            return

        # check if the project settings changed
        if view.window().project_file_name() == view.file_name():
            self.lint_all_views()
        else:
            filename = os.path.basename(view.file_name())
            if filename != "SublimeLinter.sublime-settings":
                self.file_was_saved(view)

    def on_pre_close(self, view):
        if not util.is_lintable(view):
            return

        vid = view.id()
        dicts = [
            self.loaded_views,
            self.linted_views,
            self.view_syntax,
            persist.errors,
            persist.view_linters,
            persist.views,
            persist.last_hit_times
        ]

        for d in dicts:
            if type(d) is set:
                d.discard(vid)
            else:
                d.pop(vid, None)

        queue.cleanup(vid)
        panel.fill_panel(view.window(), update=True)

    def on_hover(self, view, point, hover_zone):
        """On mouse hover event hook.

        Arguments:
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
        """Mimic a modification of all views, which will trigger a relint."""
        def apply(view):
            if view.id() in persist.view_linters:
                cls.shared_instance.hit(view)

        util.apply_to_all_views(apply)

    def lint(self, view_id, hit_time=None):
        """Lint the view with the given id.

        This method is called asynchronously by queue.Daemon when a lint
        request is pulled off the queue.

        If provided, hit_time is the time at which the lint request was added
        to the queue. It is used to determine if the view has been modified
        since the lint request was queued. If so, the lint is aborted, since
        another lint request is already in the queue.
        """
        # If this is not the latest 'hit' we're processing abort early.
        if hit_time and persist.last_hit_times.get(view_id, 0) > hit_time:
            return

        view = Linter.get_view(view_id)

        if not view:
            return

        events.broadcast(events.BEGIN_LINTING, {'buffer_id': view.buffer_id()})
        backend.lint_view(view, hit_time, self.highlight)

    def highlight(self, view, errors, hit_time):
        """
        Highlight any errors found during a lint of the given view.

        This method is called by Linter.lint_view after linting is finished.
        """
        if not view:
            return

        vid = view.id()

        # If the view has been modified since the lint was triggered,
        # don't draw marks.
        if hit_time and persist.last_hit_times.get(vid, 0) > hit_time:
            return

        bid = view.buffer_id()
        persist.raw_errors[bid] = errors

        # For compatibility we store the errors SL3 style as well.
        errors_by_line = defaultdict(lambda: defaultdict(list))
        for error in errors:
            line = error['line']
            error_type = error['error_type']
            errors_by_line[line][error_type].append(error)

        for view in all_views_into_buffer(view):
            vid = view.id()
            persist.errors[vid] = errors_by_line

        events.broadcast(events.FINISHED_LINTING, {'buffer_id': bid})

        highlights = highlight.Highlight(view)
        for error in errors:
            highlights.add_error(**error)

        for view in all_views_into_buffer(view):
            highlight.clear_view(view)
            highlights.draw(view)

        for window in sublime.windows():
            panel.fill_panel(window, update=True)

    def hit(self, view):
        """Record an activity that could trigger a lint and enqueue a desire to lint."""
        if not view:
            return

        vid = view.id()
        self.check_syntax(view)
        self.linted_views.add(vid)

        if view.size() == 0:
            for linter in persist.view_linters.get(vid, []):
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

    @classmethod
    def join_msgs(cls, line_dict, we_count, show_count=False):

        if show_count:
            part = '''
                <div class="{classname}">{count} {heading}</div>
                <div>{messages}</div>
            '''
        else:
            part = '''
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
        """Show a tooltip containing all linting errors on a given line."""
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
            show_count = False
        else:
            show_count = True

        if not line_dict:
            return

        we_count = persist.errors.get_we_count_line(vid, lineno)

        if util.is_none_or_zero(we_count):
            return

        tooltip_message = self.join_msgs(line_dict, we_count, show_count)
        if not tooltip_message:
            return

        colno = 0 if not is_inline else colno
        location = active_view.text_point(lineno, colno)
        active_view.show_popup(
            template.format(stylesheet=stylesheet, message=tooltip_message),
            flags=sublime.HIDE_ON_MOUSE_MOVE_AWAY,
            location=location,
            max_width=1000
        )

    def file_was_saved(self, view):
        """Check if the syntax changed or if we need to show errors."""
        syntax_changed = self.check_syntax(view)
        vid = view.id()
        mode = persist.settings.get('lint_mode')

        if syntax_changed:
            self.clear(view)

        if mode != 'manual':
            if vid in persist.view_linters or self.view_has_file_only_linter(vid):
                self.hit(view)


def all_views_into_buffer(view):
    """Yield all views with the same underlying buffer."""
    buffer_id = view.buffer_id()

    for window in sublime.windows():
        for view in window.views():
            if view.buffer_id() == buffer_id:
                yield view
