import sublime

from unittesting import DeferrableTestCase
from SublimeLinter.tests.mockito import unstub
from SublimeLinter.tests.parameterized import parameterized as p


from SublimeLinter.lint.quick_fix import (
    apply_edit,
    fix_eslint_error,
    fix_flake8_error,
    fix_mypy_error,
    fix_stylelint_error,
    std_provider,
    DEFAULT_DESCRIPTION,
    DEFAULT_SIMPLE_DESCRIPTION
)


class TestActionReducer(DeferrableTestCase):
    @p.expand([
        (
            "filter error without code",
            [
                dict(linter="flake", code="", msg="foo unused", line=1),
            ],
            []
        ),
        (
            "single error",
            [
                dict(linter="flake", code="201", msg="foo unused", line=1),
            ],
            [
                'flake: Disable [201]   foo unused'
            ]
        ),
        (
            "two distinct errors",
            [
                dict(linter="flake", code="201", msg="foo unused", line=1),
                dict(linter="flake", code="202", msg="zoo unused", line=1),
            ],
            [
                'flake: Disable [201]   foo unused',
                'flake: Disable [202]   zoo unused'
            ]
        ),
        (
            "two similar errors, same line",
            [
                dict(linter="flake", code="201", msg="foo unused", line=1),
                dict(linter="flake", code="201", msg="zoo unused", line=1),
            ],
            [
                'flake: Disable [201]   e.g.: foo unused',
            ]
        ),
        (
            "two similar errors, different line",
            [
                dict(linter="flake", code="201", msg="foo unused", line=1),
                dict(linter="flake", code="201", msg="zoo unused", line=2),
            ],
            [
                'flake: Disable [201]   e.g.: foo unused',
            ]
        ),
    ])
    def test_action_descriptions(self, _, ERRORS, RESULT):
        fixer = lambda: None

        actions = std_provider(DEFAULT_DESCRIPTION, DEFAULT_SIMPLE_DESCRIPTION, fixer, ERRORS)
        self.assertEquals(RESULT, [action.description for action in actions])


