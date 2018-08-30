
import pytest

from mockito import when, args, kwargs, unstub

from collections import namedtuple


class CallSignature(namedtuple('CallSignature', 'args kwargs')):
    def raises(self, reason):
        return pytest.mark.xfail(self, raises=reason, strict=True)

def sig(*a, **kw):
    return CallSignature(a, kw)


class SUT(object):
    def none_args(self):
        pass

    def one_arg(self, a):
        pass

    def two_args(self, a, b):
        pass

    def star_arg(self, *args):
        pass

    def star_kwarg(self, **kwargs):
        pass

    def arg_plus_star_arg(self, a, *b):
        pass

    def arg_plus_star_kwarg(self, a, **b):
        pass

    def two_args_wt_default(self, a, b=None):
        pass

    def combination(self, a, b=None, *c, **d):
        pass


class ClassMethods(object):
    @classmethod
    def none_args(cls):
        pass

    @classmethod
    def one_arg(cls, a):
        pass

    @classmethod
    def two_args(cls, a, b):
        pass

    @classmethod
    def star_arg(cls, *a):
        pass

    @classmethod
    def star_kwarg(cls, **kw):
        pass

    @classmethod
    def arg_plus_star_arg(cls, a, *b):
        pass

    @classmethod
    def arg_plus_star_kwarg(cls, a, **b):
        pass

    @classmethod
    def two_args_wt_default(cls, a, b=None):
        pass

    @classmethod
    def combination(cls, a, b=None, *c, **d):
        pass


class StaticMethods(object):
    @staticmethod
    def none_args():
        pass

    @staticmethod
    def one_arg(a):
        pass

    @staticmethod
    def two_args(a, b):
        pass

    @staticmethod
    def star_arg(*a):
        pass

    @staticmethod
    def star_kwarg(**kw):
        pass

    @staticmethod
    def arg_plus_star_arg(a, *b):
        pass

    @staticmethod
    def arg_plus_star_kwarg(a, **b):
        pass

    @staticmethod
    def two_args_wt_default(a, b=None):
        pass

    @staticmethod
    def combination(a, b=None, *c, **d):
        pass


@pytest.fixture(params=[
    'instance',
    'class',
    'classmethods',
    'staticmethods',
    'staticmethods_2',
])
def sut(request):
    if request.param == 'instance':
        yield SUT()
    elif request.param == 'class':
        yield SUT
    elif request.param == 'classmethods':
        yield ClassMethods
    elif request.param == 'staticmethods':
        yield StaticMethods
    elif request.param == 'staticmethods_2':
        yield StaticMethods()

    unstub()


