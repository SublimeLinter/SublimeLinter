from unittest import skip, expectedFailure

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
    def setUp(self):
        self.view = sublime.active_window().new_file()
        # make sure we have a window to work with
        s = sublime.load_settings("Preferences.sublime-settings")
        s.set("close_windows_when_empty", False)
        when(util).which('fake_linter_1').thenReturn('fake_linter_1')

    def tearDown(self):
        if self.view:
            self.view.set_scratch(True)
            self.view.window().focus_view(self.view)
            self.view.window().run_command("close_file")
        unstub()


class TestArgsDSL(_BaseTestCase):
    @p.expand([
        # Testing arg DSL
        # JOINER
        # empty joiner
        ('-a', {'a': 'foo'}, ['-a', 'foo']),
        ('-a', {'a': ['foo']}, ['-a', 'foo']),
        ('-a', {'a': ['foo', 'bar']}, ['-a', 'foo', '-a', 'bar']),
        ('--a', {'a': 'foo'}, ['--a', 'foo']),
        ('--a', {'a': ['foo']}, ['--a', 'foo']),
        ('--a', {'a': ['foo', 'bar']}, ['--a', 'foo', '--a', 'bar']),
        ('@a', {'a': 'foo'}, ['foo']),
        ('@a', {'a': ['foo']}, ['foo']),
        # The following is basically what `args` does
        ('@a', {'a': ['foo', 'bar']}, ['foo', 'bar']),
        # deprecate! ':' can be omitted
        ('-a:', {'a': 'foo'}, ['-a', 'foo']),
        ('-a:', {'a': ['foo']}, ['-a', 'foo']),
        ('-a:', {'a': ['foo', 'bar']}, ['-a', 'foo', '-a', 'bar']),
        ('--a:', {'a': 'foo'}, ['--a', 'foo']),
        ('--a:', {'a': ['foo']}, ['--a', 'foo']),
        ('--a:', {'a': ['foo', 'bar']}, ['--a', 'foo', '--a', 'bar']),
        ('@a:', {'a': 'foo'}, ['foo']),
        ('@a:', {'a': ['foo']}, ['foo']),
        ('@a:', {'a': ['foo', 'bar']}, ['foo', 'bar']),
        # '=' joiner
        ('-a=', {'a': 'foo'}, ['-a=foo']),
        ('-a=', {'a': ['foo']}, ['-a=foo']),
        ('-a=', {'a': ['foo', 'bar']}, ['-a=foo', '-a=bar']),
        ('--a=', {'a': 'foo'}, ['--a=foo']),
        ('--a=', {'a': ['foo']}, ['--a=foo']),
        ('--a=', {'a': ['foo', 'bar']}, ['--a=foo', '--a=bar']),
        # @ and = has no effect; '=' can be omitted
        ('@a=', {'a': 'foo'}, ['foo']),
        ('@a=', {'a': ['foo']}, ['foo']),
        ('@a=', {'a': ['foo', 'bar']}, ['foo', 'bar']),
        # SEPARATOR
        # empty joiner
        ('-a ', {'a': 'foo'}, ['-a', 'foo']),
        ('-a ', {'a': ['foo']}, ['-a', 'foo']),
        ('-a ', {'a': ['foo', 'bar']}, ['-a', 'foo bar']),
        ('--a ', {'a': 'foo'}, ['--a', 'foo']),
        ('--a ', {'a': ['foo']}, ['--a', 'foo']),
        ('--a ', {'a': ['foo', 'bar']}, ['--a', 'foo bar']),
        ('@a ', {'a': 'foo'}, ['foo']),
        ('@a ', {'a': ['foo']}, ['foo']),
        ('@a ', {'a': ['foo', 'bar']}, ['foo bar']),
        # ':' joiner. Can be omitted
        ('-a: ', {'a': 'foo'}, ['-a', 'foo']),
        ('-a: ', {'a': ['foo']}, ['-a', 'foo']),
        ('-a: ', {'a': ['foo', 'bar']}, ['-a', 'foo bar']),
        ('--a: ', {'a': 'foo'}, ['--a', 'foo']),
        ('--a: ', {'a': ['foo']}, ['--a', 'foo']),
        ('--a: ', {'a': ['foo', 'bar']}, ['--a', 'foo bar']),
        ('@a: ', {'a': 'foo'}, ['foo']),
        ('@a: ', {'a': ['foo']}, ['foo']),
        ('@a: ', {'a': ['foo', 'bar']}, ['foo bar']),
        ('@a,', {'a': ['foo', 'bar']}, ['foo,bar']),
        # EXCEPT if we want ':' or '=' as the separator
        ('-a::', {'a': ['foo', 'bar']}, ['-a', 'foo:bar']),
        ('-a:=', {'a': ['foo', 'bar']}, ['-a', 'foo=bar']),
        # or any char allowed in name
        ('-a:-', {'a': ['foo', 'bar']}, ['-a', 'foo-bar']),
        ('-a:_', {'a': ['foo', 'bar']}, ['-a', 'foo_bar']),
        ('-a:a', {'a': ['foo', 'bar']}, ['-a', 'fooabar']),
        #
        # '=' joiner
        ('-a= ', {'a': 'foo'}, ['-a=foo']),
        ('-a= ', {'a': ['foo']}, ['-a=foo']),
        ('-a= ', {'a': ['foo', 'bar']}, ['-a=foo bar']),
        ('--a= ', {'a': 'foo'}, ['--a=foo']),
        ('--a= ', {'a': ['foo']}, ['--a=foo']),
        ('--a= ', {'a': ['foo', 'bar']}, ['--a=foo bar']),
        ('@a= ', {'a': 'foo'}, ['foo']),
        ('@a= ', {'a': ['foo']}, ['foo']),
        ('@a= ', {'a': ['foo', 'bar']}, ['foo bar']),
        # multiple?
        # Hm, doesn't do anything on normal values
        ('-a +', {'a': 'foo'}, ['-a', 'foo']),
        ('-a +', {'a': ['foo']}, ['-a', 'foo']),
        # These are all the same
        ('-a', {'a': ['foo', 'bar']}, ['-a', 'foo', '-a', 'bar']),
        ('-a +', {'a': ['foo', 'bar']}, ['-a', 'foo', '-a', 'bar']),
        ('-a,+', {'a': ['foo', 'bar']}, ['-a', 'foo', '-a', 'bar']),
        ('-a:,+', {'a': ['foo', 'bar']}, ['-a', 'foo', '-a', 'bar']),
        #

        # Hm, doesn't do anything on normal values
        ('-a= +', {'a': 'foo'}, ['-a=foo']),
        ('-a= +', {'a': ['foo']}, ['-a=foo']),
        # Ignores the joiner on multiple values:
        ('-a= +', {'a': ['foo', 'bar']}, ['-a=foo', '-a=bar']),
        ('-a=,+', {'a': ['foo', 'bar']}, ['-a=foo', '-a=bar']),
        # is actually the same as just
        ('-a=', {'a': ['foo', 'bar']}, ['-a=foo', '-a=bar']),
        #
        # These are all the same
        ('@a', {'a': ['foo', 'bar']}, ['foo', 'bar']),
        ('@a= +', {'a': ['foo', 'bar']}, ['foo', 'bar']),
        ('@a: +', {'a': ['foo', 'bar']}, ['foo', 'bar']),
        ('@a,+', {'a': ['foo', 'bar']}, ['foo', 'bar']),

        #
        # True value acts as a switch
        ('-a', {'a': True}, ['-a']),
        ('--a', {'a': True}, ['--a']),
        ('@a', {'a': True}, ['@a']),
        # joiner doesn't matter
        ('-a=', {'a': True}, ['-a']),
        ('--a=', {'a': True}, ['--a']),

        #
        # 0 (Zero) is not falsy
        ('-a', {'a': 0}, ['-a', '0']),
        ('--a', {'a': 0}, ['--a', '0']),
        ('@a', {'a': 0}, ['0']),

        #
        #
    ])
    def test_truthy_values(self, arg, settings, result):
        class FakeLinterArgDSL(Linter):
            defaults = {
                'selector': None,
                arg: None
            }
            cmd = 'fake_linter_1'

        linter = FakeLinterArgDSL(self.view, settings)
        cmd = ['fake_linter_1'] + result
        with expect(linter)._communicate(cmd, ...):
            linter.lint(INPUT, VIEW_UNCHANGED)

    @p.expand([
        ('-a', {'a': None}),
        ('-a', {'a': False}),
        ('-a', {'a': ''}),
        ('--a', {'a': None}),
        ('--a', {'a': False}),
        ('--a', {'a': ''}),
        ('@a', {'a': None}),
        ('@a', {'a': False}),
        ('@a', {'a': ''}),
    ])
    def test_falsy_values(self, arg, settings):
        class FakeLinterArgDSL(Linter):
            defaults = {
                'selector': None,
                arg: None
            }
            cmd = 'fake_linter_1'

        linter = FakeLinterArgDSL(self.view, settings)
        with expect(linter)._communicate(['fake_linter_1'], ...):
            linter.lint(INPUT, VIEW_UNCHANGED)


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
             expect(linter)._communicate(result, ...):
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
#

# PythonLinter
# - python setting
# - pipenv