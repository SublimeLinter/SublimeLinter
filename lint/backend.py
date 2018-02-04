import sublime

from concurrent.futures import ThreadPoolExecutor, as_completed, wait
from fnmatch import fnmatch
from itertools import chain
from functools import partial
import os
import traceback

from . import persist, util


WILDCARD_SYNTAX = '*'


def lint_view(view, hit_time, next):
    """
    Lint the given view.

    This is the top level lint dispatcher. It is called
    asynchronously. The following checks are done for each linter
    assigned to the view:

    - Check if the linter has been disabled in settings.
    - Check if the filename matches any patterns in the "excludes" setting.

    If a linter fails the checks, it is disabled for this run.
    Otherwise, if the mapped syntax is not in the linter's selectors,
    the linter is run on the entirety of code.

    Then the set of selectors for all linters assigned to the view is
    aggregated, and for each selector, if it occurs in sections,
    the corresponding section is linted as embedded code.
    """
    linters, disabled_linters = get_linters(view)

    # The contract here is that we MUST fire 'updates' for every linter, so
    # that the views (status bar etc) actually update.
    for linter in disabled_linters:
        next(linter, [])

    lint_tasks = get_lint_tasks(linters, view, hit_time)

    run_concurrently(
        partial(run_tasks, tasks, next=partial(next, linter))
        for linter, tasks in lint_tasks
    )


def run_tasks(tasks, next):
    results = run_concurrently(tasks)
    errors = list(chain.from_iterable(results))  # flatten and consume

    # We don't want to guarantee that our consumers/views are thread aware.
    # So we merge here into Sublime's shared worker thread. Sublime guarantees
    # here to execute all scheduled tasks ordered and sequentially.
    sublime.set_timeout_async(lambda: next(errors))


def get_lint_tasks(linters, view, hit_time):
    for (linter, settings, regions) in get_lint_regions(linters, view):

        def make_task(linter, settings, region):
            code = view.substr(region)
            offset = view.rowcol(region.begin())
            return partial(
                execute_lint_task, linter, code, offset, hit_time, settings
            )

        yield linter, map(partial(make_task, linter, settings), regions)


def execute_lint_task(linter, code, offset, hit_time, settings):
    errors = linter.lint(code, hit_time, settings) or []
    translate_lineno_and_column(errors, offset)

    return errors


def translate_lineno_and_column(errors, offset):
    if offset == (0, 0):
        return

    line_offset, col_offset = offset

    for error in errors:
        line = error['line']
        error['line'] = line + line_offset

        if line == 0:
            error.update({
                'start': error['start'] + col_offset,
                'end': error['end'] + col_offset
            })


def get_lint_regions(linters, view):
    syntax = util.get_syntax(view)
    for (linter, settings) in linters:
        if (
            syntax not in linter.selectors and
            WILDCARD_SYNTAX not in linter.selectors
        ):
            yield linter, settings, [sublime.Region(0, view.size())]

        else:
            yield linter, settings, [
                region
                for selector in get_selectors(linter, syntax)
                for region in view.find_by_selector(selector)
            ]


def get_selectors(linter, wanted_syntax):
    for syntax in [wanted_syntax, WILDCARD_SYNTAX]:
        try:
            yield linter.selectors[syntax]
        except KeyError:
            pass


def get_linters(view):
    filename = view.file_name()
    vid = view.id()

    enabled, disabled = [], []
    for linter in persist.view_linters.get(vid, []):
        # First check to see if the linter can run in the current lint mode.
        if linter.tempfile_suffix == '-' and view.is_dirty():
            disabled.append(linter)
            continue

        view_settings = linter._get_view_settings()

        if view_settings.get('disable'):
            disabled.append(linter)
            continue

        if filename:
            filename = os.path.realpath(filename)
            excludes = util.convert_type(view_settings.get('excludes', []), [])

            if excludes:
                matched = False

                for pattern in excludes:
                    if fnmatch(filename, pattern):
                        persist.debug(
                            '{} skipped \'{}\', excluded by \'{}\''
                            .format(linter.name, filename, pattern)
                        )
                        matched = True
                        break

                if matched:
                    disabled.append(linter)
                    continue

        enabled.append((linter, view_settings))

    return enabled, disabled


def run_concurrently(tasks, max_workers=5):
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        work = [executor.submit(task) for task in tasks]
        results = await_futures(work)
        return list(results)  # consume the generator immediately


def await_futures(fs, ordered=False):
    if ordered:
        done, _ = wait(fs)
    else:
        done = as_completed(fs)

    for future in done:
        try:
            yield future.result()
        except Exception:
            ...
            traceback.print_exc()
