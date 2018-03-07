"""This module provides the SublimeLinter plugin class and supporting methods."""

from collections import defaultdict
from functools import partial
import logging
import os
import threading

import sublime
import sublime_plugin

from . import log_handler
from .lint import backend
from .lint import events
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
            util.message(
                'SublimeLinter has been installed. Please restart Sublime Text.')
        elif events.post_upgrade('SublimeLinter'):
            util.message(
                'SublimeLinter has been upgraded. Please restart Sublime Text.')
    except ImportError:
        pass

    persist.api_ready = True
    persist.settings.load()
    logger.info("debug mode: on")
    logger.info("version: " + util.get_sl_version())
    style.read_gutter_theme()
    style.StyleParser()()

    # Lint the visible views from the active window on startup
    if persist.settings.get("lint_mode") in ("background", "load_save"):
        for view in visible_views():
            hit(view)


def plugin_unloaded():
    queue.unload()
    persist.settings.unobserve()


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


guard_check_linters_for_view = defaultdict(threading.Lock)
buffer_syntaxes = {}


class BackendController(sublime_plugin.EventListener):
    def on_modified_async(self, view):
        if persist.settings.get('lint_mode') != 'background':
            return

        if not util.is_lintable(view):
            return

        hit(view)

    def on_activated_async(self, view):
        # If the user changes the buffers syntax via the command palette,
        # we get an 'activated' event right after. Since, it is very likely
        # that the linters change as well, we 'hit' immediately for users
        # convenience.
        # We also use this instead of the `on_load_async` event as 'load'
        # event, bc 'on_load' fires for preview buffers which is way too
        # early. This fires a bit too often for 'load_save' mode but it is
        # good enough.

        if persist.settings.get('lint_mode') == 'manual':
            return

        if not util.is_lintable(view):
            return

        if has_syntax_changed(view):
            hit(view)

    def on_post_save_async(self, view):
        if persist.settings.get('lint_mode') == 'manual':
            return

        # check if the project settings changed
        if view.window() and view.window().project_file_name() == view.file_name():
            lint_all_views()
            return

        if not util.is_lintable(view):
            return

        hit(view)

    def on_pre_close(self, view):
        bid = view.buffer_id()
        buffers = []
        for w in sublime.windows():
            for v in w.views():
                buffers.append(v.buffer_id())

        # Cleanup bid-based stores if this is the last view on the buffer
        if buffers.count(bid) <= 1:
            persist.errors.pop(bid, None)
            persist.view_linters.pop(bid, None)

            guard_check_linters_for_view.pop(bid, None)
            buffer_syntaxes.pop(bid, None)
            queue.cleanup(bid)


def has_syntax_changed(view):
    bid = view.buffer_id()
    current_syntax = util.get_syntax(view)

    try:
        old_value = buffer_syntaxes[bid]
    except KeyError:
        return True
    else:
        return old_value != current_syntax
    finally:
        buffer_syntaxes[bid] = current_syntax


def lint_all_views():
    """Mimic a modification of all views, which will trigger a relint."""
    for window in sublime.windows():
        for view in window.views():
            if view.buffer_id() in persist.view_linters:
                hit(view)


def hit(view):
    """Record an activity that could trigger a lint and enqueue a desire to lint."""
    bid = view.buffer_id()

    lock = guard_check_linters_for_view[bid]
    view_has_changed = make_view_has_changed_fn(view)
    fn = partial(lint, view, view_has_changed, lock)
    queue.debounce(fn, key=bid)


def lint(view, view_has_changed, lock):
    """Lint the view with the given id.

    This method is called asynchronously by queue.Daemon when a lint
    request is pulled off the queue.
    """
    if view_has_changed():  # abort early
        return

    bid = view.buffer_id()

    # We're already debounced, so races are actually unlikely
    with lock:
        linters = get_linters_for_view(view)

    if linters:
        events.broadcast(events.LINT_START, {'buffer_id': bid})

        next = partial(update_buffer_errors, bid, view_has_changed)
        backend.lint_view(linters, view, view_has_changed, next)

        events.broadcast(events.LINT_END, {'buffer_id': bid})


def update_buffer_errors(bid, view_has_changed, linter, errors):
    """Persist lint error changes and broadcast."""
    if view_has_changed():  # abort early
        return

    all_errors = [error for error in persist.errors[bid]
                  if error['linter'] != linter.name] + errors
    persist.errors[bid] = all_errors

    events.broadcast(events.LINT_RESULT, {
        'buffer_id': bid,
        'linter_name': linter.name,
        'errors': errors
    })


def get_linters_for_view(view):
    """Check and eventually instantiate linters for a view."""
    bid = view.buffer_id()

    linters = persist.view_linters.get(bid, set())
    wanted_linter_classes = {
        linter_class
        for linter_class in persist.linter_classes.values()
        if (
            not linter_class.disabled and
            linter_class.can_lint_view(view) and
            linter_class.can_lint()
        )
    }
    current_linter_classes = {linter.__class__ for linter in linters}

    if current_linter_classes != wanted_linter_classes:
        unchanged_buffer = lambda: False  # noqa: E731
        for linter in (current_linter_classes - wanted_linter_classes):
            update_buffer_errors(bid, unchanged_buffer, linter, [])

        syntax = util.get_syntax(view)
        logger.info("detected syntax: {}".format(syntax))

        linters = {
            linter_class(view, syntax)
            for linter_class in wanted_linter_classes
        }
        persist.view_linters[bid] = linters

    return linters


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
