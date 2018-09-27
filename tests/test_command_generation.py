from SublimeLinter.tests.parameterized import parameterized as p

import sublime
from SublimeLinter.lint import (
    Linter,
    backend,
    persist,
    linter as linter_module,
    util,
)
from unittesting import DeferrableTestCase

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


VIEW_UNCHANGED = lambda: False
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
            regex = r''

        linter = FakeLinterArgDSL(self.view, settings)
        cmd = ['fake_linter_1'] + result
        when(linter)._communicate(cmd, ...)
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
            regex = r''

        linter = FakeLinterArgDSL(self.view, settings)
        when(linter)._communicate(['fake_linter_1'], ...)
        linter.lint(INPUT, VIEW_UNCHANGED)

