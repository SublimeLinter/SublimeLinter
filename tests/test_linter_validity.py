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

    def test_no_defaults_fails(self):
        def def_linter():
            class Fake(Linter):
                cmd = 'foo'

            return Fake

        when(linter_module.logger).error(...).thenReturn(None)
        linter = def_linter()

        self.assertTrue(linter.disabled)

    @p.expand([
        (None, ),
        (True, ),
        (False, ),
        ('foo',),
        ([], ),
        (lambda x: x,),
        ({},),
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


