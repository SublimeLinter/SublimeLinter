from collections import defaultdict

import sublime_plugin


# Sublime internally stores all highlighted regions and gutter icons
# within its 'undo' machine. These are part of the buffer state.
# The problem herein is that even if we deleted some highlights long ago
# Sublime will resurrect them on undo/redo. These resurrected regions
# are in fact zombies bc otherwise SL has forgotten their keys, and thus
# can not access them anymore. E.g. we cannot delete them again.
# In SL we only transition from the *current* set of region keys to the
# *next*.
# The solution is to model a separate, own undo machine which essentially
# stores all region keys ever drawn.

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
        elif count > 0:
            store_undo_states(view, count)

    def on_text_command(self, view, cmd, args):
        if cmd == 'undo':
            IGNORE_NEXT_MODIFIED_EVENT.add(view.buffer_id())
            undo_region_state(view)
        elif cmd == 'redo_or_repeat':
            IGNORE_NEXT_MODIFIED_EVENT.add(view.buffer_id())
            redo_region_state(view)


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
    UNDO_STACK[bid][-1] = keys
    REDO_STACK[bid].clear()


def store_undo_states(view, count):
    bid = view.buffer_id()
    keys = get_regions_keys(view)
    UNDO_STACK[bid].extend([keys] * count)
    REDO_STACK[bid].clear()


def undo_region_state(view):
    bid = view.buffer_id()
    try:
        keys = UNDO_STACK[bid].pop()
    except IndexError:
        return

    REDO_STACK[bid].append(keys)
    current = get_regions_keys(view)
    remember_region_keys(view, current | keys)


def redo_region_state(view):
    bid = view.buffer_id()
    try:
        keys = REDO_STACK[bid].pop()
    except IndexError:
        return

    UNDO_STACK[bid].append(keys)
    current = get_regions_keys(view)
    remember_region_keys(view, current | keys)


STORAGE_KEY = 'SL.{vid}.region_keys'


def remember_region_keys(view, keys):
    setting_key = STORAGE_KEY.format(vid=view.id())
    view.settings().set(setting_key, list(keys))


def get_regions_keys(view):
    setting_key = STORAGE_KEY.format(vid=view.id())
    return set(view.settings().get(setting_key) or [])
