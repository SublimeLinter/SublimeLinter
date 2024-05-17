import sublime

from collections import deque
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_EXCEPTION
from contextlib import contextmanager
from itertools import chain, count
from functools import lru_cache, partial
import hashlib
import logging
import multiprocessing
import os
import time
import threading

from . import events, linter as linter_module, persist, style, util


MYPY = False
if MYPY:
    from typing import Callable, Dict, Iterator, List, Optional, Tuple, TypeVar
    from .persist import LintError
    from .elect import LinterInfo
    Linter = linter_module.Linter
    LinterSettings = linter_module.LinterSettings

    T = TypeVar('T')
    LintResult = List[LintError]
    Task = Callable[[], T]
    ViewChangedFn = Callable[[], bool]
    FileName = str
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

    This is the top level lint dispatcher. It falls through.
    """
    lint_tasks = {
        linter.name: tasks
        for linter in linters
        if (tasks := list(tasks_per_linter(view, view_has_changed, linter)))
    }
    warn_excessive_tasks(view, lint_tasks)

    for linter_name, tasks in lint_tasks.items():
        orchestrator.submit(
            partial(run_tasks, linter_name, view, tasks, next=partial(next, linter_name))
        )


def run_tasks(linter_name, view, tasks, next):
    # type: (LinterName, sublime.View, List[Task[LintResult]], Callable[[LintResult], None]) -> None
    with broadcast_lint_runtime(util.canonical_filename(view), linter_name):
        with remember_runtime(
            "Linting '{}' with {} took {{:.2f}}s"
            .format(util.short_canonical_filename(view), linter_name)
        ):
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
        excess_warning(
            "'{}' puts in total {}(!) tasks on the queue:  {}."
            .format(util.short_canonical_filename(view), total_tasks, linter_info)
        )
    else:
        for linter_name, tasks in uow.items():
            if len(tasks) > 3:
                excess_warning(
                    "'{}' puts {} {} tasks on the queue."
                    .format(util.short_canonical_filename(view), len(tasks), linter_name)
                )


@lru_cache(4)
def excess_warning(msg):
    # type: (str) -> None
    logger.warning(msg)


def tasks_per_linter(view, view_has_changed, linter_info):
    # type: (sublime.View, ViewChangedFn, LinterInfo) -> Iterator[Task[LintResult]]
    for region in linter_info.regions:
        linter = linter_info.klass(view, linter_info.settings.clone())
        code = view.substr(region)
        offsets = view.rowcol(region.begin()) + (region.begin(),)

        task_name = make_good_task_name(linter, view)
        task = partial(execute_lint_task, linter, code, offsets, view_has_changed)
        executor = partial(modify_thread_name, task_name, task)
        yield executor


def make_good_task_name(linter, view):
    # type: (Linter, sublime.View) -> str
    with counter_lock:
        task_number = next(task_count)

    short_canonical_filename = util.short_canonical_filename(view)
    return 'LintTask|{}|{}|{}|{}'.format(
        task_number, linter.name, short_canonical_filename, view.id())


def modify_thread_name(name, sink):
    # type: (str, Callable[..., T]) -> T
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
    view_filename = util.canonical_filename(view)
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
        # The catch-all will obviously catch any exceptions coming from the
        # actual task/future. But it will also catch 'CancelledError's from
        # the executor machinery.
        return None


global_lock = threading.RLock()
elapsed_runtimes = deque([0.6] * 3, maxlen=10)
MIN_DEBOUNCE_DELAY = 0.0005
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
    # type: (str) -> Iterator[None]
    start_time = time.perf_counter()

    yield

    end_time = time.perf_counter()
    runtime = end_time - start_time
    logger.info(log_msg.format(runtime))

    with global_lock:
        elapsed_runtimes.append(runtime)


@contextmanager
def broadcast_lint_runtime(filename, linter_name):
    # type: (FileName, LinterName) -> Iterator[None]
    events.broadcast(events.LINT_START, {'filename': filename, 'linter_name': linter_name})
    try:
        yield
    finally:
        events.broadcast(events.LINT_END, {'filename': filename, 'linter_name': linter_name})
