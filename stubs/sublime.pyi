import enum
from typing import (
    overload,
    Any,
    Optional,
    Dict,
    Iterator,
    Sequence,
    Tuple,
    Union,
    List,
    Sized,
    NewType,
    Callable,
    Collection,
    TypeVar,
    Mapping,
)
from typing_extensions import TypeAlias


CompletionKind: TypeAlias = Tuple[int, str, str]

class _LogWriter:
    def flush(self) -> None: ...
    def write(self, s: str) -> None: ...

class HoverZone(enum.IntEnum):
    """
    A zone in an open text sheet where the mouse may hover.

    See `EventListener.on_hover` and `ViewEventListener.on_hover`.

    For backwards compatibility these values are also available outside this
    enumeration with a ``HOVER_`` prefix.

    .. since:: 4132 3.8
    """

    TEXT = 1
    """ The mouse is hovered over the text. """
    GUTTER = 2
    """ The mouse is hovered over the gutter. """
    MARGIN = 3
    """ The mouse is hovered in the white space to the right of a line. """

HOVER_TEXT = HoverZone.TEXT
HOVER_GUTTER = HoverZone.GUTTER
HOVER_MARGIN = HoverZone.MARGIN

class NewFileFlags(enum.IntFlag):
    """
    Flags for creating/opening files in various ways.

    See `Window.new_html_sheet`, `Window.new_file` and `Window.open_file`.

    For backwards compatibility these values are also available outside this
    enumeration (without a prefix).

    .. since:: 4132 3.8
    """

    NONE = 0
    """ """
    ENCODED_POSITION = 1
    """
    Indicates that the file name should be searched for a ``:row`` or
    ``:row:col`` suffix.
    """
    TRANSIENT = 4
    """
    Open the file as a preview only: it won't have a tab assigned it until
    modified.
    """
    FORCE_GROUP = 8
    """
    Don't select the file if it is open in a different group. Instead make a new
    clone of that file in the desired group.
    """
    SEMI_TRANSIENT = 16
    """
    If a sheet is newly created, it will be set to semi-transient.
    Semi-transient sheets generally replace other semi-transient sheets. This
    is used for the side-bar preview. Only valid with `ADD_TO_SELECTION` or
    `REPLACE_MRU`.

    .. since:: 4096
    """
    ADD_TO_SELECTION = 32
    """
    Add the file to the currently selected sheets in the group.

    .. since:: 4050
    """
    REPLACE_MRU = 64
    """
    Causes the sheet to replace the most-recently used sheet in the current sheet selection.

    .. since:: 4096
    """
    CLEAR_TO_RIGHT = 128
    """
    All currently selected sheets to the right of the most-recently used sheet
    will be unselected before opening the file. Only valid in combination with
    `ADD_TO_SELECTION`.

    .. since:: 4100
    """
    FORCE_CLONE = 256
    """
    Don't select the file if it is open. Instead make a new clone of that file in the desired
    group.

    .. :since:: 4135
    """

ENCODED_POSITION = NewFileFlags.ENCODED_POSITION
TRANSIENT = NewFileFlags.TRANSIENT
FORCE_GROUP = NewFileFlags.FORCE_GROUP
SEMI_TRANSIENT = NewFileFlags.SEMI_TRANSIENT
ADD_TO_SELECTION = NewFileFlags.ADD_TO_SELECTION
REPLACE_MRU = NewFileFlags.REPLACE_MRU
CLEAR_TO_RIGHT = NewFileFlags.CLEAR_TO_RIGHT
FORCE_CLONE = NewFileFlags.FORCE_CLONE

class FindFlags(enum.IntFlag):
    """
    Flags for use when searching through a `View`.

    See `View.find` and `View.find_all`.

    For backwards compatibility these values are also available outside this
    enumeration (without a prefix).

    .. since:: 4132 3.8
    """

    NONE = 0
    """ """
    LITERAL = 1
    """ Whether the find pattern should be matched literally or as a regex. """
    IGNORECASE = 2
    """ Whether case should be considered when matching the find pattern. """
    WHOLEWORD = 4
    """
    Whether to only match whole words.

    .. since:: 4149
    """
    REVERSE = 8
    """
    Whether to search backwards.

    .. since:: 4149
    """
    WRAP = 16
    """
    Whether to wrap around once the end is reached.

    .. since:: 4149
    """

LITERAL = FindFlags.LITERAL
IGNORECASE = FindFlags.IGNORECASE
WHOLEWORD = FindFlags.WHOLEWORD
REVERSE = FindFlags.REVERSE
WRAP = FindFlags.WRAP

class QuickPanelFlags(enum.IntFlag):
    """
    Flags for use with a quick panel.

    See `Window.show_quick_panel`.

    For backwards compatibility these values are also available outside this
    enumeration (without a prefix).

    .. since:: 4132 3.8
    """

    NONE = 0
    """ """
    MONOSPACE_FONT = 1
    """ Use a monospace font. """
    KEEP_OPEN_ON_FOCUS_LOST = 2
    """ Keep the quick panel open if the window loses input focus. """
    WANT_EVENT = 4
    """
    Pass a second parameter to the ``on_done`` callback, a `Event`.

    .. since:: 4096
    """

