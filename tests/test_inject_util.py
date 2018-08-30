from functools import wraps
from unittest import TestCase


def inject(*factories):
    def wrapper(fn):
        print('--', fn)

        @wraps(fn)
        def wrapped(self, *args, **kwargs):
            generators = [f() for f in factories]
            fixtures = tuple(g.send(None) for g in generators)
            new_args = args + fixtures
            try:
                return fn(self, *new_args, **kwargs)
            finally:
                for g in generators:
                    try:
                        g.send(None)
                    except StopIteration:
                        pass

        return wrapped

    return wrapper


def linter():
    yield 'Hi'


class TestInjectUtil(TestCase):
    @inject(linter)
    def test_one(self, linter):
        self.assertEqual(linter, 'Hi')

