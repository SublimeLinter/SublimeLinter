"""This module provides the SublimeLinter plugin class and supporting methods."""
from __future__ import annotations

from collections import defaultdict
from itertools import chain
import logging

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
from .lint.util import flash


from typing import Callable
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


buffer_filenames: dict[Bid, FileName] = {}
buffer_base_scopes: dict[Bid, str] = {}


class BackendController(sublime_plugin.EventListener):
    @util.distinct_until_buffer_changed
    def on_modified_async(self, view):
        if not util.is_lintable(view):
            return

        backend.hit(view, 'on_modified')

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
            persist.record_filename_change(*renamed_filename)

        if has_syntax_changed(view):
            backend.hit(view, 'on_load')

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

        backend.hit(view, 'on_save')

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

    def run(self, edit, event=None, run: list[LinterName] = []):
        if not isinstance(run, list):
            run = [run]  # type: ignore[unreachable]

        assignable_linters = list(
            elect.assignable_linters_for_view(self.view, "on_user_request", set(run))
        )
        if not assignable_linters:
            flash(self.view, "No linters available for this view")
            return

        if run:
            unavailable_linters = set(run) - {linter.name for linter in assignable_linters}
        else:
            unavailable_linters = set()

        runnable_linters = [
            info.name
            for info in elect.filter_runnable_linters(assignable_linters)
        ]

        feedback = ". ".join(filter(None, (
            (
                "Running {}".format(", ".join(runnable_linters))
                if runnable_linters else
                ""
                if unavailable_linters
                else "No runnable linters, probably save first"
            ),
            (
                f"Requested {backend.format_linter_availability_note(unavailable_linters)} "
                "not available for this view"
                if unavailable_linters
                else ""
            )
        )))
        flash(self.view, feedback)

        if not runnable_linters:
            return
        backend.hit(self.view, 'on_user_request', only_run=run)


class sublime_linter_config_changed(sublime_plugin.ApplicationCommand):
    def run(self, hint: str = None, wid: sublime.WindowId = None, linter: list[LinterName] = []):
        if hint is None or hint == 'relint':
            relint_views(wid, linter)
        elif hint == 'redraw':
            force_redraw()


def relint_views(wid: sublime.WindowId = None, linter: list[LinterName] = []):
    windows = [sublime.Window(wid)] if wid else sublime.windows()
    for window in windows:
        for view in window.views():
            if view.buffer_id() in persist.assigned_linters and view.is_primary():
                backend.hit(view, 'relint_views', only_run=linter)


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
