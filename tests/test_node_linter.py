from functools import partial
import os
import shutil

from unittesting import DeferrableTestCase, AWAIT_WORKER
from SublimeLinter.tests.parameterized import parameterized as p
from SublimeLinter.tests.mockito import (
    contains,
    mock,
    patch,
    unstub,
    verify,
    when,
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
        ('/p',),
        ('/p/a',),
        ('/p/a/b',),
    ])
    def test_locally_installed(self, ROOT_DIR):
        PRESENT_BIN_PATH = os.path.join(ROOT_DIR, 'node_modules', '.bin')

        when(self.view).file_name().thenReturn('/p/a/b/f.js')
        linter = make_fake_linter(self.view)

        when(shutil).which('mylinter', ...).thenReturn(None)
        when(shutil).which('mylinter', path=PRESENT_BIN_PATH).thenReturn('fake.exe')
        patch(
            node_linter, 'paths_upwards_until_home',
            partial(node_linter.paths_upwards_until_home, home='/p')
        )

        cmd = linter.get_cmd()
        working_dir = linter.get_working_dir()
        self.assertEqual(cmd, ['fake.exe'])
        self.assertEqual(working_dir, ROOT_DIR)

    @p.expand([
        ('/p', '/p', {'dependencies': {'mylinter': '0.2'}}),
        ('/p/a', '/p/a', {'devDependencies': {'mylinter': '0.2'}}),
        ('/p/a', '/p', {'devDependencies': {'mylinter': '0.2'}}),
        ('/p/a/b', '/p/a/b', {'devDependencies': {'mylinter': '0.2'}}),
        ('/p/a/b', '/p/a', {'devDependencies': {'mylinter': '0.2'}}),
        ('/p/a/b', '/p', {'devDependencies': {'mylinter': '0.2'}}),
    ])
    def test_locally_installed_with_package_json(self, ROOT_DIR, INSTALL_DIR, CONTENT):
        PRESENT_PACKAGE_FILE = os.path.join(ROOT_DIR, 'package.json')
        PRESENT_BIN_PATH = os.path.join(INSTALL_DIR, 'node_modules', '.bin')

        when(self.view).file_name().thenReturn('/p/a/b/f.js')
        linter = make_fake_linter(self.view)

        exists = os.path.exists
        when(os.path).exists(...).thenAnswer(exists)
        when(os.path).exists(PRESENT_PACKAGE_FILE).thenReturn(True)
        when(shutil).which(...).thenReturn(None)
        when(shutil).which('mylinter', path=PRESENT_BIN_PATH).thenReturn('fake.exe')
        when(node_linter).read_json_file(PRESENT_PACKAGE_FILE).thenReturn(CONTENT)
        patch(
            node_linter, 'paths_upwards_until_home',
            partial(node_linter.paths_upwards_until_home, home='/p')
        )

        cmd = linter.get_cmd()
        working_dir = linter.get_working_dir()
        self.assertEqual(cmd, ['fake.exe'])
        self.assertEqual(working_dir, ROOT_DIR)

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
        ('/p', {'dependencies': {'mylinter': '0.2'}}, 'dependency', False),
        ('/p/a', {'devDependencies': {'mylinter': '0.2'}}, 'devDependency', False),
        ('/p', {'dependencies': {'mylinter': '0.2'}}, 'dependency', True),
        ('/p/a', {'devDependencies': {'mylinter': '0.2'}}, 'devDependency', True),
    ])
    def test_uninstalled_local_dependency(
        self, ROOT_DIR, CONTENT, DEPENDENCY_TYPE, IS_YARN_PROJECT
    ):
        PRESENT_PACKAGE_FILE = os.path.join(ROOT_DIR, 'package.json')

        when(self.view).file_name().thenReturn('/p/a/f.js')
        linter = make_fake_linter(self.view)

        when(linter).notify_failure().thenReturn(None)
        when(node_linter.logger).warning(
            "Skipping 'mylinter' for now which is listed as a {} in {} but "
            "not installed.  Forgot to '{} install'?"
            .format(DEPENDENCY_TYPE, PRESENT_PACKAGE_FILE, 'yarn' if IS_YARN_PROJECT else 'npm')
        ).thenReturn(None)
        exists = os.path.exists
        when(os.path).exists(...).thenAnswer(exists)
        when(os.path).exists(PRESENT_PACKAGE_FILE).thenReturn(True)
        when(os.path).exists(os.path.join(ROOT_DIR, 'yarn.lock')).thenReturn(IS_YARN_PROJECT)
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
        working_dir = linter.get_working_dir()
        self.assertEqual(cmd, [NODE_BIN, SCRIPT_FILE])
        self.assertEqual(working_dir, ROOT_DIR)

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

    @p.expand([
        ({'bin': {'cli': 'fake.js'}},),
        ({'bin': 'otherthing.js'},),
    ])
    def test_ignore_if_bin_does_not_contain_valid_information(self, CONTENT):
        ROOT_DIR = '/p'
        PRESENT_PACKAGE_FILE = os.path.join(ROOT_DIR, 'package.json')
        when(self.view).file_name().thenReturn('/p/a/f.js')
        exists = os.path.exists
        when(os.path).exists(...).thenAnswer(exists)
        when(os.path).exists(PRESENT_PACKAGE_FILE).thenReturn(True)
        when(node_linter).read_json_file(PRESENT_PACKAGE_FILE).thenReturn(CONTENT)
        when(util).which(...).thenReturn('fake.exe')

        linter = make_fake_linter(self.view)
        cmd = linter.get_cmd()
        self.assertEqual(cmd, ['fake.exe'])

    @p.expand([
        ('/p', {'dependencies': {'mylinter': '0.2'}, 'installConfig': {'pnp': True}}, False),
        ('/p/a', {'devDependencies': {'mylinter': '0.2'}, 'installConfig': {'pnp': True}}, False),
        ('/p', {'dependencies': {'mylinter': '0.2'}}, True),
        ('/p/a', {'devDependencies': {'mylinter': '0.2'}}, True),
    ])
    def test_installed_yarn_pnp_project(self, ROOT_DIR, CONTENT, PNP_JS_EXISTS):
        PRESENT_PACKAGE_FILE = os.path.join(ROOT_DIR, 'package.json')
        YARN_BIN = '/path/to/yarn'

        when(self.view).file_name().thenReturn('/p/a/f.js')
        linter = make_fake_linter(self.view)

        exists = os.path.exists
        when(os.path).exists(...).thenAnswer(exists)
        when(os.path).exists(PRESENT_PACKAGE_FILE).thenReturn(True)
        when(os.path).exists(os.path.join(ROOT_DIR, 'yarn.lock')).thenReturn(True)
        when(os.path).exists(os.path.join(ROOT_DIR, '.pnp.js')).thenReturn(PNP_JS_EXISTS)
        when(shutil).which(...).thenReturn(None)
        when(shutil).which('yarn').thenReturn(YARN_BIN)
        when(node_linter).read_json_file(PRESENT_PACKAGE_FILE).thenReturn(CONTENT)

        cmd = linter.get_cmd()
        working_dir = linter.get_working_dir()
        self.assertEqual(cmd, [YARN_BIN, 'run', '--silent', 'mylinter'])
        self.assertEqual(working_dir, ROOT_DIR)

    @p.expand([
        ('/p', {'dependencies': {'mylinter': '0.2'}, 'installConfig': {'pnp': True}}),
        ('/p/a', {'devDependencies': {'mylinter': '0.2'}, 'installConfig': {'pnp': True}}),
        ('/p', {'dependencies': {'mylinter': '0.2'}}, True),
        ('/p/a', {'devDependencies': {'mylinter': '0.2'}}, True),
    ])
    def test_yarn_pnp_project_warn_no_yarn(self, ROOT_DIR, CONTENT, PNP_JS_EXISTS=False):
        PRESENT_PACKAGE_FILE = os.path.join(ROOT_DIR, 'package.json')

        when(self.view).file_name().thenReturn('/p/a/f.js')
        linter = make_fake_linter(self.view)

        when(linter).notify_failure().thenReturn(None)
        when(node_linter.logger).warning(
            "This seems like a Yarn PnP project. However, finding "
            "a Yarn executable failed. Make sure to install Yarn first."
        ).thenReturn(None)
        exists = os.path.exists
        when(os.path).exists(...).thenAnswer(exists)
        when(os.path).exists(PRESENT_PACKAGE_FILE).thenReturn(True)
        when(os.path).exists(os.path.join(ROOT_DIR, 'yarn.lock')).thenReturn(True)
        when(os.path).exists(os.path.join(ROOT_DIR, '.pnp.js')).thenReturn(PNP_JS_EXISTS)
        when(shutil).which(...).thenReturn(None)
        when(node_linter).read_json_file(PRESENT_PACKAGE_FILE).thenReturn(CONTENT)

        try:
            linter.get_cmd()
        except linter_module.PermanentError:
            pass

        verify(node_linter.logger).warning(...)
        verify(linter).notify_failure()

    @p.expand([
        ('/p', {'dependencies': {'mylinter': '0.2'}}),
        ('/p/a', {'devDependencies': {'mylinter': '0.2'}}),
    ])
    def test_yarn_pnp_project_warn_not_completely_installed(self, ROOT_DIR, CONTENT):
        PRESENT_PACKAGE_FILE = os.path.join(ROOT_DIR, 'package.json')
        YARN_BIN = '/path/to/yarn'

        when(self.view).file_name().thenReturn('/p/a/f.js')
        linter = make_fake_linter(self.view)

        when(linter).notify_failure().thenReturn(None)
        when(node_linter.logger).warning(
            "We did execute 'yarn run --silent mylinter' but "
            "'mylinter' cannot be found.  Forgot to 'yarn install'?"
        ).thenReturn(None)
        exists = os.path.exists
        when(os.path).exists(...).thenAnswer(exists)
        when(os.path).exists(PRESENT_PACKAGE_FILE).thenReturn(True)
        when(os.path).exists(os.path.join(ROOT_DIR, 'yarn.lock')).thenReturn(True)
        when(os.path).exists(os.path.join(ROOT_DIR, '.pnp.js')).thenReturn(True)
        when(shutil).which(...).thenReturn(None)
        when(shutil).which('yarn').thenReturn(YARN_BIN)
        when(node_linter).read_json_file(PRESENT_PACKAGE_FILE).thenReturn(CONTENT)
        when(linter)._communicate(...).thenReturn('error Command "mylinter" not found')

        try:
            linter.lint('foo', lambda: False)
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
        backend.lint_view(
            [{'name': linter.name, 'klass': linter.__class__, 'settings': linter.settings}],
            self.view, view_has_changed, sink)

        yield AWAIT_WORKER

        verify(sink).__call__(linter.name, [])