class TestIgnoreFixers(DeferrableTestCase):
    @classmethod
    def setUpClass(cls):
        # make sure we have a window to work with
        sublime.run_command("new_window")
        cls.window = sublime.active_window()
        s = sublime.load_settings("Preferences.sublime-settings")
        s.set("close_windows_when_empty", False)

    @classmethod
    def tearDownClass(cls):
        cls.window.run_command('close_window')

    def tearDown(self):
        unstub()

    def create_view(self, window):
        view = window.new_file()
        self.addCleanup(self.close_view, view)
        return view

    def close_view(self, view):
        view.set_scratch(True)
        view.close()

    @p.expand([
        (
            "clean line",
            "view = window.new_file()",
            "view = window.new_file()  # noqa: E203"
        ),
        (
            "extend one given",
            "view = window.new_file()  # noqa: F402",
            "view = window.new_file()  # noqa: F402, E203",
        ),
        (
            "extend two given",
            "view = window.new_file()  # noqa: F402, E111",
            "view = window.new_file()  # noqa: F402, E111, E203",
        ),
        (
            "normalize joiner",
            "view = window.new_file()  # noqa: F402,E111,E203",
            "view = window.new_file()  # noqa: F402, E111, E203",
        ),
        (
            "handle surrounding whitespace",
            "    view = window.new_file()  ",
            "    view = window.new_file()  # noqa: E203",
        ),
        (
            "keep existing comment",
            "view = window.new_file()  # comment ",
            "view = window.new_file()  # comment  # noqa: E203",
        ),
        (
            "keep existing comment with only one space preceding",
            "view = window.new_file() # comment",
            "view = window.new_file() # comment  # noqa: E203",
        ),
        (
            "keep existing comment while extending",
            "view = window.new_file()  # comment  # noqa: F403",
            "view = window.new_file()  # comment  # noqa: F403, E203",
        ),
        (
            "keep python comment position while extending",
            "view = window.new_file()  # noqa: F403  # comment",
            "view = window.new_file()  # noqa: F403, E203  # comment",
        ),
        (
            "keep informal comment position while extending",
            "view = window.new_file()  # noqa: F403, comment",
            "view = window.new_file()  # noqa: F403, E203, comment",
        ),
    ])
    def test_flake8(self, _description, BEFORE, AFTER):
        view = self.create_view(self.window)
        view.run_command("insert", {"characters": BEFORE})
        error = dict(code="E203", region=sublime.Region(4))
        edit = fix_flake8_error(error, view)
        apply_edit(view, edit)
        view_content = view.substr(sublime.Region(0, view.size()))
        self.assertEquals(AFTER, view_content)

    @p.expand([
        (
            "clean line",
            "view = window.new_file()",
            "view = window.new_file()  # type: ignore[no-idea]"
        ),
        (
            "extend one given",
            "view = window.new_file()  # type: ignore[attr]",
            "view = window.new_file()  # type: ignore[attr, no-idea]"
        ),
        (
            "extend two given",
            "view = window.new_file()  # type: ignore[attr, import]",
            "view = window.new_file()  # type: ignore[attr, import, no-idea]",
        ),
        (
            "normalize joiner",
            "view = window.new_file()  # type: ignore[attr,import]",
            "view = window.new_file()  # type: ignore[attr, import, no-idea]",
        ),
        (
            "handle surrounding whitespace",
            "    view = window.new_file()  ",
            "    view = window.new_file()  # type: ignore[no-idea]"
        ),
        (
            "mypy comment must come before existing comment",
            "view = window.new_file()  # comment ",
            "view = window.new_file()  # type: ignore[no-idea]  # comment ",
        ),
        (
            "keep existing comment while extending",
            "view = window.new_file()  # type: ignore[attr]  # comment ",
            "view = window.new_file()  # type: ignore[attr, no-idea]  # comment ",
        ),
    ])
    def test_mypy(self, _description, BEFORE, AFTER):
        view = self.create_view(self.window)
        view.run_command("insert", {"characters": BEFORE})
        error = dict(code="no-idea", region=sublime.Region(4))
        edit = fix_mypy_error(error, view)
        apply_edit(view, edit)
        view_content = view.substr(sublime.Region(0, view.size()))
        self.assertEquals(AFTER, view_content)

    @p.expand([
        (
            "clean line",
            "let |document = node.ownerDocument",
            "// eslint-disable-next-line semi\nlet document = node.ownerDocument"
        ),
        (
            "handle surrounding whitespace",
            "  let |document = node.ownerDocument",
            "  // eslint-disable-next-line semi\n  let document = node.ownerDocument"
        ),
        (
            "extend one given",
            "// eslint-disable-next-line quote\nlet |document = node.ownerDocument",
            "// eslint-disable-next-line quote, semi\nlet document = node.ownerDocument"
        ),
        (
            "extend two given",
            "// eslint-disable-next-line no-alert, quote\nlet |document = node.ownerDocument",
            "// eslint-disable-next-line no-alert, quote, semi\nlet document = node.ownerDocument"
        ),
        (
            "normalize joiner",
            "// eslint-disable-next-line no-alert,quote,semi\nlet |document = node.ownerDocument",
            "// eslint-disable-next-line no-alert, quote, semi\nlet document = node.ownerDocument"
        ),
        (
            "keep existing comment while extending",
            "// eslint-disable-next-line quote -- some comment\nlet |document = node.ownerDocument",
            "// eslint-disable-next-line quote, semi -- some comment\nlet document = node.ownerDocument"
        ),
        (
            "recognize plugin rules",
            "// eslint-disable-next-line plugin/quote\nlet |document = node.ownerDocument",
            "// eslint-disable-next-line plugin/quote, semi\nlet document = node.ownerDocument"
        ),
    ])
    def test_eslint(self, _description, BEFORE, AFTER):
        view = self.create_view(self.window)
        BEFORE, POS = "".join(BEFORE.split("|")), BEFORE.index("|")
        view.run_command("insert", {"characters": BEFORE})
        error = dict(code="semi", region=sublime.Region(POS))
        edit = fix_eslint_error(error, view)
        apply_edit(view, edit)
        view_content = view.substr(sublime.Region(0, view.size()))
        self.assertEquals(AFTER, view_content)

    @p.expand([
        (
            "clean line",
            "#id| {",
            "#id { /* stylelint-disable-line selector-no-id */"
        ),
        (
            "extend given comment",
            "#id| { /* stylelint-disable-line some-rule */",
            "#id { /* stylelint-disable-line some-rule, selector-no-id */",
        ),
    ])
    def test_stylelint(self, _description, BEFORE, AFTER):
        view = self.create_view(self.window)
        BEFORE, POS = "".join(BEFORE.split("|")), BEFORE.index("|")
        view.run_command("insert", {"characters": BEFORE})
        error = dict(code="selector-no-id", region=sublime.Region(POS))
        edit = fix_stylelint_error(error, view)
        apply_edit(view, edit)
        view_content = view.substr(sublime.Region(0, view.size()))
        self.assertEquals(AFTER, view_content)
