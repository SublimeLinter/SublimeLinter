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

import os

from .test_base import TestBase
from mockito import when, unstub, verify, any
from mockito.invocation import InvocationError
from mockito.verification import VerificationError


class ModuleFunctionsTest(TestBase):
    def tearDown(self):
        unstub()

    def testUnstubs(self):
        when(os.path).exists("test").thenReturn(True)
        unstub()
        self.assertEqual(False, os.path.exists("test"))

    def testStubs(self):
        when(os.path).exists("test").thenReturn(True)

        self.assertEqual(True, os.path.exists("test"))

    def testStubsConsecutiveCalls(self):
        when(os.path).exists("test").thenReturn(False).thenReturn(True)

        self.assertEqual(False, os.path.exists("test"))
        self.assertEqual(True, os.path.exists("test"))

    def testStubsMultipleClasses(self):
        when(os.path).exists("test").thenReturn(True)
        when(os.path).dirname(any(str)).thenReturn("mocked")

        self.assertEqual(True, os.path.exists("test"))
        self.assertEqual("mocked", os.path.dirname("whoah!"))

    def testVerifiesSuccesfully(self):
        when(os.path).exists("test").thenReturn(True)

        os.path.exists("test")

        verify(os.path).exists("test")

    def testFailsVerification(self):
        when(os.path).exists("test").thenReturn(True)

        self.assertRaises(VerificationError, verify(os.path).exists, "test")

    def testFailsOnNumberOfCalls(self):
        when(os.path).exists("test").thenReturn(True)

        os.path.exists("test")

        self.assertRaises(VerificationError, verify(os.path, times=2).exists,
                          "test")

    def testStubsTwiceAndUnstubs(self):
        when(os.path).exists("test").thenReturn(False)
        when(os.path).exists("test").thenReturn(True)

        self.assertEqual(True, os.path.exists("test"))

        unstub()

        self.assertEqual(False, os.path.exists("test"))

    def testStubsTwiceWithDifferentArguments(self):
        when(os.path).exists("Foo").thenReturn(False)
        when(os.path).exists("Bar").thenReturn(True)

        self.assertEqual(False, os.path.exists("Foo"))
        self.assertEqual(True, os.path.exists("Bar"))

    def testShouldThrowIfWeStubAFunctionNotDefinedInTheModule(self):
        self.assertRaises(InvocationError,
                          lambda: when(os).walk_the_line().thenReturn(None))

    def testEnsureWeCanMockTheClassOnAModule(self):
        from . import module
        when(module).Foo().thenReturn('mocked')
        assert module.Foo() == 'mocked'
