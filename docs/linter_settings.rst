Linter Settings
===============
Each linter plugin is can provide its own settings. SublimeLinter already provides these for every linter:


disable
--------
Disables the linter.

args
----
Specifies extra arguments to pass to an external binary.

The value may be a string or an array. If it is a string, it will be parsed as if it were passed on a command line. For example, these values are equivalent:

.. code-block:: json

    {
        "args": "--foo=bar --bar=7 --no-baz"
    }

    {
        "args": [
            "--foo=bar",
            "--bar=7",
            "--no-baz"
        ]
    }

The default value is an empty array.


chdir
-----
This setting specifies the linter working directory.

The value must be a string, corresponding to a valid directory path.

.. code-block:: json

    {
        "chdir": "${project}"
    }

With the above example, the linter will get invoked from the ``${project}`` directory (see :ref:`Setting Tokens <settings-tokens>` for more info on using tokens).

.. note::

     If the value of ``chdir`` is unspecified (or inaccessible), then:

     - If linting an unsaved file, the directory is unchanged

     - If linting a saved file, the directory is set to that of the linted file


excludes
--------
This setting specifies a list of path patterns to exclude from linting. If there is only a single pattern, the value may be a string. Otherwise it must be an array of patterns.

Patterns are matched against a file’s **absolute path** with all symlinks/shortcuts resolved, using |_fnmatch|. This means to match a filename, you must match everything in the path before the filename. For example, to exclude any python files whose name begins with “foo”, you would use this pattern:

.. code-block:: json

    {
        "excludes": "*/foo*.py"
    }

The default value is an empty array.

