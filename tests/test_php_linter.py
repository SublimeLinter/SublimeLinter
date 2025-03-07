import os
import shutil

from unittesting import DeferrableTestCase, AWAIT_WORKER
from SublimeLinter.tests.parameterized import parameterized as p
from SublimeLinter.tests.mockito import (
    contains,
    mock,
    spy2,
    unstub,
    verify,
    when,
)

import sublime
from SublimeLinter import lint
from SublimeLinter.lint import elect, backend, linter as linter_module, util
from SublimeLinter.lint.base_linter import php_linter


def make_fake_linter(view):
    class FakeLinter(lint.PhpLinter):
        cmd = "mylinter"
        defaults = {"selector": "foo"}

    settings = linter_module.get_linter_settings(FakeLinter, view)
    return FakeLinter(view, settings)


class TestPhpLinters(DeferrableTestCase):
    @classmethod
    def setUpClass(cls):
        cls.view = sublime.active_window().new_file()
        # make sure we have a window to work with
        s = sublime.load_settings("Preferences.sublime-settings")
        s.set("close_windows_when_empty", False)

        # it's just faster if we mock this out
        when(linter_module).register_linter(...).thenReturn(None)

    @classmethod
    def tearDownClass(cls):
        if cls.view:
            cls.view.set_scratch(True)
            cls.view.close()

        unstub()

    def tearDown(self):
        unstub()

    def create_view(self, window):
        view = window.new_file()
        self.addCleanup(self.close_view, view)
        return view

    def close_view(self, view):
        view.set_scratch(True)
        view.close()

    def patch_home(self, home):
        previous_state = util.HOME
        util.HOME = home
        self.addCleanup(lambda: setattr(util, "HOME", previous_state))

    def test_globally_installed(self):
        linter = make_fake_linter(self.view)

        when(util).which(...).thenReturn("fake.exe")

        cmd = linter.get_cmd()
        self.assertEqual(cmd, ["fake.exe"])

    def test_warn_if_not_globally_installed(self):
        linter = make_fake_linter(self.view)

        when(linter.logger).warning(...).thenReturn(None)

        cmd = linter.get_cmd()
        self.assertEqual(cmd, None)

        verify(linter.logger).warning(...)

    @p.expand([
        ("/p",),
        ("/p/a",),
        ("/p/a/b",),
    ])
    def test_locally_installed(self, ROOT_DIR):
        PRESENT_BIN_PATH = os.path.join(ROOT_DIR, "vendor", "bin")
        PRESENT_COMPOSER_FILE = os.path.join(ROOT_DIR, "composer.json")
        spy2(os.path.exists)
        when(os.path).exists(PRESENT_COMPOSER_FILE).thenReturn(True)
        when(php_linter).read_json_file(PRESENT_COMPOSER_FILE).thenReturn({"key": "value"})

        when(self.view).file_name().thenReturn("/p/a/b/f.js")
        linter = make_fake_linter(self.view)

        when(shutil).which("mylinter", ...).thenReturn(None)
        when(shutil).which("mylinter", path=PRESENT_BIN_PATH).thenReturn("fake.exe")

        cmd = linter.get_cmd()
        self.assertEqual(cmd, ["fake.exe"])
        working_dir = linter.get_working_dir()
        self.assertEqual(working_dir, ROOT_DIR)

    @p.expand([
        ("/p",),
        ("/p/a",),
        ("/p/a/b",),
    ])
    def test_executing_bin_script(self, ROOT_DIR):
        PRESENT_COMPOSER_FILE = os.path.join(ROOT_DIR, "composer.json")
        spy2(os.path.exists)
        when(os.path).exists(PRESENT_COMPOSER_FILE).thenReturn(True)
        when(php_linter).read_json_file(PRESENT_COMPOSER_FILE).thenReturn(
            {"bin": ["someBin", "./scripts/mylinter"]}
        )

        when(self.view).file_name().thenReturn("/p/a/b/f.js")
        linter = make_fake_linter(self.view)

        cmd = linter.get_cmd()
        self.assertEqual(cmd, [os.path.normpath(os.path.join(ROOT_DIR, "scripts/mylinter"))])

    @p.expand([
        ("/p",),
        ("/p/a",),
        ("/p/a/b",),
    ])
    def test_cant_read_composer_file(self, ROOT_DIR):
        PRESENT_COMPOSER_FILE = os.path.join(ROOT_DIR, "composer.json")
        spy2(os.path.exists)
        when(os.path).exists(PRESENT_COMPOSER_FILE).thenReturn(True)

        when(self.view).file_name().thenReturn("/p/a/b/f.js")
        linter = make_fake_linter(self.view)

        when(linter).notify_failure().thenReturn(None)
        when(linter.logger).warning(
            contains(
                "We found a 'composer.json' at {}; however, reading it raised".format(
                    ROOT_DIR
                )
            )
        ).thenReturn(None)

        try:
            linter.get_cmd()
        except linter_module.PermanentError:
            pass

        verify(linter.logger).warning(...)
        verify(linter).notify_failure()

    def test_disable_if_not_dependency(self):
        linter = make_fake_linter(self.view)
        linter.settings['disable_if_not_dependency'] = True

        when(linter).notify_unassign().thenReturn(None)
        when(linter.logger).info(...).thenReturn(None)

        try:
            linter.get_cmd()
        except linter_module.PermanentError:
            pass

        verify(linter.logger).info(
            "Skipping 'fakelinter' since it is not installed locally.\nYou "
            "can change this behavior by setting 'disable_if_not_dependency' "
            "to 'false'."
        )
        verify(linter).notify_unassign()

    def test_disable_if_not_dependency_2(self):
        linter = make_fake_linter(self.view)
        linter.settings['disable_if_not_dependency'] = True

        view_has_changed = lambda: False
        sink = mock()
        when(sink).__call__(...).thenReturn(None)
        backend.lint_view(
            [
                elect.LinterInfo(
                    name=linter.name,
                    klass=linter.__class__,
                    settings=linter.settings,
                    context=linter.context,
                    regions=[sublime.Region(0, 10)],
                    runnable=True
                )
            ],
            self.view, view_has_changed, sink
        )

        yield AWAIT_WORKER
        yield AWAIT_WORKER

        verify(sink).__call__(linter.name, [])
