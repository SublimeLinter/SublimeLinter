import os
import shutil

from unittesting import DeferrableTestCase, AWAIT_WORKER
from SublimeLinter.tests.parameterized import parameterized as p
from SublimeLinter.tests.mockito import (
    verify,
    when,
    unstub,
    mock,
    contains
)

import sublime
from SublimeLinter import lint
from SublimeLinter.lint import (
    backend,
    linter as linter_module,
    util
)
from SublimeLinter.lint.base_linter import node_linter


def make_fake_linter(view):
    class FakeLinter(lint.NodeLinter):
        cmd = 'mylinter'
        defaults = {
            'selector': 'foo'
        }
    settings = linter_module.get_linter_settings(FakeLinter, view)
    return FakeLinter(view, settings)


class TestNodeLinters(DeferrableTestCase):
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

    def test_globally_installed(self):
        linter = make_fake_linter(self.view)

        when(util).which(...).thenReturn('fake.exe')

        cmd = linter.get_cmd()
        self.assertEqual(cmd, ['fake.exe'])

    def test_not_globally_installed_warn(self):
        linter = make_fake_linter(self.view)

        when(linter_module.logger).warning(...).thenReturn(None)

        cmd = linter.get_cmd()
        self.assertEqual(cmd, None)

        verify(linter_module.logger).warning(...)

    @p.expand([
        (os.path.join('/p', 'node_modules', '.bin'),),
        (os.path.join('/p/a', 'node_modules', '.bin'),),
    ])
    def test_locally_installed(self, PRESENT_BIN_PATH):
        when(self.view).file_name().thenReturn('/p/a/f.js')
        linter = make_fake_linter(self.view)

        when(shutil).which('mylinter', ...).thenReturn(None)
        when(shutil).which('mylinter', path=PRESENT_BIN_PATH).thenReturn('fake.exe')

        cmd = linter.get_cmd()
        self.assertEqual(cmd, ['fake.exe'])

    @p.expand([
        ('/p',),
        ('/p/a',),
    ])
    def test_uninstalled_local_dependency_cant_read_package_json(self, ROOT_DIR):
        PRESENT_PACKAGE_FILE = os.path.join(ROOT_DIR, 'package.json')

        when(self.view).file_name().thenReturn('/p/a/f.js')
        linter = make_fake_linter(self.view)

        when(linter).notify_failure().thenReturn(None)
        when(node_linter.logger).warning(
            contains(
                "We found a 'package.json' at {}; however, reading it raised"
                .format(ROOT_DIR)
            )
        ).thenReturn(None)
        exists = os.path.exists
        when(os.path).exists(...).thenAnswer(exists)
        when(os.path).exists(PRESENT_PACKAGE_FILE).thenReturn(True)

        try:
            linter.get_cmd()
        except linter_module.PermanentError:
            pass

        verify(node_linter.logger).warning(...)
        verify(linter).notify_failure()

    @p.expand([
        ('/p', {'dependencies': {'mylinter': '0.2'}}, 'dependency'),
        ('/p/a', {'devDependencies': {'mylinter': '0.2'}}, 'devDependency'),
    ])
    def test_uninstalled_local_dependency(self, ROOT_DIR, CONTENT, DEPENDENCY_TYPE):
        PRESENT_PACKAGE_FILE = os.path.join(ROOT_DIR, 'package.json')

        when(self.view).file_name().thenReturn('/p/a/f.js')
        linter = make_fake_linter(self.view)

        when(linter).notify_failure().thenReturn(None)
        when(node_linter.logger).warning(
            "Skipping 'mylinter' for now which is listed as a {} in {} but "
            "not installed.  Forgot to 'npm install'?"
            .format(DEPENDENCY_TYPE, PRESENT_PACKAGE_FILE)
        ).thenReturn(None)
        exists = os.path.exists
        when(os.path).exists(...).thenAnswer(exists)
        when(os.path).exists(PRESENT_PACKAGE_FILE).thenReturn(True)
        when(node_linter).read_json_file(PRESENT_PACKAGE_FILE).thenReturn(CONTENT)

        try:
            linter.get_cmd()
        except linter_module.PermanentError:
            pass

        verify(node_linter.logger).warning(...)
        verify(linter).notify_failure()

    @p.expand([
        ('/p', {'bin': {'mylinter': 'fake.js'}}),
        ('/p/a', {'bin': {'mylinter': 'fake.js'}}),
    ])
    def test_executing_bin_script(self, ROOT_DIR, CONTENT):
        PRESENT_PACKAGE_FILE = os.path.join(ROOT_DIR, 'package.json')
        BIN_FOLDER = os.path.join(ROOT_DIR, 'node_modules', '.bin')
        SCRIPT_FILE = os.path.normcase(os.path.join(ROOT_DIR, 'fake.js'))
        NODE_BIN = '/x/node'

        when(self.view).file_name().thenReturn('/p/a/f.js')
        linter = make_fake_linter(self.view)

        exists = os.path.exists
        when(os.path).exists(...).thenAnswer(exists)
        when(os.path).exists(PRESENT_PACKAGE_FILE).thenReturn(True)
        when(os.path).exists(BIN_FOLDER).thenReturn(True)
        when(node_linter).read_json_file(PRESENT_PACKAGE_FILE).thenReturn(CONTENT)
        when(linter).which('node').thenReturn(NODE_BIN)

        cmd = linter.get_cmd()
        self.assertEqual(cmd, [NODE_BIN, SCRIPT_FILE])

    @p.expand([
        ('/p', {'bin': {'mylinter': 'fake.js'}}),
        ('/p/a', {'bin': {'mylinter': 'fake.js'}}),
    ])
    def test_executing_bin_script_warn_prior_install(self, ROOT_DIR, CONTENT):
        PRESENT_PACKAGE_FILE = os.path.join(ROOT_DIR, 'package.json')
        SCRIPT_FILE = os.path.normcase(os.path.join(ROOT_DIR, 'fake.js'))

        when(self.view).file_name().thenReturn('/p/a/f.js')
        linter = make_fake_linter(self.view)

        when(linter).notify_failure().thenReturn(None)
        when(node_linter.logger).warning(
            "We want to execute 'node {}'; but you should first 'npm install' "
            "this project."
            .format(SCRIPT_FILE)
        ).thenReturn(None)
        exists = os.path.exists
        when(os.path).exists(...).thenAnswer(exists)
        when(os.path).exists(PRESENT_PACKAGE_FILE).thenReturn(True)
        when(node_linter).read_json_file(PRESENT_PACKAGE_FILE).thenReturn(CONTENT)

        try:
            linter.get_cmd()
        except linter_module.PermanentError:
            pass

        verify(node_linter.logger).warning(...)
        verify(linter).notify_failure()

    @p.expand([
        ('/p', {'bin': {'mylinter': 'fake.js'}}),
        ('/p/a', {'bin': {'mylinter': 'fake.js'}}),
    ])
    def test_executing_bin_script_warn_no_node(self, ROOT_DIR, CONTENT):
        PRESENT_PACKAGE_FILE = os.path.join(ROOT_DIR, 'package.json')
        BIN_FOLDER = os.path.join(ROOT_DIR, 'node_modules', '.bin')
        SCRIPT_FILE = os.path.normcase(os.path.join(ROOT_DIR, 'fake.js'))

        when(self.view).file_name().thenReturn('/p/a/f.js')
        linter = make_fake_linter(self.view)

        when(linter).notify_failure().thenReturn(None)
        when(node_linter.logger).warning(
            "We want to execute 'node {}'; however, finding a node executable failed."
            .format(SCRIPT_FILE)
        ).thenReturn(None)
        exists = os.path.exists
        when(os.path).exists(...).thenAnswer(exists)
        when(os.path).exists(PRESENT_PACKAGE_FILE).thenReturn(True)
        when(os.path).exists(BIN_FOLDER).thenReturn(True)
        when(node_linter).read_json_file(PRESENT_PACKAGE_FILE).thenReturn(CONTENT)
        when(linter).which('node').thenReturn(None)

        try:
            linter.get_cmd()
        except linter_module.PermanentError:
            pass

        verify(node_linter.logger).warning(...)
        verify(linter).notify_failure()

    def test_disable_if_not_dependency(self):
        linter = make_fake_linter(self.view)
        linter.settings['disable_if_not_dependency'] = True

        when(linter).notify_unassign().thenReturn(None)
        when(node_linter.logger).info(
            "Skipping 'fakelinter' since it is not installed locally.\nYou "
            "can change this behavior by setting 'disable_if_not_dependency' "
            "to 'false'."
        ).thenReturn(None)

        try:
            linter.get_cmd()
        except linter_module.PermanentError:
            pass

        verify(node_linter.logger).info(...)
        verify(linter).notify_unassign()

    def test_disable_if_not_dependency_2(self):
        linter = make_fake_linter(self.view)
        linter.settings['disable_if_not_dependency'] = True

        view_has_changed = lambda: False
        sink = mock()
        when(sink).__call__(...).thenReturn(None)
        backend.lint_view([linter], self.view, view_has_changed, sink)

        yield AWAIT_WORKER

        verify(sink).__call__(linter, [])
