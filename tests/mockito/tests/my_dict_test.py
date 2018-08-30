
import pytest

from mockito.mock_registry import _Dict
from mockito.mocking import Mock


class TestCustomDictLike:

    def testAssignKeyValuePair(self):
        td = _Dict()
        obj = {}
        mock = Mock(None)

        td[obj] = mock

    def testGetValueForKey(self):
        td = _Dict()
        obj = {}
        mock = Mock(None)
        td[obj] = mock

        assert td.get(obj) == mock

    def testReplaceValueForSameKey(self):
        td = _Dict()
        obj = {}
        mock1 = Mock(None)
        mock2 = Mock(None)
        td[obj] = mock1
        td[obj] = mock2

        assert td.pop(obj) == mock2
        with pytest.raises(KeyError):
            td.pop(obj)

    def testPopKey(self):
        td = _Dict()
        obj = {}
        mock = Mock(None)
        td[obj] = mock

        assert td.pop(obj) == mock
        assert td.get(obj) is None

    def testIterValues(self):
        td = _Dict()
        obj = {}
        mock = Mock(None)
        td[obj] = mock

        assert list(td.values()) == [mock]

    def testClear(self):
        td = _Dict()
        obj = {}
        mock = Mock(None)
        td[obj] = mock

        td.clear()
        assert td.get(obj) is None

