"""This module provides the SublimeLinter plugin class and supporting methods."""
from __future__ import annotations

from collections import defaultdict
from functools import partial
from itertools import chain
import logging
import threading

import sublime
import sublime_plugin

from . import log_handler
from .lint import backend
from .lint import elect
from .lint import events
from .lint import linter as linter_module
from .lint import persist
from .lint import queue
from .lint import reloader
from .lint import settings
from .lint import util
from .lint.const import IS_ENABLED_SWITCH
from .lint.util import flash


from typing import Callable, Optional
from typing_extensions import TypeAlias

Bid: TypeAlias = "sublime.BufferId"
LinterName = str
FileName = str
Reason = str
LintError = persist.LintError
Linter = linter_module.Linter
LinterSettings = linter_module.LinterSettings
ViewChangedFn = Callable[[], bool]

logger = logging.getLogger(__name__)
flatten = chain.from_iterable


def plugin_loaded():
    log_handler.install()

    try:
        import package_control.events
        if (
            package_control.events.install('SublimeLinter') or
            package_control.events.post_upgrade('SublimeLinter')
        ):
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
    events.broadcast('plugin_loaded')
    persist.settings.load()
    util.determine_thread_names()
    logger.info("debug mode: on")
    logger.info("version: " + util.get_sl_version())

    # Lint the visible views from the active window on startup
    bc = BackendController()
    for view in other_visible_views():
        bc.on_activated_async(view)


def plugin_unloaded():
    log_handler.uninstall()

    try:
        import package_control
        if (
            package_control.events.pre_upgrade('SublimeLinter') or
            package_control.events.remove('SublimeLinter')
        ):
            logger.info("Enable kill_switch.")
            persist.kill_switch = True
            persist.linter_classes.clear()
    except ImportError:
        pass

    queue.unload()
    persist.settings.unobserve()
    util.close_all_error_panels()
    events.off(on_settings_changed)


@events.on('settings_changed')
def on_settings_changed(settings, **kwargs):
    if (
        settings.has_changed('linters') or
        settings.has_changed('no_column_highlights_line')
    ):
        sublime.run_command(
            'sublime_linter_config_changed', {'hint': 'relint'}
        )

    elif (
        settings.has_changed('gutter_theme') or
        settings.has_changed('highlights.demote_while_editing') or
        settings.has_changed('show_marks_in_minimap') or
        settings.has_changed('styles')
    ):
        sublime.run_command(
            'sublime_linter_config_changed', {'hint': 'redraw'}
        )


class sublime_linter_reload(sublime_plugin.ApplicationCommand):
    def run(self):
        log_handler.uninstall()
        try:
            reloader.reload_everything()
        except Exception:
            util.show_message(
                'Reloading SublimeLinter failed. :-(\n'
                'Please restart Sublime Text.'
            )
            raise  # Still write the traceback to the console!
        finally:
            log_handler.install()


def reload_sublime_linter():
    sublime.run_command("sublime_linter_reload")


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


guard_check_linters_for_view: defaultdict[Bid, threading.Lock] = defaultdict(threading.Lock)
buffer_filenames: dict[Bid, FileName] = {}
buffer_base_scopes: dict[Bid, str] = {}


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

        # check if the view has been renamed
        renamed_filename = detect_rename(view)
        if renamed_filename:
            update_on_filename_change(*renamed_filename)

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

    def on_close(self, view: sublime.View) -> None:
        bid = view.buffer_id()
        filename = util.canonical_filename(view)

        open_filenames = set()
        for w in sublime.windows():
            for v in w.views():
                if v.buffer_id() == bid:
                    # abort since another view into the same buffer is open
                    return

                open_filenames.add(util.canonical_filename(v))

        # We want to discard this file and its dependencies but never a
        # file that is currently open or still referenced by another
        dependencies_per_file = {
            filename_: set(flatten(deps_per_linter.values()))
            for filename_, deps_per_linter in persist.affected_filenames_per_filename.items()
        }
        direct_deps = dependencies_per_file.pop(filename, set())
        other_deps = set(flatten(dependencies_per_file.values()))

        to_discard = ({filename} | direct_deps) - open_filenames - other_deps
        for fn in to_discard:
            persist.affected_filenames_per_filename.pop(fn, None)
            persist.file_errors.pop(fn, None)

        persist.assigned_linters.pop(bid, None)
        guard_check_linters_for_view.pop(bid, None)
        buffer_filenames.pop(bid, None)
        buffer_base_scopes.pop(bid, None)
        queue.cleanup(bid)


