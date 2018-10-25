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

from . import matchers
from . import signature
from . import verification as verificationModule
from .utils import contains_strict

from collections import deque
import functools


class InvocationError(AttributeError):
    pass


class Invocation(object):
    def __init__(self, mock, method_name):
        self.mock = mock
        self.method_name = method_name
        self.strict = mock.strict

        self.params = ()
        self.named_params = {}

    def _remember_params(self, params, named_params):
        self.params = params
        self.named_params = named_params

    def __repr__(self):
        args = [repr(p) if p is not Ellipsis else '...'
                for p in self.params]
        kwargs = ["%s=%r" % (key, val)
                  if key is not matchers.KWARGS_SENTINEL else '**kwargs'
                  for key, val in self.named_params.items()]
        params = ", ".join(args + kwargs)
        return "%s(%s)" % (self.method_name, params)


class RememberedInvocation(Invocation):
    def __init__(self, mock, method_name):
        super(RememberedInvocation, self).__init__(mock, method_name)
        self.verified = False
        self.verified_inorder = False

    def ensure_mocked_object_has_method(self, method_name):
        if not self.mock.has_method(method_name):
            raise InvocationError(
                "You tried to call a method '%s' the object (%s) doesn't "
                "have." % (method_name, self.mock.mocked_obj))

    def ensure_signature_matches(self, method_name, args, kwargs):
        sig = self.mock.get_signature(method_name)
        if not sig:
            return

        signature.match_signature(sig, args, kwargs)

    def __call__(self, *params, **named_params):
        if self.strict:
            self.ensure_mocked_object_has_method(self.method_name)
            self.ensure_signature_matches(
                self.method_name, params, named_params)

        self._remember_params(params, named_params)
        self.mock.remember(self)

        for matching_invocation in self.mock.stubbed_invocations:
            if matching_invocation.matches(self):
                matching_invocation.should_answer(self)
                return matching_invocation.answer_first(
                    *params, **named_params)

        if self.strict:
            stubbed_invocations = [
                invoc
                for invoc in self.mock.stubbed_invocations
                if invoc.method_name == self.method_name
            ]
            raise InvocationError(
                """
Called but not expected:

    %s

Stubbed invocations are:

    %s

"""
                % (
                    self,
                    "\n    ".join(
                        str(invoc) for invoc in reversed(stubbed_invocations)
                    )
                )
            )

        return None


class RememberedProxyInvocation(Invocation):
    '''Remeber params and proxy to method of original object.

    Calls method on original object and returns it's return value.
    '''
    def __init__(self, mock, method_name):
        super(RememberedProxyInvocation, self).__init__(mock, method_name)
        self.verified = False
        self.verified_inorder = False

    def __call__(self, *params, **named_params):
        self._remember_params(params, named_params)
        self.mock.remember(self)
        obj = self.mock.spec
        try:
            method = getattr(obj, self.method_name)
        except AttributeError:
            raise AttributeError(
                "You tried to call method '%s' which '%s' instance does not "
                "have." % (self.method_name, obj))
        return method(*params, **named_params)


class MatchingInvocation(Invocation):
    @staticmethod
    def compare(p1, p2):
        if isinstance(p1, matchers.Matcher):
            if not p1.matches(p2):
                return False
        elif p1 != p2:
            return False
        return True

    def _remember_params(self, params, named_params):
        if (
            contains_strict(params, Ellipsis)
            and (params[-1] is not Ellipsis or named_params)
        ):
            raise TypeError('Ellipsis must be the last argument you specify.')

        if contains_strict(params, matchers.args):
            raise TypeError('args must be used as *args')

        if (
            contains_strict(params, matchers.kwargs)
            or contains_strict(params, matchers.KWARGS_SENTINEL)
        ):
            raise TypeError('kwargs must be used as **kwargs')

        def wrap(p):
            if p is any or p is matchers.any_:
                return matchers.any_()
            return p

        self.params = tuple(wrap(p) for p in params)
        self.named_params = {k: wrap(v) for k, v in named_params.items()}


    # Note: matches(a, b) does not imply matches(b, a) because
    # the left side might contain wildcards (like Ellipsis) or matchers.
    # In its current form the right side is a concrete call signature.
    def matches(self, invocation):  # noqa: C901 (too complex)
        if self.method_name != invocation.method_name:
            return False

        for x, p1 in enumerate(self.params):
            # assume Ellipsis is the last thing a user declares
            if p1 is Ellipsis:
                return True

            if p1 is matchers.ARGS_SENTINEL:
                break

            try:
                p2 = invocation.params[x]
            except IndexError:
                return False

            if not self.compare(p1, p2):
                return False
        else:
            if len(self.params) != len(invocation.params):
                return False

        for key, p1 in sorted(
            self.named_params.items(),
            key=lambda k_v: 1 if k_v[0] is matchers.KWARGS_SENTINEL else 0
        ):
            if key is matchers.KWARGS_SENTINEL:
                break

            try:
                p2 = invocation.named_params[key]
            except KeyError:
                return False

            if not self.compare(p1, p2):
                return False
        else:
            if len(self.named_params) != len(invocation.named_params):
                return False

        return True


