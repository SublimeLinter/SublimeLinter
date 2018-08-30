
import pytest

from mockito.utils import get_obj, get_obj_attr_tuple

import sys


PY3 = sys.version_info >= (3,)


def foo():
    pass

class TestLateImports:

    def testOs(self):
        import os
        assert get_obj('os') is os

    def testOsPath(self):
        import os.path
        assert get_obj('os.path') is os.path

    def testOsPathExists(self):
        import os.path
        assert get_obj('os.path.exists') is os.path.exists

    def testOsPathWhatever(self):
        with pytest.raises(AttributeError) as exc:
            get_obj('os.path.whatever')

        assert str(exc.value) == "module 'os.path' has no attribute 'whatever'"

    def testOsPathExistsForever(self):
        with pytest.raises(AttributeError) as exc:
            get_obj('os.path.exists.forever')

        assert str(exc.value) == \
            "object 'os.path.exists' has no attribute 'forever'"

    def testOsPathExistsForeverAndEver(self):
        with pytest.raises(AttributeError) as exc:
            get_obj('os.path.exists.forever.and.ever')

        assert str(exc.value) == \
            "object 'os.path.exists' has no attribute 'forever'"

    def testUnknownMum(self):
        with pytest.raises(ImportError) as exc:
            assert get_obj('mum') is foo
        if PY3:
            assert str(exc.value) == "No module named 'mum'"
        else:
            assert str(exc.value) == "No module named mum"

    def testUnknownMumFoo(self):
        with pytest.raises(ImportError) as exc:
            assert get_obj('mum.foo') is foo
        if PY3:
            assert str(exc.value) == "No module named 'mum'"
        else:
            assert str(exc.value) == "No module named mum"

    def testReturnGivenObject(self):
        import os
        assert get_obj(os) == os
        assert get_obj(os.path) == os.path
        assert get_obj(2) == 2

    def testDisallowRelativeImports(self):
        with pytest.raises(TypeError):
            get_obj('.mum')

class TestReturnTuple:
    def testOs(self):
        with pytest.raises(TypeError):
            get_obj_attr_tuple('os')

    def testOsPath(self):
        import os
        assert get_obj_attr_tuple('os.path') == (os, 'path')

    def testOsPathExists(self):
        import os
        assert get_obj_attr_tuple('os.path.exists') == (os.path, 'exists')

    def testOsPathExistsNot(self):
        import os
        assert get_obj_attr_tuple('os.path.exists.not') == (
            os.path.exists, 'not')

    def testDisallowRelativeImports(self):
        with pytest.raises(TypeError):
            get_obj('.mum')


