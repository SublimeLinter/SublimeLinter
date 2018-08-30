import mockito
from mockito import when, patch
import pytest

import numpy as np
from . import module


pytestmark = pytest.mark.usefixtures("unstub")


def xcompare(a, b):
    if isinstance(a, mockito.matchers.Matcher):
        return a.matches(b)

    return np.array_equal(a, b)


class TestEnsureNumpyWorks:
    def testEnsureNumpyArrayAllowedWhenStubbing(self):
        array = np.array([1, 2, 3])
        when(module).one_arg(array).thenReturn('yep')

        with patch(mockito.invocation.MatchingInvocation.compare, xcompare):
            assert module.one_arg(array) == 'yep'

    def testEnsureNumpyArrayAllowedWhenCalling(self):
        array = np.array([1, 2, 3])
        when(module).one_arg(Ellipsis).thenReturn('yep')
        assert module.one_arg(array) == 'yep'

