import subprocess
from textwrap import dedent

from unittesting import DeferrableTestCase

from SublimeLinter.tests.mockito import (
    unstub,
    verify,
    when,
)

from SublimeLinter.lint import util


class TestCheckOutput(DeferrableTestCase):
    def teardown(self):
        unstub()

    def test_emits_nicely_formatted_warning(self):
        when(util.logger).warning(...)

        cmd = ["python", "--foo"]
        returncode = 2
        output = bytes(dedent("""\
        unknown option --foo
        unknown option --foo
        unknown option --foo
        usage: python [option] ... [-c cmd | -m mod | file | -] [arg] ...
        Try `python -h' for more information.
        """.rstrip()), "utf8")
        when(subprocess).check_output(...).thenRaise(
            subprocess.CalledProcessError(returncode, cmd, output)
        )
        try:
            util.check_output(cmd)
        except Exception:
            ...

        verify(util.logger).warning("""\
Executing `python --foo` failed
  Command '['python', '--foo']' returned non-zero exit status 2.
  ...
  unknown option --foo
  unknown option --foo
  unknown option --foo
  usage: python [option] ... [-c cmd | -m mod | file | -] [arg] ...
  Try `python -h' for more information.""")

    def test_accepts_any_exception(self):
        when(util.logger).warning(...)
        when(subprocess).check_output(...).thenRaise(Exception("some message"))

        cmd = ["python", "--foo"]
        try:
            util.check_output(cmd)
        except Exception:
            ...

        verify(util.logger).warning("""\
Executing `python --foo` failed
  some message""")
