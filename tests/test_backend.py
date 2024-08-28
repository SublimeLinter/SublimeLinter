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
        cloneA, cloneB = settings.copy(), settings.copy()

        self.assertIsNot(cloneA, settings)
        self.assertIsNot(cloneB, settings)

        settings['foo'] = 'bar'
        self.assertIn('foo', cloneA)
        self.assertIn('foo', cloneB)

    def test_independent_settings_do_not_share_their_own_settings(self):
        settings = linter_module.LinterSettings({}, {})
        cloneA, cloneB = settings.copy(), settings.copy()

        cloneA['a'] = 'foo'
        cloneB['a'] = 'bar'
        self.assertEqual('foo', cloneA['a'])
        self.assertEqual('bar', cloneB['a'])

    def test_parent_context_is_shared_after_cloning_settings(self):
        settings = linter_module.LinterSettings({}, {})
        cloneA, cloneB = settings.copy().context, settings.copy().context

        self.assertIsNot(cloneA, settings)
        self.assertIsNot(cloneB, settings)

        settings.context['foo'] = 'bar'
        self.assertIn('foo', cloneA)
        self.assertIn('foo', cloneB)

    def test_contexts_are_independent_after_cloning_settings(self):
        settings = linter_module.LinterSettings({}, {})
        cloneA, cloneB = settings.copy().context, settings.copy().context

        cloneA['a'] = 'foo'
        cloneB['a'] = 'bar'
        self.assertEqual('foo', cloneA['a'])
        self.assertEqual('bar', cloneB['a'])
