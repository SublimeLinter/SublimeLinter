import sublime

from concurrent.futures import ThreadPoolExecutor, wait, FIRST_EXCEPTION
from itertools import chain, count
from functools import partial
import hashlib
import logging
import multiprocessing
import os
import threading

from . import linter as linter_module, style, util


if False:
    from typing import Callable, Dict, Iterator, List, Optional, Tuple, Type, TypeVar
    from .persist import LintError
    from .elect import LinterInfo
    Linter = linter_module.Linter
    LinterSettings = linter_module.LinterSettings

    T = TypeVar('T')
    LintResult = List[LintError]
    Task = Callable[[], T]
    ViewChangedFn = Callable[[], bool]
    LinterName = str


logger = logging.getLogger(__name__)

MAX_CONCURRENT_TASKS = multiprocessing.cpu_count() or 1
orchestrator = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_TASKS)
executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_TASKS)


task_count = count(start=1)
counter_lock = threading.Lock()


def lint_view(
    linters,           # type: List[LinterInfo]
    view,              # type: sublime.View
    view_has_changed,  # type: ViewChangedFn
    next               # type: Callable[[LinterName, LintResult], None]
):
    # type: (...) -> None
    """Lint the given view.

    This is the top level lint dispatcher. It is called
    asynchronously.
    """
    lint_tasks = {
        linter['name']: list(tasks_per_linter(view, view_has_changed, linter['klass'], linter['settings']))
        for linter in linters
    }
    warn_excessive_tasks(view, lint_tasks)

    run_concurrently([
        partial(run_tasks, tasks, next=partial(next, linter_name))
        for linter_name, tasks in lint_tasks.items()
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


def warn_excessive_tasks(view, uow):
    # type: (sublime.View, Dict[LinterName, List[Task[LintResult]]]) -> None
    total_tasks = sum(len(tasks) for tasks in uow.values())
    if total_tasks > 4:
        linter_info = ", ".join(
            "{}x {}".format(len(tasks), linter_name)
            for linter_name, tasks in uow.items()
        )
        logger.warning(
            "'{}' puts in total {}(!) tasks on the queue:  {}."
            .format(short_canonical_filename(view), total_tasks, linter_info)
        )
    else:
        for linter_name, tasks in uow.items():
            if len(tasks) > 3:
                logger.warning(
                    "'{}' puts {} {} tasks on the queue."
                    .format(short_canonical_filename(view), len(tasks), linter_name)
                )


def tasks_per_linter(view, view_has_changed, linter_class, settings):
    # type: (sublime.View, ViewChangedFn, Type[Linter], LinterSettings) -> Iterator[Task[LintResult]]
    selector = settings.get('selector')
    if selector is None:
        return []

    for region in extract_lintable_regions(view, selector):
        linter = linter_class(view, settings.clone())
        code = view.substr(region)
        offsets = view.rowcol(region.begin()) + (region.begin(),)

        # Due to a limitation in python 3.3, we cannot 'name' a thread when
        # using the ThreadPoolExecutor. (This feature has been introduced
        # in python 3.6.) So, we do this manually.
        task_name = make_good_task_name(linter, view)
        task = partial(execute_lint_task, linter, code, offsets, view_has_changed)
        executor = partial(modify_thread_name, task_name, task)
        yield executor


def extract_lintable_regions(view, selector):
    # type: (sublime.View, str) -> List[sublime.Region]
    # Inspecting just the first char is faster
    if view.score_selector(0, selector):
        return [sublime.Region(0, view.size())]
    else:
        return [region for region in view.find_by_selector(selector)]


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
    # type: (Linter, str, Tuple, ViewChangedFn) -> LintResult
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


PROPERTIES_FOR_UID = (
    'filename', 'linter', 'line', 'start', 'error_type', 'code', 'msg',
)


def make_error_uid(error):
    # type: (LintError) -> str
    return hashlib.sha256(
        ''.join(
            str(error[k])  # type: ignore
            for k in PROPERTIES_FOR_UID
        )
        .encode('utf-8')
    ).hexdigest()


def finalize_errors(linter, errors, offsets):
    # type: (Linter, List[LintError], Tuple[int, ...]) -> None
    linter_name = linter.name
    view = linter.view
    eof = view.size()
    view_filename = util.get_filename(view)
    line_offset, col_offset, pt_offset = offsets

    for error in errors:
        belongs_to_main_file = (
            os.path.normcase(error['filename']) == os.path.normcase(view_filename)
        )

        region, line, start = error['region'], error['line'], error['start']
        offending_text = error['offending_text']
        if belongs_to_main_file:  # offsets are for the main file only
            if line == 0:
                start += col_offset
            line += line_offset
            region = sublime.Region(region.a + pt_offset, region.b + pt_offset)
            # If only parts of a file are linted, the virtual view inside
            # the linter can "think" it has an error on eof when it is
            # actually on the end of the linted *part* of the file only.
            # Check here, and maybe undo.
            if region.empty() and region.a != eof:
                region.b += 1
                offending_text = view.substr(region)

        error.update({
            'linter': linter_name,
            'region': region,
            'line': line,
            'start': start,
            'offending_text': offending_text,
        })

        error.update({
            'uid': make_error_uid(error),
            'priority': style.get_value('priority', error, 0),
        })


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
