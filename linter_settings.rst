.. include:: defines.inc

Linter Settings
===============
Each linter plugin is responsible for providing its own settings. In addition to the linter-provided settings, |sl| adds the following settings to every linter:


.. _disable-linter-setting:

@disable
~~~~~~~~
This is actually a meta setting that is added to every linter’s settings. For a discussion of the ``@disable`` setting, see :ref:`Meta Settings <disable-meta-setting>`.

Rather than change this setting manually, you can use the user interface to :ref:`disable or enable a linter <toggling-linters>`.


args
~~~~
This setting specifies extra arguments to pass to an external binary. This is useful when a linter binary supports an option that is not part of the linter’s settings.

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

.. note::

   If a linter runs python code directly, without calling an external binary, it is up to the linter to decide what to do with this setting.


excludes
~~~~~~~~
This setting specifies a list of path patterns to exclude from linting. If there is only a single pattern, the value may be a string. Otherwise it must be an array of patterns.

Patterns are matched against a file’s **absolute path** with all symlinks/shortcuts resolved, using |_fnmatch|. This means to match a filename, you must match everything in the path before the filename. For example, to exclude any python files whose name begins with “foo”, you would use this pattern:

.. code-block:: json

    {
        "excludes": "*/foo*.py"
    }

The default value is an empty array.
