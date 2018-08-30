# Copyright (c) 2008-2016 Szczepan Faber, Serhiy Oplakanets, Herr Kaste
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import pytest
import sys

from .test_base import TestBase
from mockito import (
    spy, spy2, verify, VerificationError, verifyZeroInteractions)

import time

class Dummy(object):
    def foo(self):
        return "foo"

    def bar(self):
        raise TypeError

    def return_args(self, *args, **kwargs):
        return (args, kwargs)

    @classmethod
    def class_method(cls, arg):
        return arg


class SpyingTest(TestBase):
    def testPreservesReturnValues(self):
        dummy = Dummy()
        spiedDummy = spy(dummy)
        self.assertEqual(dummy.foo(), spiedDummy.foo())

    def testPreservesSideEffects(self):
        dummy = spy(Dummy())
        self.assertRaises(TypeError, dummy.bar)

    def testPassesArgumentsCorrectly(self):
        dummy = spy(Dummy())
        self.assertEqual((('foo', 1), {'bar': 'baz'}),
                          dummy.return_args('foo', 1, bar='baz'))

    def testIsVerifiable(self):
        dummy = spy(Dummy())
        dummy.foo()
        verify(dummy).foo()
        self.assertRaises(VerificationError, verify(dummy).bar)

    def testVerifyZeroInteractionsWorks(self):
        dummy = spy(Dummy())
        verifyZeroInteractions(dummy)

    def testRaisesAttributeErrorIfNoSuchMethod(self):
        original = Dummy()
        dummy = spy(original)
        try:
            dummy.lol()
            self.fail("Should fail if no such method.")
        except AttributeError as e:
            self.assertEqual("You tried to call method 'lol' which '%s' "
                              "instance does not have." % original, str(e))

    def testIsInstanceFakesOriginalClass(self):
        dummy = spy(Dummy())

        assert isinstance(dummy, Dummy)

    def testHasNiceRepr(self):
        dummy = spy(Dummy())

        assert repr(dummy) == "<SpiedDummy id=%s>" % id(dummy)



    def testCallClassmethod(self):
        dummy = spy(Dummy)

        assert dummy.class_method('foo') == 'foo'
        verify(dummy).class_method('foo')


    @pytest.mark.xfail(
        sys.version_info >= (3,),
        reason="python3 allows any value for self")
    def testCantCallInstanceMethodWhenSpyingClass(self):
        dummy = spy(Dummy)
        with pytest.raises(TypeError):
            dummy.return_args('foo')


    def testModuleFunction(self):
        import time
        dummy = spy(time)

        assert dummy.time() is not None

        verify(dummy).time()


class TestSpy2:

    def testA(self):
        dummy = Dummy()
        spy2(dummy.foo)

        assert dummy.foo() == 'foo'
        verify(dummy).foo()

    def testB(self):
        spy2(Dummy.class_method)

        assert Dummy.class_method('foo') == 'foo'
        verify(Dummy).class_method('foo')

    def testModule(self):
        spy2(time.time)

        assert time.time() is not None
        verify(time).time()


