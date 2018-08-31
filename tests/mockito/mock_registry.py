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



class MockRegistry:
    """Registry for mocks

    Registers mock()s, ensures that we only have one mock() per mocked_obj, and
    iterates over them to unstub each stubbed method.
    """

    def __init__(self):
        self.mocks = _Dict()

    def register(self, obj, mock):
        self.mocks[obj] = mock

    def mock_for(self, obj):
        return self.mocks.get(obj, None)

    def unstub(self, obj):
        try:
            mock = self.mocks.pop(obj)
        except KeyError:
            pass
        else:
            mock.unstub()

    def unstub_all(self):
        for mock in self.get_registered_mocks():
            mock.unstub()
        self.mocks.clear()

    def get_registered_mocks(self):
        return self.mocks.values()


# We have this dict like because we want non-hashable items in our registry.
# This is just enough to match the invoking code above. TBC
class _Dict(object):
    def __init__(self):
        self._store = []

    def __setitem__(self, key, value):
        self.remove(key)
        self._store.append((key, value))

    def remove(self, key):
        self._store = [(k, v) for k, v in self._store if k != key]

    def pop(self, key):
        rv = self.get(key)
        if rv is not None:
            self.remove(key)
            return rv
        else:
            raise KeyError()

    def get(self, key, default=None):
        for k, value in self._store:
            if k == key:
                return value
        return default

    def values(self):
        return [v for k, v in self._store]

    def clear(self):
        self._store[:] = []


mock_registry = MockRegistry()