MONOSPACE_FONT = QuickPanelFlags.MONOSPACE_FONT
KEEP_OPEN_ON_FOCUS_LOST = QuickPanelFlags.KEEP_OPEN_ON_FOCUS_LOST
WANT_EVENT = QuickPanelFlags.WANT_EVENT

class PopupFlags(enum.IntFlag):
    """
    Flags for use with popups.

    See `View.show_popup`.

    For backwards compatibility these values are also available outside this
    enumeration (without a prefix).

    .. since:: 4132 3.8
    """

    NONE = 0
    """ """
    COOPERATE_WITH_AUTO_COMPLETE = 2
    """ Causes the popup to display next to the auto complete menu. """
    HIDE_ON_MOUSE_MOVE = 4
    """
    Causes the popup to hide when the mouse is moved, clicked or scrolled.
    """
    HIDE_ON_MOUSE_MOVE_AWAY = 8
    """
    Causes the popup to hide when the mouse is moved (unless towards the popup),
    or when clicked or scrolled.
    """
    KEEP_ON_SELECTION_MODIFIED = 16
    """
    Prevent the popup from hiding when the selection is modified.

    .. since:: 4057
    """
    HIDE_ON_CHARACTER_EVENT = 32
    """
    Hide the popup when a character is typed.

    .. since:: 4057
    """

# Deprecated
HTML = 1
COOPERATE_WITH_AUTO_COMPLETE = PopupFlags.COOPERATE_WITH_AUTO_COMPLETE
HIDE_ON_MOUSE_MOVE = PopupFlags.HIDE_ON_MOUSE_MOVE
HIDE_ON_MOUSE_MOVE_AWAY = PopupFlags.HIDE_ON_MOUSE_MOVE_AWAY
KEEP_ON_SELECTION_MODIFIED = PopupFlags.KEEP_ON_SELECTION_MODIFIED
HIDE_ON_CHARACTER_EVENT = PopupFlags.HIDE_ON_CHARACTER_EVENT

class RegionFlags(enum.IntFlag):
    """
    Flags for use with added regions. See `View.add_regions`.

    For backwards compatibility these values are also available outside this
    enumeration (without a prefix).

    .. since:: 4132 3.8
    """

    NONE = 0
    """ """
    DRAW_EMPTY = 1
    """ Draw empty regions with a vertical bar. By default, they aren't drawn at all. """
    HIDE_ON_MINIMAP = 2
    """ Don't show the regions on the minimap. """
    DRAW_EMPTY_AS_OVERWRITE = 4
    """ Draw empty regions with a horizontal bar instead of a vertical one. """
    PERSISTENT = 16
    """ Save the regions in the session. """
    DRAW_NO_FILL = 32
    """ Disable filling the regions, leaving only the outline. """
    HIDDEN = 128
    """ Don't draw the regions.  """
    DRAW_NO_OUTLINE = 256
    """ Disable drawing the outline of the regions. """
    DRAW_SOLID_UNDERLINE = 512
    """ Draw a solid underline below the regions. """
    DRAW_STIPPLED_UNDERLINE = 1024
    """ Draw a stippled underline below the regions. """
    DRAW_SQUIGGLY_UNDERLINE = 2048
    """ Draw a squiggly underline below the regions. """
    NO_UNDO = 8192
    """ """

DRAW_EMPTY = RegionFlags.DRAW_EMPTY
HIDE_ON_MINIMAP = RegionFlags.HIDE_ON_MINIMAP
DRAW_EMPTY_AS_OVERWRITE = RegionFlags.DRAW_EMPTY_AS_OVERWRITE
PERSISTENT = RegionFlags.PERSISTENT
DRAW_NO_FILL = RegionFlags.DRAW_NO_FILL
# Deprecated, use DRAW_NO_FILL instead
DRAW_OUTLINED = DRAW_NO_FILL
DRAW_NO_OUTLINE = RegionFlags.DRAW_NO_OUTLINE
DRAW_SOLID_UNDERLINE = RegionFlags.DRAW_SOLID_UNDERLINE
DRAW_STIPPLED_UNDERLINE = RegionFlags.DRAW_STIPPLED_UNDERLINE
DRAW_SQUIGGLY_UNDERLINE = RegionFlags.DRAW_SQUIGGLY_UNDERLINE
NO_UNDO = RegionFlags.NO_UNDO
HIDDEN = RegionFlags.HIDDEN

class QueryOperator(enum.IntEnum):
    """
    Enumeration of operators able to be used when querying contexts.

    See `EventListener.on_query_context` and
    `ViewEventListener.on_query_context`.

    For backwards compatibility these values are also available outside this
    enumeration with a ``OP_`` prefix.

    .. since:: 4132 3.8
    """

    EQUAL = 0
    """ """
    NOT_EQUAL = 1
    """ """
    REGEX_MATCH = 2
    """ """
    NOT_REGEX_MATCH = 3
    """ """
    REGEX_CONTAINS = 4
    """ """
    NOT_REGEX_CONTAINS = 5
    """ """

