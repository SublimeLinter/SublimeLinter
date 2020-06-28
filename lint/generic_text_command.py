from contextlib import contextmanager, ExitStack
from functools import lru_cache, wraps
import inspect
import threading
import uuid

import sublime
import sublime_plugin

MYPY = False
if MYPY:
    from typing import (
        Any, Callable, ContextManager, Dict, Iterator, List, Optional,
        Tuple, TypeVar
    )
    T = TypeVar("T")
    Callback = Tuple[Callable, Tuple[Any, ...], Dict[str, Any]]
    ReturnValue = Any
    WrapperFn = Callable[[sublime.View], ContextManager[None]]


lock = threading.Lock()
COMMANDS = {}  # type: Dict[str, Callback]
RESULTS = {}  # type: Dict[str, ReturnValue]


def run_as_text_command(fn, view, *args, **kwargs):
    # type: (Callable[..., T], sublime.View, Any, Any) -> Optional[T]
    token = uuid.uuid4().hex
    with lock:
        COMMANDS[token] = (fn, (view, ) + args, kwargs)
    view.run_command('sl_generic_text_cmd', {'token': token})
    with lock:
        # If the view has been closed, Sublime will not run
        # text commands on it anymore (but also not throw).
        # For now, we stay close, don't raise and just return
        # `None`.
        rv = RESULTS.pop(token, None)
    return rv


def text_command(fn):
    # type: (Callable[..., T]) -> Callable[..., T]
    @wraps(fn)
    def decorated(view, *args, **kwargs):
        # type: (sublime.View, Any, Any) -> Optional[T]
        return run_as_text_command(fn, view, *args, **kwargs)
    return decorated


@lru_cache()
def wants_edit_object(fn):
    sig = inspect.signature(fn)
    return 'edit' in sig.parameters


class sl_generic_text_cmd(sublime_plugin.TextCommand):
    def run_(self, edit_token, cmd_args):
        cmd_args = self.filter_args(cmd_args)
        token = cmd_args['token']
        with lock:
            # Any user can "redo" text commands, but we don't want that.
            try:
                fn, args, kwargs = COMMANDS.pop(token)
            except KeyError:
                return

        edit = self.view.begin_edit(edit_token, self.name(), cmd_args)
        try:
            if wants_edit_object(fn):
                return self.run(token, fn, args[0], edit, *args[1:], **kwargs)
            else:
                return self.run(token, fn, *args, **kwargs)
        finally:
            self.view.end_edit(edit)

    def run(self, token, fn, *args, **kwargs):
        rv = fn(*args, **kwargs)
        with lock:
            RESULTS[token] = rv


# `replace_view_content` is a wrapper for `_replace_region` to get some
# typing support from mypy.
def replace_view_content(view, text, region=None, wrappers=[]):
    # type: (sublime.View, str, sublime.Region, List[WrapperFn]) -> None
    """Replace the content of the view

    If no region is given the whole content will get replaced. Otherwise
    only the selected region.
    """
    _replace_region(view, text, region, wrappers)


@text_command
def _replace_region(view, edit, text, region=None, wrappers=[]):
    # type: (sublime.View, sublime.Edit, str, sublime.Region, List[WrapperFn]) -> None
    if region is None:
        # If you "replace" (or expand) directly at the cursor,
        # the cursor expands into a selection.
        # This is a common case for an empty view so we take
        # care of it out of box.
        region = sublime.Region(0, max(1, view.size()))

    wrappers = wrappers[:] + [stable_viewport]
    if any(
        region.contains(s) or region.intersects(s)
        for s in view.sel()
    ):
        wrappers += [restore_cursors]

    with ExitStack() as stack:
        for wrapper in wrappers:
            stack.enter_context(wrapper(view))
        stack.enter_context(writable_view(view))
        view.replace(edit, region, text)


@contextmanager
def writable_view(view):
    # type: (sublime.View) -> Iterator[None]
    is_read_only = view.is_read_only()
    view.set_read_only(False)
    try:
        yield
    finally:
        view.set_read_only(is_read_only)


@contextmanager
def restore_cursors(view):
    # type: (sublime.View) -> Iterator[None]
    save_cursors = [
        (view.rowcol(s.begin()), view.rowcol(s.end()))
        for s in view.sel()
    ] or [((0, 0), (0, 0))]

    try:
        yield
    finally:
        view.sel().clear()
        for (begin, end) in save_cursors:
            view.sel().add(
                sublime.Region(view.text_point(*begin), view.text_point(*end))
            )


@contextmanager
def stable_viewport(view):
    # type: (sublime.View) -> Iterator[None]
    # Ref: https://github.com/SublimeTextIssues/Core/issues/2560
    # See https://github.com/jonlabelle/SublimeJsPrettier/pull/171/files
    # for workaround.
    vx, vy = view.viewport_position()
    try:
        yield
    finally:
        view.set_viewport_position((0, 0))  # intentional!
        view.set_viewport_position((vx, vy))
