import sublime

from concurrent.futures import ThreadPoolExecutor, wait, FIRST_EXCEPTION
from itertools import chain, count
from functools import partial
import hashlib
import json
import logging
import multiprocessing
import os
import threading

from . import style, linter as linter_module


if False:
    from typing import Callable, Iterator, List, Optional, Tuple, TypeVar
    from .persist import LintError
    Linter = linter_module.Linter

    T = TypeVar('T')
    LintResult = List[LintError]
    Task = Callable[[], T]
    LinterName = str


logger = logging.getLogger(__name__)

MAX_CONCURRENT_TASKS = multiprocessing.cpu_count() or 1
orchestrator = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_TASKS)
executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_TASKS)


task_count = count(start=1)
counter_lock = threading.Lock()


def lint_view(
    linters,           # type: List[Linter]
    view,              # type: sublime.View
    view_has_changed,  # type: Callable[[], bool]
    next               # type: Callable[[LinterName, LintResult], None]
):
    # type: (...) -> None
    """Lint the given view.

    This is the top level lint dispatcher. It is called
    asynchronously.
    """
    lint_tasks = get_lint_tasks(linters, view, view_has_changed)

    run_concurrently([
        partial(run_tasks, tasks, next=partial(next, linter.name))
        for linter, tasks in lint_tasks
    ], executor=orchestrator)


def run_tasks(tasks, next):
    # type: (List[Task[LintResult]], Callable[[LintResult], None]) -> None
    results = run_concurrently(tasks, executor=executor)
    if results is None:
        return  # ABORT

    errors = list(chain.from_iterable(results))  # flatten and consume

    # We don't want to guarantee that our consumers/views are thread aware.
    # So we merge here into Sublime's shared worker thread. Sublime guarantees
    # here to execute all scheduled tasks ordered and sequentially.
    sublime.set_timeout_async(lambda: next(errors))


def get_lint_tasks(
    linters,           # type: List[Linter]
    view,              # type: sublime.View
    view_has_changed,  # type: Callable[[], bool]
):                     # type: (...) -> Iterator[Tuple[Linter, List[Task[LintResult]]]]
    total_tasks = 0
    for (linter, regions) in get_lint_regions(linters, view):
        tasks = _make_tasks(linter, regions, view, view_has_changed)
        total_tasks += len(tasks)
        yield linter, tasks

    if total_tasks > 4:
        logger.warning(
            "'{}' puts in total {}(!) tasks on the queue."
            .format(short_canonical_filename(view), total_tasks)
        )


def _make_tasks(linter_, regions, view, view_has_changed):
    # type: (Linter, List[sublime.Region], sublime.View, Callable[[], bool]) -> List[Task[LintResult]]
    independent_linters = create_n_independent_linters(linter_, len(regions))
    tasks = []  # type: List[Task[LintResult]]
    for linter, region in zip(independent_linters, regions):
        code = view.substr(region)
        offsets = view.rowcol(region.begin()) + (region.begin(),)

        # Due to a limitation in python 3.3, we cannot 'name' a thread when
        # using the ThreadPoolExecutor. (This feature has been introduced
        # in python 3.6.) So, we do this manually.
        task_name = make_good_task_name(linter, view)
        task = partial(execute_lint_task, linter, code, offsets, view_has_changed)
        executor = partial(modify_thread_name, task_name, task)
        tasks.append(executor)

    if len(tasks) > 3:
        logger.warning(
            "'{}' puts {} {} tasks on the queue."
            .format(short_canonical_filename(view), len(tasks), linter_.name)
        )
    return tasks


def create_n_independent_linters(linter, n):
    return (
        [linter]
        if n == 1
        else [clone_linter(linter) for _ in range(n)]
    )


def clone_linter(linter):
    # type: (linter_module.Linter) -> linter_module.Linter
    return linter.__class__(linter.view, linter.settings.clone())


def short_canonical_filename(view):
    return (
        os.path.basename(view.file_name())
        if view.file_name()
        else '<untitled {}>'.format(view.buffer_id())
    )


