
import pytest

from mockito import when2, patch, spy2, verify
from mockito.utils import newmethod


import os


pytestmark = pytest.mark.usefixtures("unstub")


class Dog(object):
    def bark(self, sound):
        return sound

    def bark_hard(self, sound):
        return sound + '!'


class TestMockito2:
    def testWhen2(self):
        rex = Dog()
        when2(rex.bark, 'Miau').thenReturn('Wuff')
        when2(rex.bark, 'Miau').thenReturn('Grrr')
        assert rex.bark('Miau') == 'Grrr'


    def testPatch(self):
        rex = Dog()
        patch(rex.bark, lambda sound: sound + '!')
        assert rex.bark('Miau') == 'Miau!'


    def testPatch2(self):
        rex = Dog()
        patch(rex.bark, rex.bark_hard)
        assert rex.bark('Miau') == 'Miau!'

    def testPatch3(self):
        rex = Dog()

        def f(self, sound):
            return self.bark_hard(sound)

        f = newmethod(f, rex)
        patch(rex.bark, f)

        assert rex.bark('Miau') == 'Miau!'

    def testAddFnWithPatch(self):
        rex = Dog()

        patch(rex, 'newfn', lambda s: s)
        assert rex.newfn('Hi') == 'Hi'


class TestFancyObjResolver:
    def testWhen2WithArguments(self):
        # This test is a bit flaky bc pytest does not like a patched
        # `os.path.exists` module.
        when2(os.path.commonprefix, '/Foo').thenReturn(False)
        when2(os.path.commonprefix, '/Foo').thenReturn(True)
        when2(os.path.exists, '/Foo').thenReturn(True)

        assert os.path.commonprefix('/Foo')
        assert os.path.exists('/Foo')

    def testWhen2WithoutArguments(self):
        import time
        when2(time.time).thenReturn('None')
        assert time.time() == 'None'

    def testWhenSplitOnNextLine(self):
        # fmt: off
        when2(
            os.path.commonprefix, '/Foo').thenReturn(True)
        # fmt: on
        assert os.path.commonprefix('/Foo')

    def testEnsureWithWhen2SameLine(self):
        with when2(os.path.commonprefix, '/Foo'):
            pass

    def testEnsureWithWhen2SplitLine(self):
        # fmt: off
        with when2(
                os.path.commonprefix, '/Foo'):
            pass
        # fmt: on

    def testEnsureToResolveMethodOnClass(self):
        class A(object):
            class B(object):
                def c(self):
                    pass

        when2(A.B.c)

    def testEnsureToResolveClass(self):
        class A(object):
            class B(object):
                pass

        when2(A.B, 'Hi').thenReturn('Ho')
        assert A.B('Hi') == 'Ho'


    def testPatch(self):
        patch(os.path.commonprefix, lambda m: 'yup')
        patch(os.path.commonprefix, lambda m: 'yep')

        assert os.path.commonprefix(Ellipsis) == 'yep'

    def testWithPatchGivenTwoArgs(self):
        with patch(os.path.exists, lambda m: 'yup'):
            assert os.path.exists('foo') == 'yup'

        assert not os.path.exists('foo')

    def testWithPatchGivenThreeArgs(self):
        with patch(os.path, 'exists', lambda m: 'yup'):
            assert os.path.exists('foo') == 'yup'

        assert not os.path.exists('foo')

    def testSpy2(self):
        spy2(os.path.exists)

        assert os.path.exists('/Foo') is False

        verify(os.path).exists('/Foo')

    class TestRejections:
        def testA(self):
            with pytest.raises(TypeError) as exc:
                when2(os)
            assert str(exc.value) == "can't guess origin of 'os'"

            cp = os.path.commonprefix
            with pytest.raises(TypeError) as exc:
                spy2(cp)
            assert str(exc.value) == "can't guess origin of 'cp'"

            ptch = patch
            with pytest.raises(TypeError) as exc:
                ptch(os.path.exists, lambda: 'boo')
            assert str(exc.value) == "could not destructure first argument"
