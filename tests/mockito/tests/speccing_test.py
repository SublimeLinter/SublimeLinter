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

from mockito.invocation import InvocationError
from mockito import mock, when, verify


class Foo(object):
    def bar(self):
        pass

class Action(object):
    def no_arg(self):
        pass

    def run(self, arg):
        return arg

    def __call__(self, task):
        return task


class TestSpeccing:
    def testStubCallAndVerify(self):
        action = mock(Action)

        when(action).run(11).thenReturn(12)
        assert action.run(11) == 12
        verify(action).run(11)


    def testShouldScreamWhenStubbingUnknownMethod(self):
        action = mock(Action)

        with pytest.raises(InvocationError):
            when(action).unknownMethod()

    def testShouldScreamWhenCallingUnknownMethod(self):
        action = mock(Action)

        with pytest.raises(AttributeError):
            action.unknownMethod()

    def testShouldScreamWhenCallingUnexpectedMethod(self):
        action = mock(Action)

        with pytest.raises(AttributeError):
            action.run(11)

    def testPreconfigureMockWithAttributes(self):
        action = mock({'foo': 'bar'}, spec=Action)

        assert action.foo == 'bar'
        with pytest.raises(InvocationError):
            when(action).remember()

    def testPreconfigureWithFunction(self):
        action = mock({
            'run': lambda _: 12
        }, spec=Action)

        assert action.run(11) == 12

        verify(action).run(11)

    def testPreconfigureWithFunctionThatTakesNoArgs(self):
        action = mock({
            'no_arg': lambda: 12
        }, spec=Action)

        assert action.no_arg() == 12

        verify(action).no_arg()

    def testShouldScreamOnUnknownAttribute(self):
        action = mock(Action)

        with pytest.raises(AttributeError):
            action.cam

    def testShouldPassIsInstanceChecks(self):
        action = mock(Action)

        assert isinstance(action, Action)

    def testHasANiceName(self):
        action = mock(Action)

        assert repr(action) == "<DummyAction id=%s>" % id(action)


class TestSpeccingLoose:
    def testReturnNoneForEveryMethod(self):
        action = mock(Action, strict=False)
        assert action.unknownMethod() is None
        assert action.run(11) is None

