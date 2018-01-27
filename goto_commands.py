import sublime
import sublime_plugin

from itertools import dropwhile, takewhile
from .lint import persist


"""
Implement typical Goto Next Previous Error Commands.
"""


class SublimeLinterGotoError(sublime_plugin.WindowCommand):
    def run(self, direction='next', count=1, wrap=False):
        goto(self.window.active_view(), direction, count, wrap)


def goto(view, direction, count, wrap):
    bid = view.buffer_id()

    try:
        errors = persist.errors[bid]
    except KeyError:
        flash(view, 'No problems')
        return

    if len(errors) == 0:
        flash(view, 'No problems')
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
        flash(view, 'No more problems')
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
                'No more problems {}'.format('above' if reverse else 'below')
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


class _sublime_linter_goto_line(sublime_plugin.TextCommand):

    def run(self, edit, line, col):
        pt = self.view.text_point(line, col)
        self.view.sel().clear()
        self.view.sel().add(pt)
        self.view.show(pt)


def move_to(view, line, col):
    window = view.window()
    if view == window.active_view():
        # If the region we're moving to is already visible, then we don't want
        # the view to suddenly scroll. If the region is not visible, then we
        # want the surrounding area of the region to be visible.
        # We need to a use a custom goto line command for several reasons:
        # * ST's goto line command doesn't accept a col argument.
        # * SL requires that on_selection_modified events MUST be triggered for
        #   each move.
        # See https://github.com/SublimeLinter/SublimeLinter/pull/867.
        view.run_command('_sublime_linter_goto_line', {'line': line, 'col': col})
    else:
        filename = view.file_name() or "<untitled {}>".format(view.buffer_id())
        target = "{}:{}:{}".format(filename, line + 1, col + 1)
        window.open_file(target, sublime.ENCODED_POSITION)


def get_current_pos(view):
    try:
        return view.rowcol(view.sel()[0].begin())
    except (AttributeError, IndexError):
        return -1, -1


def flash(view, msg):
    window = view.window() or sublime.active_window()
    window.status_message(msg)