OP_EQUAL = QueryOperator.EQUAL
OP_NOT_EQUAL = QueryOperator.NOT_EQUAL
OP_REGEX_MATCH = QueryOperator.REGEX_MATCH
OP_NOT_REGEX_MATCH = QueryOperator.NOT_REGEX_MATCH
OP_REGEX_CONTAINS = QueryOperator.REGEX_CONTAINS
OP_NOT_REGEX_CONTAINS = QueryOperator.NOT_REGEX_CONTAINS

class PointClassification(enum.IntFlag):
    """
    Flags that identify characteristics about a `Point` in a text sheet. See
    `View.classify`.

    For backwards compatibility these values are also available outside this
    enumeration with a ``CLASS_`` prefix.

    .. since:: 4132 3.8
    """

    NONE = 0
    """ """
    WORD_START = 1
    """ The point is the start of a word. """
    WORD_END = 2
    """ The point is the end of a word. """
    PUNCTUATION_START = 4
    """ The point is the start of a sequence of punctuation characters. """
    PUNCTUATION_END = 8
    """ The point is the end of a sequence of punctuation characters. """
    SUB_WORD_START = 16
    """ The point is the start of a sub-word. """
    SUB_WORD_END = 32
    """ The point is the end of a sub-word. """
    LINE_START = 64
    """ The point is the start of a line. """
    LINE_END = 128
    """ The point is the end of a line. """
    EMPTY_LINE = 256
    """ The point is an empty line. """

CLASS_WORD_START = PointClassification.WORD_START
CLASS_WORD_END = PointClassification.WORD_END
CLASS_PUNCTUATION_START = PointClassification.PUNCTUATION_START
CLASS_PUNCTUATION_END = PointClassification.PUNCTUATION_END
CLASS_SUB_WORD_START = PointClassification.SUB_WORD_START
CLASS_SUB_WORD_END = PointClassification.SUB_WORD_END
CLASS_LINE_START = PointClassification.LINE_START
CLASS_LINE_END = PointClassification.LINE_END
CLASS_EMPTY_LINE = PointClassification.EMPTY_LINE

class AutoCompleteFlags(enum.IntFlag):
    """
    Flags controlling how asynchronous completions function. See
    `CompletionList`.

    For backwards compatibility these values are also available outside this
    enumeration (without a prefix).

    .. since:: 4132 3.8
    """

    NONE = 0
    """ """
    INHIBIT_WORD_COMPLETIONS = 8
    """
    Prevent Sublime Text from showing completions based on the contents of the
    view.
    """
    INHIBIT_EXPLICIT_COMPLETIONS = 16
    """
    Prevent Sublime Text from showing completions based on
    :path:`.sublime-completions` files.
    """
    DYNAMIC_COMPLETIONS = 32
    """
    If completions should be re-queried as the user types.

    .. since:: 4057
    """
    INHIBIT_REORDER = 128
    """
    Prevent Sublime Text from changing the completion order.

    .. since:: 4074
    """

INHIBIT_WORD_COMPLETIONS = AutoCompleteFlags.INHIBIT_WORD_COMPLETIONS
INHIBIT_EXPLICIT_COMPLETIONS = AutoCompleteFlags.INHIBIT_EXPLICIT_COMPLETIONS
DYNAMIC_COMPLETIONS = AutoCompleteFlags.DYNAMIC_COMPLETIONS
INHIBIT_REORDER = AutoCompleteFlags.INHIBIT_REORDER

class CompletionItemFlags(enum.IntFlag):
    """:meta private:"""

    NONE = 0
    KEEP_PREFIX = 1

COMPLETION_FLAG_KEEP_PREFIX = CompletionItemFlags.KEEP_PREFIX

class DialogResult(enum.IntEnum):
    """
    The result from a *yes / no / cancel* dialog. See `yes_no_cancel_dialog`.

    For backwards compatibility these values are also available outside this
    enumeration with a ``DIALOG_`` prefix.

    .. since:: 4132 3.8
    """

    CANCEL = 0
    """ """
    YES = 1
    """ """
    NO = 2
    """ """

DIALOG_CANCEL = DialogResult.CANCEL
DIALOG_YES = DialogResult.YES
DIALOG_NO = DialogResult.NO

class UIElement(enum.IntEnum):
    """:meta private:"""

    SIDE_BAR = 1
    MINIMAP = 2
    TABS = 4
    STATUS_BAR = 8
    MENU = 16
    OPEN_FILES = 32

class PhantomLayout(enum.IntEnum):
    """
    How a `Phantom` should be positioned. See `PhantomSet`.

    For backwards compatibility these values are also available outside this
    enumeration with a ``LAYOUT_`` prefix.

    .. since:: 4132 3.8
    """

    INLINE = 0
    """
    The phantom is positioned inline with the text at the beginning of its
    `Region`.
    """
    BELOW = 1
    """
    The phantom is positioned below the line, left-aligned with the beginning of
    its `Region`.
    """
    BLOCK = 2
    """
    The phantom is positioned below the line, left-aligned with the beginning of
    the line.
    """

LAYOUT_INLINE = PhantomLayout.INLINE
LAYOUT_BELOW = PhantomLayout.BELOW
LAYOUT_BLOCK = PhantomLayout.BLOCK

