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

from mockito import (mock, when, verify, VerificationError,
                     verifyNoMoreInteractions, verification)
from mockito.verification import never


class TestVerificationErrors:

    def testPrintsNicely(self):
        theMock = mock()
        with pytest.raises(VerificationError) as exc:
            verify(theMock).foo()
        assert str(exc.value) == '\nWanted but not invoked:  foo()' \
                                 '\nInstead got:             []'

    def testPrintsNicelyUnexpectedResultWithOneParameter(self):
        theMock = mock()
        theMock.foo("bar")
        with pytest.raises(VerificationError) as exc:
            verify(theMock).foo()
        assert str(exc.value) == '\nWanted but not invoked:  foo()' \
                                 '\nInstead got:             [foo(\'bar\')]'

    def testPrintsNicelyUnexpectedResultWithTwoParameters(self):
        theMock = mock()
        theMock.foo("bar", 1)
        with pytest.raises(VerificationError) as exc:
            verify(theMock).foo()
        assert str(exc.value) == \
            '\nWanted but not invoked:  foo()' \
            '\nInstead got:             [foo(\'bar\', 1)]'

    def testPrintsNicelyUnexpectedResultWithNamedParameter(self):
        theMock = mock()
        theMock.foo("bar", baz=1)
        with pytest.raises(VerificationError) as exc:
            verify(theMock).foo()
        assert str(exc.value) == \
            '\nWanted but not invoked:  foo()' \
            '\nInstead got:             [foo(\'bar\', baz=1)]'

    def testPrintsNicelyOneArgument(self):
        theMock = mock()
        with pytest.raises(VerificationError) as exc:
            verify(theMock).foo("bar")
        assert str(exc.value) == \
            '\nWanted but not invoked:  foo(\'bar\')' \
            '\nInstead got:             []'

    def testPrintsNicelyArguments(self):
        theMock = mock()
        with pytest.raises(VerificationError) as exc:
            verify(theMock).foo(1, 2)
        assert str(exc.value) == \
            '\nWanted but not invoked:  foo(1, 2)' \
            '\nInstead got:             []'

    def testPrintsNicelyStringArguments(self):
        theMock = mock()
        with pytest.raises(VerificationError) as exc:
            verify(theMock).foo(1, 'foo')
        assert str(exc.value) == \
            '\nWanted but not invoked:  foo(1, \'foo\')' \
            '\nInstead got:             []'

    def testPrintKeywordArgumentsNicely(self):
        theMock = mock()
        with pytest.raises(VerificationError) as exc:
            verify(theMock).foo(foo='foo', one=1)
        message = str(exc.value)
        # We do not want to guarantee any order of arguments here
        assert "foo='foo'" in message
        assert "one=1" in message

    def testPrintsOutThatTheActualAndExpectedInvocationCountDiffers(self):
        theMock = mock()
        when(theMock).foo().thenReturn(0)

        theMock.foo()
        theMock.foo()

        with pytest.raises(VerificationError) as exc:
            verify(theMock).foo()
        assert "\nWanted times: 1, actual times: 2" == str(exc.value)

    def testPrintsUnwantedInteraction(self):
        theMock = mock()
        theMock.foo(1, 'foo')
        with pytest.raises(VerificationError) as exc:
            verifyNoMoreInteractions(theMock)
        assert "\nUnwanted interaction: foo(1, 'foo')" == str(exc.value)

    def testPrintsNeverWantedInteractionsNicely(self):
        theMock = mock()
        theMock.foo()
        with pytest.raises(VerificationError) as exc:
            verify(theMock, never).foo()
        assert "\nUnwanted invocation of foo(), times: 1" == str(exc.value)


class TestReprOfVerificationClasses:
    def testTimes(self):
        times = verification.Times(1)
        assert repr(times) == "<Times wanted=1>"

    def testAtLeast(self):
        atleast = verification.AtLeast(2)
        assert repr(atleast) == "<AtLeast wanted=2>"

    def testAtMost(self):
        atmost = verification.AtMost(3)
        assert repr(atmost) == "<AtMost wanted=3>"

    def testBetween(self):
        between = verification.Between(1, 2)
        assert repr(between) == "<Between [1, 2]>"