def make_good_task_name(linter, view):
    with counter_lock:
        task_number = next(task_count)

    canonical_filename = short_canonical_filename(view)
    return 'LintTask|{}|{}|{}|{}'.format(
        task_number, linter.name, canonical_filename, view.id())


def modify_thread_name(name, sink):
    original_name = threading.current_thread().name
    # We 'name' our threads, for logging purposes.
    threading.current_thread().name = name
    try:
        return sink()
    finally:
        threading.current_thread().name = original_name


def execute_lint_task(linter, code, offsets, view_has_changed):
    # type: (Linter, str, Tuple, Callable[[], bool]) -> LintResult
    try:
        errors = linter.lint(code, view_has_changed)
        finalize_errors(linter, errors, offsets)
        return errors
    except linter_module.TransientError:
        # For `TransientError`s we want to omit calling the `sink` at all.
        # Usually achieved by a `return None` (see: `run_tasks`). Here we
        # throw to abort all other tasks submitted (see: `run_concurrently`).
        # It's a bit stinky but good enough for our purpose.
        # Note that `run_concurrently` turns the whole result into a `None`,
        # making in turn the `result is None` check in `run_tasks` trivial.
        # If we were to return a `None` just here, we had to check
        # `None in result` instead. ¯\_(ツ)_/¯
        raise
    except linter_module.PermanentError:
        return []  # Empty list here to clear old errors
    except Exception:
        linter.notify_failure()
        # Log while multi-threaded to get a nicer log message
        logger.exception('Unhandled exception:\n', extra={'demote': True})
        return []  # Empty list here to clear old errors


def error_json_serializer(o):
    """Return a JSON serializable representation of error properties."""
    if isinstance(o, sublime.Region):
        return (o.a, o.b)

    return o


def finalize_errors(linter, errors, offsets):
    # type: (Linter, List[LintError], Tuple[int, ...]) -> None
    linter_name = linter.name
    view = linter.view
    line_offset, col_offset, pt_offset = offsets

    for error in errors:
        # see if this error belongs to the main file
        belongs_to_main_file = True
        if 'filename' in error:
            if (os.path.normcase(error['filename']) != os.path.normcase(view.file_name() or '') and
                    error['filename'] != "<untitled {}>".format(view.buffer_id())):
                belongs_to_main_file = False

        line, start, end = error['line'], error['start'], error['end']
        if belongs_to_main_file:  # offsets are for the main file only
            if line == 0:
                start += col_offset
                end += col_offset

            line += line_offset

        try:
            region = error['region']
        except KeyError:
            line_start = view.text_point(line, 0)
            region = sublime.Region(line_start + start, line_start + end)
            if len(region) == 0:
                region.b = region.b + 1

        else:
            if belongs_to_main_file:  # offsets are for the main file only
                region = sublime.Region(region.a + pt_offset, region.b + pt_offset)

        error.update({
            'line': line,
            'start': start,
            'end': end,
            'linter': linter_name,
            'region': region
        })

        uid = hashlib.sha256(
            json.dumps(error, sort_keys=True, default=error_json_serializer).encode('utf-8')).hexdigest()

        error.update({
            'uid': uid,
            'priority': style.get_value('priority', error, 0)
        })


def get_lint_regions(linters, view):
    # type: (List[Linter], sublime.View) -> Iterator[Tuple[Linter, List[sublime.Region]]]
    for linter in linters:
        settings = linter.get_view_settings()
        selector = settings.get('selector', None)
        if selector is not None:
            # Inspecting just the first char is faster
            if view.score_selector(0, selector):
                yield linter, [sublime.Region(0, view.size())]
            else:
                yield linter, [
                    region for region in view.find_by_selector(selector)
                ]


def run_concurrently(tasks, executor):
    # type: (List[Task[T]], ThreadPoolExecutor) -> Optional[List[T]]
    work = [executor.submit(task) for task in tasks]
    done, not_done = wait(work, return_when=FIRST_EXCEPTION)

    for future in not_done:
        future.cancel()

    try:
        return [future.result() for future in done]
    except Exception:
        # The catch-all will obviously catch any expections coming from the
        # actual task/future. But it will also catch 'CancelledError's from
        # the executor machinery.
        return None