class KindId(enum.IntEnum):
    """
    For backwards compatibility these values are also available outside this
    enumeration with a ``KIND_ID_`` prefix.

    .. since:: 4132 3.8
    """

    AMBIGUOUS = 0
    """ """
    KEYWORD = 1
    """ """
    TYPE = 2
    """ """
    FUNCTION = 3
    """ """
    NAMESPACE = 4
    """ """
    NAVIGATION = 5
    """ """
    MARKUP = 6
    """ """
    VARIABLE = 7
    """ """
    SNIPPET = 8
    """ """

    # These should only be used for QuickPanelItem
    # and ListInputItem, not for CompletionItem
    COLOR_REDISH = 9
    """ """
    COLOR_ORANGISH = 10
    """ """
    COLOR_YELLOWISH = 11
    """ """
    COLOR_GREENISH = 12
    """ """
    COLOR_CYANISH = 13
    """ """
    COLOR_BLUISH = 14
    """ """
    COLOR_PURPLISH = 15
    """ """
    COLOR_PINKISH = 16
    """ """
    COLOR_DARK = 17
    """ """
    COLOR_LIGHT = 18
    """ """

KIND_ID_AMBIGUOUS = KindId.AMBIGUOUS
KIND_ID_KEYWORD = KindId.KEYWORD
KIND_ID_TYPE = KindId.TYPE
KIND_ID_FUNCTION = KindId.FUNCTION
KIND_ID_NAMESPACE = KindId.NAMESPACE
KIND_ID_NAVIGATION = KindId.NAVIGATION
KIND_ID_MARKUP = KindId.MARKUP
KIND_ID_VARIABLE = KindId.VARIABLE
KIND_ID_SNIPPET = KindId.SNIPPET
KIND_ID_COLOR_REDISH = KindId.COLOR_REDISH
KIND_ID_COLOR_ORANGISH = KindId.COLOR_ORANGISH
KIND_ID_COLOR_YELLOWISH = KindId.COLOR_YELLOWISH
KIND_ID_COLOR_GREENISH = KindId.COLOR_GREENISH
KIND_ID_COLOR_CYANISH = KindId.COLOR_CYANISH
KIND_ID_COLOR_BLUISH = KindId.COLOR_BLUISH
KIND_ID_COLOR_PURPLISH = KindId.COLOR_PURPLISH
KIND_ID_COLOR_PINKISH = KindId.COLOR_PINKISH
KIND_ID_COLOR_DARK = KindId.COLOR_DARK
KIND_ID_COLOR_LIGHT = KindId.COLOR_LIGHT

KIND_AMBIGUOUS = (KindId.AMBIGUOUS, "", "")
"""
.. since:: 4052
"""
KIND_KEYWORD = (KindId.KEYWORD, "", "")
"""
.. since:: 4052
"""
KIND_TYPE = (KindId.TYPE, "", "")
"""
.. since:: 4052
"""
KIND_FUNCTION = (KindId.FUNCTION, "", "")
"""
.. since:: 4052
"""
KIND_NAMESPACE = (KindId.NAMESPACE, "", "")
"""
.. since:: 4052
"""
KIND_NAVIGATION = (KindId.NAVIGATION, "", "")
"""
.. since:: 4052
"""
KIND_MARKUP = (KindId.MARKUP, "", "")
"""
.. since:: 4052
"""
KIND_VARIABLE = (KindId.VARIABLE, "", "")
"""
.. since:: 4052
"""
KIND_SNIPPET = (KindId.SNIPPET, "s", "Snippet")
"""
.. since:: 4052
"""

class SymbolSource(enum.IntEnum):
    """
    See `Window.symbol_locations`.

    For backwards compatibility these values are also available outside this
    enumeration with a ``SYMBOL_SOURCE_`` prefix.

    .. since:: 4132 3.8
    """

    ANY = 0
    """
    Use any source - both the index and open files.

    .. since:: 4085
    """
    INDEX = 1
    """
    Use the index created when scanning through files in a project folder.

    .. since:: 4085
    """
    OPEN_FILES = 2
    """
    Use the open files, unsaved or otherwise.

    .. since:: 4085
    """

SYMBOL_SOURCE_ANY = SymbolSource.ANY
SYMBOL_SOURCE_INDEX = SymbolSource.INDEX
SYMBOL_SOURCE_OPEN_FILES = SymbolSource.OPEN_FILES

class SymbolType(enum.IntEnum):
    """
    See `Window.symbol_locations` and `View.indexed_symbol_regions`.

    For backwards compatibility these values are also available outside this
    enumeration with a ``SYMBOL_TYPE_`` prefix.

    .. since:: 4132 3.8
    """

    ANY = 0
    """ Any symbol type - both definitions and references.

    .. since:: 4085
    """
    DEFINITION = 1
    """
    Only definitions.

    .. since:: 4085
    """
    REFERENCE = 2
    """
    Only references.

    .. since:: 4085
    """

SYMBOL_TYPE_ANY = SymbolType.ANY
SYMBOL_TYPE_DEFINITION = SymbolType.DEFINITION
SYMBOL_TYPE_REFERENCE = SymbolType.REFERENCE

