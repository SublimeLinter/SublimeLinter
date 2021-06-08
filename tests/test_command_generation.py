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
    contains,
    expect,
    mock,
    unstub,
    verify,
    when,
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
        when(linter_module).register_linter(...).thenReturn(None)

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

    # Related bug: https://github.com/SublimeTextIssues/Core/issues/1878
    @p.expand([
        ("\\a\\b\\c.py", ),
        ("\\\\HOST\\a\\b\\c.py", ),
        ("\\a\\b\\c$foo.py", ),
        ("\\a\\b\\c{foo}.py", ),
    ])
    def test_ensure_paths_format(self, FILENAME):
        class FakeLinter(Linter):
            cmd = 'fake_linter_1'
            defaults = {'selector': None, '--foo': '${file}'}

        FINAL_CMD = ["fake_linter_1", "--foo", FILENAME]
        when(self.view).file_name().thenReturn(FILENAME)
        settings = linter_module.get_linter_settings(FakeLinter, self.view)
        linter = FakeLinter(self.view, settings)

        with expect(linter)._communicate(FINAL_CMD, ...):
            linter.lint(INPUT, VIEW_UNCHANGED)

    @p.expand([
        ("\\a\\b\\c.py", ),
        ("\\\\HOST\\a\\b\\c.py", ),
        # ("\\a\\b\\c$foo.py", ),  # `$foo` on the cmd denotes a variable!
        ("\\a\\b\\c{foo}.py", ),
    ])
    def test_do_not_mangle_literal_paths_in_cmd(self, FILENAME):
        class FakeLinter(Linter):
            cmd = "fake_linter_1 '{}'".format(FILENAME)
            defaults = {'selector': None}

        FINAL_CMD = ["fake_linter_1", FILENAME]
        linter = FakeLinter(self.view, {})

        with expect(linter)._communicate(FINAL_CMD, ...):
            linter.lint(INPUT, VIEW_UNCHANGED)

    @p.expand([
        ("\\a\\b\\c.py", ),
        ("\\\\HOST\\a\\b\\c.py", ),
        ("\\a\\b\\c$foo.py", ),
        ("\\a\\b\\c$$foo.py", ),
        ("\\a\\b\\c{foo}.py", ),
        ("\\a\\b\\c{{foo}}.py", ),
    ])
    def test_ensure_transparent_settings(self, FILENAME):
        class FakeLinter(Linter):
            cmd = 'fake_linter_1'
            defaults = {'selector': None, '--foo': '${file}'}

        when(self.view).file_name().thenReturn(FILENAME)
        settings = linter_module.get_linter_settings(FakeLinter, self.view)
        linter = FakeLinter(self.view, settings)

        self.assertEqual(linter.settings['foo'], FILENAME)


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

        EXECUTABLE = 'my_linter'
        RESULT = ['resolved']
        settings = {'executable': EXECUTABLE}

        linter = FakeLinter(self.view, settings)
        when(util).which('my_linter').thenReturn('resolved')
        with expect(linter)._communicate(RESULT, ...):
            linter.lint(INPUT, VIEW_UNCHANGED)

    def test_executable_is_set_to_an_array(self):
        class FakeLinter(Linter):
            cmd = ('fake_linter_1',)
            defaults = {'selector': None}

        EXECUTABLE = ['my_interpreter', 'my_linter']
        RESULT = ['resolved', 'my_linter']
        settings = {'executable': EXECUTABLE}

        linter = FakeLinter(self.view, settings)
        when(util).which('my_interpreter').thenReturn('resolved')
        with expect(linter)._communicate(RESULT, ...):
            linter.lint(INPUT, VIEW_UNCHANGED)

    def test_unhappy_given_short_name(self):
        class FakeLinter(Linter):
            cmd = ('fake_linter_1',)
            defaults = {'selector': None}

        EXECUTABLE = 'my_linter'
        settings = {'executable': EXECUTABLE}

        linter = FakeLinter(self.view, settings)
        when(linter).notify_failure().thenReturn(None)
        when(util).which(...).thenReturn(None)
        when(linter.logger).error(...)

        try:
            linter.lint(INPUT, VIEW_UNCHANGED)
        except linter_module.PermanentError:
            pass

        verify(linter.logger).error(
            contains(
                "You set 'executable' to 'my_linter'.  "
                "However, 'which my_linter' returned nothing.\n"
                "Try setting an absolute path to the binary."
            )
        )
        verify(linter).notify_failure()

    def test_unhappy_given_abs_path(self):
        class FakeLinter(Linter):
            cmd = ('fake_linter_1',)
            defaults = {'selector': None}

        EXECUTABLE = '/usr/bin/my_linter'
        settings = {'executable': EXECUTABLE}

        linter = FakeLinter(self.view, settings)
        when(linter).notify_failure().thenReturn(None)
        when(util).which(...).thenReturn(None)
        when(linter.logger).error(...)

        try:
            linter.lint(INPUT, VIEW_UNCHANGED)
        except linter_module.PermanentError:
            pass

        verify(linter.logger).error(
            "You set 'executable' to '/usr/bin/my_linter'.  However, "
            "'/usr/bin/my_linter' does not exist or is not executable. "
        )
        verify(linter).notify_failure()

    def test_unhappy_given_short_name_in_array(self):
        class FakeLinter(Linter):
            cmd = ('fake_linter_1',)
            defaults = {'selector': None}

        EXECUTABLE = ['my_interpreter', 'my_linter']
        settings = {'executable': EXECUTABLE}

        linter = FakeLinter(self.view, settings)
        when(linter).notify_failure().thenReturn(None)
        when(util).which(...).thenReturn(None)
        when(linter.logger).error(...)

        try:
            linter.lint(INPUT, VIEW_UNCHANGED)
        except linter_module.PermanentError:
            pass

        verify(linter.logger).error(
            contains(
                "You set 'executable' to ['my_interpreter', 'my_linter'].  "
                "However, 'which my_interpreter' returned nothing.\n"
                "Try setting an absolute path to the binary."
            )
        )
        verify(linter).notify_failure()

    def test_unhappy_given_abs_path_in_array(self):
        class FakeLinter(Linter):
            cmd = ('fake_linter_1',)
            defaults = {'selector': None}

        EXECUTABLE = ['/usr/bin/my_interpreter', 'my_linter']
        settings = {'executable': EXECUTABLE}

        linter = FakeLinter(self.view, settings)
        when(linter).notify_failure().thenReturn(None)
        when(util).which(...).thenReturn(None)
        when(linter.logger).error(...)

        try:
            linter.lint(INPUT, VIEW_UNCHANGED)
        except linter_module.PermanentError:
            pass

        verify(linter.logger).error(
            "You set 'executable' to ['/usr/bin/my_interpreter', 'my_linter'].  "
            "However, '/usr/bin/my_interpreter' does not exist or is not executable. "
        )
        verify(linter).notify_failure()


