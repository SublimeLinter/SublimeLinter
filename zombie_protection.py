from collections import defaultdict

import sublime
import sublime_plugin

from .lint import events

"""
Sublime internally stores all highlighted regions and gutter icons
within its 'undo' machine. These are part of the buffer state.
The problem herein is that even if we deleted some highlights long ago
Sublime will resurrect them on undo/redo. These resurrected regions
are in fact zombies bc otherwise SL has forgotten their keys, and thus
can not access them anymore. E.g. we cannot delete them again.
In SL we only transition from the *current* set of region keys to the
*next*.
The solution is to model a separate, own undo machine which reimplements
Sublime's undo stack and essentially stores all region keys ever drawn.

Ticks:        1 2 3 4 5 6 7 8 9 0 1
Edit States:  a     b     c   d
Draw States:    A B   C D   E   F G
                   \     \   \
Undo:               B B B D D E E E

Undo Stack:     A B B C D D E E F G   (-1)
                    B B B D D E E E   (-2)
                          B B D D D   (-3)
                              B B B   (-4)

E.g. of Sublime's behavior: If your at '6' and hit 'undo' Sublime will
not jump to pos '1', but to '3'. SL core store will still think it has
drawn 'D', but Sublime replaced the regions from its undo stack and
so actually the view/buffer state is 'B'. (To further elaborate: If we
now get new results 'H' from any linter SL core would thus transition from
set 'D' -> 'H', but it must transition from 'B' -> 'H'. Note: Usually
the new state H is derived from and very similar to B if not the same
since it is computed from the source code 'a'.)

"""


# TODO Move to util and use it throughout SL
def distinct_until_buffer_changed(method):
    last_call = None

    def wrapper(self, view):
        nonlocal last_call

        bid = view.buffer_id()
        change_count = view.change_count()
        this_call = (bid, change_count)
        if this_call == last_call:
            return

        last_call = this_call
        method(self, view)

    return wrapper


def plugin_unloaded():
    events.off(on_lint_result)


IGNORE_NEXT_MODIFIED_EVENT = set()


class UndoManager(sublime_plugin.EventListener):
    @distinct_until_buffer_changed
    def on_modified_async(self, view):
        bid = view.buffer_id()
        if bid in IGNORE_NEXT_MODIFIED_EVENT:
            IGNORE_NEXT_MODIFIED_EVENT.discard(bid)
            return

        count = count_command_history_changes(view)
        if count == -1:
            replace_top_undo_state(view)
            forget_redo_states(view)
        elif count > 0:
            store_undo_states(view, count)
            forget_redo_states(view)

    def on_text_command(self, view, cmd, args):
        if cmd == 'undo':
            IGNORE_NEXT_MODIFIED_EVENT.add(view.buffer_id())
            undo_region_state(view)
        elif cmd == 'redo_or_repeat':
            IGNORE_NEXT_MODIFIED_EVENT.add(view.buffer_id())
            redo_region_state(view)

    def on_pre_close(self, view):
        bid = view.buffer_id()
        views_into_buffer = list(all_views_into_buffer(bid))

        if len(views_into_buffer) <= 1:
            IGNORE_NEXT_MODIFIED_EVENT.discard(bid)
            COMMAND_HISTORY_STORE.pop(bid, None)
            UNDO_STACK.pop(bid, None)
            REDO_STACK.pop(bid, None)


@events.on(events.LINT_RESULT)
def on_lint_result(buffer_id, linter_name, **kwargs):
    # Now, whenever new lint results fly in, we possibly draw, and with
    # it we actually modify the buffer **without** an 'on_modified' event
    # and **without** generating a new undo command in Sublime's
    # `command_history`.
    # Still, Sublime internally holds these updated regions as buffer state,
    # so we treat them like undoable updates and modify the top undo command.
    try:
        view = next(all_views_into_buffer(buffer_id))
    except StopIteration:
        ...
    else:
        sublime.set_timeout_async(
            # timeout=1 so we actually run as soon as possible **after**
            # this 'micro'-task. Essentially, we want to run after the
            # main side-effects of the event (here probably: drawing)
            # are done.
            lambda: replace_top_undo_state(view), 1)


