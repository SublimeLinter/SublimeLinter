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

from .test_base import TestBase
from mockito import (
    mock, when, verify, forget_invocations, inorder, VerificationError,
    ArgumentError, verifyNoMoreInteractions, verifyZeroInteractions,
    verifyNoUnwantedInteractions, verifyStubbedInvocationsAreUsed,
    any)
from mockito.verification import never


class VerificationTestBase(TestBase):
    def __init__(self, verification_function, *args, **kwargs):
        self.verification_function = verification_function
        TestBase.__init__(self, *args, **kwargs)

    def setUp(self):
        self.mock = mock()

    def testVerifies(self):
        self.mock.foo()
        self.mock.someOtherMethod(1, "foo", "bar")

        self.verification_function(self.mock).foo()
        self.verification_function(self.mock).someOtherMethod(1, "foo", "bar")

    def testVerifiesWhenMethodIsUsingKeywordArguments(self):
        self.mock.foo()
        self.mock.someOtherMethod(1, fooarg="foo", bararg="bar")

        self.verification_function(self.mock).foo()
        self.verification_function(self.mock).someOtherMethod(1, bararg="bar",
                                                              fooarg="foo")

    def testVerifiesDetectsNamedArguments(self):
        self.mock.foo(fooarg="foo", bararg="bar")

        self.verification_function(self.mock).foo(bararg="bar", fooarg="foo")
        try:
            self.verification_function(self.mock).foo(bararg="foo",
                                                      fooarg="bar")
            self.fail()
        except VerificationError:
            pass

    def testKeywordArgumentsOrderIsUnimportant(self):
        self.mock.blub(
            line="blabla", runs="55", failures="1", errors="2")
        self.verification_function(self.mock).blub(
            runs="55", failures="1", errors="2", line="blabla")

    def testFailsVerification(self):
        self.mock.foo("boo")

        self.assertRaises(VerificationError,
                          self.verification_function(self.mock).foo, "not boo")

    def testVerifiesAnyTimes(self):
        self.mock = mock()
        self.mock.foo()

        self.verification_function(self.mock).foo()
        self.verification_function(self.mock).foo()
        self.verification_function(self.mock).foo()

    def testVerifiesMultipleCalls(self):
        self.mock = mock()
        self.mock.foo()
        self.mock.foo()
        self.mock.foo()

        self.verification_function(self.mock, times=3).foo()

    def testVerifiesMultipleCallsWhenMethodUsedAsFunction(self):
        self.mock = mock()
        f = self.mock.foo
        f(1, 2)
        f('foobar')

        self.verification_function(self.mock).foo(1, 2)
        self.verification_function(self.mock).foo('foobar')

    def testFailsVerificationOfMultipleCalls(self):
        self.mock = mock()
        self.mock.foo()
        self.mock.foo()
        self.mock.foo()

        self.assertRaises(VerificationError,
                          self.verification_function(self.mock, times=2).foo)

    def testVerifiesUsingAnyMatcher(self):
        self.mock.foo(1, "bar")

        self.verification_function(self.mock).foo(1, any())
        self.verification_function(self.mock).foo(any(), "bar")
        self.verification_function(self.mock).foo(any(), any())

    def testVerifiesUsingAnyIntMatcher(self):
        self.mock.foo(1, "bar")

        self.verification_function(self.mock).foo(any(int), "bar")

    def testFailsVerificationUsingAnyIntMatcher(self):
        self.mock.foo(1, "bar")

        self.assertRaises(VerificationError,
                          self.verification_function(self.mock).foo, 1,
                          any(int))
        self.assertRaises(VerificationError,
                          self.verification_function(self.mock).foo, any(int))

    def testNumberOfTimesDefinedDirectlyInVerify(self):
        self.mock.foo("bar")

        self.verification_function(self.mock, times=1).foo("bar")

    def testFailsWhenTimesIsLessThanZero(self):
        self.assertRaises(ArgumentError, self.verification_function, None, -1)

    def testVerifiesAtLeastTwoWhenMethodInvokedTwice(self):
        self.mock.foo()
        self.mock.foo()

        self.verification_function(self.mock, atleast=2).foo()

    def testVerifiesAtLeastTwoWhenMethodInvokedFourTimes(self):
        self.mock.foo()
        self.mock.foo()
        self.mock.foo()
        self.mock.foo()

        self.verification_function(self.mock, atleast=2).foo()

    def testFailsWhenMethodInvokedOnceForAtLeastTwoVerification(self):
        self.mock.foo()
        self.assertRaises(VerificationError,
                          self.verification_function(self.mock, atleast=2).foo)

    def testVerifiesAtMostTwoWhenMethodInvokedTwice(self):
        self.mock.foo()
        self.mock.foo()

        self.verification_function(self.mock, atmost=2).foo()

    def testVerifiesAtMostTwoWhenMethodInvokedOnce(self):
        self.mock.foo()

        self.verification_function(self.mock, atmost=2).foo()

    def testFailsWhenMethodInvokedFourTimesForAtMostTwoVerification(self):
        self.mock.foo()
        self.mock.foo()
        self.mock.foo()
        self.mock.foo()

        self.assertRaises(VerificationError,
                          self.verification_function(self.mock, atmost=2).foo)

    def testVerifiesBetween(self):
        self.mock.foo()
        self.mock.foo()

        self.verification_function(self.mock, between=[1, 2]).foo()
        self.verification_function(self.mock, between=[2, 3]).foo()
        self.verification_function(self.mock, between=[1, 5]).foo()
        self.verification_function(self.mock, between=[2, 2]).foo()

    def testFailsVerificationWithBetween(self):
        self.mock.foo()
        self.mock.foo()
        self.mock.foo()

        self.assertRaises(VerificationError,
                          self.verification_function(self.mock,
                                                     between=[1, 2]).foo)
        self.assertRaises(VerificationError,
                          self.verification_function(self.mock,
                                                     between=[4, 9]).foo)

    def testFailsAtMostAtLeastAndBetweenVerificationWithWrongArguments(self):
        self.assertRaises(ArgumentError, self.verification_function,
                          self.mock, atleast=0)
        self.assertRaises(ArgumentError, self.verification_function,
                          self.mock, atleast=-5)
        self.assertRaises(ArgumentError, self.verification_function,
                          self.mock, atmost=0)
        self.assertRaises(ArgumentError, self.verification_function,
                          self.mock, atmost=-5)
        self.assertRaises(ArgumentError, self.verification_function,
                          self.mock, between=[5, 1])
        self.assertRaises(ArgumentError, self.verification_function,
                          self.mock, between=[-1, 1])
        self.assertRaises(ArgumentError, self.verification_function,
                          self.mock, atleast=5, atmost=5)
        self.assertRaises(ArgumentError, self.verification_function,
                          self.mock, atleast=5, between=[1, 2])
        self.assertRaises(ArgumentError, self.verification_function,
                          self.mock, atmost=5, between=[1, 2])
        self.assertRaises(ArgumentError, self.verification_function,
                          self.mock, atleast=5, atmost=5, between=[1, 2])

    def runTest(self):
        pass


