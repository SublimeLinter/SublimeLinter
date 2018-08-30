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
from mockito import mock, when, verify, times, any


class TestEmptyMocks:
    def testAllMethodsReturnNone(self):
        dummy = mock()

        assert dummy.foo() is None
        assert dummy.foo(1, 2) is None


    def testConfigureDummy(self):
        dummy = mock({'foo': 'bar'})
        assert dummy.foo == 'bar'

    def testConfigureDummyWithFunction(self):
        dummy = mock({
            'getStuff': lambda s: s + ' thing'
        })

        assert dummy.getStuff('da') == 'da thing'
        verify(dummy).getStuff('da')

    def testDummiesAreCallable(self):
        dummy = mock()
        assert dummy() is None
        assert dummy(1, 2) is None

    def testCallsAreVerifiable(self):
        dummy = mock()
        dummy(1, 2)

        verify(dummy).__call__(1, 2)

    def testConfigureCallBehavior(self):
        dummy = mock()
        when(dummy).__call__(1).thenReturn(2)

        assert dummy(1) == 2
        verify(dummy).__call__(1)

    def testCheckIsInstanceAgainstItself(self):
        dummy = mock()
        assert isinstance(dummy, dummy.__class__)


    def testConfigureMagicMethod(self):
        dummy = mock()
        when(dummy).__getitem__(1).thenReturn(2)

        assert dummy[1] == 2

class TestStrictEmptyMocks:
    def testScream(self):
        dummy = mock(strict=True)

        with pytest.raises(AttributeError):
            dummy.foo()

    def testAllowStubbing(self):
        dummy = mock(strict=True)
        when(dummy).foo()
        dummy.foo()
        verify(dummy).foo()

    def testCanConfigureCall(self):
        dummy = mock(strict=True)
        when(dummy).__call__(1).thenReturn(2)

        assert dummy(1) == 2

    def testScreamOnUnconfiguredCall(self):
        dummy = mock(strict=True)

        with pytest.raises(AttributeError):
            dummy(1)

    def testConfigureMagicMethod(self):
        dummy = mock(strict=True)
        when(dummy).__getitem__(1).thenReturn(2)

        assert dummy[1] == 2