class CompletionFormat(enum.IntEnum):
    """
    The format completion text can be in. See `CompletionItem`.

    For backwards compatibility these values are also available outside this
    enumeration with a ``COMPLETION_FORMAT_`` prefix.

    .. since:: 4132 3.8
    """

    TEXT = 0
    """
    Plain text, upon completing the text is inserted verbatim.

    .. since:: 4050
    """
    SNIPPET = 1
    """
    A snippet, with ``$`` variables. See also
    `CompletionItem.snippet_completion`.

    .. since:: 4050
    """
    COMMAND = 2
    """
    A command string, in the format returned by `format_command()`. See also
    `CompletionItem.command_completion()`.

    .. since:: 4050
    """

COMPLETION_FORMAT_TEXT = CompletionFormat.TEXT
COMPLETION_FORMAT_SNIPPET = CompletionFormat.SNIPPET
COMPLETION_FORMAT_COMMAND = CompletionFormat.COMMAND

def version() -> str: ...
def platform() -> str: ...
def arch() -> str: ...
def channel() -> str: ...
def executable_path() -> str: ...
def executable_hash() -> str: ...
def packages_path() -> str: ...
def installed_packages_path() -> str: ...
def cache_path() -> str: ...
def status_message(msg: str) -> None: ...
def error_message(msg: str) -> None: ...
def message_dialog(msg: str) -> None: ...
def ok_cancel_dialog(msg: str, ok_title: str = ...) -> bool: ...
def yes_no_cancel_dialog(
    msg: str, yes_title: str = ..., no_title: str = ...
) -> int: ...
def run_command(cmd: str, args: Optional[Any] = ...) -> None: ...
def get_clipboard(size_limit: int = ...) -> str: ...
def set_clipboard(text: str) -> None: ...
def log_commands(flag: bool) -> None: ...
def log_input(flag: bool) -> None: ...
def log_result_regex(flag: bool) -> None: ...
def log_indexing(flag: bool) -> None: ...
def log_build_systems(flag: bool) -> None: ...
def score_selector(scope_name: str, selector: str) -> int: ...
def load_resource(name: str) -> str: ...
def load_binary_resource(name: str) -> bytes: ...
def find_resources(pattern: str) -> Sequence[str]: ...
def encode_value(val: Any, pretty: bool = ...) -> str: ...
def decode_value(data: str) -> Any: ...
def expand_variables(val: Any, variables: Mapping[str, str]) -> Any: ...
def load_settings(base_name: str) -> Settings: ...
def save_settings(base_name: str) -> None: ...
def set_timeout(f: Callable[[], Any], timeout_ms: int = ...) -> None: ...
def set_timeout_async(f: Callable[[], Any], timeout_ms: int = ...) -> None: ...
def active_window() -> Window: ...
def windows() -> Sequence[Window]: ...
def get_macro() -> Sequence[dict]: ...

WindowId = NewType("WindowId", int)
BufferId = NewType("BufferId", int)
ViewId = NewType("ViewId", int)
_T = TypeVar("_T")

Point = int
Pixel = float
Vector = Tuple[Pixel, Pixel]
DIP = float

class Window:
    window_id = ...  # type: WindowId
    settings_object = ...  # type: Any
    template_settings_object = ...  # type: Any
    def __init__(self, id: WindowId) -> None: ...
    def __eq__(self, other: Any) -> bool: ...
    def __bool__(self) -> bool: ...
    def id(self) -> WindowId: ...
    def is_valid(self) -> bool: ...
    def hwnd(self): ...
    def active_sheet(self) -> Sheet: ...
    def active_view(self) -> Optional[View]: ...
    def run_command(self, cmd: str, args: Optional[Any] = ...) -> None: ...
    def new_file(self, flags: int = ..., syntax: str = ...) -> View: ...
    def open_file(self, fname: str, flags: int = ..., group: int = ...) -> View: ...
    def find_open_file(self, fname: str) -> Optional[View]: ...
    def num_groups(self) -> int: ...
    def active_group(self) -> int: ...
    def focus_group(self, idx: int) -> None: ...
    def focus_sheet(self, sheet: Sheet) -> None: ...
    def focus_view(self, view: View) -> None: ...
    def get_sheet_index(self, sheet: Sheet) -> Tuple[int, int]: ...
    def get_view_index(self, view: View) -> Tuple[int, int]: ...
    def set_sheet_index(self, sheet: Sheet, group: int, idx: int) -> None: ...
    def set_view_index(self, view: View, group: int, idx: int) -> None: ...
    def sheets(self) -> List[Sheet]: ...
    def views(self) -> List[View]: ...
    def selected_sheets(self) -> List[Sheet]: ...
    def selected_sheets_in_group(self, group: int) -> List[Sheet]: ...
    def active_sheet_in_group(self, group: int) -> Optional[Sheet]: ...
    def active_view_in_group(self, group: int) -> Optional[View]: ...
    def sheets_in_group(self, group: int) -> List[Sheet]: ...
    def views_in_group(self, group: int) -> List[View]: ...
    def transient_sheet_in_group(self, group: int) -> Optional[View]: ...
    def transient_view_in_group(self, group: int) -> Optional[View]: ...
    def layout(self) -> Dict: ...
    def get_layout(self) -> Dict: ...
    def set_layout(self, layout: Dict) -> None: ...
    def create_output_panel(self, name: str, unlisted: bool = ...) -> View: ...
    def find_output_panel(self, name: str) -> Optional[View]: ...
    def destroy_output_panel(self, name: str) -> None: ...
    def active_panel(self) -> Optional[str]: ...
    def panels(self) -> List[str]: ...
    def get_output_panel(self, name: str) -> View: ...
    def show_input_panel(
        self,
        caption: str,
        initial_text: str,
        on_done: Optional[Callable[[str], None]],
        on_change: Optional[Callable[[str], None]],
        on_cancel: Optional[Callable[[], None]],
    ) -> View: ...
    def show_quick_panel(
        self,
        items: Union[Collection[str], Collection[Sequence[str]], Collection[Union[str, QuickPanelItem]]],
        on_select: Optional[Callable[[int], None]],
        flags: int = ...,
        selected_index: int = ...,
        on_highlight: Optional[Callable[[int], None]] = ...,
    ) -> None: ...
    def is_sidebar_visible(self) -> bool: ...
    def set_sidebar_visible(self, flag: bool) -> None: ...
    def is_minimap_visible(self) -> bool: ...
    def set_minimap_visible(self, flag: bool) -> None: ...
    def is_status_bar_visible(self) -> bool: ...
    def set_status_bar_visible(self, flag: bool) -> None: ...
    def get_tabs_visible(self) -> bool: ...
    def set_tabs_visible(self, flag: bool) -> None: ...
    def is_menu_visible(self) -> bool: ...
    def set_menu_visible(self, flag: bool) -> None: ...
    def folders(self) -> List[str]: ...
    def project_file_name(self) -> Optional[str]: ...
    def project_data(self) -> Optional[dict]: ...
    def set_project_data(self, v: dict) -> None: ...
    def settings(self) -> Settings: ...
    def template_settings(self) -> Settings: ...
    def lookup_symbol_in_index(self, sym: str) -> List[str]: ...
    def lookup_symbol_in_open_files(self, sym: str) -> List[str]: ...
    def extract_variables(self) -> dict: ...
    def status_message(self, msg: str) -> None: ...