class TestSignatures:

    class TestNoneArg:

        @pytest.mark.parametrize('call', [
            sig(),
            sig(Ellipsis),
        ])
        def test_passing(self, sut, call):
            when(sut).none_args(*call.args, **call.kwargs).thenReturn('stub')


        @pytest.mark.parametrize('call', [
            sig(12),
            sig(*args),
            sig(**kwargs),
            sig(*args, **kwargs)
        ])
        def test_failing(self, sut, call):
            with pytest.raises(TypeError):
                when(sut).none_args(*call.args, **call.kwargs)


    class TestOneArg:

        @pytest.mark.parametrize('call', [
            sig(12),
            sig(a=12),

            sig(Ellipsis),

            sig(*args),
            sig(*args, **kwargs),
            sig(**kwargs),
        ])
        def test_passing(self, sut, call):
            when(sut).one_arg(*call.args, **call.kwargs).thenReturn('stub')

        @pytest.mark.parametrize('call', [
            sig(12, 13),
            sig(12, b=2),
            sig(12, 13, 14),
            sig(b=2),
            sig(12, c=2),
            sig(12, b=2, c=2),

            sig(12, Ellipsis),

            sig(1, *args),
            sig(*args, a=1),
            sig(*args, b=1),
            sig(1, **kwargs),
        ])
        def test_failing(self, sut, call):
            with pytest.raises(TypeError):
                when(sut).one_arg(*call.args, **call.kwargs)


    class TestTwoArgs:

        # def two_args(a, b)
        @pytest.mark.parametrize('call', [
            sig(12, 13),
            sig(12, b=2),

            sig(Ellipsis),
            sig(12, Ellipsis),

            sig(*args),
            sig(*args, **kwargs),
            sig(12, *args),
            sig(**kwargs),
            sig(12, **kwargs),
            sig(b=13, **kwargs),

        ])
        def test_passing(self, sut, call):
            when(sut).two_args(*call.args, **call.kwargs)

        @pytest.mark.parametrize('call', [
            sig(12),
            sig(12, 13, 14),
            sig(b=2),
            sig(12, c=2),
            sig(12, b=2, c=2),

            sig(12, 13, Ellipsis),
            sig(12, 13, *args),
            sig(12, b=13, *args),
            sig(12, 13, **kwargs),
            sig(12, b=13, **kwargs),
        ])
        def test_failing(self, sut, call):
            with pytest.raises(TypeError):
                when(sut).two_args(*call.args, **call.kwargs)

    class TestStarArg:
        # def star_arg(*args)
        @pytest.mark.parametrize('call', [
            sig(),
            sig(12),
            sig(12, 13),

            sig(Ellipsis),
            sig(12, Ellipsis),
            sig(12, 13, Ellipsis),

            sig(*args),
            sig(12, *args),
            sig(12, 13, *args)
        ], ids=lambda i: str(i))
        def test_passing(self, sut, call):
            when(sut).star_arg(*call.args, **call.kwargs)

        @pytest.mark.parametrize('call', [
            sig(**kwargs),
            sig(12, **kwargs),
            sig(Ellipsis, **kwargs),
            sig(a=12),
            sig(args=12)
        ], ids=lambda i: str(i))
        def test_failing(self, sut, call):
            with pytest.raises(TypeError):
                when(sut).star_arg(*call.args, **call.kwargs)


    class TestStarKwarg:
        # def star_kwarg(**kwargs)
        @pytest.mark.parametrize('call', [
            sig(),
            sig(a=1),
            sig(a=1, b=2),

            sig(Ellipsis),

            sig(**kwargs),
            sig(a=1, **kwargs)

        ], ids=lambda i: str(i))
        def test_passing(self, sut, call):
            when(sut).star_kwarg(*call.args, **call.kwargs)

        @pytest.mark.parametrize('call', [
            sig(12),
            sig(*args),
            sig(*args, **kwargs),
            sig(12, a=1)
        ], ids=lambda i: str(i))
        def test_failing(self, sut, call):
            with pytest.raises(TypeError):
                when(sut).star_kwarg(*call.args, **call.kwargs)


    class TestArgPlusStarArg:
        # def arg_plus_star_arg(a, *args)
        @pytest.mark.parametrize('call', [
            sig(12),
            sig(a=12),
            sig(12, 13),

            sig(Ellipsis),
            sig(12, Ellipsis),
            sig(12, 13, Ellipsis),

            sig(*args),
            sig(12, *args),

            sig(**kwargs),
        ], ids=lambda i: str(i))
        def test_passing(self, sut, call):
            when(sut).arg_plus_star_arg(*call.args, **call.kwargs)

        @pytest.mark.parametrize('call', [
            sig(),
            sig(13, a=12),

            sig(b=13),
            sig(12, b=13, *args),
            sig(a=12, b=13, *args),

            sig(12, **kwargs),
            sig(a=12, **kwargs),
        ], ids=lambda i: str(i))
        def test_failing(self, sut, call):
            with pytest.raises(TypeError):
                when(sut).arg_plus_star_arg(*call.args, **call.kwargs)


    class TestArgPlusStarKwarg:
        # def arg_plus_star_kwarg(a, **kwargs)
        @pytest.mark.parametrize('call', [
            sig(12),
            sig(a=12),
            sig(12, b=1),

            sig(Ellipsis),
            sig(12, Ellipsis),

            sig(**kwargs),
            sig(12, **kwargs),
            sig(a=12, **kwargs),
            sig(12, b=1, **kwargs),
            sig(a=12, b=1, **kwargs),

            sig(*args),
            sig(*args, b=1),

            sig(*args, **kwargs)
        ], ids=lambda i: str(i))
        def test_passing(self, sut, call):
            when(sut).arg_plus_star_kwarg(*call.args, **call.kwargs)

        @pytest.mark.parametrize('call', [
            sig(),
            sig(12, 13),
            sig(b=1),
            sig(12, a=1),
            sig(12, 13, Ellipsis),
            sig(*args, a=1),
            sig(12, *args)
        ], ids=lambda i: str(i))
        def test_failing(self, sut, call):
            with pytest.raises(TypeError):
                when(sut).arg_plus_star_kwarg(*call.args, **call.kwargs)




    class TestTwoArgsWtDefault:

        @pytest.mark.parametrize('call', [
            sig(12),
            sig(12, 13),
            sig(12, b=2),

            sig(Ellipsis),
            sig(12, Ellipsis),

            sig(*args),
            sig(*args, **kwargs),
            sig(12, *args),
            sig(*args, b=2),
            sig(**kwargs),
            sig(12, **kwargs),
        ], ids=lambda i: str(i))
        def test_passing(self, sut, call):
            when(sut).two_args_wt_default(
                *call.args, **call.kwargs).thenReturn()


        @pytest.mark.parametrize('call', [
            sig(12, 13, 14),
            sig(b=2),
            sig(12, c=2),
            sig(12, b=2, c=2),

            sig(12, 13, Ellipsis),

            sig(12, 13, *args),
            sig(12, b=13, *args),
            sig(12, c=13, *args),
            sig(12, *args, b=2),
            sig(*args, a=2),
            sig(*args, c=2),
            sig(12, 13, **kwargs),
            sig(12, b=13, **kwargs),
            sig(12, c=13, **kwargs),
        ], ids=lambda i: str(i))
        def test_failing(self, sut, call):
            with pytest.raises(TypeError):
                when(sut).two_args_wt_default(
                    *call.args, **call.kwargs).thenReturn()

    class TestCombination:

        # def combination(self, a, b=None, *c, **d)
        @pytest.mark.parametrize('call', [
            sig(12),
            sig(12, 13),
            sig(12, 13, 14),
            sig(12, 13, 14, 15),

            sig(Ellipsis),
            sig(12, Ellipsis),
            sig(12, 13, Ellipsis),
            sig(12, 13, 14, Ellipsis),
            sig(12, 13, 14, 15, Ellipsis)

        ], ids=lambda i: str(i))
        def test_passing(self, sut, call):
            when(sut).combination(
                *call.args, **call.kwargs).thenReturn()


        @pytest.mark.parametrize('call', [
            sig(12, 13, b=16),
        ], ids=lambda i: str(i))
        def test_failing(self, sut, call):
            with pytest.raises(TypeError):
                when(sut).combination(
                    *call.args, **call.kwargs).thenReturn()


    class TestBuiltin:

        def testBuiltinOpen(self):
            try:
                import builtins
            except ImportError:
                import builtins as builtins

            try:
                when(builtins).open('foo')
            finally:  # just to be sure
                unstub()

