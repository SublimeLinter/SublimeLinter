Creating a linter plugin
========================

Use the `template repo <https://github.com/SublimeLinter/SublimeLinter-template>`_
to get started on your plugin. It contains a how-to with all the information you need.

The SublimeLinter `package control channel <https://github.com/SublimeLinter/package_control_channel>`_
lists all existing plugins, you can find examples there too.

To publish your plugin, start a `PR <https://github.com/SublimeLinter/package_control_channel/pulls>`_.


Mandatory things
----------------

All linter plugins must be subclasses of either ``SublimeLinter.lint.Linter`` or  one of its specialized subclasses, ``SublimeLinter.lint.NodeLinter`` for Node based linters, ``SublimeLinter.lint.PythonLinter`` for Python linters, ``SublimeLinter.lint.RubyLinter`` for Ruby, and finally ``SublimeLinter.lint.PhpLinter`` for PHP .

The specialized subclasses usually provide better lookup for local executables, and may find and set the correct project root directory which in turn should help the linter itself in finding and using their correct configuration files.

Node, Python, and Php linters also implement the user setting ``disable_if_not_dependency`` to never use globally installed linters, and Ruby adds support for ``rvm`` and ``bundle``.

.. note::

   If the language specific Linter does something obviously wrong or is too limited, consider making a change and submitting a pull request against the SublimeLinter framework instead of implementing a fix in your specific plugin.  Your fix or enhancement might benefit everyone using the framework.

After deciding which class to inherit from, you define a class for the integration. For example::

    class ESLint(NodeLinter):
        ...

    # or

    class Flake8(PythonLinter):
        ...

Notice how the name of the class is just the name of tool you're integrating to.  We use this name everywhere, in the settings, in the status bar, so beware that name changes are breaking changes.

.. hint::

    If you need funny characters in the name, like "c#", you can use the attribute :ref:`name`.

    .. code-block:: python

        class MyLinter(Linter):
            name = 'c#'
            ...

    This allows you to use the custom name in the settings and other places.

You may now just save the file, and the class will try to register itself with SublimeLinter.  However, you additionally need to define at least three things, the ``cmd``, the ``selector``, and very likely the ``regex``, well unless you want to parse JSON output.

1. ``cmd``: a string or a sequence of strings that describes the command we should run.

E.g.::

    cmd = "flake8 --format=foo -"
    cmd = ("flake8", "--format=foo", "-")


.. note ::

    Although the correct and final type is "List of arguments", strings are just fine and very readable as long as we can split them.  (We use Python's ``shlex.split`` function for that if you're curious.)  Use the sequence format if quoting of the command is likely an issue, for example because you need spaces or special characters in the command.


.. hint::

    If you need more dynamism, you can make ``cmd`` a method that will return the command::

        def cmd(self):
            # Do something
            return "flake8 --format=foo -"

    The return *type* is the same as before.

By default, SublimeLinter will run he linter in "stdin" mode, but you can change that.  For detailed documentation refer to the :ref:`cmd <not_stdin>`.

2. ``selector``: the default selector that specifies for which views the linter should be enabled or run.  The ``selector`` is not a top-level attribute but placed inside the ``defaults`` mapping, to make it overridable by users.  For example::

    defaults = {
        "selector": "source.python",
    }

.. hint::

    To find out what selector to use for a given file, use the
    "Tools > Developer > Show Scope Name" menu entry (``ctrl+alt+shift+p``). Likely it will show a very detailed scope, the first part is usually what you're after.

3. ``regex``: a regular expression that is matched against each line of the linter output.  This regex *must* use named patterns.  For example::

    regex = (
        r'^(?P<filename>.+?):'
        r'(?P<line>\d+):(?P<col>\d+): '
        r'(?P<message>.*)'
    )

Only ``message`` and ``line`` are mandatory fields here, but usually you also capture ``col``, ``error_type`` (e.g. "warning", "error"), and ``code`` (the name of the rule, e.g. "E302" or "no-console-log").  You can omit ``filename`` if the linter emits for only one file at a time anyways.  You can also report ``end_line`` and ``end_col`` but that is seldom.

.. note::

    If you only report ``col``, SublimeLinter will select the word beginning at that column.  What a word is, is defined by the :ref:`word_re` attribute.

.. note::

    If the linter prints multiple lines per error you can prepend ``(?m)`` to switch to :ref:`multiline` mode.

.. hint::

    You can also let the linter emit JSON and parse that.  In this case, set ``regex = None`` and implement ``find_errors`` instead.  `eslint <https://github.com/SublimeLinter/SublimeLinter-eslint>`_ is a comprehensive, sophisticated example for that.