class Edit:
    edit_token = ...  # type: Any
    def __init__(self, token: Any) -> None: ...

class Region:
    a: Point
    b: Point
    xpos: DIP
    def __init__(self, a: Point, b: Optional[Point] = None, xpos: DIP = -1) -> None: ...
    def __iter__(self) -> Iterator[Point]: ...
    def __str__(self) -> str: ...
    def __repr__(self) -> str: ...
    def __len__(self) -> int: ...
    def __eq__(self, rhs: object) -> bool: ...
    def __lt__(self, rhs: Region) -> bool: ...
    def __contains__(self, v: Union[Point, Region]) -> bool: ...
    def to_tuple(self) -> tuple[Point, Point]: ...
    def empty(self) -> bool: ...
    def begin(self) -> Point: ...
    def end(self) -> Point: ...
    def size(self) -> int: ...
    def contains(self, x: Union[Point, Region]) -> bool: ...
    def cover(self, region: Region) -> Region: ...
    def intersection(self, region: Region) -> Region: ...
    def intersects(self, region: Region) -> bool: ...

class Selection(Sized):
    view_id = ...  # type: ViewId
    def __init__(self, id: int) -> None: ...
    def __len__(self) -> int: ...
    def __getitem__(self, index: int) -> Region: ...
    def __delitem__(self, index: int) -> None: ...
    def __iter__(self) -> Iterator[Region]: ...
    def __eq__(self, rhs: Any) -> bool: ...
    def __lt__(self, rhs: Selection) -> bool: ...
    def __bool__(self) -> bool: ...
    def is_valid(self) -> bool: ...
    def clear(self) -> None: ...
    def add(self, x: Union[Region, Point]) -> None: ...
    def add_all(self, regions: Sequence[Union[Region, Point]]) -> None: ...
    def subtract(self, region: Region) -> None: ...
    def contains(self, region: Region) -> bool: ...

class Sheet:
    sheet_id = ...  # type: Any
    def __init__(self, id: int) -> None: ...
    def __eq__(self, other: Any) -> bool: ...
    def id(self) -> int: ...
    def window(self) -> Optional[Window]: ...
    def view(self) -> Optional[View]: ...
    def is_semi_transient(self) -> bool: ...

class Buffer:
    def __init__(self, id: BufferId) -> None: ...
    def id(self) -> int: ...
    def file_name(self) -> str | None: ...
    def views(self) -> list[View]: ...
    def primary_view(self) -> View | None: ...

