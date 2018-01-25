import sublime

from collections import defaultdict
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
    linters = get_linters(view)
    lint_tasks = get_lint_tasks(linters, view, hit_time)

    tasks_by_linter = defaultdict(list)
    for linter, task in lint_tasks:
        tasks_by_linter[linter].append(task)

    all_errors = run_concurrently(
        partial(run_tasks, tasks) for linter, tasks in tasks_by_linter.items()
    )
    all_errors = list(chain.from_iterable(all_errors))

    # We don't want to guarantee that our consumers/views are thread aware.
    # So we merge here into Sublime's shared worker thread. Sublime guarantees
    # here to execute all scheduled tasks ordered and sequentially.
    sublime.set_timeout_async(lambda: next(all_errors))


def run_tasks(tasks):
    results = run_concurrently(tasks)
    errors = list(chain.from_iterable(results))
    return errors


def get_lint_tasks(linters, view, hit_time):
    for (linter, region) in get_lint_regions(linters, view):
        code = view.substr(region)
        offset = view.rowcol(region.begin())
        yield linter, partial(execute_lint_task, linter, code, offset, hit_time)


def execute_lint_task(linter, code, offset, hit_time):
    errors = linter.lint(code, hit_time) or []
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
    for linter in linters:
        if (
            syntax not in linter.selectors and
            WILDCARD_SYNTAX not in linter.selectors
        ):
            yield (linter, sublime.Region(0, view.size()))

        else:
            for selector in get_selectors(linter, syntax):
                for region in view.find_by_selector(selector):
                    yield (linter, region)


def get_selectors(linter, wanted_syntax):
    for syntax in [wanted_syntax, WILDCARD_SYNTAX]:
        try:
            yield linter.selectors[syntax]
        except KeyError:
            pass


def get_linters(view):
    filename = view.file_name()
    vid = view.id()

    for linter in persist.view_linters.get(vid, []):
        # First check to see if the linter can run in the current lint mode.
        if linter.tempfile_suffix == '-' and view.is_dirty():
            continue

        view_settings = linter.get_view_settings()

        if view_settings.get('disable'):
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
                    continue

        yield linter


def run_concurrently(tasks, max_workers=5):
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        work = [executor.submit(task) for task in tasks]
        yield from await_futures(work)


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