class VerifiableInvocation(MatchingInvocation):
    def __init__(self, mock, method_name, verification):
        super(VerifiableInvocation, self).__init__(mock, method_name)
        self.verification = verification

    def __call__(self, *params, **named_params):
        self._remember_params(params, named_params)
        matched_invocations = []
        for invocation in self.mock.invocations:
            if self.matches(invocation):
                matched_invocations.append(invocation)

        self.verification.verify(self, len(matched_invocations))

        # check (real) invocations as verified
        for invocation in matched_invocations:
            invocation.verified = True

        # check stubs as 'used'
        if verification_has_lower_bound_of_zero(self.verification):
            for stub in self.mock.stubbed_invocations:
                # Remember: matches(a, b) does not imply matches(b, a)
                # (see above!), so we check for both
                if stub.matches(self) or self.matches(stub):
                    stub.allow_zero_invocations = True


def verification_has_lower_bound_of_zero(verification):
    if (isinstance(verification, verificationModule.Times) and
            verification.wanted_count == 0):
        return True

    if (isinstance(verification, verificationModule.Between) and
            verification.wanted_from == 0):
        return True

    return False


class StubbedInvocation(MatchingInvocation):
    def __init__(self, mock, method_name, verification=None, strict=None):
        super(StubbedInvocation, self).__init__(mock, method_name)

        #: Holds the verification set up via `expect`.
        #: The verification will be verified implicitly, while using this stub.
        self.verification = verification

        if strict is not None:
            self.strict = strict

        self.answers = CompositeAnswer()

        #: Counts how many times this stub has been 'used'.
        #: A stub gets used, when a real invocation matches its argument
        #: signature, and asks for an answer.
        self.used = 0

        #: Set if `verifyStubbedInvocationsAreUsed` should pass, regardless
        #: of any factual invocation. E.g. set by `verify(..., times=0)`
        if verification_has_lower_bound_of_zero(verification):
            self.allow_zero_invocations = True
        else:
            self.allow_zero_invocations = False


    def ensure_mocked_object_has_method(self, method_name):
        if not self.mock.has_method(method_name):
            raise InvocationError(
                "You tried to stub a method '%s' the object (%s) doesn't "
                "have." % (method_name, self.mock.mocked_obj))

    def ensure_signature_matches(self, method_name, args, kwargs):
        sig = self.mock.get_signature(method_name)
        if not sig:
            return

        signature.match_signature_allowing_placeholders(sig, args, kwargs)

    def __call__(self, *params, **named_params):
        if self.strict:
            self.ensure_mocked_object_has_method(self.method_name)
            self.ensure_signature_matches(
                self.method_name, params, named_params)
        self._remember_params(params, named_params)

        self.mock.stub(self.method_name)
        self.mock.finish_stubbing(self)
        return AnswerSelector(self)

    def forget_self(self):
        self.mock.forget_stubbed_invocation(self)

    def add_answer(self, answer):
        self.answers.add(answer)

    def answer_first(self, *args, **kwargs):
        self.used += 1
        return self.answers.answer(*args, **kwargs)

    def should_answer(self, invocation):
        # type: (RememberedInvocation) -> None
        verification = self.verification
        if not verification:
            return

        # This check runs before `answer_first`. We add '1' because we want
        # to know if the verification passes if this call gets through.
        actual_count = self.used + 1

        if isinstance(verification, verificationModule.Times):
            if actual_count > verification.wanted_count:
                raise InvocationError(
                    "\nWanted times: %i, actual times: %i"
                    % (verification.wanted_count, actual_count))
        elif isinstance(verification, verificationModule.AtMost):
            if actual_count > verification.wanted_count:
                raise InvocationError(
                    "\nWanted at most: %i, actual times: %i"
                    % (verification.wanted_count, actual_count))
        elif isinstance(verification, verificationModule.Between):
            if actual_count > verification.wanted_to:
                raise InvocationError(
                    "\nWanted between: [%i, %i], actual times: %i"
                    % (verification.wanted_from,
                       verification.wanted_to,
                       actual_count))

        # The way mockito's `verify` works is, that it checks off all 'real',
        # remembered invocations, if they get verified. This is a simple
        # mechanism so that a later `verifyNoMoreInteractions` just has to
        # ensure that all invocations have this flag set to ``True``.
        # For verifications set up via `expect` we want all invocations
        # to get verified 'implicitly', on-the-go, so we set this flag here.
        invocation.verified = True


    def verify(self):
        if not self.verification:
            return

        actual_count = self.used
        self.verification.verify(self, actual_count)



def return_(value, *a, **kw):
    return value

def raise_(exception, *a, **kw):
    raise exception


class AnswerSelector(object):
    def __init__(self, invocation):
        self.invocation = invocation

    def thenReturn(self, *return_values):
        for return_value in return_values:
            self.__then(functools.partial(return_, return_value))
        return self

    def thenRaise(self, *exceptions):
        for exception in exceptions:
            self.__then(functools.partial(raise_, exception))
        return self

    def thenAnswer(self, *callables):
        for callable in callables:
            self.__then(callable)
        return self

    def __then(self, answer):
        self.invocation.add_answer(answer)

    def __enter__(self):
        pass

    def __exit__(self, *exc_info):
        self.invocation.forget_self()


class CompositeAnswer(object):
    def __init__(self):
        #: Container for answers, which are just ordinary callables
        self.answers = deque()

        #: Counter for the maximum answers we ever had
        self.answer_count = 0

    def __len__(self):
        # The minimum is '1' bc we always have a default answer of 'None'
        return max(1, self.answer_count)

    def add(self, answer):
        self.answer_count += 1
        self.answers.append(answer)

    def answer(self, *args, **kwargs):
        if len(self.answers) == 0:
            return None

        if len(self.answers) == 1:
            a = self.answers[0]
        else:
            a = self.answers.popleft()

        return a(*args, **kwargs)