class View:
    view_id = ...  # type: ViewId
    selection = ...  # type: Any
    settings_object = ...  # type: Any
    def __init__(self, id: ViewId) -> None: ...
    def __len__(self) -> int: ...
    def __eq__(self, other: Any) -> bool: ...
    def __bool__(self) -> bool: ...
    def id(self) -> ViewId: ...
    def buffer_id(self) -> BufferId: ...
    def buffer(self) -> Buffer: ...
    def element(self) -> Optional[str]: ...
    def sheet(self) -> Optional[Sheet]: ...
    def is_valid(self) -> bool: ...
    def is_primary(self) -> bool: ...
    def window(self) -> Optional[Window]: ...
    def clones(self) -> List[View]: ...
    def file_name(self) -> Optional[str]: ...
    def close(self) -> None: ...
    def retarget(self, new_fname: str) -> None: ...
    def name(self) -> str: ...
    def set_name(self, name: str) -> None: ...
    def is_loading(self) -> bool: ...
    def is_dirty(self) -> bool: ...
    def is_read_only(self) -> bool: ...
    def set_read_only(self, read_only: bool) -> None: ...
    def is_scratch(self) -> bool: ...
    def set_scratch(self, scratch: bool) -> None: ...
    def encoding(self) -> str: ...
    def set_encoding(self, encoding_name: str) -> None: ...
    def line_endings(self) -> str: ...
    def set_line_endings(self, line_ending_name: str) -> None: ...
    def size(self) -> int: ...
    def begin_edit(self, edit_token, cmd, args: Optional[Any] = ...): ...
    def end_edit(self, edit: Edit) -> None: ...
    def is_in_edit(self) -> bool: ...
    def insert(self, edit: Edit, pt: int, text: str) -> None: ...
    def erase(self, edit: Edit, r: Region) -> None: ...
    def replace(self, edit: Edit, r: Region, text: str) -> None: ...
    def change_count(self) -> int: ...
    def run_command(self, cmd: str, args: Optional[Any] = ...) -> None: ...
    def sel(self) -> Selection: ...
    def substr(self, x: Union[Region, int]) -> str: ...
    def find(self, pattern: str, start_pt: Point, flags: int = ...) -> Region: ...
    def find_all(
        self,
        pattern,
        flags: int = ...,
        fmt: Optional[Any] = ...,
        extractions: Optional[Any] = ...,
    ) -> List[Region]: ...
    def settings(self) -> Settings: ...
    def meta_info(self, key: str, pt: Point): ...
    def extract_tokens_with_scopes(self, region: Region) -> List[Tuple[Region, str]]: ...
    def extract_scope(self, pt: Point) -> Region: ...
    def expand_to_scope(self, pt: Point, selector: str) -> Optional[Region]: ...
    def scope_name(self, pt: Point) -> str: ...
    def style(self) -> Dict[str, Any]: ...
    def style_for_scope(self, scope_name: str) -> Dict[str, Any]: ...
    def match_selector(self, pt: int, selector: str) -> bool: ...
    def score_selector(self, pt: int, selector: str) -> int: ...
    def find_by_selector(self, selector: str) -> List[Region]: ...
    def indented_region(self, pt: int): ...
    def indentation_level(self, pt: int): ...
    def has_non_empty_selection_region(self): ...
    def lines(self, r: Region) -> List[Region]: ...
    def split_by_newlines(self, r: Region) -> List[Region]: ...
    def line(self, x: Union[Region, int]) -> Region: ...
    def full_line(self, x: Union[Region, int]) -> Region: ...
    def word(self, x: Union[Region, int]) -> Region: ...
    def classify(self, pt: int) -> int: ...
    def find_by_class(
        self, pt: int, forward: bool, classes: int, separators: str = ...
    ) -> Region: ...
    def expand_by_class(
        self, x: Union[Region, int], classes: int, separators: str = ...
    ) -> Region: ...
    def rowcol(self, tp: Point) -> Tuple[int, int]: ...
    def text_point(self, row: int, col: int) -> Point: ...
    def text_point_utf16(self, row: int, col: int, clamp_column: bool = False) -> Point: ...
    def visible_region(self) -> Region: ...
    def show(
        self, x: Union[Selection, Region, Point], show_surrounds: bool = ...
    ) -> None: ...
    def show_at_center(self, x: Union[Selection, Region, Point]) -> None: ...
    def viewport_position(self) -> Vector: ...
    def set_viewport_position(self, xy: Vector, animate: bool = ...) -> None: ...
    def viewport_extent(self) -> Vector: ...
    def layout_extent(self) -> Vector: ...
    def text_to_layout(self, tp: Point) -> Vector: ...
    def text_to_window(self, tp: Point) -> Vector: ...
    def layout_to_text(self, xy: Vector) -> Point: ...
    def layout_to_window(self, xy: Vector) -> Vector: ...
    def window_to_layout(self, xy: Vector) -> Vector: ...
    def window_to_text(self, xy: Vector) -> Point: ...
    def line_height(self) -> Pixel: ...
    def em_width(self) -> Pixel: ...
    def is_folded(self, sr) -> bool: ...
    def folded_regions(self): ...
    def fold(self, x: Union[Region, List[Region]]) -> bool: ...
    def unfold(self, x): ...
    def add_regions(
        self,
        key: str,
        regions: List[Region],
        scope: str = ...,
        icon: str = ...,
        flags: int = ...,
        annotations: List[str] = ...,
        annotation_color: str = ...,
    ) -> None: ...
    def get_regions(self, key: str) -> List[Region]: ...
    def erase_regions(self, key: str) -> None: ...
    def add_phantom(
        self,
        key: str,
        region: Region,
        content: str,
        layout,
        on_navigate: Optional[Any] = ...,
    ): ...
    def erase_phantoms(self, key: str) -> None: ...
    def erase_phantom_by_id(self, pid) -> None: ...
    def query_phantom(self, pid): ...
    def query_phantoms(self, pids): ...
    def assign_syntax(self, syntax_file: str) -> None: ...
    def set_syntax_file(self, syntax_file: str) -> None: ...
    def symbols(self) -> List[Tuple[Region, str]]: ...
    def get_symbols(self): ...
    def indexed_symbols(self) -> List[Tuple[Region, str]]: ...
    def indexed_references(self) -> List[Tuple[Region, str]]: ...
    def symbol_regions(self) -> List[SymbolRegion]: ...
    def indexed_symbol_regions(self, type: int = SYMBOL_TYPE_ANY) -> List[SymbolRegion]:
        """
        :param type:
            The type of symbol to return. One of the values:

             - sublime.SYMBOL_TYPE_ANY
             - sublime.SYMBOL_TYPE_DEFINITION
             - sublime.SYMBOL_TYPE_REFERENCE

        :return:
            A list of sublime.SymbolRegion() objects for the indexed symbols
            in this view.
        """
        ...

    def set_status(self, key: str, value: str) -> None: ...
    def get_status(self, key: str) -> str: ...
    def erase_status(self, key: str) -> None: ...
    def extract_completions(self, prefix: str, tp: int = ...): ...
    def find_all_results(self): ...
    def find_all_results_with_text(self): ...
    def command_history(self, delta, modifying_only: bool = ...): ...
    def overwrite_status(self) -> bool: ...
    def set_overwrite_status(self, value: bool) -> None: ...
    def show_popup_menu(
        self, items: List[str], on_select, flags: int = ...
    ) -> None: ...
    def show_popup(
        self,
        content: str,
        flags: int = ...,
        location: int = ...,
        max_width: Union[int, float] = ...,
        max_height: Union[int, float] = ...,
        on_navigate: Optional[Any] = ...,
        on_hide: Optional[Any] = ...,
    ) -> None: ...
    def update_popup(self, content: str) -> None: ...
    def is_popup_visible(self) -> bool: ...
    def hide_popup(self) -> None: ...
    def is_auto_complete_visible(self) -> bool: ...
    def export_to_html(
        self,
        regions: Region | list[Region] | None = None,
        minihtml: bool = False,
        enclosing_tags: bool = False,
        font_size: bool = True,
        font_family: bool = True
    ) -> str: ...
    def set_reference_document(self, reference: str) -> None: ...
    def reset_reference_document(self) -> None: ...
    def clear_undo_stack(self) -> None: ...

