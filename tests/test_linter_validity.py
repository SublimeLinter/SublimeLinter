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
    unstub,
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

    def test_having_a_should_lint_instance_method_fails(self):
        def def_linter():
            class Fake(Linter):
                cmd = 'foo'
                defaults = {'selector': ''}

                def should_lint(self, reason=None):
                    pass

            return Fake

        when(linter_module.logger).error(...).thenReturn(None)
        linter = def_linter()

        self.assertTrue(linter.disabled)
        verify(linter_module.logger).error(
            contains(
                "fake disabled. 'should_lint' now is a `@classmethod` and has a "
                "different call signature."
            )
        )

    def test_implementing_should_lint_as_a_classmethod_is_ok(self):
        def def_linter():
            class Fake(Linter):
                cmd = 'foo'
                defaults = {'selector': ''}

                @classmethod
                def should_lint(cls, view, settings, reason):
                    pass

            return Fake

        linter = def_linter()

        self.assertIsNone(linter.disabled)

    def test_implementing_get_environment_old_signature_fails(self):
        def def_linter():
            class Fake(Linter):
                cmd = 'foo'
                defaults = {'selector': ''}

                def get_environment(self, settings):
                    pass

            return Fake

        when(linter_module.logger).error(...).thenReturn(None)
        linter = def_linter()

        self.assertTrue(linter.disabled)
        verify(linter_module.logger).error(
            contains(
                "fake disabled. 'get_environment' now has a simplified signature:\n"
                "    def get_environment(self): ...\n"
            )
        )

    def test_implementing_get_environment_new_signature_is_ok(self):
        def def_linter():
            class Fake(Linter):
                cmd = 'foo'
                defaults = {'selector': ''}

                def get_environment(self):
                    pass

            return Fake

        linter = def_linter()

        self.assertIsNone(linter.disabled)

    def test_implementing_get_working_dir_old_signature_fails(self):
        def def_linter():
            class Fake(Linter):
                cmd = 'foo'
                defaults = {'selector': ''}

                def get_working_dir(self, settings):
                    pass

            return Fake

        when(linter_module.logger).error(...).thenReturn(None)
        linter = def_linter()

        self.assertTrue(linter.disabled)
        verify(linter_module.logger).error(
            contains(
                "fake disabled. 'get_working_dir' now has a simplified signature:\n"
                "    def get_working_dir(self): ...\n"
            )
        )

    def test_implementing_get_working_dir_new_signature_is_ok(self):
        def def_linter():
            class Fake(Linter):
                cmd = 'foo'
                defaults = {'selector': ''}

                def get_working_dir(self):
                    pass

            return Fake

        linter = def_linter()

        self.assertIsNone(linter.disabled)


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

        linter_class = def_linter()
        view = self.create_view(sublime.active_window())
        linter = linter_class(view, {})
        when(util).which('foo').thenReturn('foo.exe')
        when(linter)._communicate(...).thenReturn(OUTPUT)
        when(linter.logger).error(...).thenReturn(None)

        try:
            linter.lint(INPUT, lambda: False)
        except Exception:
            pass

        verify(linter.logger).error(
            contains("'self.regex' is not defined.")
        )
