"""This module provides the SublimeLinter plugin class and supporting methods."""

from collections import defaultdict, deque
from functools import partial
import logging
import time
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


def plugin_loaded():
    log_handler.install()

    try:
        from package_control import events
        if events.install('SublimeLinter') or events.post_upgrade('SublimeLinter'):
            # In case the user has an old version installed without the below
            # `unload`, we 'unload' here.
            persist.kill_switch = True
            persist.linter_classes.clear()

            # The 'event' (flag) is set for 5 seconds. To not get into a
            # reloader excess we wait for that time, so that the next time
            # this exact `plugin_loaded` handler runs, the flag is already
            # unset.
            sublime.set_timeout_async(reload_sublime_linter, 5000)
            return
    except ImportError:
        pass

    persist.api_ready = True
    persist.kill_switch = False
    persist.settings.load()
    logger.info("debug mode: on")
    logger.info("version: " + util.get_sl_version())
    style.read_gutter_theme()

    # Lint the visible views from the active window on startup
    if persist.settings.get("lint_mode") in ("background", "load_save"):
        for view in visible_views():
            if util.is_lintable(view):
                hit(view)


def plugin_unloaded():
    try:
        from package_control import events

        if events.pre_upgrade('SublimeLinter') or events.remove('SublimeLinter'):
            logger.info("Enable kill_switch.")
            persist.kill_switch = True
            persist.linter_classes.clear()
    except ImportError:
        pass

    queue.unload()
    persist.settings.unobserve()


class SublimeLinterReloadCommand(sublime_plugin.WindowCommand):
    def run(self):
        log_handler.uninstall()
        try:
            reloader.reload_everything()
        except Exception:
            show_restart_message()
            raise  # Still write the traceback to the console!
        finally:
            log_handler.install()


def reload_sublime_linter():
    window = sublime.active_window()
    window.run_command("sublime_linter_reload")


def show_restart_message():
    window = sublime.active_window()
    window.run_command("sublime_linter_display_panel", {
        'msg': (
            'SublimeLinter has been installed or upgraded. '
            'Please restart Sublime Text.'
        )
    })


def visible_views():
    """Yield all visible views of the active window."""
    window = sublime.active_window()

    # Priority for the active view
    active_view = window.active_view()
    if active_view:
        yield active_view

    num_groups = window.num_groups()
    for group_id in range(num_groups):
        view = window.active_view_in_group(group_id)
        if view != active_view:
            yield view


global_lock = threading.RLock()
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

        if persist.settings.get('lint_mode') in ('manual', 'save'):
            return

        if not util.is_lintable(view):
            return

        if has_syntax_changed(view):
            hit(view)

    def on_post_save_async(self, view):
        if persist.settings.get('lint_mode') == 'manual':
            return

        # check if the project settings changed
        window = view.window()
        if window and window.project_file_name() == view.file_name():
            sublime.run_command('sublime_linter_config_changed')
            return

        if not util.is_lintable(view):
            return

        hit(view, reason='on_save')

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


class SublimeLinterLintCommand(sublime_plugin.TextCommand):
    """A command that lints the current view if it has a linter."""

    def is_enabled(self):
        """
        Return True if the current view can be linted.

        If the view has *only* file-only linters, it can be linted
        only if the view is not dirty.

        Otherwise it can be linted.
        """
        has_non_file_only_linter = False

        bid = self.view.buffer_id()
        linters = persist.view_linters.get(bid, [])

        for lint in linters:
            if lint.tempfile_suffix != '-':
                has_non_file_only_linter = True
                break

        if not has_non_file_only_linter:
            return not self.view.is_dirty()

        return True

    def run(self, edit):
        """Lint the current view."""
        hit(self.view, reason='on_user_request')


class sublime_linter_config_changed(sublime_plugin.ApplicationCommand):
    def run(self):
        lint_all_views()


def lint_all_views():
    """Mimic a modification of all views, which will trigger a relint."""
    for window in sublime.windows():
        for view in window.views():
            if view.buffer_id() in persist.view_linters:
                hit(view)


def hit(view, reason=None):
    """Record an activity that could trigger a lint and enqueue a desire to lint."""
    bid = view.buffer_id()

    delay = get_delay(reason)
    logger.info('Delay buffer {} for {:.2}s'.format(bid, delay))
    lock = guard_check_linters_for_view[bid]
    view_has_changed = make_view_has_changed_fn(view)
    fn = partial(lint, view, view_has_changed, lock, reason)
    queue.debounce(fn, delay=delay, key=bid)


