"""This module provides the SublimeLinter plugin class and supporting methods."""

from collections import defaultdict, deque
from contextlib import contextmanager
from functools import partial
import logging
import time
import threading

import sublime
import sublime_plugin

from . import log_handler
from .lint import backend
from .lint import elect
from .lint import events
from .lint import linter as linter_module
from .lint import queue
from .lint import persist, util, style
from .lint import reloader
from .lint import settings


MYPY = False
if MYPY:
    from typing import Callable, DefaultDict, Dict, List, Optional, Set, Type

    Bid = sublime.BufferId
    LinterName = str
    FileName = str
    LintError = persist.LintError
    Linter = linter_module.Linter
    LinterSettings = linter_module.LinterSettings
    ViewChangedFn = Callable[[], bool]

    LinterInfo = elect.LinterInfo


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
    bc = BackendController()
    for view in other_visible_views():
        bc.on_activated_async(view)


def plugin_unloaded():
    log_handler.uninstall()

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
            'Reloading SublimeLinter failed. :-(\n'
            'Please restart Sublime Text.'
        )
    })


def other_visible_views():
    """Yield all visible views of the active window except the active_view."""
    window = sublime.active_window()

    # The active view gets 'activated' by ST after `plugin_loaded`.
    active_view = window.active_view()

    num_groups = window.num_groups()
    for group_id in range(num_groups):
        view = window.active_view_in_group(group_id)
        if view != active_view:
            yield view


global_lock = threading.RLock()
guard_check_linters_for_view = defaultdict(threading.Lock)  # type: DefaultDict[Bid, threading.Lock]
buffer_syntaxes = {}  # type: Dict[Bid, str]


class BackendController(sublime_plugin.EventListener):
    @util.distinct_until_buffer_changed
    def on_modified_async(self, view):
        if not util.is_lintable(view):
            return

        hit(view, 'on_modified')

    def on_activated_async(self, view):
        # If the user changes the buffers syntax via the command palette,
        # we get an 'activated' event right after. Since, it is very likely
        # that the linters change as well, we 'hit' immediately for users
        # convenience.
        # We also use this instead of the `on_load_async` event as 'load'
        # event, bc 'on_load' fires for preview buffers which is way too
        # early. This fires a bit too often for 'load_save' mode but it is
        # good enough.
        if not util.is_lintable(view):
            return

        if has_syntax_changed(view):
            hit(view, 'on_load')

    @util.distinct_until_buffer_changed
    def on_post_save_async(self, view):
        # check if the project settings changed
        window = view.window()
        filename = view.file_name()
        if window and window.project_file_name() == filename:
            if settings.validate_project_settings(filename):
                for window in sublime.windows():
                    if window.project_file_name() == filename:
                        sublime.run_command('sublime_linter_config_changed', {
                            'hint': 'relint',
                            'wid': window.id()
                        })
            return

        if not util.is_lintable(view):
            return

        hit(view, 'on_save')

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
            affected_filenames_per_bid.pop(bid, None)
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


class sublime_linter_lint(sublime_plugin.TextCommand):
    """A command that lints the current view if it has a linter."""

    def is_enabled(self):
        return any(elect.runnable_linters_for_view(self.view, 'on_user_request'))

    def run(self, edit):
        hit(self.view, 'on_user_request')


class sublime_linter_config_changed(sublime_plugin.ApplicationCommand):
    def run(self, hint=None, wid=None):
        if hint is None or hint == 'relint':
            relint_views(wid)
        elif hint == 'redraw':
            force_redraw()


def relint_views(wid=None):
    windows = [sublime.Window(wid)] if wid else sublime.windows()
    for window in windows:
        for view in window.views():
            if view.buffer_id() in persist.view_linters and view.is_primary():
                hit(view, 'relint_views')


def hit(view, reason):
    # type: (sublime.View, str) -> None
    """Record an activity that could trigger a lint and enqueue a desire to lint."""
    bid = view.buffer_id()

    delay = get_delay() if reason == 'on_modified' else 0.0
    logger.info(
        "Delay linting '{}' for {:.2}s"
        .format(util.canonical_filename(view), delay)
    )
    lock = guard_check_linters_for_view[bid]
    view_has_changed = make_view_has_changed_fn(view)
    fn = partial(lint, view, view_has_changed, lock, reason)
    queue.debounce(fn, delay=delay, key=bid)


def lint(view, view_has_changed, lock, reason):
    # type: (sublime.View, ViewChangedFn, threading.Lock, str) -> None
    """Lint the view with the given id.

    This function MUST run on a thread because it blocks!
    """
    linters = list(elect.assignable_linters_for_view(view, reason))
    with lock:
        _assign_linters_to_view(view, {linter['klass'] for linter in linters})

    runnable_linters = list(elect.filter_runnable_linters(linters))
    if not runnable_linters:
        return

    window = view.window()
    bid = view.buffer_id()

    # Very, very unlikely that `view_has_changed` is already True at this
    # point, but it also implements the kill_switch, so we ask here
    if view_has_changed():  # abort early
        return

    if persist.settings.get('kill_old_processes'):
        kill_active_popen_calls(bid)

    events.broadcast(events.LINT_START, {'buffer_id': bid})

    with remember_runtime(
        "Linting '{}' took {{:.2f}}s".format(util.canonical_filename(view))
    ):
        sink = partial(group_by_filename_and_update, window, bid, view_has_changed, reason)
        backend.lint_view(runnable_linters, view, view_has_changed, sink)

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
        setattr(proc, 'friendly_terminated', True)


