import sublime
import sublime_plugin

from itertools import dropwhile, takewhile
from .lint import persist


"""
Implement typical Goto Next Previous Error Commands. If you will, add
the following to your key bindings.

```
  { "keys": ["ctrl+k", "n"],
    "command": "sublime_linter_goto_error",
    "args": {"direction": "next"}
  },
  { "keys": ["ctrl+k", "p"],
    "command": "sublime_linter_goto_error",
    "args": {"direction": "previous"}
  },
```

Supported args:

* `direction`: 'previous' | 'next'
* `count`: How wide you will jump. Defaults to 1.
* `wrap`: Set to True, to jump to the top if you're on the last error and
          vice versa. Defaults to False

"""


class SublimeLinterGotoError(sublime_plugin.WindowCommand):
    def run(self, direction='next', count=1, wrap=False):
        goto(self.window.active_view(), direction, count, wrap)


def goto(view, direction, count, wrap):
    bid = view.buffer_id()

    try:
        errors = persist.raw_errors[bid]
    except KeyError:
        flash(view, 'No errors/problems')
        return

    if len(errors) == 0:
        flash(view, 'No errors/problems')
        return

    current_line, current_col = get_current_pos(view)
    if (current_line, current_col) == (-1, -1):
        return

    # Filter out duplicates on the same position. Also filter out errors
    # under the cursor, bc we don't want to jump to them.
    errors = {(error['line'], error['start'])
              for error in errors
              if not(error['line'] == current_line and
                     error['start'] <= current_col <= error['end'])}
    errors = sorted(errors)

    # Edge case: Since we filtered, it is possible we get here with nothing
    # left. That is the case if we sit on the last remaining error, where we
    # don't have anything to jump to and even `wrap` becomes a no-op.
    if len(errors) == 0:
        flash(view, 'No more problems.')
        return

    def before_current_pos(error):
        line, start = error
        return (
            line < current_line or
            # `start < current_col` is only safe bc we already
            # filtered errors directly under cursor (!)
            line == current_line and start < current_col)

    next_positions = dropwhile(before_current_pos, errors)
    previous_positions = takewhile(before_current_pos, errors)

    reverse = direction == 'previous'
    jump_positions = list(previous_positions if reverse else next_positions)
    if reverse:
        jump_positions = list(reversed(jump_positions))

    if not jump_positions:
        if wrap:
            error = errors[-1] if reverse else errors[0]
        else:
            flash(
                view,
                'No more problems {}.'.format('above' if reverse else 'below')
            )
            return
    elif len(jump_positions) <= count:
        # If we cannot jump wide enough, do not wrap, but jump as wide as
        # possible to reduce disorientation.
        error = jump_positions[-1]
    else:
        error = jump_positions[count - 1]

    line, start = error
    move_to(view, line, start)


def move_to(view, line, col):
    loc = view.text_point(line, col)
    region = sublime.Region(loc, loc)
    view.sel().clear()
    view.sel().add(region)
    center_region_in_view(view, region)


def center_region_in_view(view, region):
    """Center the given region in view.

    There is a bug in ST3 that prevents a selection change
    from being drawn when a quick panel is open unless the
    viewport moves. So we get the current viewport position,
    move it down 1.0, center the region, see if the viewport
    moved, and if not, move it up 1.0 and center again.
    """
    x1, y1 = view.viewport_position()
    view.set_viewport_position((x1, y1 + 1.0))
    view.show_at_center(region)
    x2, y2 = view.viewport_position()

    if y2 == y1:
        view.set_viewport_position((x1, y1 - 1.0))
        view.show_at_center(region)


def get_current_pos(view):
    try:
        return view.rowcol(view.sel()[0].begin())
    except (AttributeError, IndexError):
        return -1, -1


def flash(view, msg):
    window = view.window() or sublime.active_window()
    window.status_message(msg)
