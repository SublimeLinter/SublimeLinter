.. include:: defines.inc

Linter Settings
===============
Each linter plugin is responsible for providing its own settings. In addition to the linter-provided settings, |sl| adds the following settings to every linter:


.. _disable-linter-setting:

@disable
--------
This is actually a meta setting that is added to every linter’s settings. For a discussion of the ``@disable`` setting, see :ref:`Meta Settings <disable-meta-setting>`.

Rather than change this setting manually, you can use the user interface to :ref:`disable or enable a linter <toggling-linters>`.


args
----
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
--------
This setting specifies a list of path patterns to exclude from linting. If there is only a single pattern, the value may be a string. Otherwise it must be an array of patterns.

Patterns are matched against a file’s **absolute path** with all symlinks/shortcuts resolved, using |_fnmatch|. This means to match a filename, you must match everything in the path before the filename. For example, to exclude any python files whose name begins with “foo”, you would use this pattern:

.. code-block:: json

    {
        "excludes": "*/foo*.py"
    }

The default value is an empty array.


ignore_match
------------
This setting specifies a `python regular expression`_ that is matched against error messages reported by the linter. If the regular expression matches a message, the error is ignored.

The value of this setting may be:

- A single regular expression pattern string.

- An array of pattern strings.

- A map, where the keys are **lowercase** filename extensions to match (with or without a leading dot), and the values are either single pattern strings or arrays of pattern strings.

.. note::

   The pattern strings are regular JSON strings, not raw strings as you would usually use in python. If you need to escape regular expression pattern characters, be sure to use double backslashes (``\\``). For example, to match ``Undeclared (variable)``, you would have to use the string ``"Undeclared \\(variable\\)"``.

For example, the ``html-tidy`` linter complains if you are editing a portion of a page, as is often the case with ``php``. The errors are:

.. code-block:: none

   missing <!DOCTYPE> declaration
   inserting implicit <body>
   inserting missing 'title' element

Obviously we don’t want to see those errors, because we know they don’t apply in this case. By using the ``ignore_match`` setting, we can ignore them like this:

.. code-block:: json

    {
        "ignore_match": [
            "missing <!DOCTYPE> declaration",
            "inserting implicit <body>",
            "inserting missing 'title' element"
        ]
    }

Of course, since these are regular expressions, we could also do it like this:

.. code-block:: json

    {
        "ignore_match": [
            "missing <!DOCTYPE> declaration",
            "inserting (?:implicit <body>|missing 'title' element)"
        ]
    }

Now let’s suppose you only want the ``ignore_match`` to apply to ``.inc`` files, which we use for partials. We can do that by using a map like this:

.. code-block:: json

    {
        "ignore_match": {
            "inc": [
                "missing <!DOCTYPE> declaration",
                "inserting (?:implicit <body>|missing 'title' element)"
            ]
    }

In :ref:`debug mode <debug-mode>`, |sl| logs each occurrence of an ignore match.

.. note::

   |re-try|
