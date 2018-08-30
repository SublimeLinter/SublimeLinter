
import pytest

from mockito import when, when2, expect, verify, patch, mock, spy2
from mockito.invocation import InvocationError

class Dog(object):
    def bark(self):
        pass


class Unhashable(object):
    def update(self, **kwargs):
        pass

    def __hash__(self):
        raise TypeError("I'm immutable")


@pytest.mark.usefixtures('unstub')
class TestUserExposedInterfaces:

    def testWhen(self):
        whening = when(Dog)
        assert whening.__dict__ == {}

    def testExpect(self):
        expecting = expect(Dog)
        assert expecting.__dict__ == {}

    def testVerify(self):
        dummy = mock()
        verifying = verify(dummy)
        assert verifying.__dict__ == {}


    def testEnsureUnhashableObjectCanBeMocked(self):
        obj = Unhashable()
        when(obj).update().thenReturn(None)


@pytest.mark.usefixtures('unstub')
class TestPassAroundStrictness:

    def testReconfigureStrictMock(self):
        when(Dog).bark()  # important first call, inits theMock

        when(Dog, strict=False).waggle().thenReturn('Sure')
        expect(Dog, strict=False).weggle().thenReturn('Sure')


        with pytest.raises(InvocationError):
            when(Dog).wuggle()

        with pytest.raises(InvocationError):
            when(Dog).woggle()

        rex = Dog()
        assert rex.waggle() == 'Sure'
        assert rex.weggle() == 'Sure'

        # For documentation; the inital strict value of the mock will be used
        # here. So the above when(..., strict=False) just assures we can
        # actually *add* an attribute to the mocked object
        with pytest.raises(InvocationError):
            rex.waggle(1)

        verify(Dog).waggle()
        verify(Dog).weggle()



    def testReconfigureLooseMock(self):
        when(Dog, strict=False).bark()  # important first call, inits theMock

        when(Dog, strict=False).waggle().thenReturn('Sure')
        expect(Dog, strict=False).weggle().thenReturn('Sure')

        with pytest.raises(InvocationError):
            when(Dog).wuggle()

        with pytest.raises(InvocationError):
            when(Dog).woggle()

        rex = Dog()
        assert rex.waggle() == 'Sure'
        assert rex.weggle() == 'Sure'

        # For documentation; see test above. strict is inherited from the
        # initial mock. So we return `None`
        assert rex.waggle(1) is None

        verify(Dog).waggle()
        verify(Dog).weggle()



    # Where to put this test?
    def testEnsureAddedAttributesGetRemovedOnUnstub(self):
        with when(Dog, strict=False).wggle():
            pass

        with pytest.raises(AttributeError):
            getattr(Dog, 'wggle')


@pytest.mark.usefixtures('unstub')
class TestDottedPaths:

    def testWhen(self):
        when('os.path').exists('/Foo').thenReturn(True)

        import os.path
        assert os.path.exists('/Foo')

    def testWhen2(self):
        when2('os.path.exists', '/Foo').thenReturn(True)

        import os.path
        assert os.path.exists('/Foo')

    def testPatch(self):
        dummy = mock()
        patch('os.path.exists', dummy)

        import os.path
        assert os.path.exists('/Foo') is None

        verify(dummy).__call__('/Foo')

    def testVerify(self):
        when('os.path').exists('/Foo').thenReturn(True)

        import os.path
        os.path.exists('/Foo')

        verify('os.path', times=1).exists('/Foo')

    def testSpy2(self):
        spy2('os.path.exists')

        import os.path
        assert not os.path.exists('/Foo')

        verify('os.path', times=1).exists('/Foo')
