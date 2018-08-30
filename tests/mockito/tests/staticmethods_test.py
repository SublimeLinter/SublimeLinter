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

from .test_base import TestBase
from mockito import when, verify, unstub, any
from mockito.verification import VerificationError

class Dog:
    @staticmethod
    def bark():
        return "woof"

    @staticmethod
    def barkHardly(*args):
        return "woof woof"


class Cat:
    @staticmethod
    def meow():
        return "miau"


class StaticMethodsTest(TestBase):

    def tearDown(self):
        unstub()

    def testUnstubs(self):
        when(Dog).bark().thenReturn("miau")
        unstub()
        self.assertEqual("woof", Dog.bark())

    # TODO decent test case please :) without testing irrelevant implementation
    # details
    def testUnstubShouldPreserveMethodType(self):
        when(Dog).bark().thenReturn("miau!")
        unstub()
        self.assertTrue(isinstance(Dog.__dict__.get("bark"), staticmethod))

    def testStubs(self):
        self.assertEqual("woof", Dog.bark())

        when(Dog).bark().thenReturn("miau")

        self.assertEqual("miau", Dog.bark())

    def testStubsConsecutiveCalls(self):
        when(Dog).bark().thenReturn(1).thenReturn(2)

        self.assertEqual(1, Dog.bark())
        self.assertEqual(2, Dog.bark())
        self.assertEqual(2, Dog.bark())

    def testStubsWithArgs(self):
        self.assertEqual("woof woof", Dog.barkHardly(1, 2))

        when(Dog).barkHardly(1, 2).thenReturn("miau")

        self.assertEqual("miau", Dog.barkHardly(1, 2))

    def testStubsButDoesNotMachArguments(self):
        self.assertEqual("woof woof", Dog.barkHardly(1, "anything"))

        when(Dog, strict=False).barkHardly(1, 2).thenReturn("miau")

        self.assertEqual(None, Dog.barkHardly(1))

    def testStubsMultipleClasses(self):
        when(Dog).barkHardly(1, 2).thenReturn(1)
        when(Dog).bark().thenReturn(2)
        when(Cat).meow().thenReturn(3)

        self.assertEqual(1, Dog.barkHardly(1, 2))
        self.assertEqual(2, Dog.bark())
        self.assertEqual(3, Cat.meow())

        unstub()

        self.assertEqual("woof", Dog.bark())
        self.assertEqual("miau", Cat.meow())

    def testVerifiesSuccesfully(self):
        when(Dog).bark().thenReturn("boo")

        Dog.bark()

        verify(Dog).bark()

    def testVerifiesWithArguments(self):
        when(Dog).barkHardly(1, 2).thenReturn("boo")

        Dog.barkHardly(1, 2)

        verify(Dog).barkHardly(1, any())

    def testFailsVerification(self):
        when(Dog).bark().thenReturn("boo")

        Dog.bark()

        self.assertRaises(VerificationError, verify(Dog).barkHardly, (1, 2))

    def testFailsOnInvalidArguments(self):
        when(Dog).bark().thenReturn("boo")

        Dog.barkHardly(1, 2)

        self.assertRaises(VerificationError, verify(Dog).barkHardly, (1, 20))

    def testFailsOnNumberOfCalls(self):
        when(Dog).bark().thenReturn("boo")

        Dog.bark()

        self.assertRaises(VerificationError, verify(Dog, times=2).bark)

    def testStubsAndVerifies(self):
        when(Dog).bark().thenReturn("boo")

        self.assertEqual("boo", Dog.bark())

        verify(Dog).bark()

    def testStubsTwiceAndUnstubs(self):
        when(Dog).bark().thenReturn(1)
        when(Dog).bark().thenReturn(2)

        self.assertEqual(2, Dog.bark())

        unstub()

        self.assertEqual("woof", Dog.bark())

    def testDoesNotVerifyStubbedCalls(self):
        when(Dog).bark().thenReturn(1)

        verify(Dog, times=0).bark()