def detect_rename(view: sublime.View) -> tuple[FileName, FileName] | None:
    bid = view.buffer_id()
    current_filename = util.canonical_filename(view)

    try:
        old_filename = buffer_filenames[bid]
    except KeyError:
        return None
    else:
        if old_filename != current_filename:
            return (old_filename, current_filename)

        return None
    finally:
        buffer_filenames[bid] = current_filename


def has_syntax_changed(view: sublime.View) -> bool:
    bid = view.buffer_id()
    base_scope = view.scope_name(0).split(" ")[0]

    try:
        old_value = buffer_base_scopes[bid]
    except KeyError:
        return True
    else:
        return old_value != base_scope
    finally:
        buffer_base_scopes[bid] = base_scope


class sublime_linter_lint(sublime_plugin.TextCommand):
    """A command that lints the current view if it has a linter."""

    def want_event(self):
        return True

    def is_visible(self, event=None, **kwargs):
        return (
            util.is_lintable(self.view)
            and any(
                "on_modified" not in linter_module.get_effective_lint_mode(info.settings)
                for info in elect.runnable_linters_for_view(self.view, "on_user_request")
            )
        ) if event else True

    def run(self, edit, event=None):
        assignable_linters = list(
            elect.assignable_linters_for_view(self.view, "on_user_request")
        )
        if not assignable_linters:
            flash(self.view, "No linters available for this view")
            return

        runnable_linters = [
            info.name
            for info in elect.filter_runnable_linters(assignable_linters)
        ]
        if not runnable_linters:
            flash(self.view, "No runnable linters, probably save first")
            return

        flash(self.view, "Running {}".format(", ".join(runnable_linters)))
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
            if view.buffer_id() in persist.assigned_linters and view.is_primary():
                hit(view, 'relint_views')


def hit(view: sublime.View, reason: Reason) -> None:
    """Record an activity that could trigger a lint and enqueue a desire to lint."""
    bid = view.buffer_id()

    delay = backend.get_delay() if reason == 'on_modified' else 0.0
    logger.info(
        "Delay linting '{}' for {:.2}s"
        .format(util.short_canonical_filename(view), delay)
    )
    lock = guard_check_linters_for_view[bid]
    view_has_changed = make_view_has_changed_fn(view)
    fn = partial(lint, view, view_has_changed, lock, reason)
    queue.debounce(fn, delay=delay, key=bid)


def lint(view: sublime.View, view_has_changed: ViewChangedFn, lock: threading.Lock, reason: Reason) -> None:
    """Lint the view with the given id."""
    if view.settings().get(IS_ENABLED_SWITCH) is False:
        linters = []
    else:
        linters = list(elect.assignable_linters_for_view(view, reason))
        if not linters:
            logger.info("No installed linter matches the view.")

    with lock:
        _assign_linters_to_view(view, {linter.name for linter in linters})

    runnable_linters = list(elect.filter_runnable_linters(linters))
    if not runnable_linters:
        return

    window = view.window()
    bid = view.buffer_id()
    filename = util.canonical_filename(view)

    # Very, very unlikely that `view_has_changed` is already True at this
    # point, but it also implements the kill_switch, so we ask here
    if view_has_changed():  # abort early
        return

    assert window  # now that `view_has_changed` has been checked

    if persist.settings.get('kill_old_processes'):
        kill_active_popen_calls(bid)

    sink = partial(
        group_by_filename_and_update, window, filename, view_has_changed, reason)
    backend.lint_view(runnable_linters, view, view_has_changed, sink)


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