class TestViewContext(_BaseTestCase):
    @p.expand([
        (['/foo'], None, '/foo'),
        (['/foo'], '/foo/faa/foz.py', '/foo'),
        (['/bar', '/foo'], '/foo/faa/foz.py', '/foo'),
        (['/bar'], '/foo/faa/foz.py', None),
        ([], '/foo/faa/foz.py', None),
        ([], None, None),
    ])
    def test_folder_setting(self, FOLDERS, FILENAME, RESULT):
        window = mock(sublime.Window)
        when(window).folders().thenReturn(FOLDERS)
        when(window).extract_variables().thenReturn({})
        when(self.view).file_name().thenReturn(FILENAME)
        when(self.view).window().thenReturn(window)

        context = linter_module.get_view_context(self.view)
        self.assertEqual(RESULT, context.get('folder'))

    def test_ensure_file_properties_come_from_given_view_case_saved_file(self):
        sublime.run_command("new_window")
        window = sublime.active_window()
        self.addCleanup(window.run_command, 'close_window')

        view = window.open_file(__file__, sublime.ENCODED_POSITION)

        context = linter_module.get_view_context(view)
        self.assertEqual(context.get('file'), __file__)

    def test_ensure_file_properties_come_from_given_view_case_new_file(self):
        sublime.run_command("new_window")
        window = sublime.active_window()
        self.addCleanup(window.run_command, 'close_window')

        view = window.new_file()

        context = linter_module.get_view_context(view)
        self.assertEqual(context.get('file'), None)

    def test_ensure_file_properties_come_from_given_view_not_the_active(self):
        sublime.run_command("new_window")
        window = sublime.active_window()
        self.addCleanup(window.run_command, 'close_window')

        unsaved_view = window.new_file()
        focused_view = window.open_file(__file__, sublime.ENCODED_POSITION)
        window.focus_view(focused_view)

        context = linter_module.get_view_context(unsaved_view)
        self.assertEqual(context.get('file', None), None)


class TestLintModeSetting(_BaseTestCase):
    def test_use_provided_mode(self):
        class FakeLinter(Linter):
            cmd = ('fake_linter_1',)
            defaults = {'selector': None, 'lint_mode': 'manual'}

        settings = linter_module.get_linter_settings(FakeLinter, self.view)
        self.assertEqual(settings.get('lint_mode'), 'manual')

    def test_use_fallback(self):
        class FakeLinter(Linter):
            cmd = ('fake_linter_1',)
            defaults = {'selector': None}

        settings = linter_module.get_linter_settings(FakeLinter, self.view)
        self.assertEqual(settings.get('lint_mode'), 'background')


