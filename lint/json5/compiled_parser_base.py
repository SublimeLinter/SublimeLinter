# Taken from https://github.com/dpranke/pyjson5/blob/ebd41b0a93/json5/compiled_parser_base.py

# Copyright 2014 Google Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


class CompiledParserBase(object):
    def __init__(self, msg, fname, starting_rule='grammar', starting_pos=0):
        self.msg = msg
        self.fname = fname
        self.starting_rule = starting_rule
        self.starting_pos = starting_pos
        self.end = len(msg)
        self.val = None
        self.err = None
        self.pos = self.starting_pos
        self.builtins = ('anything', 'digit', 'letter', 'end')

    def parse(self, rule=None, start=0):
        rule = rule or self.starting_rule
        self.pos = start
        self.apply_rule(rule)
        if self.err:
            lineno, colno = self._line_and_colno()
            return None, "%s:%d:%d expecting %s" % (
                self.fname, lineno, colno, self.err)
        return self.val, None

    def apply_rule(self, rule):
        rule_fn = getattr(self, '_' + rule + '_', None)
        if not rule_fn:
            self.err = 'unknown rule "%s"' % rule
        rule_fn()

    def _line_and_colno(self):
        lineno = 1
        colno = 1
        i = 0
        while i < self.pos:
            if self.msg[i] == '\n':
                lineno += 1
                colno = 1
            else:
                colno += 1
            i += 1
        return lineno, colno

    def _expect(self, expr):
        p = self.pos
        l = len(expr)
        if (p + l <= self.end) and self.msg[p:p + l] == expr:
            self.pos += l
            self.val = expr
            self.err = None
        else:
            self.val = None
            self.err = "'%s'" % expr
        return

    def _anything_(self):
        if self.pos < self.end:
            self.val = self.msg[self.pos]
            self.err = None
            self.pos += 1
        else:
            self.val = None
            self.err = "anything"

    def _end_(self):
        self._anything_()
        if self.err:
            self.val = None
            self.err = None
        else:
            self.val = None
            self.err = "the end"
        return

    def _letter_(self):
        if self.pos < self.end and self.msg[self.pos].isalpha():
            self.val = self.msg[self.pos]
            self.err = None
            self.pos += 1
        else:
            self.val = None
            self.err = "a letter"
        return

    def _digit_(self):
        if self.pos < self.end and self.msg[self.pos].isdigit():
            self.val = self.msg[self.pos]
            self.err = None
            self.pos += 1
        else:
            self.val = None
            self.err = "a digit"
        return