def group_by_filename_and_update(
    window: sublime.Window,
    main_filename: FileName,
    view_has_changed: ViewChangedFn,
    reason: Reason,
    linter: LinterName,
    errors: list[LintError]
) -> None:
    """Group lint errors by filename and update them."""
    if view_has_changed():  # abort early
        return

    grouped: defaultdict[FileName, list[LintError]] = defaultdict(list)
    for error in errors:
        grouped[error['filename']].append(error)

    # The contract for a simple linter is that it reports `[errors]` or an
    # empty list `[]` if the buffer is clean. For linters that report errors
    # for multiple files we collect information about which files are actually
    # reported by a given linted file so that we can clean the results.
    affected_filenames = persist.affected_filenames_per_filename[main_filename]
    previous_filenames = affected_filenames[linter]

    current_filenames = set(grouped.keys()) - {main_filename}
    affected_filenames[linter] = current_filenames

    # Basically, we must fake a `[]` response for every filename that is no
    # longer reported.
    # For the main view we MUST *always* report an outcome. This is not for
    # cleanup but functions as a signal that we're done. Merely for the status
    # bar view.
    clean_files = previous_filenames - current_filenames
    for filename in clean_files | {main_filename}:
        grouped[filename]  # For the side-effect of creating a new empty `list`

    for filename, errors in grouped.items():
        # Ignore errors of other files if their view is dirty; but still
        # propagate if there are no errors, t.i. cleanup is allowed even
        # then.
        if filename != main_filename and errors:
            view = window.find_open_file(filename)
            if view and view.is_dirty():
                continue

        update_file_errors(filename, linter, errors, reason)


def update_file_errors(
    filename: FileName,
    linter: LinterName,
    errors: list[LintError],
    reason: Optional[Reason] = None
) -> None:
    """Persist lint error changes and broadcast."""
    update_errors_store(filename, linter, errors)
    events.broadcast(events.LINT_RESULT, {
        'filename': filename,
        'linter_name': linter,
        'errors': errors,
        'reason': reason
    })


def update_errors_store(filename: FileName, linter_name: LinterName, errors: list[LintError]) -> None:
    persist.file_errors[filename] = [
        error
        for error in persist.file_errors[filename]
        if error['linter'] != linter_name
    ] + errors


def update_on_filename_change(old_filename: FileName, new_filename: FileName) -> None:
    # update the error store
    if old_filename in persist.file_errors:
        errors = persist.file_errors.pop(old_filename)
        persist.file_errors[new_filename] = errors

    # update the affected filenames
    if old_filename in persist.affected_filenames_per_filename:
        filenames = persist.affected_filenames_per_filename.pop(old_filename)
        persist.affected_filenames_per_filename[new_filename] = filenames

    # notify the views
    events.broadcast('file_renamed', {
        'new_filename': new_filename,
        'old_filename': old_filename
    })


def force_redraw():
    for filename, errors in persist.file_errors.items():
        for linter_name, linter_errors in group_by_linter(errors).items():
            events.broadcast(events.LINT_RESULT, {
                'filename': filename,
                'linter_name': linter_name,
                'errors': linter_errors
            })


def group_by_linter(errors: list[LintError]) -> defaultdict[LinterName, list[LintError]]:
    by_linter: defaultdict[LinterName, list[LintError]] = defaultdict(list)
    for error in errors:
        by_linter[error['linter']].append(error)

    return by_linter


def _assign_linters_to_view(view: sublime.View, next_linters: set[LinterName]) -> None:
    window = view.window()
    # It is possible that the user closes the view during debounce time,
    # in that case `window` will get None and we will just abort. We check
    # here bc above code is slow enough to make the difference. We don't
    # pass a valid `window` around bc we do not want to update `assigned_linters`
    # for detached views as well bc `on_close` already has been called
    # at this time.
    if not window:
        return

    bid = view.buffer_id()
    filename = util.canonical_filename(view)
    current_linters = persist.assigned_linters.get(bid, set())

    persist.assigned_linters[bid] = next_linters
    window.run_command('sublime_linter_assigned', {
        'filename': filename,
        'linter_names': list(next_linters)
    })

    affected_files = persist.affected_filenames_per_filename[filename]
    for linter in (current_linters - next_linters):
        affected_files.pop(linter, None)
        update_file_errors(filename, linter, [])


def make_view_has_changed_fn(view: sublime.View) -> ViewChangedFn:
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