class TestWorkingDirSetting(_BaseTestCase):
    # XXX: We shouldn't have to mock anything here but use the settings context

    @p.expand([
        (['/foo'], None, '/foo'),
        (['/foo'], '/foo/faa/boz.py', '/foo'),
        (['/bar', '/foo'], '/foo/faa/boz.py', '/foo'),
    ])
    def test_working_dir_set_none_returns_project_root(
        self, folders, filename, result
    ):
        class FakeLinter(Linter):
            cmd = ('fake_linter_1',)
            defaults = {'selector': None}

        window = mock(sublime.Window)
        when(window).folders().thenReturn(folders)
        when(window).extract_variables().thenReturn({})
        when(window).project_data().thenReturn({})
        when(self.view).file_name().thenReturn(filename)
        when(self.view).window().thenReturn(window)

        settings = linter_module.get_linter_settings(FakeLinter, self.view)
        linter = FakeLinter(self.view, settings)
        actual = linter.get_working_dir()
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

        filename = '/foo/faa/bar.py'
        result = '/foo/faa'

        window = mock(sublime.Window)
        when(window).folders().thenReturn(folders)
        when(window).extract_variables().thenReturn({})
        when(window).project_data().thenReturn({})
        when(self.view).window().thenReturn(window if has_window else None)
        when(self.view).file_name().thenReturn(filename)

        settings = linter_module.get_linter_settings(FakeLinter, self.view)
        linter = FakeLinter(self.view, settings)
        actual = linter.get_working_dir()
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
        actual = linter.get_working_dir()
        self.assertEqual(result, actual)

    def test_working_dir_set_to_valid_path_returns_path(self):
        class FakeLinter(Linter):
            cmd = ('fake_linter_1',)
            defaults = {'selector': None}

        dir = '/foo'
        settings = {'working_dir': dir}
        when('os.path').isdir(dir).thenReturn(True)

        linter = FakeLinter(self.view, settings)
        actual = linter.get_working_dir()
        self.assertEqual('/foo', actual)

    def test_working_dir_set_to_invalid_path_returns_none(self):
        class FakeLinter(Linter):
            cmd = ('fake_linter_1',)
            defaults = {'selector': None}

        dir = '/foo'
        settings = {'working_dir': dir}
        when('os.path').isdir(dir).thenReturn(False)

        linter = FakeLinter(self.view, settings)
        with expect(linter.logger).error(
            "{}: wanted working_dir '{}' is not a directory".format('fakelinter', dir)
        ):
            actual = linter.get_working_dir()

        self.assertEqual(None, actual)


