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

__all__ = ['never', 'VerificationError']


class VerificationError(AssertionError):
    '''Indicates error during verification of invocations.

    Raised if verification fails. Error message contains the cause.
    '''
    pass


class AtLeast(object):
    def __init__(self, wanted_count):
        self.wanted_count = wanted_count

    def verify(self, invocation, actual_count):
        if actual_count < self.wanted_count:
            raise VerificationError("\nWanted at least: %i, actual times: %i"
                                    % (self.wanted_count, actual_count))

    def __repr__(self):
        return "<%s wanted=%s>" % (type(self).__name__, self.wanted_count)

class AtMost(object):
    def __init__(self, wanted_count):
        self.wanted_count = wanted_count

    def verify(self, invocation, actual_count):
        if actual_count > self.wanted_count:
            raise VerificationError("\nWanted at most: %i, actual times: %i"
                                    % (self.wanted_count, actual_count))

    def __repr__(self):
        return "<%s wanted=%s>" % (type(self).__name__, self.wanted_count)

class Between(object):
    def __init__(self, wanted_from, wanted_to):
        self.wanted_from = wanted_from
        self.wanted_to = wanted_to

    def verify(self, invocation, actual_count):
        if actual_count < self.wanted_from or actual_count > self.wanted_to:
            raise VerificationError(
                "\nWanted between: [%i, %i], actual times: %i"
                % (self.wanted_from, self.wanted_to, actual_count))

    def __repr__(self):
        return "<%s [%s, %s]>" % (
            type(self).__name__, self.wanted_from, self.wanted_to)

class Times(object):
    def __init__(self, wanted_count):
        self.wanted_count = wanted_count

    def verify(self, invocation, actual_count):
        if actual_count == self.wanted_count:
                return
        if actual_count == 0:
            invocations = (
                [
                    invoc
                    for invoc in invocation.mock.invocations
                    if invoc.method_name == invocation.method_name
                ] or
                invocation.mock.invocations or
                ['Nothing']
            )
            raise VerificationError(
                """
Wanted but not invoked:

    %s

Instead got:

    %s

"""
                % (
                    invocation,
                    "\n    ".join(
                        str(invoc) for invoc in reversed(invocations)
                    )
                )
            )
        else:
            if self.wanted_count == 0:
                raise VerificationError(
                    "\nUnwanted invocation of %s, times: %i"
                    % (invocation, actual_count))
            else:
                raise VerificationError("\nWanted times: %i, actual times: %i"
                                        % (self.wanted_count, actual_count))

    def __repr__(self):
        return "<%s wanted=%s>" % (type(self).__name__, self.wanted_count)

class InOrder(object):
    '''Verifies invocations in order.

    Verifies if invocation was in expected order, and if yes -- degrades to
    original Verifier (AtLeast, Times, Between, ...).
    '''

    def __init__(self, original_verification):
        '''

        @param original_verification: Original verifiaction to degrade to if
                                      order of invocation was ok.
        '''
        self.original_verification = original_verification

    def verify(self, wanted_invocation, count):
        for invocation in reversed(wanted_invocation.mock.invocations):
            if not invocation.verified_inorder:
                if not wanted_invocation.matches(invocation):
                    raise VerificationError(
                        '\nWanted %s to be invoked,'
                        '\ngot    %s instead.' %
                        (wanted_invocation, invocation))
                invocation.verified_inorder = True
                break
        # proceed with original verification
        self.original_verification.verify(wanted_invocation, count)


never = 0
