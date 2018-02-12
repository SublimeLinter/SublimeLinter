"""This module provides the SublimeLinter plugin class and supporting methods."""

from functools import partial
import logging
import os

import sublime
import sublime_plugin

from .lint import events
from .lint import log_handler
from .lint.linter import Linter
from .lint import queue
from .lint import persist, util, style
from .lint import backend


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

    persist.plugin_is_loaded = True
    persist.settings.load()
    logger.info("debug mode: on")
    logger.info("version: " + util.get_sl_version())
    style.load_gutter_icons()
    style.StyleParser()()

    for linter in persist.linter_classes.values():
        linter.initialize()

    plugin = SublimeLinter.shared_plugin()

    # Lint the visible views from the active window on startup
    if persist.settings.get("lint_mode") in ("background", "load_save"):
        for view in visible_views():
            plugin.hit(view)


def plugin_unloaded():
    log_handler.uninstall()


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
            persist.view_linters,
            persist.views
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

    def hit(self, view):
        """Record an activity that could trigger a lint and enqueue a desire to lint."""
        if not view:
            return

        vid = view.id()
        self.check_syntax(view)
        self.linted_views.add(vid)

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
        syntax = util.get_syntax(view)

        # Syntax either has never been set or just changed
        if vid not in self.view_syntax or self.view_syntax[vid] != syntax:
            bid = view.buffer_id()
            persist.errors[bid].clear()
            for linter in persist.view_linters.get(vid, []):
                events.broadcast(events.LINT_RESULT, {
                    'buffer_id': bid,
                    'linter_name': linter.name,
                    'errors': []
                })

            self.view_syntax[vid] = syntax
            self.linted_views.discard(vid)
            Linter.assign(view, reset=True)
            return True
        else:
            return False

    def view_has_file_only_linter(self, vid):
        """Return True if any linters for the given view are file-only."""
        for linter in persist.view_linters.get(vid, []):
            if linter.tempfile_suffix == '-':
                return True

        return False

    def file_was_saved(self, view):
        """Check if the syntax changed or if we need to show errors."""
        self.check_syntax(view)
        vid = view.id()
        mode = persist.settings.get('lint_mode')

        if mode != 'manual':
            if vid in persist.view_linters or self.view_has_file_only_linter(vid):
                self.hit(view)


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
