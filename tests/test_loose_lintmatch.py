from unittesting import DeferrableTestCase

from SublimeLinter.lint.linter import LintMatch


class TestLooseLintMatch(DeferrableTestCase):
    def test_attribute_access(self):
        m = object()
        match = {
            "match": m,
            "line": 1,
            "col": 2,
            "error": "error_txt",
            "warning": "warning_txt",
            "message": "message_txt",
            "near": "near_txt"
        }

        rv = LintMatch(**match)

        self.assertEqual(rv.match, m)
        self.assertEqual(rv.line, 1)
        self.assertEqual(rv.col, 2)
        self.assertEqual(rv.error, "error_txt")
        self.assertEqual(rv.warning, "warning_txt")
        self.assertEqual(rv.message, "message_txt")
        self.assertEqual(rv.near, "near_txt")

    def test_attribute_access_returns_defaults_for_missing_common_names(self):
        rv = LintMatch()

        for k in (
            "match", "line", "col", "error", "warning", "message", "near",
            "filename", "error_type", "code", "end_line", "end_col",
        ):
            self.assertEqual(getattr(rv, k), '' if k == 'message' else None)

    def test_unknown_keys_raise_on_attribute_access(self):
        rv = LintMatch()

        try:
            rv.foo
        except AttributeError as e:
            self.assertEqual(str(e), "'LintMatch' object has no attribute 'foo'")
        except Exception:
            self.fail('Should have thrown AttributeError.')
        else:
            self.fail('Should have thrown AttributeError.')

    def test_self_repr(self):
        rv = LintMatch(foo='bar')

        self.assertEqual(str(rv), "LintMatch({'foo': 'bar'})")
        self.assertEqual(eval(repr(rv)), rv)

    def test_copy_lint_match(self):
        rv = LintMatch(foo='bar')

        self.assertEqual(rv.copy(), rv)
        self.assertEqual(type(rv.copy()), LintMatch)

    def test_double_star_unpacking_to_dict(self):
        m = object()
        match = {
            "match": m,
            "line": 1,
            "col": 2,
            "error": "error_txt",
            "warning": "warning_txt",
            "message": "message_txt",
            "near": "near_txt"
        }

        expected = LintMatch(match)
        actual = dict(**expected)
        self.assertEqual(actual, expected)

    def test_tuple_like_unpacking(self):
        m = object()
        match = {
            "match": m,
            "line": 1,
            "col": 2,
            "error": "error_txt",
            "warning": "warning_txt",
            "message": "message_txt",
            "near": "near_txt"
        }
        rv = LintMatch(**match)

        match, line, col, error, warning, message, near = rv

        self.assertEqual(match, m)
        self.assertEqual(line, 1)
        self.assertEqual(col, 2)
        self.assertEqual(error, "error_txt")
        self.assertEqual(warning, "warning_txt")
        self.assertEqual(message, "message_txt")
        self.assertEqual(near, "near_txt")

    def test_tuple_like_index_access(self):
        m = object()
        match = {
            "match": m,
            "line": 1,
            "col": 2,
            "error": "error_txt",
            "warning": "warning_txt",
            "message": "message_txt",
            "near": "near_txt"
        }
        rv = LintMatch(**match)

        self.assertEqual(rv[0], m)
        self.assertEqual(rv[1], 1)
        self.assertEqual(rv[2], 2)
        self.assertEqual(rv[3], "error_txt")
        self.assertEqual(rv[4], "warning_txt")
        self.assertEqual(rv[5], "message_txt")
        self.assertEqual(rv[6], "near_txt")

        self.assertRaises(IndexError, lambda: rv[7])

    def test_namedtuple_like_mutating(self):
        rv = LintMatch({'foo': 'bar'})
        rv2 = rv._replace(foo='baz')

        self.assertEqual(rv2.foo, 'baz')

        # unlike namedtuple LintMatch is mutable
        self.assertEqual(rv.foo, 'baz')

    def test_standard_items_access(self):
        m = object()
        match = {
            "match": m,
            "line": 1,
            "col": 2,
            "error": "error_txt",
            "warning": "warning_txt",
            "message": "message_txt",
            "near": "near_txt"
        }
        rv = LintMatch(**match)

        self.assertEqual(rv['match'], m)
        self.assertEqual(rv['line'], 1)
        self.assertEqual(rv['col'], 2)
        self.assertEqual(rv['error'], "error_txt")
        self.assertEqual(rv['warning'], "warning_txt")
        self.assertEqual(rv['message'], "message_txt")
        self.assertEqual(rv['near'], "near_txt")

    def test_standard_item_access_throws_on_unknown_keys(self):
        rv = LintMatch()

        self.assertRaises(KeyError, lambda: rv['line'])

    def test_create_from_tuple(self):
        m = object()
        match = (m, 1, 2, "error_txt", "warning_txt", "message_txt", "near_txt")
        actual = LintMatch(*match)
        expected = LintMatch({
            "match": m,
            "line": 1,
            "col": 2,
            "error": "error_txt",
            "warning": "warning_txt",
            "message": "message_txt",
            "near": "near_txt"
        })

        self.assertEqual(actual, expected)
