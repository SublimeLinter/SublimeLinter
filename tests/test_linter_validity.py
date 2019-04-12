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
    verify,
    contains,
    verifyNoUnwantedInteractions,
    expect,
    unstub,
    mock
)


class TestLinterValidity(DeferrableTestCase):
    def setUp(self):
        when(linter_module).register_linter(...).thenReturn(None)

    def tearDown(self):
        unstub()

    @p.expand([
        ('syntax',),
        ('selectors',)
    ])
    def test_defining_x_errs(self, KEY):
        def def_linter():
            class Fake(Linter):
                locals()[KEY] = 'foo'

            return Fake


        when(linter_module.logger).error(...).thenReturn(None)
        linter = def_linter()

        self.assertTrue(linter.disabled)
        verify(linter_module.logger).error(
            contains("Defining 'cls.{}' has no effect anymore.".format(KEY))
        )

    def test_no_cmd_fails(self):
        def def_linter():
            class Fake(Linter):
                ...

            return Fake

        when(linter_module.logger).error(...).thenReturn(None)
        linter = def_linter()

        self.assertTrue(linter.disabled)
        verify(linter_module.logger).error(
            contains("'cmd' must be specified.")
        )

    def test_no_defaults_fails(self):
        def def_linter():
            class Fake(Linter):
                cmd = 'foo'

            return Fake

        when(linter_module.logger).error(...).thenReturn(None)
        linter = def_linter()

        self.assertTrue(linter.disabled)
        verify(linter_module.logger).error(
            contains("'cls.defaults' is mandatory")
        )

    @p.expand([
        (None, ),
        (True, ),
        (False, ),
        ('foo',),
        ([], ),
        (lambda x: x,),
    ])
    def test_wrong_defaults_fails(self, VAL):
        def def_linter():
            class Fake(Linter):
                cmd = 'foo'
                defaults = VAL

            return Fake

        when(linter_module.logger).error(...).thenReturn(None)
        linter = def_linter()

        self.assertTrue(linter.disabled)
        verify(linter_module.logger).error(
            contains("'cls.defaults' is mandatory and MUST be a dict.")
        )

    def test_selector_is_mandatory(self):
        def def_linter():
            class Fake(Linter):
                cmd = 'foo'
                defaults = {}

            return Fake

        when(linter_module.logger).error(...).thenReturn(None)
        linter = def_linter()

        self.assertTrue(linter.disabled)
        verify(linter_module.logger).error(
            contains("'selector' is mandatory")
        )

class TestRegexCompiling(DeferrableTestCase):
    def setUp(self):
        when(linter_module).register_linter(...).thenReturn(None)

    def tearDown(self):
        unstub()

    def create_view(self, window):
        view = window.new_file()
        self.addCleanup(self.close_view, view)
        return view

    def close_view(self, view):
        view.set_scratch(True)
        view.close()

    def test_not_multiline_by_default(self):
        def def_linter():
            class Fake(Linter):
                cmd = 'foo'
                defaults = {'selector': ''}
                regex = r'bar'

            return Fake

        import re
        linter = def_linter()
        self.assertTrue(linter.regex.flags == re.U)
        self.assertFalse(linter.multiline)

    def test_set_multiline_automatically(self):
        def def_linter():
            class Fake(Linter):
                cmd = 'foo'
                defaults = {'selector': ''}
                regex = r'(?m)bar'

            return Fake

        import re
        linter = def_linter()

        self.assertTrue(linter.regex.flags & re.M == re.M)
        self.assertTrue(linter.multiline)

    def test_set_multiline_manually(self):
        def def_linter():
            class Fake(Linter):
                cmd = 'foo'
                defaults = {'selector': ''}
                regex = r'bar'
                multiline = True

            return Fake

        import re
        linter = def_linter()

        self.assertTrue(linter.regex.flags & re.M == re.M)
        self.assertTrue(linter.multiline)

    def test_invalid_regex_disables(self):
        def def_linter():
            class Fake(Linter):
                cmd = 'foo'
                defaults = {'selector': ''}
                regex = r'ba(r'

            return Fake

        when(linter_module.logger).error(...).thenReturn(None)
        linter = def_linter()

        self.assertTrue(linter.disabled)
        verify(linter_module.logger).error(
            contains("error compiling regex: unbalanced parenthesis.")
        )

    def test_valid_and_registered_without_defining_regex(self):
        def def_linter():
            class Fake(Linter):
                cmd = 'foo'
                defaults = {'selector': ''}

            return Fake

        when(linter_module).register_linter('fake', ...).thenReturn(None)
        linter = def_linter()

        self.assertFalse(linter.disabled)
        verify(linter_module).register_linter('fake', linter)

    def test_show_nice_error_message_for_missing_regex(self):
        def def_linter():
            class Fake(Linter):
                cmd = 'foo'
                defaults = {'selector': ''}

            return Fake

        INPUT = """\
        foo = bar
        """
        OUTPUT = """\
        errrrors
        """
        when(linter_module.logger).error(...).thenReturn(None)

        linter_class = def_linter()
        view = self.create_view(sublime.active_window())
        linter = linter_class(view, {})
        when(util).which('foo').thenReturn('foo.exe')
        when(linter)._communicate(...).thenReturn(OUTPUT)

        try:
            linter.lint(INPUT, lambda: False)
        except Exception:
            pass

        verify(linter_module.logger).error(
            contains("'self.regex' is not defined.")
        )
