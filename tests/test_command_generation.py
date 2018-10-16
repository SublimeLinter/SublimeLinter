from unittest import skip, expectedFailure  # noqa: F401

import sublime
from SublimeLinter.lint import (
    Linter,
    backend,
    persist,
    linter as linter_module,
    util,
)

from unittesting import DeferrableTestCase
from SublimeLinter.tests.parameterized import parameterized as p
from SublimeLinter.tests.mockito import (
    when,
    expect,
    patch,
    unstub,
    spy,
    spy2,
    mock,
    verify,
)


VIEW_UNCHANGED = lambda: False  # noqa: E731
INPUT = '0123456789'


class _BaseTestCase(DeferrableTestCase):
    @classmethod
    def setUpClass(cls):
        cls.view = sublime.active_window().new_file()
        # make sure we have a window to work with
        s = sublime.load_settings("Preferences.sublime-settings")
        s.set("close_windows_when_empty", False)
        when(util).which('fake_linter_1').thenReturn('fake_linter_1')

        # it's just faster if we mock this out
        when(linter_module.LinterMeta).register_linter(...).thenReturn(None)

    @classmethod
    def tearDownClass(cls):
        if cls.view:
            cls.view.set_scratch(True)
            cls.view.window().focus_view(cls.view)
            cls.view.window().run_command("close_file")

        unstub()

    def setUp(self):
        ...

    def tearDown(self):
        ...


class TestArgsSetting(_BaseTestCase):
    @p.expand([
        ({'args': ['-f', '/b']}, ['fake_linter_1', '-f', '/b', 'end']),
        # simple splitting
        ({'args': '-f /b'}, ['fake_linter_1', '-f', '/b', 'end']),
    ])
    def test_args_explicitly_placed(self, settings, result):
        class FakeLinter(Linter):
            cmd = ('fake_linter_1', '${args}', 'end')
            defaults = {'selector': None}

        linter = FakeLinter(self.view, settings)
        with expect(linter)._communicate(result, ...):
            linter.lint(INPUT, VIEW_UNCHANGED)

    @p.expand([
        ({'args': ['-f', '/b']}, ['fake_linter_1', 'end', '-f', '/b']),
        # simple splitting
        ({'args': '-f /b'}, ['fake_linter_1', 'end', '-f', '/b']),
    ])
    def test_args_implicitly_placed_at_end(self, settings, result):
        class FakeLinter(Linter):
            cmd = ('fake_linter_1', 'end')
            defaults = {'selector': None}

        linter = FakeLinter(self.view, settings)
        with expect(linter)._communicate(result, ...):
            linter.lint(INPUT, VIEW_UNCHANGED)

    @expectedFailure
    def test_splits_context_variables_correctly(self):
        class FakeLinter(Linter):
            cmd = ('fake_linter_1',)
            defaults = {'selector': None}

        var = 'C:\\foo bar\\my config.file'
        settings = linter_module.LinterSettings(
            {'args': '-c=${var}'},
            {'var': var}
        )
        linter = FakeLinter(self.view, settings)
        result = ['fake_linter_1', '-c={}'.format(var)]
        with expect(linter)._communicate(result, ...):
            linter.lint(INPUT, VIEW_UNCHANGED)


class TestExecutableSetting(_BaseTestCase):

    def test_executable_is_none(self):
        class FakeLinter(Linter):
            cmd = ('fake_linter_1',)
            defaults = {'selector': None}

        settings = {'executable': None}
        result = ['fake_linter_1']

        linter = FakeLinter(self.view, settings)
        with expect(linter)._communicate(result, ...):
            linter.lint(INPUT, VIEW_UNCHANGED)

    def test_executable_is_set_to_a_string(self):
        class FakeLinter(Linter):
            cmd = ('fake_linter_1',)
            defaults = {'selector': None}

        settings = {'executable': 'my_linter'}
        result = ['my_linter']

        linter = FakeLinter(self.view, settings)
        # XXX: We probably don't need to test `can_exec`
        # - Popen will also throw and show the error panel
        # - User could just set e.g. 'linter.exe', and the OS will use PATH
        #   to resolve that automatically
        # - We don't check for arrays, see below
        with when(util).can_exec('my_linter').thenReturn(True), \
             expect(linter)._communicate(result, ...):  # noqa: E127
            linter.lint(INPUT, VIEW_UNCHANGED)

    def test_executable_is_set_to_an_array(self):
        class FakeLinter(Linter):
            cmd = ('fake_linter_1',)
            defaults = {'selector': None}

        settings = {'executable': ['my_interpreter', 'my_linter']}
        result = ['my_interpreter', 'my_linter']

        linter = FakeLinter(self.view, settings)
        with expect(linter)._communicate(result, ...):
            linter.lint(INPUT, VIEW_UNCHANGED)

# TODO
# 'working_dir'
# if set, throws if not exists
# show default behavior
# - selects good folder if multiple folders open
# - selects first folder if no filename
# - or dirname of file
#
# 'context_sensitive_executable_path' contract
# returns
# - True, path  --> take path
# - True, None  --> abort linting
# - False, None --> use can_exec and which (SL defaults)
#
# 'cmd'
# - can be string
# - can be tuple/list
# - can be a callable which
#   - returns a string
#   - returns a tuple/list
#

# PythonLinter
# - python setting
# - pipenv
