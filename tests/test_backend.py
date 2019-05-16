from unittesting import DeferrableTestCase

from SublimeLinter.lint import (
    linter as linter_module,
)


class TestCloningSettings(DeferrableTestCase):
    def create_view(self, window):
        view = window.new_file()
        self.addCleanup(self.close_view, view)
        return view

    def close_view(self, view):
        view.set_scratch(True)
        view.close()

    def test_independent_settings_inherit_settings_from_parent(self):
        settings = linter_module.LinterSettings({}, {})
        cloneA, cloneB = settings.clone(), settings.clone()

        self.assertIsNot(cloneA, settings)
        self.assertIsNot(cloneB, settings)

        settings['foo'] = 'bar'
        self.assertIn('foo', cloneA)
        self.assertIn('foo', cloneB)

    def test_independent_settings_do_not_share_their_own_settings(self):
        settings = linter_module.LinterSettings({}, {})
        cloneA, cloneB = settings.clone(), settings.clone()

        cloneA['a'] = 'foo'
        cloneB['a'] = 'bar'
        self.assertEqual('foo', cloneA['a'])
        self.assertEqual('bar', cloneB['a'])
