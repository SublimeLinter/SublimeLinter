from unittest import skip, expectedFailure  # noqa: F401

import sublime
from SublimeLinter.lint import (
    Linter,
    linter as linter_module,
    util,
)

from unittesting import DeferrableTestCase
from SublimeLinter.tests.parameterized import parameterized as p
from SublimeLinter.tests.mockito import (
    when,
    verifyNoUnwantedInteractions,
    expect,
    unstub,
    mock
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


class TestArgsSetting(_BaseTestCase):
    @p.expand([
        ('list', {'args': ['-f', '/b']}, ['fake_linter_1', '-f', '/b', 'end']),
        # simple splitting
        ('string', {'args': '-f /b'}, ['fake_linter_1', '-f', '/b', 'end']),
    ])
    def test_args_explicitly_placed(self, _, settings, result):
        class FakeLinter(Linter):
            cmd = ('fake_linter_1', '${args}', 'end')
            defaults = {'selector': None}

        linter = FakeLinter(self.view, settings)
        with expect(linter)._communicate(result, ...):
            linter.lint(INPUT, VIEW_UNCHANGED)

    @p.expand([
        ('list', {'args': ['-f', '/b']}, ['fake_linter_1', 'end', '-f', '/b']),
        # simple splitting
        ('string', {'args': '-f /b'}, ['fake_linter_1', 'end', '-f', '/b']),
    ])
    def test_args_implicitly_placed_at_end(self, _, settings, result):
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


class TestWorkingDirSetting(_BaseTestCase):
    # XXX: `get_working_dir` is a getter and shouldn't require `settings` to get
    # injected.
    # XXX: We shouldn't have to mock anything here but use the settings context

    @p.expand([
        (['/foo'], None, '/foo'),
        (['/foo'], '/foo/foz.py', '/foo'),
        (['/bar', '/foo'], '/foo/foz.py', '/foo'),
    ])
    def test_working_dir_set_none_returns_project_root(
        self, folders, filename, result
    ):
        class FakeLinter(Linter):
            cmd = ('fake_linter_1',)
            defaults = {'selector': None}

        settings = {'working_dir': None}

        window = mock(sublime.Window)
        when(window).folders().thenReturn(folders)
        when(self.view).file_name().thenReturn(filename)
        when(self.view).window().thenReturn(window)

        linter = FakeLinter(self.view, settings)
        actual = linter.get_working_dir(settings)
        self.assertEqual(result, actual)

    @p.expand([
        (False, None),
        (True, []),
        (True, ['/bar']),
    ])
    def test_working_dir_set_none_and_no_project_root_returns_filepath(
        self, has_window, folders
    ):
        class FakeLinter(Linter):
            cmd = ('fake_linter_1',)
            defaults = {'selector': None}

        settings = {'working_dir': None}
        filename = '/foo/bar.py'
        result = '/foo'

        window = mock(sublime.Window)
        when(window).folders().thenReturn(folders)
        when(self.view).window().thenReturn(window if has_window else None)

        when(self.view).file_name().thenReturn(filename)

        linter = FakeLinter(self.view, settings)
        actual = linter.get_working_dir(settings)
        self.assertEqual(result, actual)

    @p.expand([
        (False, None),
        (True, []),
    ])
    def test_working_dir_set_none_and_no_project_root_and_no_file_returns_none(
        self, has_window, folders
    ):
        class FakeLinter(Linter):
            cmd = ('fake_linter_1',)
            defaults = {'selector': None}

        settings = {'working_dir': None}
        filename = None
        result = None

        window = mock(sublime.Window)
        when(window).folders().thenReturn(folders)
        when(self.view).window().thenReturn(window if has_window else None)

        when(self.view).file_name().thenReturn(filename)

        linter = FakeLinter(self.view, settings)
        actual = linter.get_working_dir(settings)
        self.assertEqual(result, actual)

    def test_working_dir_set_to_valid_path_returns_path(self):
        class FakeLinter(Linter):
            cmd = ('fake_linter_1',)
            defaults = {'selector': None}

        dir = '/foo'
        settings = {'working_dir': dir}
        when('os.path').isdir(dir).thenReturn(True)

        linter = FakeLinter(self.view, settings)
        actual = linter.get_working_dir(settings)
        self.assertEqual('/foo', actual)

    def test_working_dir_set_to_invalid_path_returns_none(self):
        class FakeLinter(Linter):
            cmd = ('fake_linter_1',)
            defaults = {'selector': None}

        dir = '/foo'
        settings = {'working_dir': dir}
        when('os.path').isdir(dir).thenReturn(False)

        linter = FakeLinter(self.view, settings)
        with expect(linter_module.logger).error(
            "{}: wanted working_dir '{}' is not a directory".format('fakelinter', dir)
        ):
            actual = linter.get_working_dir(settings)

            # Looks like we're using an outdated version of mockito,
            # which does not automatically verify on `__exit__`.
            verifyNoUnwantedInteractions(linter_module.logger)

        self.assertEqual(None, actual)


class TestContextSensitiveExecutablePathContract(_BaseTestCase):
    def test_returns_true_and_a_path_indicates_success(self):
        class FakeLinter(Linter):
            cmd = ('fake_linter_1',)
            defaults = {'selector': None}

        executable = '/foo/foz.exe'
        linter = FakeLinter(self.view, {})
        when(linter).context_sensitive_executable_path(...).thenReturn((True, executable))

        result = [executable]
        with expect(linter)._communicate(result, ...):
            linter.lint(INPUT, VIEW_UNCHANGED)

    def test_returns_true_and_a_list_of_strings_indicates_success(self):
        class FakeLinter(Linter):
            cmd = ('fake_linter_1',)
            defaults = {'selector': None}

        executable = ['/foo/foz.exe', '-S', 'baz']
        linter = FakeLinter(self.view, {})
        when(linter).context_sensitive_executable_path(...).thenReturn((True, executable))

        result = executable
        with expect(linter)._communicate(result, ...):
            linter.lint(INPUT, VIEW_UNCHANGED)

    def test_returns_true_and_none_indicates_failure(self):
        class FakeLinter(Linter):
            cmd = ('fake_linter_1',)
            defaults = {'selector': None}

        linter = FakeLinter(self.view, {})
        when(linter).context_sensitive_executable_path(...).thenReturn((True, None))

        with expect(linter, times=0)._communicate(...):
            linter.lint(INPUT, VIEW_UNCHANGED)

    def test_returns_false_and_any_indicates_fallback(self):
        class FakeLinter(Linter):
            cmd = ('fake_linter_1',)
            defaults = {'selector': None}

        linter = FakeLinter(self.view, {})
        when(linter).context_sensitive_executable_path(...).thenReturn((False, ...))

        with expect(linter)._communicate(['fake_linter_1'], ...):
            linter.lint(INPUT, VIEW_UNCHANGED)


class TestCmdType(_BaseTestCase):
    @p.expand([
        ('string', 'fake_linter_1 -foo', ['fake_linter_1', '-foo']),
        ('list', ['fake_linter_1', '-foo'], ['fake_linter_1', '-foo']),
        ('tuple', ('fake_linter_1', '-foo'), ['fake_linter_1', '-foo']),
        ('callable returning string', lambda self: 'fake_linter_1 -foo', ['fake_linter_1', '-foo']),
        ('callable returning list', lambda self: ['fake_linter_1', '-foo'], ['fake_linter_1', '-foo']),
        ('callable returning tuple', lambda self: ('fake_linter_1', '-foo'), ['fake_linter_1', '-foo']),
    ])
    def test_cmd_types(self, _, initial_cmd, final_cmd):
        class FakeLinter(Linter):
            cmd = initial_cmd
            defaults = {'selector': None}

        linter = FakeLinter(self.view, {})
        with expect(linter)._communicate(final_cmd, ...):
            linter.lint(INPUT, VIEW_UNCHANGED)

# TODO
#

# PythonLinter
# - python setting
# - pipenv
