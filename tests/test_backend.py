from unittesting import DeferrableTestCase

import sublime
from SublimeLinter.lint import (
    Linter,
    linter as linter_module,
    backend,
)


class TestCloningLinters(DeferrableTestCase):
    def create_view(self, window):
        view = window.new_file()
        self.addCleanup(self.close_view, view)
        return view

    def close_view(self, view):
        view.set_scratch(True)
        view.close()

    def test_independent_linters_inherit_settings_from_parent(self):
        view = self.create_view(sublime.active_window())
        settings = linter_module.LinterSettings({}, {})
        linter = Linter(view, settings)

        cloneA, cloneB = backend.create_n_independent_linters(linter, 2)
        self.assertIsNot(cloneA, linter)
        self.assertIsNot(cloneB, linter)

        linter.settings['foo'] = 'bar'
        self.assertIn('foo', cloneA.settings)
        self.assertIn('foo', cloneB.settings)

    def test_independent_linter_do_not_share_their_own_settings(self):
        view = self.create_view(sublime.active_window())
        settings = linter_module.LinterSettings({}, {})
        linter = Linter(view, settings)
        cloneA, cloneB = backend.create_n_independent_linters(linter, 2)

        cloneA.settings['a'] = 'foo'
        cloneB.settings['a'] = 'bar'
        self.assertEqual('foo', cloneA.settings['a'])
        self.assertEqual('bar', cloneB.settings['a'])