def lint(view, view_has_changed, lock, reason=None):
    """Lint the view with the given id.

    This method is called asynchronously by queue.Daemon when a lint
    request is pulled off the queue.
    """
    # We call `get_linters_for_view` first and unconditionally for its
    # side-effect. Yeah, it's a *getter* LOL.
    with lock:  # We're already debounced, so races are actually unlikely.
        linters = get_linters_for_view(view)

    linters = [
        linter for linter in linters
        if linter.should_lint(reason)]
    if not linters:
        return

    # Very, very unlikely that `view_has_changed` is already True at this
    # point, but it also implements the kill_switch, so we ask here
    if view_has_changed():  # abort early
        return

    bid = view.buffer_id()

    if persist.settings.get('kill_old_processes'):
        kill_active_popen_calls(bid)

    events.broadcast(events.LINT_START, {'buffer_id': bid})
    start_time = time.time()

    next = partial(update_buffer_errors, bid, view_has_changed)
    backend.lint_view(linters, view, view_has_changed, next)

    end_time = time.time()
    runtime = end_time - start_time
    logger.info('Linting buffer {} took {:.2f}s'.format(bid, runtime))
    remember_runtime(runtime)
    events.broadcast(events.LINT_END, {'buffer_id': bid})


def kill_active_popen_calls(bid):
    with persist.active_procs_lock:
        procs = persist.active_procs[bid][:]

    if procs:
        logger.info('Friendly terminate: {}'.format(
            ', '.join('<pid {}>'.format(proc.pid) for proc in procs)
        ))
    for proc in procs:
        proc.terminate()
        proc.friendly_terminated = True


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
    syntax = util.get_syntax(view)

    current_linters = persist.view_linters.get(bid, set())
    current_linter_classes = {linter.__class__ for linter in current_linters}
    wanted_linter_classes = {
        linter_class
        for linter_class in persist.linter_classes.values()
        if linter_class.can_lint_view(view)
    }

    linters = {
        linter_class(view, syntax)
        for linter_class in wanted_linter_classes
    }

    # It is possible that the user closes the view during debounce time,
    # in that case `window` will get None and we will just abort. We check
    # here bc above code is slow enough to make the difference. We don't
    # pass a valid `window` around bc we do not want to update `view_linters`
    # for detached views as well bc `on_pre_close` already has been called
    # at this time.
    window = view.window()
    if window is None:
        return []

    persist.view_linters[bid] = linters
    window.run_command('sublime_linter_assigned', {
        'bid': bid,
        'linter_names': [linter.name for linter in linters]
    })

    if current_linter_classes != wanted_linter_classes:
        logger.info("detected syntax: {}".format(syntax))

        unchanged_buffer = lambda: False  # noqa: E731
        for linter in (current_linter_classes - wanted_linter_classes):
            update_buffer_errors(bid, unchanged_buffer, linter, [])

    return linters


def make_view_has_changed_fn(view):
    initial_change_count = view.change_count()

    def view_has_changed():
        if persist.kill_switch:
            window = sublime.active_window()
            window.status_message(
                'SublimeLinter upgrade in progress. Aborting lint.')
            return True

        if view.buffer_id() == 0:
            logger.info('View detached (no buffer_id). Aborting lint.')
            return True

        if view.window() is None:
            logger.info('View detached (no window). Aborting lint.')
            return True

        if view.change_count() != initial_change_count:
            logger.info(
                'Buffer {} inconsistent. Aborting lint.'
                .format(view.buffer_id()))
            return True

        return False

    return view_has_changed


elapsed_runtimes = deque([0.6] * 3, maxlen=10)
MIN_DEBOUNCE_DELAY = 0.05
MAX_AUTOMATIC_DELAY = 2.0


def get_delay(reason=None):
    """Return the delay between a lint request and when it will be processed."""
    if reason == 'on_user_request':
        return 0.0

    # Need to debounce on_save bc Sublime will fire the event per view
    if reason == 'on_save':
        return MIN_DEBOUNCE_DELAY

    runtimes = sorted(elapsed_runtimes)
    middle = runtimes[len(runtimes) // 2]
    return max(
        max(MIN_DEBOUNCE_DELAY, float(persist.settings.get('delay'))),
        min(MAX_AUTOMATIC_DELAY, middle / 2)
    )


def remember_runtime(elapsed_runtime):
    with global_lock:
        elapsed_runtimes.append(elapsed_runtime)