affected_filenames_per_bid = defaultdict(
    lambda: defaultdict(set)
)  # type: DefaultDict[Bid, DefaultDict[LinterName, Set[FileName]]]


def group_by_filename_and_update(window, bid, view_has_changed, reason, linter, errors):
    # type: (sublime.Window, Bid, ViewChangedFn, str, LinterName, List[LintError]) -> None
    """Group lint errors by filename and update them."""
    if view_has_changed():  # abort early
        return

    # group all errors by filenames to update them separately
    grouped = defaultdict(list)  # type: DefaultDict[FileName, List[LintError]]
    for error in errors:
        grouped[error.get('filename')].append(error)

    # The contract for a simple linter is that it reports `[errors]` or an
    # empty list `[]` if the buffer is clean. For linters that report errors
    # for multiple files we collect information about which files are actually
    # reported by a given `bid` so that we can clean the results. Basically,
    # we must fake a `[]` response for every filename that is no longer
    # reported.

    current_filenames = set(grouped.keys())  # `set` for the immutable version
    previous_filenames = affected_filenames_per_bid[bid][linter]
    clean_files = previous_filenames - current_filenames

    for filename in clean_files:
        grouped[filename]  # For the side-effect of creating a new empty `list`

    did_update_main_view = False
    for filename, errors in grouped.items():
        if not filename:  # backwards compatibility
            update_buffer_errors(bid, linter, errors, reason)
        else:
            # search for an open view for this file to get a bid
            view = window.find_open_file(filename)
            if view:
                this_bid = view.buffer_id()

                # ignore errors of other files if their view is dirty
                if this_bid != bid and view.is_dirty() and errors:
                    continue

                update_buffer_errors(this_bid, linter, errors, reason)

                if this_bid == bid:
                    did_update_main_view = True

    # For the main view we MUST *always* report an outcome. This is not for
    # cleanup but functions as a signal that we're done. Merely for the status
    # bar view.
    if not did_update_main_view:
        update_buffer_errors(bid, linter, [], reason)

    affected_filenames_per_bid[bid][linter] = current_filenames


def update_buffer_errors(bid, linter, errors, reason=None):
    # type: (Bid, LinterName, List[LintError], Optional[str]) -> None
    """Persist lint error changes and broadcast."""
    update_errors_store(bid, linter, errors)
    events.broadcast(events.LINT_RESULT, {
        'buffer_id': bid,
        'linter_name': linter,
        'errors': errors,
        'reason': reason
    })


def update_errors_store(bid, linter_name, errors):
    # type: (Bid, LinterName, List[LintError]) -> None
    persist.errors[bid] = [
        error
        for error in persist.errors[bid]
        if error['linter'] != linter_name
    ] + errors


def force_redraw():
    for bid, errors in persist.errors.items():
        for linter_name, linter_errors in group_by_linter(errors).items():
            events.broadcast(events.LINT_RESULT, {
                'buffer_id': bid,
                'linter_name': linter_name,
                'errors': linter_errors
            })


def group_by_linter(errors):
    # type: (List[LintError]) -> DefaultDict[LinterName, List[LintError]]
    by_linter = defaultdict(list)  # type: DefaultDict[LinterName, List[LintError]]
    for error in errors:
        by_linter[error['linter']].append(error)

    return by_linter


def _assign_linters_to_view(view, next_linters):
    # type: (sublime.View, Set[Type[Linter]]) -> None
    bid = view.buffer_id()
    window = view.window()
    # It is possible that the user closes the view during debounce time,
    # in that case `window` will get None and we will just abort. We check
    # here bc above code is slow enough to make the difference. We don't
    # pass a valid `window` around bc we do not want to update `view_linters`
    # for detached views as well bc `on_pre_close` already has been called
    # at this time.
    if not window:
        return

    current_linters = persist.view_linters.get(bid, set())
    current_linter_names = {linter.name for linter in current_linters}
    next_linter_names = {linter.name for linter in next_linters}

    persist.view_linters[bid] = next_linters
    window.run_command('sublime_linter_assigned', {
        'bid': bid,
        'linter_names': list(next_linter_names)
    })

    for linter in (current_linter_names - next_linter_names):
        update_buffer_errors(bid, linter, [])


def make_view_has_changed_fn(view):
    # type: (sublime.View) -> ViewChangedFn
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


def get_delay():
    # type: () -> float
    """Return the delay between a lint request and when it will be processed."""
    runtimes = sorted(elapsed_runtimes)
    middle = runtimes[len(runtimes) // 2]
    return max(
        max(MIN_DEBOUNCE_DELAY, float(persist.settings.get('delay'))),
        min(MAX_AUTOMATIC_DELAY, middle / 2)
    )


@contextmanager
def remember_runtime(log_msg):
    start_time = time.time()

    yield

    end_time = time.time()
    runtime = end_time - start_time
    logger.info(log_msg.format(runtime))

    with global_lock:
        elapsed_runtimes.append(runtime)
