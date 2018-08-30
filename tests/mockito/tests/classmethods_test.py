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
from mockito import when, unstub, verify
from mockito.verification import VerificationError

class Dog:
    @classmethod
    def bark(cls):
        return "woof!"


class Cat:
    @classmethod
    def meow(cls, m):
        return cls.__name__ + " " + str(m)


class Lion(object):
    @classmethod
    def roar(cls):
        return "Rrrrr!"


class ClassMethodsTest(TestBase):

    def tearDown(self):
        unstub()

    def testUnstubs(self):
        when(Dog).bark().thenReturn("miau!")
        unstub()
        self.assertEqual("woof!", Dog.bark())

    # TODO decent test case please :) without testing irrelevant implementation
    # details
    def testUnstubShouldPreserveMethodType(self):
        when(Dog).bark().thenReturn("miau!")
        unstub()
        self.assertTrue(isinstance(Dog.__dict__.get("bark"), classmethod))

    def testStubs(self):
        self.assertEqual("woof!", Dog.bark())

        when(Dog).bark().thenReturn("miau!")

        self.assertEqual("miau!", Dog.bark())

    def testStubsClassesDerivedFromTheObjectClass(self):
        self.assertEqual("Rrrrr!", Lion.roar())

        when(Lion).roar().thenReturn("miau!")

        self.assertEqual("miau!", Lion.roar())

    def testVerifiesMultipleCallsOnClassmethod(self):
        when(Dog).bark().thenReturn("miau!")

        Dog.bark()
        Dog.bark()

        verify(Dog, times=2).bark()

    def testFailsVerificationOfMultipleCallsOnClassmethod(self):
        when(Dog).bark().thenReturn("miau!")

        Dog.bark()

        self.assertRaises(VerificationError, verify(Dog, times=2).bark)

    def testStubsAndVerifiesClassmethod(self):
        when(Dog).bark().thenReturn("miau!")

        self.assertEqual("miau!", Dog.bark())

        verify(Dog).bark()

    def testPreservesClassArgumentAfterUnstub(self):
        self.assertEqual("Cat foo", Cat.meow("foo"))

        when(Cat).meow("foo").thenReturn("bar")

        self.assertEqual("bar", Cat.meow("foo"))

        unstub()

        self.assertEqual("Cat foo", Cat.meow("foo"))


