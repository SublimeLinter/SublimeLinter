import sublime
import sublime_plugin

from itertools import dropwhile, takewhile


"""
Implement typical Goto Next Previous Error Commands.
"""


class SublimeLinterGotoError(sublime_plugin.WindowCommand):
    def run(self, direction='next', count=1, wrap=False):
        goto(self.window.active_view(), direction, count, wrap)


STORAGE_KEY = 'SL.{vid}.region_keys'


def get_region_keys(view):
    setting_key = STORAGE_KEY.format(vid=view.id())
    return set(view.settings().get(setting_key) or [])


def get_highlighted_regions(view):
    return [
        region
        for key in get_region_keys(view)
        if '.Highlights.' in key
        for region in view.get_regions(key)
    ]


def goto(view, direction, count, wrap):
    cursor = view.sel()[0].begin()

    regions = get_highlighted_regions(view)
    if not regions:
        flash(view, 'No problems')
        return

    # Filter regions under the cursor, bc we don't want to jump to them.
    # Also filter duplicate start positions.
    all_jump_positions = sorted({
        region.a
        for region in regions
        if not region.contains(cursor)})

    # Edge case: Since we filtered, it is possible we get here with nothing
    # left. That is the case if we sit on the last remaining error, where we
    # don't have anything to jump to and even `wrap` becomes a no-op.
    if len(all_jump_positions) == 0:
        flash(view, 'No more problems')
        return

    def before_current_pos(pos):
        return pos < cursor

    next_positions = dropwhile(before_current_pos, all_jump_positions)
    previous_positions = takewhile(before_current_pos, all_jump_positions)

    reverse = direction == 'previous'
    jump_positions = list(previous_positions if reverse else next_positions)
    if reverse:
        jump_positions = list(reversed(jump_positions))

    if not jump_positions:
        if wrap:
            point = all_jump_positions[-1] if reverse else all_jump_positions[0]
            flash(
                view,
                'Jumped to {} problem'.format('last' if reverse else 'first'))
        else:
            flash(
                view,
                'No more problems {}'.format('above' if reverse else 'below'))
            return
    elif len(jump_positions) <= count:
        # If we cannot jump wide enough, do not wrap, but jump as wide as
        # possible to reduce disorientation.
        point = jump_positions[-1]
    else:
        point = jump_positions[count - 1]

    move_to(view, point)


class _sublime_linter_goto_line(sublime_plugin.TextCommand):

    def run(self, edit, point):
        self.view.sel().clear()
        self.view.sel().add(point)
        self.view.show(point)


def move_to(view, point):
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
        view.run_command('_sublime_linter_goto_line', {'point': point})
    else:
        filename = view.file_name() or "<untitled {}>".format(view.buffer_id())
        line, col = view.rowcol(point)
        target = "{}:{}:{}".format(filename, line + 1, col + 1)
        window.open_file(target, sublime.ENCODED_POSITION)


def flash(view, msg):
    window = view.window() or sublime.active_window()
    window.status_message(msg)
