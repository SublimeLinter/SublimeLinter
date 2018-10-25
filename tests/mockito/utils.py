
import importlib
import inspect
import sys
import types
import re


PY3 = sys.version_info >= (3,)


def contains_strict(seq, element):
    return any(item is element for item in seq)


def newmethod(fn, obj):
    if PY3:
        return types.MethodType(fn, obj)
    else:
        return types.MethodType(fn, obj, obj.__class__)


def get_function_host(fn):
    """Destructure a given function into its host and its name.

    The 'host' of a function is a module, for methods it is usually its
    instance or its class. This is safe only for methods, for module wide,
    globally declared names it must be considered experimental.

    For all reasonable fn: ``getattr(*get_function_host(fn)) == fn``

    Returns tuple (host, fn-name)
    Otherwise should raise TypeError
    """

    obj = None
    try:
        name = fn.__name__
        obj = fn.__self__
    except AttributeError:
        pass

    if obj is None:
        # Due to how python imports work, everything that is global on a module
        # level must be regarded as not safe here. For now, we go for the extra
        # mile, TBC, because just specifying `os.path.exists` would be 'cool'.
        #
        # TLDR;:
        # E.g. `inspect.getmodule(os.path.exists)` returns `genericpath` bc
        # that's where `exists` is defined and comes from. But from the point
        # of view of the user `exists` always comes and is used from `os.path`
        # which points e.g. to `ntpath`. We thus must patch `ntpath`.
        # But that's the same for most imports::
        #
        #     # b.py
        #     from a import foo
        #
        # Now asking `getmodule(b.foo)` it tells you `a`, but we access and use
        # `b.foo` and we therefore must patch `b`.

        obj, name = find_invoking_frame_and_try_parse()
        # safety check!
        assert getattr(obj, name) == fn


    return obj, name


FIND_ID = re.compile(r'.*\s*.*(?:when2|patch|spy2)\(\s*(.+?)[,\)]', re.M)


def find_invoking_frame_and_try_parse():
    # Actually we just want the first frame in user land; we're open for
    # refactorings here and don't yet decide on which frame exactly we hit
    # that user land.
    stack = inspect.stack(2)[2:10]
    for frame_info in stack:
        # Within `patch` and `spy2` we delegate to `when2` but that's not
        # user land code
        if frame_info[3] in ('patch', 'spy2'):
            continue

        source = ''.join(frame_info[4])
        m = FIND_ID.match(source)
        if m:
            # id should be something like `os.path.exists` etc.
            id = m.group(1)
            parts = id.split('.')
            if len(parts) < 2:
                raise TypeError("can't guess origin of '%s'" % id)

            frame = frame_info[0]
            vars = frame.f_globals.copy()
            vars.update(frame.f_locals)

            # Now that's a simple reduce; we get the initial value from the
            # locally available `vars`, and then reduce the middle parts via
            # `getattr`. The last path component gets not resolved, but is
            # returned as plain string value.
            obj = vars.get(parts[0])
            for part in parts[1:-1]:
                obj = getattr(obj, part)
            return obj, parts[-1]

    raise TypeError('could not destructure first argument')

def get_obj(path):
    """Return obj for given dotted path.

    Typical inputs for `path` are 'os' or 'os.path' in which case you get a
    module; or 'os.path.exists' in which case you get a function from that
    module.

    Just returns the given input in case it is not a str.

    Note: Relative imports not supported.
    Raises ImportError or AttributeError as appropriate.

    """
    # Since we usually pass in mocks here; duck typing is not appropriate
    # (mocks respond to every attribute).
    if not isinstance(path, str):
        return path

    if path.startswith('.'):
        raise TypeError('relative imports are not supported')

    parts = path.split('.')
    head, tail = parts[0], parts[1:]

    obj = importlib.import_module(head)

    # Normally a simple reduce, but we go the extra mile
    # for good exception messages.
    for i, name in enumerate(tail):
        try:
            obj = getattr(obj, name)
        except AttributeError:
            # Note the [:i] instead of [:i+1], so we get the path just
            # *before* the AttributeError, t.i. the part of it that went ok.
            module = '.'.join([head] + tail[:i])
            try:
                importlib.import_module(module)
            except ImportError:
                raise AttributeError(
                    "object '%s' has no attribute '%s'" % (module, name))
            else:
                raise AttributeError(
                    "module '%s' has no attribute '%s'" % (module, name))
    return obj

def get_obj_attr_tuple(path):
    """Split path into (obj, attribute) tuple.

    Given `path` is 'os.path.exists' will thus return `(os.path, 'exists')`

    If path is not a str, delegates to `get_function_host(path)`

    """
    if not isinstance(path, str):
        return get_function_host(path)

    if path.startswith('.'):
        raise TypeError('relative imports are not supported')

    try:
        leading, end = path.rsplit('.', 1)
    except ValueError:
        raise TypeError('path must have dots')

    return get_obj(leading), end





