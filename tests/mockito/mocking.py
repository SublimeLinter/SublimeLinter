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

from collections import deque
import inspect
import functools

from . import invocation
from . import signature
from . import utils
from .mock_registry import mock_registry


__all__ = ['mock']


class _Dummy(object):
    # We spell out `__call__` here for convenience. All other magic methods
    # must be configured before use, but we want `mock`s to be callable by
    # default.
    def __call__(self, *args, **kwargs):
        return self.__getattr__('__call__')(*args, **kwargs)


def remembered_invocation_builder(mock, method_name, *args, **kwargs):
    invoc = invocation.RememberedInvocation(mock, method_name)
    return invoc(*args, **kwargs)


class Mock(object):
    def __init__(self, mocked_obj, strict=True, spec=None):
        self.mocked_obj = mocked_obj
        self.strict = strict
        self.spec = spec

        self.invocations = deque()
        self.stubbed_invocations = deque()

        self.original_methods = {}
        self._signatures_store = {}

    def remember(self, invocation):
        self.invocations.appendleft(invocation)

    def finish_stubbing(self, stubbed_invocation):
        self.stubbed_invocations.appendleft(stubbed_invocation)

    def clear_invocations(self):
        self.invocations = deque()

    # STUBBING

    def get_original_method(self, method_name):
        if self.spec is None:
            return None

        try:
            return self.spec.__dict__.get(method_name)
        except AttributeError:
            return getattr(self.spec, method_name, None)

    def set_method(self, method_name, new_method):
        setattr(self.mocked_obj, method_name, new_method)

    def replace_method(self, method_name, original_method):

        def new_mocked_method(*args, **kwargs):
            # we throw away the first argument, if it's either self or cls
            if (inspect.ismethod(new_mocked_method) or
                    inspect.isclass(self.mocked_obj) and
                    not isinstance(new_mocked_method, staticmethod)):
                args = args[1:]

            return remembered_invocation_builder(
                self, method_name, *args, **kwargs)

        new_mocked_method.__name__ = method_name
        if original_method:
            new_mocked_method.__doc__ = original_method.__doc__
            new_mocked_method.__wrapped__ = original_method
            try:
                new_mocked_method.__module__ = original_method.__module__
            except AttributeError:
                pass

        if (inspect.ismethod(original_method)):
            new_mocked_method = utils.newmethod(
                new_mocked_method, self.mocked_obj)
        if isinstance(original_method, staticmethod):
            new_mocked_method = staticmethod(new_mocked_method)
        elif isinstance(original_method, classmethod):
            new_mocked_method = classmethod(new_mocked_method)
        elif (inspect.isclass(self.mocked_obj) and  # TBC: Inner classes
                inspect.isclass(original_method)):
            new_mocked_method = staticmethod(new_mocked_method)

        self.set_method(method_name, new_mocked_method)

    def stub(self, method_name):
        try:
            self.original_methods[method_name]
        except KeyError:
            original_method = self.get_original_method(method_name)
            self.original_methods[method_name] = original_method

            self.replace_method(method_name, original_method)

    def forget_stubbed_invocation(self, invocation):
        assert invocation in self.stubbed_invocations

        if len(self.stubbed_invocations) == 1:
            mock_registry.unstub(self.mocked_obj)
            return

        self.stubbed_invocations.remove(invocation)

        if not any(
            inv.method_name == invocation.method_name
            for inv in self.stubbed_invocations
        ):
            original_method = self.original_methods.pop(invocation.method_name)
            self.restore_method(invocation.method_name, original_method)

    def restore_method(self, method_name, original_method):
        # If original_method is None, we *added* it to mocked_obj, so we
        # must delete it here.
        # If we mocked an instance, our mocked function will actually hide
        # the one on its class, so we delete as well.
        if (not original_method or not inspect.isclass(self.mocked_obj) and
                inspect.ismethod(original_method)):
            delattr(self.mocked_obj, method_name)
        else:
            self.set_method(method_name, original_method)

    def unstub(self):
        while self.original_methods:
            method_name, original_method = self.original_methods.popitem()
            self.restore_method(method_name, original_method)

    # SPECCING

    def has_method(self, method_name):
        if self.spec is None:
            return True

        return hasattr(self.spec, method_name)

    def get_signature(self, method_name):
        if self.spec is None:
            return None

        try:
            return self._signatures_store[method_name]
        except KeyError:
            sig = signature.get_signature(self.spec, method_name)
            self._signatures_store[method_name] = sig
            return sig


class _OMITTED(object):
    def __repr__(self):
        return 'OMITTED'


OMITTED = _OMITTED()

def mock(config_or_spec=None, spec=None, strict=OMITTED):
    """Create 'empty' objects ('Mocks').

    Will create an empty unconfigured object, that you can pass
    around. All interactions (method calls) will be recorded and can be
    verified using :func:`verify` et.al.

    A plain `mock()` will be not `strict`, and thus all methods regardless
    of the arguments will return ``None``.

    .. note:: Technically all attributes will return an internal interface.
        Because of that a simple ``if mock().foo:`` will surprisingly pass.

    If you set strict to ``True``: ``mock(strict=True)`` all unexpected
    interactions will raise an error instead.

    You configure a mock using :func:`when`, :func:`when2` or :func:`expect`.
    You can also very conveniently just pass in a dict here::

        response = mock({'text': 'ok', 'raise_for_status': lambda: None})

    You can also create an empty Mock which is specced against a given
    `spec`: ``mock(requests.Response)``. These mock are by default strict,
    thus they raise if you want to stub a method, the spec does not implement.
    Mockito will also match the function signature.

    You can pre-configure a specced mock as well::

        response = mock({'json': lambda: {'status': 'Ok'}},
                        spec=requests.Response)

    Mocks are by default callable. Configure the callable behavior using
    `when`::

        dummy = mock()
        when(dummy).__call_(1).thenReturn(2)

    All other magic methods must be configured this way or they will raise an
    AttributeError.


    See :func:`verify` to verify your interactions after usage.

    """

    if type(config_or_spec) is dict:
        config = config_or_spec
    else:
        config = {}
        spec = config_or_spec

    if strict is OMITTED:
        strict = False if spec is None else True


    class Dummy(_Dummy):
        if spec:
            __class__ = spec  # make isinstance work

        def __getattr__(self, method_name):
            if strict:
                raise AttributeError(
                    "'Dummy' has no attribute %r configured" % method_name)
            return functools.partial(
                remembered_invocation_builder, theMock, method_name)

        def __repr__(self):
            name = 'Dummy'
            if spec:
                name += spec.__name__
            return "<%s id=%s>" % (name, id(self))


    # That's a tricky one: The object we will return is an *instance* of our
    # Dummy class, but the mock we register will point and patch the class.
    # T.i. so that magic methods (`__call__` etc.) can be configured.
    obj = Dummy()
    theMock = Mock(Dummy, strict=strict, spec=spec)

    for n, v in config.items():
        if inspect.isfunction(v):
            invocation.StubbedInvocation(theMock, n)(Ellipsis).thenAnswer(v)
        else:
            setattr(obj, n, v)

    mock_registry.register(obj, theMock)
    return obj
