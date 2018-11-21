from functools import partial
from textwrap import dedent
from unittest import skip, expectedFailure  # noqa: F401

import sublime
from SublimeLinter.lint import (
    backend,
    Linter,
    linter as linter_module,
    util,
)

from unittesting import DeferrableTestCase
from SublimeLinter.tests.parameterized import parameterized as p
from SublimeLinter.tests.mockito import (
    when,
    expect,
    unstub,
    verifyNoUnwantedInteractions
)


class _BaseTestCase(DeferrableTestCase):
    @classmethod
    def setUpClass(cls):
        cls.view = sublime.active_window().new_file()
        # make sure we have a window to work with
        s = sublime.load_settings("Preferences.sublime-settings")
        s.set("close_windows_when_empty", False)

    @classmethod
    def tearDownClass(cls):
        if cls.view:
            cls.view.set_scratch(True)
            cls.view.window().focus_view(cls.view)
            cls.view.window().run_command("close_file")

    def setUp(self):
        when(util).which('fake_linter_1').thenReturn('fake_linter_1')
        # it's just faster if we mock this out
        when(linter_module.LinterMeta).register_linter(...).thenReturn(None)

    def tearDown(self):
        unstub()


VIEW_UNCHANGED = lambda: False  # noqa: E731
execute_lint_task = partial(
    backend.execute_lint_task, offset=(0, 0), view_has_changed=VIEW_UNCHANGED
)


class TestPostFilterResults(_BaseTestCase):

    @p.expand([
        # Ensure 'falsy' values do not filter anything
        ([], [{'line': 0}, {'line': 1}, {'line': 2}, {'line': 3}]),
        (None, [{'line': 0}, {'line': 1}, {'line': 2}, {'line': 3}]),
        (False, [{'line': 0}, {'line': 1}, {'line': 2}, {'line': 3}]),

        (['age'], []),
        (['massage'], [{'line': 0}, {'line': 1}, {'line': 2}]),

        # For convenience allow strings as input
        ('age', []),
        ('massage', [{'line': 0}, {'line': 1}, {'line': 2}]),

        # All input is interpreted as regex strings
        (['m[ae]ss'], []),
        (['mess|mass'], []),
        (['mess', 'mas{2}'], []),

        # the error code (aka rule name) can be checked
        (['W3:'], [{'line': 1}, {'line': 2}, {'line': 3}]),
        (['W3: '], [{'line': 1}, {'line': 2}, {'line': 3}]),
        (['W3:  '], [{'line': 0}, {'line': 1}, {'line': 2}, {'line': 3}]),
        ([r'W\d*:'], [{'line': 1}, {'line': 2}, {'line': 3}]),

        # filter error_type 'error'
        (['error'], [{'line': 0}, {'line': 1}]),
        (['error:'], [{'line': 0}, {'line': 1}]),
        (['error: '], [{'line': 0}, {'line': 1}]),
        (['error:  '], [{'line': 0}, {'line': 1}, {'line': 2}, {'line': 3}]),

        # filter error_type 'warning'
        (['warning'], [{'line': 2}, {'line': 3}]),
        (['warning:'], [{'line': 2}, {'line': 3}]),
        (['warning: '], [{'line': 2}, {'line': 3}]),
        (['warning:  '], [{'line': 0}, {'line': 1}, {'line': 2}, {'line': 3}]),
    ], doc_func=lambda f, n, param: repr(param.args[0]))
    def test_post_filter_results(self, filter_errors, expected):
        class FakeLinter(Linter):
            cmd = ('fake_linter_1')
            defaults = {'selector': None}
            regex = r"""(?x)
                ^stdin:(?P<line>\d+):(?P<col>\d+)?\s
                (\[(?P<warning>[^\]]+)\]\s)?
                (?P<message>.*)$
            """

        settings = {
            'filter_errors': filter_errors
        }
        linter = FakeLinter(self.view, settings)
        INPUT = dedent("""
        I
        am
        the
        swan""")
        OUTPUT = dedent("""\
            stdin:1:1 [w3] The message
            stdin:2:1 [S534] The message
            stdin:3:1 The mess age
            stdin:4:1 The massage
            """)

        when(linter)._communicate(...).thenReturn(OUTPUT)
        result = execute_lint_task(linter, INPUT)
        result = [{'line': error['line']} for error in result]

        self.assertEqual(result, expected)

    @p.expand([
        (['d('], "'d(' in 'filter_errors' is not a valid regex pattern: 'unbalanced parenthesis'."),
        (True, "'filter_errors' must be set to a string or a list of strings.\nGot 'True' instead"),
        (123, "'filter_errors' must be set to a string or a list of strings.\nGot '123' instead"),
    ])
    def test_warn_on_illegal_regex_string(self, filter_errors, message):
        class FakeLinter(Linter):
            cmd = ('fake_linter_1')
            defaults = {'selector': None}
            regex = r"""(?x)
                ^stdin:(?P<line>\d+):(?P<col>\d+)?\s
                (\[(?P<warning>[^\]]+)\]\s)?
                (?P<message>.*)$
            """

        settings = {
            'filter_errors': filter_errors
        }
        linter = FakeLinter(self.view, settings)
        INPUT = dedent("""
        I
        am
        the
        swan""")
        OUTPUT = dedent("""\
            stdin:1:1 [w3] The message
            stdin:2:1 [S534] The message
            stdin:3:1 The mess age
            stdin:4:1 The massage
            """)

        when(linter)._communicate(...).thenReturn(OUTPUT)
        expect(linter_module.logger, times=1).error(message)
        execute_lint_task(linter, INPUT)
        # `execute_lint_task` eats all uncatched errors, so we check again
        # to get faster and nicer output during the test
        verifyNoUnwantedInteractions(linter_module.logger)
