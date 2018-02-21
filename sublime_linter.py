"""This module provides the SublimeLinter plugin class and supporting methods."""

from functools import partial
import logging
import os

import sublime
import sublime_plugin

from . import log_handler
from .lint import backend
from .lint import events
from .lint.linter import Linter
from .lint import queue
from .lint import persist, util, style
from .lint import reloader


logger = logging.getLogger(__name__)


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
    log_handler.install()
    backup_old_settings()

    try:
        from package_control import events
        if events.install('SublimeLinter'):
            reloader.reload_linter_plugins()
            return
        elif events.post_upgrade('SublimeLinter'):
            reloader.reload_everything()
            return
    except ImportError:
        pass

    persist.api_ready = True
    persist.settings.load()
    logger.info("debug mode: on")
    logger.info("version: " + util.get_sl_version())
    style.load_gutter_icons()
    style.StyleParser()()

    plugin = SublimeLinter.shared_plugin()

    # Lint the visible views from the active window on startup
    if persist.settings.get("lint_mode") in ("background", "load_save"):
        for view in visible_views():
            plugin.hit(view)


class SublimeLinterReloadCommand(sublime_plugin.WindowCommand):
    def run(self):
        reloader.reload_everything()


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

        if persist.settings.get('lint_mode') == 'background':
            self.hit(view)

    def on_activated_async(self, view):
        if not util.is_lintable(view):
            return

        self.check_syntax(view)

        view_id = view.id()
        if view_id not in self.linted_views:
            lint_mode = persist.settings.get('lint_mode')
            if lint_mode in ('background', 'load_save'):
                self.hit(view)

    def on_post_save_async(self, view):
        if not util.is_lintable(view):
            return

        # check if the project settings changed
        if view.window().project_file_name() == view.file_name():
            self.lint_all_views()
        else:
            lint_mode = persist.settings.get('lint_mode')
            if lint_mode != 'manual':
                self.hit(view)

    def on_pre_close(self, view):
        if not util.is_lintable(view):
            return

        vid = view.id()
        dicts = [
            self.linted_views,
            persist.view_linters,
        ]

        for d in dicts:
            if type(d) is set:
                d.discard(vid)
            else:
                d.pop(vid, None)

        bid = view.buffer_id()
        buffers = []
        for w in sublime.windows():
            for v in w.views():
                buffers.append(v.buffer_id())

        # Cleanup bid-based stores if this is the last view on the buffer
        if buffers.count(bid) <= 1:
            persist.errors.pop(bid, None)
            queue.cleanup(bid)


class SublimeLinter(sublime_plugin.EventListener, Listener):
    shared_instance = None

    @classmethod
    def shared_plugin(cls):
        """Return the plugin instance."""
        return cls.shared_instance

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Keeps track of which views have actually been linted
        self.linted_views = set()

        self.__class__.shared_instance = self

    @classmethod
    def lint_all_views(cls):
        """Mimic a modification of all views, which will trigger a relint."""
        for window in sublime.windows():
            for view in window.views():
                if view.id() in persist.view_linters:
                    cls.shared_instance.hit(view)

    def hit(self, view):
        """Record an activity that could trigger a lint and enqueue a desire to lint."""
        if not view:
            return

        vid = view.id()
        self.check_syntax(view)
        self.linted_views.add(vid)

        if vid in persist.view_linters:
            view_has_changed = make_view_has_changed_fn(view)
            fn = partial(self.lint, view, view_has_changed)
            queue.debounce(fn, key=view.buffer_id())

    def lint(self, view, view_has_changed):
        """Lint the view with the given id.

        This method is called asynchronously by queue.Daemon when a lint
        request is pulled off the queue.
        """
        if view_has_changed():  # abort early
            return

        events.broadcast(events.LINT_START, {'buffer_id': view.buffer_id()})

        next = partial(self.highlight, view, view_has_changed)
        backend.lint_view(view, view_has_changed, next)

        events.broadcast(events.LINT_END, {'buffer_id': view.buffer_id()})

    def highlight(self, view, view_has_changed, linter, errors):
        """
        Highlight any errors found during a lint of the given view.

        This method is called by Linter.lint_view after linting is finished.
        """
        if view_has_changed():  # abort early
            return

        bid = view.buffer_id()
        all_errors = [error for error in persist.errors[bid]
                      if error['linter'] != linter.name] + errors
        persist.errors[bid] = all_errors

        events.broadcast(events.LINT_RESULT, {
            'buffer_id': bid,
            'linter_name': linter.name,
            'errors': errors
        })

    def check_syntax(self, view):
        """
        Check and return if view's syntax has changed.

        If the syntax has changed, a new linter is assigned.
        """
        if not view:
            return

        vid = view.id()

        old_linters = persist.view_linters.get(vid, [])
        changed = Linter.assign(view)
        if changed:
            bid = view.buffer_id()
            persist.errors[bid].clear()
            for linter in old_linters:
                events.broadcast(events.LINT_RESULT, {
                    'buffer_id': bid,
                    'linter_name': linter.name,
                    'errors': []
                })

            self.linted_views.discard(vid)
            return True
        else:
            return False


def make_view_has_changed_fn(view):
    initial_change_count = view.change_count()

    def view_has_changed():
        changed = view.change_count() != initial_change_count
        if changed:
            persist.debug(
                'Buffer {} inconsistent. Aborting lint.'
                .format(view.buffer_id()))

        return changed

    return view_has_changed
