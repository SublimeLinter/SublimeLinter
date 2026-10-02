from unittest import TestCase, mock

import sublime
from SublimeLinter import sublime_linter
from SublimeLinter.lint import Linter, persist


def make_linter(package):
    linter_name = package.lower()

    class FakeLinter(Linter):
        name = linter_name
        defaults = {'selector': '*'}
        cmd = 'fake_linter'

    # The metaclass registered the class already; claim it belongs to the
    # plugin `package`, as a real linter package's class would.
    FakeLinter.__module__ = package + '.linter'
    FakeLinter.plugin_name = package
    return FakeLinter


class TestForgetLintersOfPackages(TestCase):
    def setUp(self):
        persist.linter_classes.clear()
        self.addCleanup(persist.linter_classes.clear)

    def test_linters_of_the_given_packages_are_forgotten(self):
        gone = make_linter('SublimeLinter-gone')
        kept = make_linter('SublimeLinter-kept')

        self.assertEqual(persist.forget_linters_of_packages({'SublimeLinter-gone'}), [gone.name])

        self.assertNotIn(gone.name, persist.linter_classes)
        self.assertIn(kept.name, persist.linter_classes)

    def test_unknown_packages_forget_nothing(self):
        kept = make_linter('SublimeLinter-kept')

        self.assertEqual(persist.forget_linters_of_packages({'Vintage', 'Other'}), [])
        self.assertEqual(persist.forget_linters_of_packages(set()), [])

        self.assertIn(kept.name, persist.linter_classes)


class TestOnPreferencesChanged(TestCase):
    def setUp(self):
        persist.linter_classes.clear()
        self.addCleanup(persist.linter_classes.clear)

        # Registering a linter class runs commands itself, so create it first
        self.klass = make_linter('SublimeLinter-off')

    def changed(self, before, after):
        """Run the observer for an `ignored_packages` change; return the mocked `run_command`."""
        with mock.patch.object(sublime_linter, 'ignored_packages', set(before)):
            with mock.patch.object(sublime_linter, 'get_ignored_packages', return_value=set(after)):
                with mock.patch.object(sublime, 'run_command') as run_command:
                    sublime_linter.on_preferences_changed()
                    self.assertEqual(sublime_linter.ignored_packages, set(after))
                    return run_command

    def test_newly_disabled_package_forgets_its_linter_and_relints_once(self):
        run_command = self.changed(before={'Vintage'}, after={'Vintage', 'SublimeLinter-off'})

        self.assertNotIn(self.klass.name, persist.linter_classes)
        run_command.assert_called_once_with('sublime_linter_config_changed')

    def test_unrelated_preferences_change_does_nothing(self):
        run_command = self.changed(before={'Vintage'}, after={'Vintage'})

        self.assertIn(self.klass.name, persist.linter_classes)
        run_command.assert_not_called()

    def test_newly_disabled_package_without_a_linter_does_not_relint(self):
        run_command = self.changed(before=set(), after={'Vintage'})

        self.assertIn(self.klass.name, persist.linter_classes)
        run_command.assert_not_called()

    def test_package_that_was_already_disabled_is_not_processed_again(self):
        # e.g. a linter registered again by an upgrade while the package is still listed
        run_command = self.changed(before={'SublimeLinter-off'}, after={'SublimeLinter-off', 'Vintage'})

        self.assertIn(self.klass.name, persist.linter_classes)
        run_command.assert_not_called()

    def test_enabling_a_package_does_not_forget_anything(self):
        run_command = self.changed(before={'SublimeLinter-off'}, after=set())

        self.assertIn(self.klass.name, persist.linter_classes)
        run_command.assert_not_called()