class VerifyTest(VerificationTestBase):
    def __init__(self, *args, **kwargs):
        VerificationTestBase.__init__(self, verify, *args, **kwargs)

    def testVerifyNeverCalled(self):
        verify(self.mock, never).someMethod()

    def testVerifyNeverCalledRaisesError(self):
        self.mock.foo()
        self.assertRaises(VerificationError, verify(self.mock, never).foo)


class InorderVerifyTest(VerificationTestBase):
    def __init__(self, *args, **kwargs):
        VerificationTestBase.__init__(self, inorder.verify, *args, **kwargs)

    def setUp(self):
        self.mock = mock()

    def testPassesIfOneIteraction(self):
        self.mock.first()
        inorder.verify(self.mock).first()

    def testPassesIfMultipleInteractions(self):
        self.mock.first()
        self.mock.second()
        self.mock.third()

        inorder.verify(self.mock).first()
        inorder.verify(self.mock).second()
        inorder.verify(self.mock).third()

    def testFailsIfNoInteractions(self):
        self.assertRaises(VerificationError, inorder.verify(self.mock).first)

    def testFailsIfWrongOrderOfInteractions(self):
        self.mock.first()
        self.mock.second()

        self.assertRaises(VerificationError, inorder.verify(self.mock).second)

    def testErrorMessage(self):
        self.mock.second()
        self.mock.first()
        self.assertRaisesMessage(
            '\nWanted first() to be invoked,\ngot    second() instead.',
            inorder.verify(self.mock).first)


    def testPassesMixedVerifications(self):
        self.mock.first()
        self.mock.second()

        verify(self.mock).first()
        verify(self.mock).second()

        inorder.verify(self.mock).first()
        inorder.verify(self.mock).second()

    def testFailsMixedVerifications(self):
        self.mock.second()
        self.mock.first()

        # first - normal verifications, they should pass
        verify(self.mock).first()
        verify(self.mock).second()

        # but, inorder verification should fail
        self.assertRaises(VerificationError, inorder.verify(self.mock).first)


class VerifyNoMoreInteractionsTest(TestBase):
    def testVerifies(self):
        mockOne, mockTwo = mock(), mock()
        mockOne.foo()
        mockTwo.bar()

        verify(mockOne).foo()
        verify(mockTwo).bar()
        verifyNoMoreInteractions(mockOne, mockTwo)

    def testFails(self):
        theMock = mock()
        theMock.foo()
        self.assertRaises(VerificationError, verifyNoMoreInteractions, theMock)


class VerifyZeroInteractionsTest(TestBase):
    def testVerifies(self):
        theMock = mock()
        verifyZeroInteractions(theMock)
        theMock.foo()
        self.assertRaises(
            VerificationError, verifyNoMoreInteractions, theMock)


class ClearInvocationsTest(TestBase):
    def testClearsInvocations(self):
        theMock1 = mock()
        theMock2 = mock()
        theMock1.do_foo()
        theMock2.do_bar()

        self.assertRaises(VerificationError, verifyZeroInteractions, theMock1)
        self.assertRaises(VerificationError, verifyZeroInteractions, theMock2)

        forget_invocations(theMock1, theMock2)

        verifyZeroInteractions(theMock1)
        verifyZeroInteractions(theMock2)

    def testPreservesStubs(self):
        theMock = mock()
        when(theMock).do_foo().thenReturn('hello')
        self.assertEqual('hello', theMock.do_foo())

        forget_invocations(theMock)

        self.assertEqual('hello', theMock.do_foo())


class TestRaiseOnUnknownObjects:
    @pytest.mark.parametrize('verification_fn', [
        verify,
        verifyNoMoreInteractions,
        verifyZeroInteractions,
        verifyNoUnwantedInteractions,
        verifyStubbedInvocationsAreUsed
    ])
    def testVerifyShouldRaise(self, verification_fn):
        class Foo(object):
            pass

        with pytest.raises(ArgumentError) as exc:
            verification_fn(Foo)
        assert str(exc.value) == "obj '%s' is not registered" % Foo