class Settings:
    settings_id = ...  # type: Any
    def __init__(self, id) -> None: ...
    @overload
    def get(self, key: str) -> Any: ...
    @overload
    def get(self, key: str, default: _T | None = None) -> _T: ...
    def has(self, key: str) -> bool: ...
    def set(self, key: str, value: Any): ...
    def erase(self, key: str) -> None: ...
    def add_on_change(self, tag: str, callback: Any) -> None: ...
    def clear_on_change(self, tag: str) -> None: ...

class Phantom:
    region = ...  # type: Region
    content = ...  # type: Any
    layout = ...  # type: Any
    on_navigate = ...  # type: Any
    id = ...  # type: Any
    def __init__(
        self,
        region: Region,
        content: str,
        layout: int,
        on_navigate: Optional[Any] = ...,
    ) -> None: ...
    def __eq__(self, rhs): ...

class PhantomSet:
    view = ...  # type: View
    key = ...  # type: Any
    phantoms = ...  # type: Any
    def __init__(self, view: View, key: str = ...) -> None: ...
    def __del__(self): ...
    def update(self, new_phantoms: Sequence[Phantom]): ...

class Syntax:
    path: str
    name: str
    hidden: bool
    scope: str

def list_syntaxes() -> List[Syntax]:
    """list all known syntaxes.

    Returns a list of Syntax."""

def syntax_from_path(path: str) -> Optional[Syntax]:
    """Get the syntax for a specific path.

    Returns a Syntax or None."""

def find_syntax_by_name(name: str) -> list[Syntax]:
    """Find syntaxes with the specified name.

    Name must match exactly. Return a list of Syntax."""

def find_syntax_by_scope(scope: str) -> list[Syntax]:
    """Find syntaxes with the specified scope.

    Scope must match exactly. Return a list of Syntax."""

def find_syntax_for_file(path: str, first_line: str = "") -> Optional[Syntax]:
    """Find the syntax to use for a path.

    Uses the file extension, various application settings and optionally the first line of the file to pick the right syntax for the file.

    Returns a Syntax."""


class QuickPanelItem:
    trigger: str
    details: str | list[str] | tuple[str]
    annotation: str
    kind: CompletionKind

    def __init__(
        self,
        trigger: str,
        details: str | Sequence[str] = ...,
        annotation: str = ...,
        kind: CompletionKind = ...
    ) -> None:
        ...

    def __repr__(self) -> str:
        ...


class SymbolRegion:
    name: str
    region: Region
    syntax: Syntax
    type: int
    kind: CompletionKind

    def __init__(
        self,
        name: str,
        region: Region,
        syntax: Syntax,
        type: int,
        kind: CompletionKind,
    ) -> None:
        ...

    def __repr__(self) -> str:
        ...
