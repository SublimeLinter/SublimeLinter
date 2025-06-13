import logging
import os
from threading import Lock

from unittesting import DeferrableTestCase
from SublimeLinter.tests.parameterized import parameterized as p
from SublimeLinter.tests.mockito import captor, unstub, verify, when

import sublime
from SublimeLinter.lint import Linter, backend, persist
from SublimeLinter.lint.generic_text_command import replace_view_content


class _BaseTestCase(DeferrableTestCase):
    @classmethod
    def setUpClass(cls):
        s = sublime.load_settings("Preferences.sublime-settings")
        s.set("close_windows_when_empty", False)
        # make sure we have a window to work with
        sublime.run_command("new_window")
        cls.window = window = sublime.active_window()
        cls.addClassCleanup(lambda: window.run_command('close_window'))

    @classmethod
    def tearDownClass(cls):
        unstub()

    def setUp(self):
        persist.linter_classes.clear()

    def tearDown(self):
        persist.linter_classes.clear()
        unstub()

    def create_view(self, window):
        view = window.new_file()
        self.addCleanup(self.close_view, view)
        return view

    def close_view(self, view):
        view.set_scratch(True)
        view.close()


ALL_MODES = ['on_save', 'on_load', 'on_modified']


class TestLinterElection(_BaseTestCase):
    def test_happy_path(self):
        class FakeLinter(Linter):
            defaults = {'selector': ''}
            cmd = 'fake_linter_1'

        when(backend.orchestrator).submit(...).thenReturn(None)

        view = self.create_view(self.window)
        backend.lint(view, lambda: False, Lock(), 'on_user_request')

        verify(backend.orchestrator).submit(...)

    @p.expand([
        ('on_user_request',),
        ('config_changed',),
        ('on_load',),
        ('on_modified',),
        ('on_save',),
    ])
    def test_background_capable_linter_responds_to_every_reason(self, reason):
        class FakeLinter(Linter):
            defaults = {'selector': '', 'lint_mode': ALL_MODES}
            cmd = 'fake_linter_1'
        when(backend.orchestrator).submit(...).thenReturn(None)
        view = self.create_view(self.window)
        backend.lint(view, lambda: False, Lock(), reason)
        verify(backend.orchestrator).submit(...)

    @p.expand([
        (reason, lint_mode, ok)
        for lint_mode, reasons in {
            'background': [
                ('on_user_request', True),
                ('config_changed', True),
                ('on_save', True),
                ('on_load', True),
                ('on_modified', True),
            ],
            'load_save': [
                ('on_user_request', True),
                ('config_changed', True),
                ('on_save', True),
                ('on_load', True),
                ('on_modified', False),
            ],
            'save': [
                ('on_user_request', True),
                ('config_changed', True),
                ('on_save', True),
                ('on_load', False),
                ('on_modified', False),
            ],
            'manual': [
                ('on_user_request', True),
                ('config_changed', True),
                ('on_save', False),
                ('on_load', False),
                ('on_modified', False),
            ],
            ('on_modified',): [
                ('on_user_request', True),
                ('config_changed', True),
                ('on_save', False),
                ('on_load', False),
                ('on_modified', True),
            ],
            ('on_load',): [
                ('on_user_request', True),
                ('config_changed', True),
                ('on_save', False),
                ('on_load', True),
                ('on_modified', False),
            ],
            ('on_save',): [
                ('on_user_request', True),
                ('config_changed', True),
                ('on_save', True),
                ('on_load', False),
                ('on_modified', False),
            ],
            ('on_modified', 'on_load'): [
                ('on_user_request', True),
                ('config_changed', True),
                ('on_save', False),
                ('on_load', True),
                ('on_modified', True),
            ],
            ('on_modified', 'on_save'): [
                ('on_user_request', True),
                ('config_changed', True),
                ('on_save', True),
                ('on_load', False),
                ('on_modified', True),
            ],
            ('on_load', 'on_save'): [
                ('on_user_request', True),
                ('config_changed', True),
                ('on_save', True),
                ('on_load', True),
                ('on_modified', False),
            ],
            ('on_modified', 'on_load', 'on_save'): [
                ('on_user_request', True),
                ('config_changed', True),
                ('on_save', True),
                ('on_load', True),
                ('on_modified', True),
            ],
        }.items()
        for reason, ok in reasons
    ])
    def test_background_capable_linter_matches_reason_and_lint_mode(self, reason, lint_mode, ok):
        class FakeLinter(Linter):
            defaults = {'selector': '', 'lint_mode': lint_mode}
            cmd = 'fake_linter_1'
        when(backend.orchestrator).submit(...).thenReturn(None)
        view = self.create_view(self.window)
        backend.lint(view, lambda: False, Lock(), reason)
        verify(backend.orchestrator, times=1 if ok else 0).submit(...)

    @p.expand([
        ('on_user_request',),
        ('config_changed',),
    ])
    def test_unknown_reason_message(self, reason):
        class FakeLinter(Linter):
            defaults = {'selector': ''}
            cmd = 'fake_linter_1'
        when(backend.orchestrator).submit(...).thenReturn(None)
        when(FakeLinter.logger).info(...).thenReturn(None)
        view = self.create_view(self.window)
        backend.lint(view, lambda: False, Lock(), reason)
        verify(FakeLinter.logger).info(
            f"fakelinter: Lint reason '{reason}' is okay."
        )

    @p.expand([
        (reason, lint_mode)
        for lint_mode, reasons in {
            'background': ['on_save', 'on_load', 'on_modified'],
            'load_save':  ['on_save', 'on_load'],                 # noqa: E241
            'save':       ['on_save'],                            # noqa: E241
        }.items()
        for reason in reasons
    ])
    def test_known_reason_ok_message(self, reason, lint_mode):
        class FakeLinter(Linter):
            defaults = {'selector': '', 'lint_mode': lint_mode}
            cmd = 'fake_linter_1'
        when(backend.orchestrator).submit(...).thenReturn(None)
        when(FakeLinter.logger).isEnabledFor(logging.INFO).thenReturn(True)
        when(FakeLinter.logger).info(...).thenReturn(None)
        view = self.create_view(self.window)
        backend.lint(view, lambda: False, Lock(), reason)
        verify(FakeLinter.logger).info(
            f"fakelinter: Checking lint mode '{lint_mode}' vs lint reason '{reason}'.  Ok."
        )

    @p.expand([
        (reason, lint_mode)
        for lint_mode, reasons in {
            'background': [],
            'load_save':  ['on_modified'],                        # noqa: E241
            'save':       ['on_modified', 'on_load'],             # noqa: E241
            'manual':     ['on_modified', 'on_load', 'on_save']   # noqa: E241
        }.items()
        for reason in reasons
    ])
    def test_known_reason_skip_message(self, reason, lint_mode):
        class FakeLinter(Linter):
            defaults = {'selector': '', 'lint_mode': lint_mode}
            cmd = 'fake_linter_1'
        when(backend.orchestrator).submit(...).thenReturn(None)
        when(FakeLinter.logger).isEnabledFor(logging.INFO).thenReturn(True)
        when(FakeLinter.logger).info(...).thenReturn(None)
        view = self.create_view(self.window)
        backend.lint(view, lambda: False, Lock(), reason)
        verify(FakeLinter.logger).info(
            f"fakelinter: Checking lint mode '{lint_mode}' vs lint reason '{reason}'.  Skip linting."
        )

    def test_complex_lint_mode_formatting(self):
        class FakeLinter(Linter):
            defaults = {'selector': '', 'lint_mode': ('on_load', 'on_save')}
            cmd = 'fake_linter_1'
        when(backend.orchestrator).submit(...).thenReturn(None)
        when(FakeLinter.logger).isEnabledFor(logging.INFO).thenReturn(True)
        when(FakeLinter.logger).info(...).thenReturn(None)
        view = self.create_view(self.window)
        backend.lint(view, lambda: False, Lock(), 'on_modified')
        verify(FakeLinter.logger).info(
            "fakelinter: Checking lint mode 'on_load, on_save' vs lint reason 'on_modified'.  Skip linting."
        )

    @p.expand([
        ('unknown',),
        (('on_load', 'unknown'),),
    ])
    def test_unknown_lint_mode_error_message(self, lint_mode):
        class FakeLinter(Linter):
            defaults = {'selector': '', 'lint_mode': lint_mode}
            cmd = 'fake_linter_1'
        when(backend.orchestrator).submit(...).thenReturn(None)
        when(FakeLinter.logger).warning(...).thenReturn(None)
        view = self.create_view(self.window)
        backend.lint(view, lambda: False, Lock(), 'on_modified')
        verify(FakeLinter.logger).warning(
            "fakelinter: Unknown lint mode 'unknown'.  "
            "Check your SublimeLinter settings for typos."
        )

    def test_unknown_lint_mode_will_lint(self):
        class FakeLinter(Linter):
            defaults = {'selector': '', 'lint_mode': 'unknown'}
            cmd = 'fake_linter_1'
        when(backend.orchestrator).submit(...).thenReturn(None)
        view = self.create_view(self.window)
        backend.lint(view, lambda: False, Lock(), 'on_modified')
        verify(backend.orchestrator).submit(...)

    @p.expand([
        ('on_user_request',),
        ('config_changed',),
        ('on_load',),
        ('on_modified',),
        ('on_save',),
    ])
    def test_tempfile_linter_responds_to_every_reason(self, reason):
        class FakeLinter(Linter):
            defaults = {'selector': '', 'lint_mode': ALL_MODES}
            cmd = 'fake_linter_1'
            tempfile_suffix = 'py'
        when(backend.orchestrator).submit(...).thenReturn(None)
        view = self.create_view(self.window)
        backend.lint(view, lambda: False, Lock(), reason)
        verify(backend.orchestrator).submit(...)

    @p.expand([
        ('on_user_request',),
        ('config_changed',),
        ('on_load',),
        ('on_modified',),
        ('on_save',),
    ])
    def test_file_only_linter_skip_on_unsaved_file(self, reason):
        class FakeLinter(Linter):
            defaults = {'selector': '', 'lint_mode': ALL_MODES}
            cmd = 'fake_linter_1'
            tempfile_suffix = '-'

        when(backend.orchestrator).submit(...).thenReturn(None)
        view = self.create_view(self.window)
        when(view).file_name().thenReturn(None)
        when(view).is_dirty().thenReturn(False)
        backend.lint(view, lambda: False, Lock(), reason)

        verify(backend.orchestrator, times=0).submit(...)

    @p.expand([
        ('on_user_request',),
        ('config_changed',),
        ('on_load',),
        ('on_modified',),
        ('on_save',),
    ])
    def test_file_only_linter_skip_on_dirty_file(self, reason):
        class FakeLinter(Linter):
            defaults = {'selector': '', 'lint_mode': ALL_MODES}
            cmd = 'fake_linter_1'
            tempfile_suffix = '-'

        when(backend.orchestrator).submit(...).thenReturn(None)
        view = self.create_view(self.window)
        when(os.path).exists("some_filename.txt").thenReturn(True)
        when(view).file_name().thenReturn("some_filename.txt")
        when(view).is_dirty().thenReturn(True)
        backend.lint(view, lambda: False, Lock(), reason)

        verify(backend.orchestrator, times=0).submit(...)

    @p.expand([
        ('background', True),
        ('load_save', True),
        ('save', True),
        ('manual', False),
        (['on_load'], False),
        (['on_save'], True),
        (['on_modified'], True),
    ])
    def test_file_only_linter_lint_on_save(self, lint_mode, ok):
        class FakeLinter(Linter):
            defaults = {'selector': '', 'lint_mode': lint_mode}
            cmd = 'fake_linter_1'
            tempfile_suffix = '-'

        when(backend.orchestrator).submit(...).thenReturn(None)
        view = self.create_view(self.window)
        when(os.path).exists("some_filename.txt").thenReturn(True)
        when(view).file_name().thenReturn("some_filename.txt")
        when(view).is_dirty().thenReturn(False)
        backend.lint(view, lambda: False, Lock(), "on_save")

        verify(backend.orchestrator, times=1 if ok else 0).submit(...)

    def test_log_info_if_no_assignable_linter(self):
        class FakeLinter(Linter):
            defaults = {'selector': 'foobar'}
            cmd = 'fake_linter_1'

        when(backend.logger).info(...).thenReturn(None)

        view = self.create_view(self.window)
        backend.lint(view, lambda: False, Lock(), 'on_user_request')

        verify(backend.logger).info(
            "No installed linter matches the view."
        )

    def test_log_if_no_linter_installed(self):
        when(backend.logger).info(...).thenReturn(None)

        view = self.create_view(self.window)
        backend.lint(view, lambda: False, Lock(), 'on_user_request')

        verify(backend.logger).info(
            "No installed linter matches the view."
        )

    def test_only_run_requested_linter(self):
        class FakeLinter(Linter):
            defaults = {'selector': ''}
            cmd = 'fake_linter_1'

        job = captor()
        when(backend.orchestrator).submit(...).thenReturn(None)

        view = self.create_view(self.window)
        backend.lint(view, lambda: False, Lock(), 'on_user_request', only_run=set(["fakelinter"]))

        verify(backend.orchestrator).submit(any, job, ...)
        self.assertEqual(job.value.linter_name, "fakelinter")

    def test_log_if_requested_linter_is_not_assigned(self):
        class FakeLinter(Linter):
            defaults = {'selector': ''}
            cmd = 'fake_linter_1'

        when(backend.logger).info(...).thenReturn(None)

        view = self.create_view(self.window)
        backend.lint(view, lambda: False, Lock(), 'on_user_request', only_run=set(["fuke"]))

        verify(backend.logger).info(
            "Requested linter fuke is not assigned to the view."
        )

    def test_log_if_requested_linter_is_not_assigned_format2(self):
        class FakeLinter(Linter):
            defaults = {'selector': ''}
            cmd = 'fake_linter_1'

        when(backend.logger).info(...).thenReturn(None)

        view = self.create_view(self.window)
        backend.lint(view, lambda: False, Lock(), 'on_user_request', only_run=set(["fuke", "fork"]))

        verify(backend.logger).info(
            "Requested linters fork and fuke are not assigned to the view."
        )

    def test_log_if_requested_linter_is_not_assigned_format3(self):
        class FakeLinter(Linter):
            defaults = {'selector': ''}
            cmd = 'fake_linter_1'

        when(backend.logger).info(...).thenReturn(None)

        view = self.create_view(self.window)
        backend.lint(view, lambda: False, Lock(), 'on_user_request', only_run=set(["fuke", "fork", "fark"]))

        verify(backend.logger).info(
            "Requested linters fark, fork and fuke are not assigned to the view."
        )

    def test_cells_dont_trigger_by_default(self):
        class FakeLinter(Linter):
            defaults = {'selector': 'source.python'}
            cmd = 'fake_linter_1'
        when(backend.orchestrator).submit(...).thenReturn(None)

        view = self.create_view(self.window)
        view.assign_syntax("scope:text.html.markdown.multimarkdown")
        replace_view_content(view, MARDOWN_WITH_CELL)

        backend.lint(view, lambda: False, Lock(), 'on_user_request')
        verify(backend.orchestrator, times=0).submit(...)

    def test_cells_optionally_trigger(self):
        class FakeLinter(Linter):
            defaults = {
                'selector': 'source.python',
                'enable_cells': True,
            }
            cmd = 'fake_linter_1'
        when(backend.orchestrator).submit(...).thenReturn(None)

        view = self.create_view(self.window)
        view.assign_syntax("scope:text.html.markdown.multimarkdown")
        replace_view_content(view, MARDOWN_WITH_CELL)

        backend.lint(view, lambda: False, Lock(), 'on_user_request')
        verify(backend.orchestrator, times=1).submit(...)

    def test_cells_forcefully_do_not_trigger(self):
        class FakeLinter(Linter):
            defaults = {
                'selector': 'source.python',
                'enable_cells': False,
            }
            cmd = 'fake_linter_1'
        when(backend.orchestrator).submit(...).thenReturn(None)

        view = self.create_view(self.window)
        view.assign_syntax("scope:text.html.markdown.multimarkdown")
        replace_view_content(view, MARDOWN_WITH_CELL)

        backend.lint(view, lambda: False, Lock(), 'on_user_request')
        verify(backend.orchestrator, times=0).submit(...)


MARDOWN_WITH_CELL = """\
Hello

```python
foo = 2
```

World!
"""