class TestDeprecations(_BaseTestCase):
    def test_working_dir_takes_no_arg_anymore(self):
        class FakeLinter(Linter):
            cmd = ('fake_linter_1',)
            defaults = {'selector': None}

        linter = FakeLinter(self.view, {})

        when(linter_module.logger).warning(...)
        linter.get_working_dir({})
        verify(linter_module.logger).warning(
            "fakelinter: Passing a `settings` object down to `get_working_dir` "
            "has been deprecated and no effect anymore.  "
            "Just use `self.get_working_dir()`."
        )

    def test_get_environment_takes_no_arg_anymore(self):
        class FakeLinter(Linter):
            cmd = ('fake_linter_1',)
            defaults = {'selector': None}

        linter = FakeLinter(self.view, {})

        when(linter_module.logger).warning(...)
        linter.get_environment({})
        verify(linter_module.logger).warning(
            "fakelinter: Passing a `settings` object down to `get_environment` "
            "has been deprecated and no effect anymore.  "
            "Just use `self.get_environment()`."
        )

    def test_get_view_settings_warns(self):
        class FakeLinter(Linter):
            cmd = ('fake_linter_1',)
            defaults = {'selector': None}

        linter = FakeLinter(self.view, {})

        when(linter_module.logger).warning(...)
        linter.get_view_settings()
        verify(linter_module.logger).warning(
            "fakelinter: `self.get_view_settings()` has been deprecated.  "
            "Just use the member `self.settings` which is the same thing."
        )

    def test_executable_path_warns(self):
        class FakeLinter(Linter):
            cmd = ('fake_linter_1',)
            defaults = {'selector': None}

        linter = FakeLinter(self.view, {})

        when(linter_module.logger).warning(...)
        linter.executable_path
        verify(linter_module.logger).warning(
            "fakelinter: `executable_path` has been deprecated. "
            "Just use an ordinary binary name instead. "
        )

    def test_args_star_marker_warns(self):
        class FakeLinter(Linter):
            cmd = ('fake_linter_1', '*')
            defaults = {'selector': None}

        linter = FakeLinter(self.view, {})

        when(linter_module.logger).warning(...)
        linter.get_cmd()
        verify(linter_module.logger).warning(
            "fakelinter: Usage of '*' as a special marker in `cmd` "
            "has been deprecated, use '${args}' instead."
        )

    def test_old_file_marker_in_cmd_warns_stdin_linter(self):
        class FakeLinter(Linter):
            cmd = ('fake_linter_1', '@')
            defaults = {'selector': None}

        linter = FakeLinter(self.view, {})
        when(linter_module.logger).warning(...)
        when(linter)._communicate(...).thenReturn('')
        when(util).which(...).thenReturn('fake.exe')

        linter.lint('foo', lambda: False)

        verify(linter_module.logger).warning(
            "fakelinter: Usage of '@' as a special marker in `cmd` "
            "has been deprecated, use '${file}' instead."
        )

    def test_old_file_marker_in_cmd_warns_file_linter(self):
        class FakeLinter(Linter):
            cmd = ('fake_linter_1', '@')
            defaults = {'selector': None}
            tempfile_suffix = '-'

        linter = FakeLinter(self.view, {})
        when(linter_module.logger).warning(...)
        when(linter)._communicate(...).thenReturn('')
        when(util).which(...).thenReturn('fake.exe')

        linter.lint('foo', lambda: False)

        verify(linter_module.logger).warning(
            "fakelinter: Usage of '@' as a special marker in `cmd` "
            "has been deprecated, use '${file_on_disk}' instead."
        )

    def test_old_file_marker_in_cmd_warns_tempfile_linter(self):
        class FakeLinter(Linter):
            cmd = ('fake_linter_1', '@')
            defaults = {'selector': None}
            tempfile_suffix = 'py'

        linter = FakeLinter(self.view, {})
        when(linter_module.logger).warning(...)
        when(linter)._communicate(...).thenReturn('')
        when(util).which(...).thenReturn('fake.exe')

        linter.lint('foo', lambda: False)

        verify(linter_module.logger).warning(
            "fakelinter: Usage of '@' as a special marker in `cmd` "
            "has been deprecated, use '${temp_file}' instead."
        )

    def test_implicit_file_marker_warns_file_linter(self):
        class FakeLinter(Linter):
            cmd = ('fake_linter_1', )
            defaults = {'selector': None}
            tempfile_suffix = '-'

        linter = FakeLinter(self.view, {})
        when(linter_module.logger).warning(...)
        when(linter)._communicate(...).thenReturn('')
        when(util).which(...).thenReturn('fake.exe')

        linter.lint('foo', lambda: False)

        verify(linter_module.logger).warning(
            "fakelinter: Implicit appending a filename to `cmd` "
            "has been deprecated, add '${file_on_disk}' explicitly."
        )

    def test_implicit_file_marker_warns_tempfile_linter(self):
        class FakeLinter(Linter):
            cmd = ('fake_linter_1', )
            defaults = {'selector': None}
            tempfile_suffix = 'py'

        linter = FakeLinter(self.view, {})
        when(linter_module.logger).warning(...)
        when(linter)._communicate(...).thenReturn('')
        when(util).which(...).thenReturn('fake.exe')

        linter.lint('foo', lambda: False)

        verify(linter_module.logger).warning(
            "fakelinter: Implicit appending a filename to `cmd` "
            "has been deprecated, add '${temp_file}' explicitly."
        )


class TestContextSensitiveExecutablePathContract(_BaseTestCase):
    @p.expand([
        ('/foo/foz.exe', ),
        ('\\\\HOST\\foo\\foz.exe'),
    ])
    def test_returns_true_and_a_path_indicates_success(self, EXECUTABLE):
        class FakeLinter(Linter):
            cmd = ('fake_linter_1',)
            defaults = {'selector': None}

        linter = FakeLinter(self.view, {})
        when(linter).context_sensitive_executable_path(...).thenReturn((True, EXECUTABLE))

        result = [EXECUTABLE]
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

        with self.assertRaises(linter_module.PermanentError):
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

    @p.expand([
        ("\\a\\b\\c.py", ),
        ("\\\\HOST\\a\\b\\c.py", ),
        ("\\a\\b\\c$foo.py", ),
        ("\\a\\b\\c{foo}.py", ),
    ])
    def test_substitute_variables_in_cmd(self, FILENAME):
        class FakeLinter(Linter):
            cmd = 'fake_linter_1 ${file}'
            defaults = {'selector': None}

        FINAL_CMD = ["fake_linter_1", FILENAME]
        when(self.view).file_name().thenReturn(FILENAME)
        settings = linter_module.get_linter_settings(FakeLinter, self.view)
        linter = FakeLinter(self.view, settings)

        with expect(linter)._communicate(FINAL_CMD, ...):
            linter.lint(INPUT, VIEW_UNCHANGED)


# TODO
#

# PythonLinter
# - python setting
# - pipenv