class StubbingTest(TestBase):
    def testStubsWithReturnValue(self):
        theMock = mock()
        when(theMock).getStuff().thenReturn("foo")
        when(theMock).getMoreStuff(1, 2).thenReturn(10)

        self.assertEqual("foo", theMock.getStuff())
        self.assertEqual(10, theMock.getMoreStuff(1, 2))
        self.assertEqual(None, theMock.getMoreStuff(1, 3))

    def testStubsWhenNoArgsGiven(self):
        theMock = mock()
        when(theMock).getStuff().thenReturn("foo")
        when(theMock).getWidget().thenReturn("bar")

        self.assertEqual("foo", theMock.getStuff())
        self.assertEqual("bar", theMock.getWidget())

    def testStubsConsecutivelyWhenNoArgsGiven(self):
        theMock = mock()
        when(theMock).getStuff().thenReturn("foo").thenReturn("bar")
        when(theMock).getWidget().thenReturn("baz").thenReturn("baz2")

        self.assertEqual("foo", theMock.getStuff())
        self.assertEqual("bar", theMock.getStuff())
        self.assertEqual("bar", theMock.getStuff())
        self.assertEqual("baz", theMock.getWidget())
        self.assertEqual("baz2", theMock.getWidget())
        self.assertEqual("baz2", theMock.getWidget())

    def testStubsWithException(self):
        theMock = mock()
        when(theMock).someMethod().thenRaise(Exception("foo"))

        self.assertRaisesMessage("foo", theMock.someMethod)

    def testStubsAndVerifies(self):
        theMock = mock()
        when(theMock).foo().thenReturn("foo")

        self.assertEqual("foo", theMock.foo())
        verify(theMock).foo()

    def testStubsVerifiesAndStubsAgain(self):
        theMock = mock()

        when(theMock).foo().thenReturn("foo")
        self.assertEqual("foo", theMock.foo())
        verify(theMock).foo()

        when(theMock).foo().thenReturn("next foo")
        self.assertEqual("next foo", theMock.foo())
        verify(theMock, times(2)).foo()

    def testOverridesStubbing(self):
        theMock = mock()

        when(theMock).foo().thenReturn("foo")
        when(theMock).foo().thenReturn("bar")

        self.assertEqual("bar", theMock.foo())

    def testStubsAndInvokesTwiceAndVerifies(self):
        theMock = mock()

        when(theMock).foo().thenReturn("foo")

        self.assertEqual("foo", theMock.foo())
        self.assertEqual("foo", theMock.foo())

        verify(theMock, times(2)).foo()

    def testStubsAndReturnValuesForSameMethodWithDifferentArguments(self):
        theMock = mock()
        when(theMock).getStuff(1).thenReturn("foo")
        when(theMock).getStuff(1, 2).thenReturn("bar")

        self.assertEqual("foo", theMock.getStuff(1))
        self.assertEqual("bar", theMock.getStuff(1, 2))

    def testStubsAndReturnValuesForSameMethodWithDifferentNamedArguments(self):
        repo = mock()
        when(repo).findby(id=6).thenReturn("John May")
        when(repo).findby(name="John").thenReturn(["John May", "John Smith"])

        self.assertEqual("John May", repo.findby(id=6))
        self.assertEqual(["John May", "John Smith"], repo.findby(name="John"))

    def testStubsForMethodWithSameNameAndNamedArgumentsInArbitraryOrder(self):
        theMock = mock()

        when(theMock).foo(first=1, second=2, third=3).thenReturn(True)

        self.assertEqual(True, theMock.foo(third=3, first=1, second=2))

    def testStubsMethodWithSameNameAndMixedArguments(self):
        repo = mock()
        when(repo).findby(1).thenReturn("John May")
        when(repo).findby(1, active_only=True).thenReturn(None)
        when(repo).findby(name="Sarah").thenReturn(["Sarah Connor"])
        when(repo).findby(name="Sarah", active_only=True).thenReturn([])

        self.assertEqual("John May", repo.findby(1))
        self.assertEqual(None, repo.findby(1, active_only=True))
        self.assertEqual(["Sarah Connor"], repo.findby(name="Sarah"))
        self.assertEqual([], repo.findby(name="Sarah", active_only=True))

    def testStubsWithChainedReturnValues(self):
        theMock = mock()
        when(theMock).getStuff().thenReturn("foo") \
                                .thenReturn("bar") \
                                .thenReturn("foobar")

        self.assertEqual("foo", theMock.getStuff())
        self.assertEqual("bar", theMock.getStuff())
        self.assertEqual("foobar", theMock.getStuff())

    def testStubsWithChainedReturnValuesAndException(self):
        theMock = mock()
        when(theMock).getStuff().thenReturn("foo") \
                                .thenReturn("bar") \
                                .thenRaise(Exception("foobar"))

        self.assertEqual("foo", theMock.getStuff())
        self.assertEqual("bar", theMock.getStuff())
        self.assertRaisesMessage("foobar", theMock.getStuff)

    def testStubsWithChainedExceptionAndReturnValue(self):
        theMock = mock()
        when(theMock).getStuff().thenRaise(Exception("foo")) \
                                .thenReturn("bar")

        self.assertRaisesMessage("foo", theMock.getStuff)
        self.assertEqual("bar", theMock.getStuff())

    def testStubsWithChainedExceptions(self):
        theMock = mock()
        when(theMock).getStuff().thenRaise(Exception("foo")) \
                                .thenRaise(Exception("bar"))

        self.assertRaisesMessage("foo", theMock.getStuff)
        self.assertRaisesMessage("bar", theMock.getStuff)

    def testStubsWithReturnValueBeingException(self):
        theMock = mock()
        exception = Exception("foo")
        when(theMock).getStuff().thenReturn(exception)

        self.assertEqual(exception, theMock.getStuff())

    def testLastStubbingWins(self):
        theMock = mock()
        when(theMock).foo().thenReturn(1)
        when(theMock).foo().thenReturn(2)

        self.assertEqual(2, theMock.foo())

    def testStubbingOverrides(self):
        theMock = mock()
        when(theMock).foo().thenReturn(1)
        when(theMock).foo().thenReturn(2).thenReturn(3)

        self.assertEqual(2, theMock.foo())
        self.assertEqual(3, theMock.foo())
        self.assertEqual(3, theMock.foo())

    def testStubsWithMatchers(self):
        theMock = mock()
        when(theMock).foo(any()).thenReturn(1)

        self.assertEqual(1, theMock.foo(1))
        self.assertEqual(1, theMock.foo(100))

    def testStubbingOverrides2(self):
        theMock = mock()
        when(theMock).foo(any()).thenReturn(1)
        when(theMock).foo("oh").thenReturn(2)

        self.assertEqual(2, theMock.foo("oh"))
        self.assertEqual(1, theMock.foo("xxx"))

    def testDoesNotVerifyStubbedCalls(self):
        theMock = mock()
        when(theMock).foo().thenReturn(1)

        verify(theMock, times=0).foo()

    def testStubsWithMultipleReturnValues(self):
        theMock = mock()
        when(theMock).getStuff().thenReturn("foo", "bar", "foobar")

        self.assertEqual("foo", theMock.getStuff())
        self.assertEqual("bar", theMock.getStuff())
        self.assertEqual("foobar", theMock.getStuff())

    def testStubsWithChainedMultipleReturnValues(self):
        theMock = mock()
        when(theMock).getStuff().thenReturn("foo", "bar") \
                                .thenReturn("foobar")

        self.assertEqual("foo", theMock.getStuff())
        self.assertEqual("bar", theMock.getStuff())
        self.assertEqual("foobar", theMock.getStuff())

    def testStubsWithMultipleExceptions(self):
        theMock = mock()
        when(theMock).getStuff().thenRaise(Exception("foo"), Exception("bar"))

        self.assertRaisesMessage("foo", theMock.getStuff)
        self.assertRaisesMessage("bar", theMock.getStuff)

    def testStubsWithMultipleChainedExceptions(self):
        theMock = mock()
        when(theMock).getStuff() \
                     .thenRaise(Exception("foo"), Exception("bar")) \
                     .thenRaise(Exception("foobar"))

        self.assertRaisesMessage("foo", theMock.getStuff)
        self.assertRaisesMessage("bar", theMock.getStuff)
        self.assertRaisesMessage("foobar", theMock.getStuff)

    def testLeavesOriginalMethodUntouchedWhenCreatingStubFromRealClass(self):
        class Person:
            def get_name(self):
                return "original name"

        # given
        person = Person()
        mockPerson = mock(Person)

        # when
        when(mockPerson).get_name().thenReturn("stubbed name")

        # then
        self.assertEqual("stubbed name", mockPerson.get_name())
        self.assertEqual("original name", person.get_name(),
                          'Original method should not be replaced.')

    def testStubsWithThenAnswer(self):
        m = mock()

        when(m).magic_number().thenAnswer(lambda: 5)

        self.assertEqual(m.magic_number(), 5)

        when(m).add_one(any()).thenAnswer(lambda number: number + 1)

        self.assertEqual(m.add_one(5), 6)
        self.assertEqual(m.add_one(8), 9)

        when(m).do_times(any(), any()).thenAnswer(lambda one, two: one * two)

        self.assertEqual(m.do_times(5, 4), 20)
        self.assertEqual(m.do_times(8, 5), 40)

        when(m).do_dev_magic(any(), any()).thenAnswer(lambda a, b: a / b)

        self.assertEqual(m.do_dev_magic(20, 4), 5)
        self.assertEqual(m.do_dev_magic(40, 5), 8)

        def test_key_words(testing="Magic"):
            return testing + " Stuff"

        when(m).with_key_words().thenAnswer(test_key_words)
        self.assertEqual(m.with_key_words(), "Magic Stuff")

        when(m).with_key_words(testing=any()).thenAnswer(test_key_words)
        self.assertEqual(m.with_key_words(testing="Very Funky"),
                          "Very Funky Stuff")

    def testSubsWithThenAnswerAndMixedArgs(self):
        repo = mock()

        def method_one(value, active_only=False):
            return None

        def method_two(name=None, active_only=False):
            return ["%s Connor" % name]

        def method_three(name=None, active_only=False):
            return [name, active_only, 0]

        when(repo).findby(1).thenAnswer(lambda x: "John May (%d)" % x)
        when(repo).findby(1, active_only=True).thenAnswer(method_one)
        when(repo).findby(name="Sarah").thenAnswer(method_two)
        when(repo).findby(
            name="Sarah", active_only=True).thenAnswer(method_three)

        self.assertEqual("John May (1)", repo.findby(1))
        self.assertEqual(None, repo.findby(1, active_only=True))
        self.assertEqual(["Sarah Connor"], repo.findby(name="Sarah"))
        self.assertEqual(
            ["Sarah", True, 0], repo.findby(name="Sarah", active_only=True))

