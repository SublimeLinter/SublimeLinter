from textwrap import dedent
import sublime

from unittesting import DeferrableTestCase
from SublimeLinter.tests.mockito import unstub
from SublimeLinter.tests.parameterized import parameterized as p


from SublimeLinter.lint.quick_fix import (
    apply_edits,
    fix_eslint_error,
    eslint_ignore_block,
    fix_flake8_error,
    fix_mypy_error,
    fix_stylelint_error,
    ignore_rules_actions,


    DEFAULT_SUBJECT,
    DEFAULT_DETAIL
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
                'flake: Disable 201 — foo unused'
            ]
        ),
        (
            "two distinct errors",
            [
                dict(linter="flake", code="201", msg="foo unused", line=1),
                dict(linter="flake", code="202", msg="zoo unused", line=1),
            ],
            [
                'flake: Disable 201 — foo unused',
                'flake: Disable 202 — zoo unused'
            ]
        ),
        (
            "two similar errors, same line",
            [
                dict(linter="flake", code="201", msg="foo unused", line=1),
                dict(linter="flake", code="201", msg="zoo unused", line=1),
            ],
            [
                'flake: Disable 201 (2x) — e.g. foo unused',
            ]
        ),
        (
            "two similar errors, same line, same message",
            [
                dict(linter="flake", code="201", msg="too much", line=1),
                dict(linter="flake", code="201", msg="too much", line=1),
            ],
            [
                'flake: Disable 201 (2x) — too much',
            ]
        ),
        (
            "two similar errors, different line",
            [
                dict(linter="flake", code="201", msg="foo unused", line=1),
                dict(linter="flake", code="201", msg="zoo unused", line=2),
            ],
            [
                'flake: Disable 201 (2x) — e.g. foo unused',
            ]
        ),
    ])
    def test_action_descriptions(self, _, ERRORS, RESULT):
        fixer = lambda: None
        except_for = set()

        actions = ignore_rules_actions(
            DEFAULT_SUBJECT, DEFAULT_DETAIL, except_for, fixer, ERRORS, None
        )
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
            "view = window.new_file()  # noqa: E203, F402",
        ),
        (
            "extend two given",
            "view = window.new_file()  # noqa: F402, E111",
            "view = window.new_file()  # noqa: E111, E203, F402",
        ),
        (
            "normalize joiner",
            "view = window.new_file()  # noqa: F402,E111,E203",
            "view = window.new_file()  # noqa: E111, E203, F402",
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
            "view = window.new_file()  # comment  # noqa: E203, F403",
        ),
        (
            "keep python comment position while extending",
            "view = window.new_file()  # noqa: F403  # comment",
            "view = window.new_file()  # noqa: E203, F403  # comment",
        ),
        (
            "keep informal comment position while extending",
            "view = window.new_file()  # noqa: F403, comment",
            "view = window.new_file()  # noqa: E203, F403, comment",
        ),
    ])
    def test_flake8(self, _description, BEFORE, AFTER):
        view = self.create_view(self.window)
        view.run_command("insert", {"characters": BEFORE})
        error = dict(code="E203", region=sublime.Region(4))
        edit = fix_flake8_error(error, view)
        apply_edits(view, edit)
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
        (
            "keep existing type comment in-place",
            "view = window.new_file()  # type: sublime.View",
            "view = window.new_file()  # type: sublime.View  # type: ignore[no-idea]",
        ),
    ])
    def test_mypy(self, _description, BEFORE, AFTER):
        view = self.create_view(self.window)
        view.run_command("insert", {"characters": BEFORE})
        error = dict(code="no-idea", region=sublime.Region(4))
        edit = fix_mypy_error(error, view)
        apply_edits(view, edit)
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
        apply_edits(view, edit)
        view_content = view.substr(sublime.Region(0, view.size()))
        self.assertEquals(AFTER, view_content)

    @p.expand([
        (
            "clean block",
            dedent("""\
            let document  = node.ownerDocument
            """.rstrip()),
            dedent("""\
            /* eslint-disable semi */
            let document  = node.ownerDocument
            /* eslint-enable semi */
            """.rstrip()),
            sublime.Region(4, 8)
        ),
        (
            "extend existing",
            dedent("""\
            /* eslint-disable emi */
            let document  = node.ownerDocument
            /* eslint-enable emi */
            """.rstrip()),
            dedent("""\
            /* eslint-disable emi, semi */
            let document  = node.ownerDocument
            /* eslint-enable emi, semi */
            """.rstrip()),
            sublime.Region(28, 32)
        )
    ])
    def test_eslint_block(self, _description, BEFORE, AFTER, REGION):
        view = self.create_view(self.window)
        view.run_command("insert", {"characters": BEFORE})
        errors = [
            dict(code="semi", region=sublime.Region(28)),
        ]
        edit = eslint_ignore_block(errors, REGION, view)
        apply_edits(view, edit)
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
            "#id { /* stylelint-disable-line selector-no-id, some-rule */",
        ),
    ])
    def test_stylelint(self, _description, BEFORE, AFTER):
        view = self.create_view(self.window)
        BEFORE, POS = "".join(BEFORE.split("|")), BEFORE.index("|")
        view.run_command("insert", {"characters": BEFORE})
        error = dict(code="selector-no-id", region=sublime.Region(POS))
        edit = fix_stylelint_error(error, view)
        apply_edits(view, edit)
        view_content = view.substr(sublime.Region(0, view.size()))
        self.assertEquals(AFTER, view_content)
