Linter Attributes
=================

The Linter class is designed to allow interfacing with most linter executables
through the configuration of class attributes. Some linters, however, may
require additional steps to set up the execution environment for the linter
executable or perform the linting directly within the linter plugin.  In such
cases, refer to the :doc:`linter method documentation <linter_methods>`.


.. _cmd:

cmd (mandatory)
---------------

A string or a tuple of strings containing the command used to lint. Mandatory
arguments must be placed here so a user cannot override them.  Mandatory
arguments are e.g. the output format of a linter because it must match the
defined :ref:`regex<regex>`.

For example:

.. code-block:: python

    cmd = ('flake8', '--format', 'default', '-')

One of the core features of SublimeLinter is that a user can always provide
additional arguments to the command by using the ``args`` setting.  By default,
we append the arguments to the command but you can also specify where they are
injected.

.. code-block:: python

    cmd = ('flake8', '--format', 'default', '${args}', '-')
    cmd = 'flake8 --format default $args -'

By default, the linter runs in "stdin" mode, which means that we pass the source
code to be linted (usually the contents of the file) through stdin. In this
mode, you can refer to the current file name using ``$file``.

For example:

.. code-block:: python

    cmd = 'eslint --stdin-filename $file'

However, SublimeLinter can also run in "temp_file" or "file_on_disk" mode.
See :ref:`tempfile_suffix` below for more details. In these modes it is
mandatory to refer the currently linted file. In "tempfile" mode, that would
be:

.. code-block:: python

    cmd = 'mypy $temp_file'

In "real"-file mode, it would be:

.. code-block:: python

    cmd = 'pylint $file_on_disk'

.. hint::

    If you don't want to use the command execution system as implemented by SublimeLinter at all, set ``cmd = None`` and implement the ``run`` method on your own.


.. _default_type:

default_type
------------
If the linter output does not provide information which can be captured as ``error_type``,
this attribute is used to determine how to classify the linter error.
The value should be ``"error"`` (the default) or ``"warning"``, but actually any string is allowed.


.. _defaults:

defaults (mandatory)
--------------------

.. note::

    The name "defaults" can be misleading as the attribute is used to declare and define any additional settings and possibly command arguments, while *also* setting default values for all these settings.


.. note::

    All settings mentioned here are user-visible and can be changed in the global or project settings!

Each linter must at least define the mandatory ``"selector"`` setting, which specifies the scopes for which the linter is run.  For example, to select all Python files::

    defaults = {
        "selector": "source.python",
    }

This is the minimum requirement that needs to be set.

Apart from the mandatory setting, you can define internal and external settings. Internal settings can only be used programmatically, and you need to extend or override specific methods to use them.  Generally, you define a setting name with its default value::

    defaults = {
        ...
        "some_flag": False,
    }

and then use it in your plugin code like this:

.. code-block:: python

    if self.settings.get("some_flag"):
        ...

External settings are defined using one of the prefixes `@`, `-`, or `--`, and automatically injected as additional arguments to the command.

For example, you can define::

    defaults = {
        ...
        "-I": [],
    }

If a user now sets:

.. code-block:: json

    {
        "I": ["/path/to/here", "/path/to/there"]
    }

then SublimeLinter will expand the command with ``-I /path/to/here -I /path/to/there``.

If you append a ``=``, like this::


    defaults = {
        "--include=": [],
    }

SublimeLinter will produce for example ``--include=E201``, t.i. the name and the value are joined by ``=`` and form technically a single argument.

The format for defining external settings is as follows:

.. code-block:: text

    <prefix><name><joiner>?<sep>?[+]?

- **prefix** – Either ``@``, ``-`` or ``--``.
- **name** – The name of the setting.
- **joiner** – Either ``=`` or ``:``.
  This is ignored if the ``prefix`` is ``@``.
  If it is ``=``, the setting value is joined with the ``name`` using ``=`` and passed as a single argument.
  If it is ``:`` (the default), the ``name`` and the value are passed as separate arguments.
- **sep** – If a list of values is given,
  ``sep`` specifies the character used to join the *values* (e.g. ``,``).
  This is redundant if **+** is also used.

  For example::

    "--rules,"  # **joiner** is omitted!

  produces something like "--rules a,b,c"

- **+** – If the setting can be a list of values,
  but each value must be passed separately,
  terminate the setting with ``+``.

  .. note::

    Do not use as it is the default!


.. note::

   When building the list of arguments to pass to the linter,
   if the setting value is ``falsy`` (``None``, zero, ``False``, or an empty sequence),
   the argument is not passed to the linter.


error_stream
------------
By default, SublimeLinter capture both ``stdout`` and ``stderr``, but it only parses ``stdout`` for reported problems (called "diagnostics" these days) and expects ``stderr`` generally to be blank.  In fact, if any messages are present on ``stderr``, SublimeLinter considers them as fatal errors.

However, some linters report the diagnostics on ``stderr`` and you have to set this attribute to ``SublimeLinter.lint.STREAM_STDERR`` accordingly.

