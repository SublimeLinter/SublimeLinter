# Taken from https://github.com/dpranke/pyjson5/blob/ebd41b0a93b29664b61b8207f23039964713623a/json5/parser.py

from .compiled_parser_base import CompiledParserBase


class Parser(CompiledParserBase):

    def _grammar_(self):
        """ ws value:v ws end -> v """
        self._ws_()
        if self.err:
            return
        self._value_()
        if not self.err:
            v_v = self.val
        if self.err:
            return
        self._ws_()
        if self.err:
            return
        self._end_()
        if self.err:
            return
        self.val = v_v
        self.err = None

    def _ws_(self):
        """ (' '|'\t'|comment|eol)* """
        vs = []
        while not self.err:
            def group():
                p = self.pos

                def choice_0():
                    self._expect(' ')
                choice_0()
                if not self.err:
                    return

                self.pos = p

                def choice_1():
                    self._expect('\t')
                choice_1()
                if not self.err:
                    return

                self.pos = p

                def choice_2():
                    self._comment_()
                choice_2()
                if not self.err:
                    return

                self.pos = p

                def choice_3():
                    self._eol_()
                choice_3()
            group()
            if not self.err:
                vs.append(self.val)
        self.val = vs
        self.err = None

    def _eol_(self):
        """ '\r\n'|'\r'|'\n' """
        p = self.pos

        def choice_0():
            self._expect('\r\n')
        choice_0()
        if not self.err:
            return

        self.pos = p

        def choice_1():
            self._expect('\r')
        choice_1()
        if not self.err:
            return

        self.pos = p

        def choice_2():
            self._expect('\n')
        choice_2()

    def _comment_(self):
        """ '//' (~(eol|end) anything)* (end|eol)|'/*' (~'*/' anything)* '*/' """
        p = self.pos

        def choice_0():
            self._expect('//')
            if self.err:
                return
            vs = []
            while not self.err:

                def group():
                    p = self.pos

                    def group():
                        p = self.pos

                        def choice_0():
                            self._eol_()
                        choice_0()
                        if not self.err:
                            return

                        self.pos = p

                        def choice_1():
                            self._end_()
                        choice_1()
                    group()
                    self.pos = p
                    if not self.err:
                        self.err = "not"
                        self.val = None
                        return
                    self.err = None
                    if self.err:
                        return
                    self._anything_()
                group()
                if not self.err:
                    vs.append(self.val)
            self.val = vs
            self.err = None
            if self.err:
                return

            def group():
                p = self.pos

                def choice_0():
                    self._end_()
                choice_0()
                if not self.err:
                    return

                self.pos = p

                def choice_1():
                    self._eol_()
                choice_1()
            group()
        choice_0()
        if not self.err:
            return

        self.pos = p

        def choice_1():
            self._expect('/*')
            if self.err:
                return
            vs = []
            while not self.err:

                def group():
                    p = self.pos
                    self._expect('*/')
                    self.pos = p
                    if not self.err:
                        self.err = "not"
                        self.val = None
                        return
                    self.err = None
                    if self.err:
                        return
                    self._anything_()
                group()
                if not self.err:
                    vs.append(self.val)
            self.val = vs
            self.err = None
            if self.err:
                return
            self._expect('*/')
        choice_1()

    def _value_(self):
        """ 'null' ->
        'None'|'true' ->
        'True'|'false' ->
        'False'|object:v ->
        ['object', v]|array:v ->
        ['array', v]|string:v ->
        ['string', v]|num_literal:v ->
        ['number', v] """
        p = self.pos

        def choice_0():
            self._expect('null')
            if self.err:
                return
            self.val = 'None'
            self.err = None
        choice_0()
        if not self.err:
            return

        self.pos = p

        def choice_1():
            self._expect('true')
            if self.err:
                return
            self.val = 'True'
            self.err = None
        choice_1()
        if not self.err:
            return

        self.pos = p

        def choice_2():
            self._expect('false')
            if self.err:
                return
            self.val = 'False'
            self.err = None
        choice_2()
        if not self.err:
            return

        self.pos = p

        def choice_3():
            self._object_()
            if not self.err:
                v_v = self.val
            if self.err:
                return
            self.val = ['object', v_v]
            self.err = None
        choice_3()
        if not self.err:
            return

        self.pos = p

        def choice_4():
            self._array_()
            if not self.err:
                v_v = self.val
            if self.err:
                return
            self.val = ['array', v_v]
            self.err = None
        choice_4()
        if not self.err:
            return

        self.pos = p

        def choice_5():
            self._string_()
            if not self.err:
                v_v = self.val
            if self.err:
                return
            self.val = ['string', v_v]
            self.err = None
        choice_5()
        if not self.err:
            return

        self.pos = p

        def choice_6():
            self._num_literal_()
            if not self.err:
                v_v = self.val
            if self.err:
                return
            self.val = ['number', v_v]
            self.err = None
        choice_6()

    def _object_(self):
        """ '{' ws member_list:v ws '}' -> v|'{' ws '}' -> [] """
        p = self.pos

        def choice_0():
            self._expect('{')
            if self.err:
                return
            self._ws_()
            if self.err:
                return
            self._member_list_()
            if not self.err:
                v_v = self.val
            if self.err:
                return
            self._ws_()
            if self.err:
                return
            self._expect('}')
            if self.err:
                return
            self.val = v_v
            self.err = None
        choice_0()
        if not self.err:
            return

        self.pos = p

        def choice_1():
            self._expect('{')
            if self.err:
                return
            self._ws_()
            if self.err:
                return
            self._expect('}')
            if self.err:
                return
            self.val = []
            self.err = None
        choice_1()

    def _array_(self):
        """ '[' ws element_list:v ws ']' -> v|'[' ws ']' -> [] """
        p = self.pos

        def choice_0():
            self._expect('[')
            if self.err:
                return
            self._ws_()
            if self.err:
                return
            self._element_list_()
            if not self.err:
                v_v = self.val
            if self.err:
                return
            self._ws_()
            if self.err:
                return
            self._expect(']')
            if self.err:
                return
            self.val = v_v
            self.err = None
        choice_0()
        if not self.err:
            return

        self.pos = p

        def choice_1():
            self._expect('[')
            if self.err:
                return
            self._ws_()
            if self.err:
                return
            self._expect(']')
            if self.err:
                return
            self.val = []
            self.err = None
        choice_1()

    def _string_(self):
        """ squote (~squote qchar)*:qs squote -> ''.join(qs)|dquote (~dquote qchar)*:qs dquote -> ''.join(qs) """
        p = self.pos

        def choice_0():
            self._squote_()
            if self.err:
                return
            vs = []
            while not self.err:

                def group():
                    p = self.pos
                    self._squote_()
                    self.pos = p
                    if not self.err:
                        self.err = "not"
                        self.val = None
                        return
                    self.err = None
                    if self.err:
                        return
                    self._qchar_()
                group()
                if not self.err:
                    vs.append(self.val)
            self.val = vs
            self.err = None
            if not self.err:
                v_qs = self.val
            if self.err:
                return
            self._squote_()
            if self.err:
                return
            self.val = ''.join(v_qs)
            self.err = None
        choice_0()
        if not self.err:
            return

        self.pos = p

        def choice_1():
            self._dquote_()
            if self.err:
                return
            vs = []
            while not self.err:

                def group():
                    p = self.pos
                    self._dquote_()
                    self.pos = p
                    if not self.err:
                        self.err = "not"
                        self.val = None
                        return
                    self.err = None
                    if self.err:
                        return
                    self._qchar_()
                group()
                if not self.err:
                    vs.append(self.val)
            self.val = vs
            self.err = None
            if not self.err:
                v_qs = self.val
            if self.err:
                return
            self._dquote_()
            if self.err:
                return
            self.val = ''.join(v_qs)
            self.err = None
        choice_1()

    def _squote_(self):
        """ '\'' """
        self._expect('\'')

    def _dquote_(self):
        """ '"' """
        self._expect('"')

    def _qchar_(self):
        """ '\\\''|'\\"'|anything """
        p = self.pos

        def choice_0():
            self._expect('\\\'')
        choice_0()
        if not self.err:
            return

        self.pos = p

        def choice_1():
            self._expect('\\"')
        choice_1()
        if not self.err:
            return

        self.pos = p

        def choice_2():
            self._anything_()
        choice_2()

    def _element_list_(self):
        """ value:v ws ',' ws element_list:vs -> [v] + vs|value:v ws ',' -> [v]|value:v -> [v] """
        p = self.pos

        def choice_0():
            self._value_()
            if not self.err:
                v_v = self.val
            if self.err:
                return
            self._ws_()
            if self.err:
                return
            self._expect(',')
            if self.err:
                return
            self._ws_()
            if self.err:
                return
            self._element_list_()
            if not self.err:
                v_vs = self.val
            if self.err:
                return
            self.val = [v_v] + v_vs
            self.err = None
        choice_0()
        if not self.err:
            return

        self.pos = p

        def choice_1():
            self._value_()
            if not self.err:
                v_v = self.val
            if self.err:
                return
            self._ws_()
            if self.err:
                return
            self._expect(',')
            if self.err:
                return
            self.val = [v_v]
            self.err = None
        choice_1()
        if not self.err:
            return

        self.pos = p

        def choice_2():
            self._value_()
            if not self.err:
                v_v = self.val
            if self.err:
                return
            self.val = [v_v]
            self.err = None
        choice_2()

    def _member_list_(self):
        """ member:m ws ',' ws member_list:ms -> [m] + ms|member:m ws ',' -> [m]|member:m -> [m] """
        p = self.pos

        def choice_0():
            self._member_()
            if not self.err:
                v_m = self.val
            if self.err:
                return
            self._ws_()
            if self.err:
                return
            self._expect(',')
            if self.err:
                return
            self._ws_()
            if self.err:
                return
            self._member_list_()
            if not self.err:
                v_ms = self.val
            if self.err:
                return
            self.val = [v_m] + v_ms
            self.err = None
        choice_0()
        if not self.err:
            return

        self.pos = p

        def choice_1():
            self._member_()
            if not self.err:
                v_m = self.val
            if self.err:
                return
            self._ws_()
            if self.err:
                return
            self._expect(',')
            if self.err:
                return
            self.val = [v_m]
            self.err = None
        choice_1()
        if not self.err:
            return

        self.pos = p

        def choice_2():
            self._member_()
            if not self.err:
                v_m = self.val
            if self.err:
                return
            self.val = [v_m]
            self.err = None
        choice_2()

    def _member_(self):
        """ string:k ws ':' ws value:v -> [k, v]|ident:k ws ':' ws value:v -> [k, v] """
        p = self.pos

        def choice_0():
            self._string_()
            if not self.err:
                v_k = self.val
            if self.err:
                return
            self._ws_()
            if self.err:
                return
            self._expect(':')
            if self.err:
                return
            self._ws_()
            if self.err:
                return
            self._value_()
            if not self.err:
                v_v = self.val
            if self.err:
                return
            self.val = [v_k, v_v]
            self.err = None
        choice_0()
        if not self.err:
            return

        self.pos = p

        def choice_1():
            self._ident_()
            if not self.err:
                v_k = self.val
            if self.err:
                return
            self._ws_()
            if self.err:
                return
            self._expect(':')
            if self.err:
                return
            self._ws_()
            if self.err:
                return
            self._value_()
            if not self.err:
                v_v = self.val
            if self.err:
                return
            self.val = [v_k, v_v]
            self.err = None
        choice_1()

    def _ident_(self):
        """ ident_start:hd (ident_start|digit)*:tl -> ''.join([hd] + tl) """
        self._ident_start_()
        if not self.err:
            v_hd = self.val
        if self.err:
            return
        vs = []
        while not self.err:

            def group():
                p = self.pos

                def choice_0():
                    self._ident_start_()
                choice_0()
                if not self.err:
                    return

                self.pos = p

                def choice_1():
                    self._digit_()
                choice_1()
            group()
            if not self.err:
                vs.append(self.val)
        self.val = vs
        self.err = None
        if not self.err:
            v_tl = self.val
        if self.err:
            return
        self.val = ''.join([v_hd] + v_tl)
        self.err = None

    def _ident_start_(self):
        """ (letter|'$'|'_'):i -> i """

        def group():
            p = self.pos

            def choice_0():
                self._letter_()
            choice_0()
            if not self.err:
                return

            self.pos = p

            def choice_1():
                self._expect('$')
            choice_1()
            if not self.err:
                return

            self.pos = p

            def choice_2():
                self._expect('_')
            choice_2()
        group()
        if not self.err:
            v_i = self.val
        if self.err:
            return
        self.val = v_i
        self.err = None

    def _num_literal_(self):
        """ dec_literal:d ~(ident_start|digit) -> d|hex_literal """
        p = self.pos

        def choice_0():
            self._dec_literal_()
            if not self.err:
                v_d = self.val
            if self.err:
                return
            p = self.pos

            def group():
                p = self.pos

                def choice_0():
                    self._ident_start_()
                choice_0()
                if not self.err:
                    return

                self.pos = p

                def choice_1():
                    self._digit_()
                choice_1()
            group()
            self.pos = p
            if not self.err:
                self.err = "not"
                self.val = None
                return
            self.err = None
            if self.err:
                return
            self.val = v_d
            self.err = None
        choice_0()
        if not self.err:
            return

        self.pos = p

        def choice_1():
            self._hex_literal_()
        choice_1()

    def _dec_literal_(self):
        """ dec_int_lit:d frac:f exp:e -> d + '.' + f +
        e|dec_int_lit:d frac:f -> d + '.' +
        f|dec_int_lit:d exp:e -> d +
        e|dec_int_lit:d -> d|frac:f exp:e -> f + e|frac:f -> f """
        p = self.pos

        def choice_0():
            self._dec_int_lit_()
            if not self.err:
                v_d = self.val
            if self.err:
                return
            self._frac_()
            if not self.err:
                v_f = self.val
            if self.err:
                return
            self._exp_()
            if not self.err:
                v_e = self.val
            if self.err:
                return
            self.val = v_d + '.' + v_f + v_e
            self.err = None
        choice_0()
        if not self.err:
            return

        self.pos = p

        def choice_1():
            self._dec_int_lit_()
            if not self.err:
                v_d = self.val
            if self.err:
                return
            self._frac_()
            if not self.err:
                v_f = self.val
            if self.err:
                return
            self.val = v_d + '.' + v_f
            self.err = None
        choice_1()
        if not self.err:
            return

        self.pos = p

        def choice_2():
            self._dec_int_lit_()
            if not self.err:
                v_d = self.val
            if self.err:
                return
            self._exp_()
            if not self.err:
                v_e = self.val
            if self.err:
                return
            self.val = v_d + v_e
            self.err = None
        choice_2()
        if not self.err:
            return

        self.pos = p

        def choice_3():
            self._dec_int_lit_()
            if not self.err:
                v_d = self.val
            if self.err:
                return
            self.val = v_d
            self.err = None
        choice_3()
        if not self.err:
            return

        self.pos = p

        def choice_4():
            self._frac_()
            if not self.err:
                v_f = self.val
            if self.err:
                return
            self._exp_()
            if not self.err:
                v_e = self.val
            if self.err:
                return
            self.val = v_f + v_e
            self.err = None
        choice_4()
        if not self.err:
            return

        self.pos = p

        def choice_5():
            self._frac_()
            if not self.err:
                v_f = self.val
            if self.err:
                return
            self.val = v_f
            self.err = None
        choice_5()

    def _dec_int_lit_(self):
        """ '0' ~digit -> '0'|nonzerodigit:n digit*:ds -> n + ''.join(ds) """
        p = self.pos

        def choice_0():
            self._expect('0')
            if self.err:
                return
            p = self.pos
            self._digit_()
            self.pos = p
            if not self.err:
                self.err = "not"
                self.val = None
                return
            self.err = None
            if self.err:
                return
            self.val = '0'
            self.err = None
        choice_0()
        if not self.err:
            return

        self.pos = p

        def choice_1():
            self._nonzerodigit_()
            if not self.err:
                v_n = self.val
            if self.err:
                return
            vs = []
            while not self.err:
                self._digit_()
                if not self.err:
                    vs.append(self.val)
            self.val = vs
            self.err = None
            if not self.err:
                v_ds = self.val
            if self.err:
                return
            self.val = v_n + ''.join(v_ds)
            self.err = None
        choice_1()

    def _nonzerodigit_(self):
        """ ('1'|'2'|'3'|'4'|'5'|'6'|'7'|'8'|'9') """

        def group():
            p = self.pos

            def choice_0():
                self._expect('1')
            choice_0()
            if not self.err:
                return

            self.pos = p

            def choice_1():
                self._expect('2')
            choice_1()
            if not self.err:
                return

            self.pos = p

            def choice_2():
                self._expect('3')
            choice_2()
            if not self.err:
                return

            self.pos = p

            def choice_3():
                self._expect('4')
            choice_3()
            if not self.err:
                return

            self.pos = p

            def choice_4():
                self._expect('5')
            choice_4()
            if not self.err:
                return

            self.pos = p

            def choice_5():
                self._expect('6')
            choice_5()
            if not self.err:
                return

            self.pos = p

            def choice_6():
                self._expect('7')
            choice_6()
            if not self.err:
                return

            self.pos = p

            def choice_7():
                self._expect('8')
            choice_7()
            if not self.err:
                return

            self.pos = p

            def choice_8():
                self._expect('9')
            choice_8()
        group()

    def _hex_literal_(self):
        """ ('0x'|'0X') hex_digit+:hs -> '0x' + ''.join(hs) """

        def group():
            p = self.pos

            def choice_0():
                self._expect('0x')
            choice_0()
            if not self.err:
                return

            self.pos = p

            def choice_1():
                self._expect('0X')
            choice_1()
        group()
        if self.err:
            return
        vs = []
        self._hex_digit_()
        if self.err:
            return
        vs.append(self.val)
        while not self.err:
            self._hex_digit_()
            if not self.err:
                vs.append(self.val)
        self.val = vs
        self.err = None
        if not self.err:
            v_hs = self.val
        if self.err:
            return
        self.val = '0x' + ''.join(v_hs)
        self.err = None

    def _hex_digit_(self):
        """ ('a'|'b'|'c'|'d'|'e'|'f'|'A'|'B'|'C'|'D'|'E'|'F'|digit) """

        def group():
            p = self.pos

            def choice_0():
                self._expect('a')
            choice_0()
            if not self.err:
                return

            self.pos = p

            def choice_1():
                self._expect('b')
            choice_1()
            if not self.err:
                return

            self.pos = p

            def choice_2():
                self._expect('c')
            choice_2()
            if not self.err:
                return

            self.pos = p

            def choice_3():
                self._expect('d')
            choice_3()
            if not self.err:
                return

            self.pos = p

            def choice_4():
                self._expect('e')
            choice_4()
            if not self.err:
                return

            self.pos = p

            def choice_5():
                self._expect('f')
            choice_5()
            if not self.err:
                return

            self.pos = p

            def choice_6():
                self._expect('A')
            choice_6()
            if not self.err:
                return

            self.pos = p

            def choice_7():
                self._expect('B')
            choice_7()
            if not self.err:
                return

            self.pos = p

            def choice_8():
                self._expect('C')
            choice_8()
            if not self.err:
                return

            self.pos = p

            def choice_9():
                self._expect('D')
            choice_9()
            if not self.err:
                return

            self.pos = p

            def choice_10():
                self._expect('E')
            choice_10()
            if not self.err:
                return

            self.pos = p

            def choice_11():
                self._expect('F')
            choice_11()
            if not self.err:
                return

            self.pos = p

            def choice_12():
                self._digit_()
            choice_12()
        group()

    def _frac_(self):
        """ '.' digit*:ds -> ''.join(ds) """
        self._expect('.')
        if self.err:
            return
        vs = []
        while not self.err:
            self._digit_()
            if not self.err:
                vs.append(self.val)
        self.val = vs
        self.err = None
        if not self.err:
            v_ds = self.val
        if self.err:
            return
        self.val = ''.join(v_ds)
        self.err = None

    def _exp_(self):
        """ ('e'|'E') ('+'|'-'):s digit*:ds -> 'e' + s + ''.join(ds)|('e'|'E') digit*:ds -> 'e' + ''.join(ds) """
        p = self.pos

        def choice_0():

            def group():
                p = self.pos

                def choice_0():
                    self._expect('e')
                choice_0()
                if not self.err:
                    return

                self.pos = p

                def choice_1():
                    self._expect('E')
                choice_1()
            group()
            if self.err:
                return

            def group():
                p = self.pos

                def choice_0():
                    self._expect('+')
                choice_0()
                if not self.err:
                    return

                self.pos = p

                def choice_1():
                    self._expect('-')
                choice_1()
            group()
            if not self.err:
                v_s = self.val
            if self.err:
                return
            vs = []
            while not self.err:
                self._digit_()
                if not self.err:
                    vs.append(self.val)
            self.val = vs
            self.err = None
            if not self.err:
                v_ds = self.val
            if self.err:
                return
            self.val = 'e' + v_s + ''.join(v_ds)
            self.err = None
        choice_0()
        if not self.err:
            return

        self.pos = p

        def choice_1():

            def group():
                p = self.pos

                def choice_0():
                    self._expect('e')
                choice_0()
                if not self.err:
                    return

                self.pos = p

                def choice_1():
                    self._expect('E')
                choice_1()
            group()
            if self.err:
                return
            vs = []
            while not self.err:
                self._digit_()
                if not self.err:
                    vs.append(self.val)
            self.val = vs
            self.err = None
            if not self.err:
                v_ds = self.val
            if self.err:
                return
            self.val = 'e' + ''.join(v_ds)
            self.err = None
        choice_1()