def all_views_into_buffer(buffer_id):
    for window in sublime.windows():
        for view in window.views():
            if view.buffer_id() == buffer_id:
                yield view


LOOK_BACK_LENGTH = 10
COMMAND_HISTORY_STORE = defaultdict(list)
UNDO_STACK = defaultdict(list)
REDO_STACK = defaultdict(list)
NONE_UNDO_CMD = (None, None, None)


def count_command_history_changes(view):
    current = [
        view.command_history(n, True)
        for n in range(0, -LOOK_BACK_LENGTH, -1)]
    current = list(map(normalize_undo_command, current))

    bid = view.buffer_id()
    previous = COMMAND_HISTORY_STORE[bid]

    # On the first run assume '1'
    if not previous:
        count = 1

    # If you type fast enough, Sublime will exchange the topmost undo cmd
    elif (
        previous[0] != current[0] and
        previous[1:] == current[1:]
    ):
        count = -1

    # Otherwise one or more items are added on top of the stack. E.g.
    #   previous => v, w, x, y, z
    #   current  => a, b, v, w, x
    # So we check which possible suffix of `current` matches the beginning
    # (prefix) of `previous`. E.g.
    #   `previous` starts_with? b, v, w, x  => False
    #   `previous` starts_with? v, w, x     => True
    else:
        count = next((
            n for n in range(1, LOOK_BACK_LENGTH)
            if starts_with(previous, current[n:])
        ), 1)  # Assume 1 if no match can be found

    COMMAND_HISTORY_STORE[bid] = current
    return count


def normalize_undo_command(undo_command_description):
    # Sublime does not return a stable 'None' command, but a falsy `cmd`
    # is a stable indicator.
    cmd, _args, _count = undo_command_description
    return undo_command_description if cmd else NONE_UNDO_CMD


def starts_with(list, sublist):
    return (
        # Note: A generalized `starts_with` needs to check the list
        # lengths as well. But here we know that sublist is always
        # smaller than list
        # len(sublist) <= len(list) and
        all(a == b for (a, b) in zip(list, sublist))
    )


def replace_top_undo_state(view):
    bid = view.buffer_id()
    keys = get_regions_keys(view)
    try:
        UNDO_STACK[bid][-1] = keys
    except IndexError:
        return


def store_undo_states(view, count):
    bid = view.buffer_id()
    keys = get_regions_keys(view)
    UNDO_STACK[bid].extend([keys] * count)


def forget_redo_states(view):
    bid = view.buffer_id()
    REDO_STACK[bid].clear()


def undo_region_state(view):
    bid = view.buffer_id()
    # On top op the UNDO_STACK is always the current state.
    # On undo we `pop` the current state and store it in the REDO_STACK.
    try:
        keys = UNDO_STACK[bid].pop()
    except IndexError:
        return
    else:
        REDO_STACK[bid].append(keys)

    load_current_state(view)


def redo_region_state(view):
    bid = view.buffer_id()
    try:
        keys = REDO_STACK[bid].pop()
    except IndexError:
        return
    else:
        UNDO_STACK[bid].append(keys)

    load_current_state(view)


def load_current_state(view):
    bid = view.buffer_id()
    try:
        keys = UNDO_STACK[bid][-1]
    except IndexError:
        ...
    else:
        remember_region_keys(view, keys)


STORAGE_KEY = 'SL.{vid}.region_keys'


def remember_region_keys(view, keys):
    setting_key = STORAGE_KEY.format(vid=view.id())
    view.settings().set(setting_key, list(keys))


def get_regions_keys(view):
    setting_key = STORAGE_KEY.format(vid=view.id())
    return set(view.settings().get(setting_key) or [])