For completeness, you can also force to only read ``stdout`` by setting the
attribute to ``SublimeLinter.lint.STREAM_STDOUT``.  However, this approach is
not recommended.  If your linter produces noise on ``stderr`` consider
implementing the ``on_stderr`` method instead.  Take a look at the `eslint
plugin <https://github.com/SublimeLinter/SublimeLinter-eslint>`_ as an example.
It filters out deprecation warnings while still keeping other hard errors and
reports them back to the user.


.. _line_col_base:

line_col_base
-------------
This attribute is a tuple that defines the number base used by linters in reporting line and column numbers.
In general, most linters use one-based line numbers and column numbers, so the default value is ``(1, 1)``.
If a linter uses zero-based line numbers or column numbers,
the linter class should define this attribute accordingly.

.. note::

    For example, if the linter reports one-based line numbers but zero-based column numbers,
    the value of this attribute should be ``(1, 0)``.


multiline
---------

.. note::

    You can also set the flag inline ``(?m)`` on the :ref:`regex<regex>` attribute.

This attribute determines whether the :ref:`regex<regex>` attribute parses multiple lines.
The linter may output multiline error messages, but if ``regex`` only parses single lines,
this attribute should be ``False`` (the default).

- If ``multiline`` is ``False``, the linter output is split into lines (using ``str.splitlines``
  and each line is matched against ``regex`` pattern.
- If ``multiline`` is ``True``, the linter output is iterated over using ``re.finditer``
  until no more matches are found.

.. note::

    It is important that you set this flag correctly; it does more than just
    add the ``re.MULTILINE`` flag when it compiles the ``regex`` pattern.


name
----
Usually the name of the linter is derived from the name of the class.
If that doesn't work out, you can also set it explicitly with this attribute.


re_flags
--------
If you wish to add custom ``re flags`` that are used when compiling the :ref:`regex` pattern,
you may specify them here.

For example, if you want the pattern to be case-insensitive, you could do this:

.. code-block:: python

    re_flags = re.IGNORECASE


.. note::

    These flags can also be included within the ``regex`` pattern itself.
    It's up to you which technique you prefer.


.. _regex:

regex (mandatory)
-----------------
A python regular expression pattern used to extract information from the linter's output.
The pattern must contain at least the following named capture groups:

+-----------+-----------------------------------------------------------------+
| Name      | Description                                                     |
+===========+=================================================================+
| line      | The line number on which the problem occurred                   |
+-----------+-----------------------------------------------------------------+
| message   | The description of the problem                                  |
+-----------+-----------------------------------------------------------------+

In addition to the above capture groups,
the pattern should contain the following named capture groups when possible:

+------------+-----------------------------------------------------------------+
| Name       | Description                                                     |
+============+=================================================================+
| col        | The column number where the error occurred, or                  |
|            | a string whose length provides the column number                |
+------------+-----------------------------------------------------------------+
| error_type | The error type, e.g. "error" or "warning"                       |
|            |                                                                 |
+------------+-----------------------------------------------------------------+
| code       | The corresponding error code given by the linter, if supported. |
+------------+-----------------------------------------------------------------+

You can also capture ``end_line`` and ``end_col``, otherwise the :ref:`word<word_re>` beginning at ``col`` will be highlighted.  How the numbers are interpreted is defined by :ref:`line_col_base`.

If you can't capture the ``error_type`` directly, you may use ``error`` and ``warning`` to set the type.  Alterantively, you fallback to :ref:`default_type`.

+------------+-----------------------------------------------------------------+
| error      | If this is not empty, the error will be marked                  |
|            | as an error by SublimeLinter                                    |
+------------+-----------------------------------------------------------------+
| warning    | If this is not empty, the error will be marked                  |
|            | as a warning by SublimeLinter                                   |
+------------+-----------------------------------------------------------------+

You can also just search the source code line for a word to highlight:

+-----------++-----------------------------------------------------------------+
| near       | If the linter does not provide a column number but              |
|            | mentions a name, match the name with this capture               |
|            | group and SublimeLinter will attempt to highlight that name.    |
|            | Enclosing single or double quotes will be stripped,             |
|            | you may include them in the capture group. If the               |
|            | linter provides a column number, you may still use              |
|            | this capture group and SublimeLinter will highlight that text   |
|            | (stripped of quotes) exactly.                                   |
+------------+-----------------------------------------------------------------+


.. _tempfile_suffix:

tempfile_suffix
---------------
This attribute configures the behaviour of linter executables that cannot receive input from ``stdin``.

If the linter executable require input from a file,
SublimeLinter can automatically create a temp file from the current code
and pass that file to the linter executable.
To enable automatic temp file creation,
set this attribute to the suffix of the temp file name (with or without a leading ``.``).


File-only linters
~~~~~~~~~~~~~~~~~
Some linters can only work from an actual disk file, because they rely on an
entire directory structure that cannot be realistically be copied to a temp directory.
In such cases, you can mark a linter as *file-only* by setting :ref:`tempfile_suffix` to ``-``.

File-only linters will only run on files that have not been modified since their last save,
ensuring that what the user sees and what the linter executable sees is in sync.


.. _word_re:

word_re
-------
If a linter reports a column position, SublimeLinter highlights the nearest word at that point.
By default, SublimeLinter uses the regex pattern ``r'^([-\w]+)'`` to determine what is a word.
You can customize the regex used to highlight words by setting this attribute to a pattern string or a compiled regex.
