import sublime

from concurrent.futures import ThreadPoolExecutor, as_completed, wait
from itertools import chain, count
from functools import partial
import logging
import os
import threading

from . import util, linter as linter_module


logger = logging.getLogger(__name__)

WILDCARD_SYNTAX = '*'


task_count = count(start=1)
counter_lock = threading.Lock()


def lint_view(linters, view, view_has_changed, next):
    """Lint the given view.

    This is the top level lint dispatcher. It is called
    asynchronously.
    """
    lint_tasks = get_lint_tasks(linters, view, view_has_changed)

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


def get_lint_tasks(linters, view, view_has_changed):
    for (linter, settings, regions) in get_lint_regions(linters, view):
        tasks = []
        for region in regions:
            code = view.substr(region)
            if not code:
                continue

            offset = view.rowcol(region.begin())

            # Due to a limitation in python 3.3, we cannot 'name' a thread when
            # using the ThreadPoolExecutor. (This feature has been introduced
            # in python 3.6.) So, we pass the name down.
            with counter_lock:
                task_number = next(task_count)
            canonical_filename = (
                os.path.basename(view.file_name()) if view.file_name()
                else '<untitled {}>'.format(view.buffer_id()))
            task_name = 'LintTask|{}|{}|{}|{}'.format(
                task_number, linter.name, canonical_filename, view.id())

            tasks.append(partial(
                execute_lint_task, linter, code, offset, view_has_changed,
                settings, task_name
            ))
        yield linter, tasks


def execute_lint_task(linter, code, offset, view_has_changed, settings, task_name):
    try:
        # We 'name' our threads, for logging purposes.
        threading.current_thread().name = task_name

        errors = linter.lint(code, view_has_changed, settings) or []
        translate_lineno_and_column(errors, offset)

        return errors
    except BaseException:
        linter.notify_failure()
        # Log while multi-threaded to get a nicer log message
        logger.exception('Linter crashed.\n\n')
        return []  # Empty list here to clear old errors


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
        settings = linter_module.get_linter_settings(linter, view)
        selector = settings.get('selector')
        if selector:
            # Inspecting just the first char is faster
            if view.score_selector(0, selector):
                yield linter, settings, [sublime.Region(0, view.size())]
            else:
                yield linter, settings, [
                    region for region in view.find_by_selector(selector)
                ]

            continue

        # Fallback using deprecated `cls.syntax` and `cls.selectors`
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
        yield future.result()
