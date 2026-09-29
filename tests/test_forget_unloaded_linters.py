import sys
import types
from unittest import TestCase, mock

import sublime
from SublimeLinter import sublime_linter
from SublimeLinter.lint import Linter, persist


class TestForgetUnloadedLinters(TestCase):
    def setUp(self):
        persist.linter_classes.clear()
        self.addCleanup(persist.linter_classes.clear)

    def make_linter(self, module):
        linter_name = module.split('.')[0].lower()

        class FakeLinter(Linter):
            name = linter_name
            defaults = {'selector': '*'}
            cmd = 'fake_linter'

        # The metaclass registered the class already; claim it belongs to the
        # plugin module `module`, as a real linter package's class would.
        FakeLinter.__module__ = module
        FakeLinter.plugin_name = module.split('.')[0]
        return FakeLinter

    def test_linter_of_a_module_that_is_not_loaded_is_forgotten(self):
        # What Sublime leaves behind after a linter package was removed: the
        # plugin module is popped from `sys.modules`, the class stays registered.
        klass = self.make_linter('SublimeLinter-gone.linter')
        self.assertNotIn('SublimeLinter-gone.linter', sys.modules)
        self.assertIn(klass.name, persist.linter_classes)

        self.assertEqual(persist.forget_unloaded_linters(), [klass.name])
        self.assertNotIn(klass.name, persist.linter_classes)

    def test_linter_of_a_loaded_module_is_kept(self):
        klass = self.make_linter('SublimeLinter-here.linter')

        with mock.patch.dict(sys.modules, {'SublimeLinter-here.linter': types.ModuleType('x')}):
            self.assertEqual(persist.forget_unloaded_linters(), [])

        self.assertIn(klass.name, persist.linter_classes)

    def test_linter_of_a_disabled_package_is_forgotten(self):
        klass = self.make_linter('SublimeLinter-off.linter')

        with mock.patch.dict(sys.modules, {'SublimeLinter-off.linter': types.ModuleType('x')}):
            self.assertEqual(persist.forget_unloaded_linters({'Other'}), [])
            self.assertIn(klass.name, persist.linter_classes)

            self.assertEqual(persist.forget_unloaded_linters({'SublimeLinter-off'}), [klass.name])

        self.assertNotIn(klass.name, persist.linter_classes)

    def test_relints_only_when_something_was_forgotten(self):
        # Registering a linter class runs commands itself, so create them first
        self.make_linter('SublimeLinter-here.linter')

        with mock.patch.object(sublime, 'run_command') as run_command:
            with mock.patch.dict(sys.modules, {'SublimeLinter-here.linter': types.ModuleType('x')}):
                sublime_linter.forget_unloaded_linters()
            run_command.assert_not_called()

        self.make_linter('SublimeLinter-gone.linter')

        with mock.patch.object(sublime, 'run_command') as run_command:
            with mock.patch.dict(sys.modules, {'SublimeLinter-here.linter': types.ModuleType('x')}):
                sublime_linter.forget_unloaded_linters()
            run_command.assert_called_once_with('sublime_linter_config_changed')
