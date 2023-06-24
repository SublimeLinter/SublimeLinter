Linter Settings
===============

SublimeLinter provides the following settings that are applicable to every linter. Please note that each linter plugin may introduce additional settings. For more details on specific linter settings, please refer to the respective READMEs of the linter plugins.


args
----
Specifies extra arguments to pass to an external binary.

The value may be a string or an array. If it is a string,
it will be parsed as if it were passed on a command line.
For example, these values are equivalent:

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

The default value is `nil`, not-set.


disable
-------
Disables the linter, either `true` or `false`.

.. attention::

    The default is "not-set".
    Please note that we differentiate three states for `disable`.


disable_if_not_dependency - *Python/Node only*
~~~~~~~~~~~~~~~~~~~~~~~~

For both, Python and Node, SublimeLinter has sophisticated ways to find *locally* installed tools.

When the `disable_if_not_dependency` setting is set to `true`, SublimeLinter will not attempt to use globally installed binaries if a local installation cannot be found. Instead, it will skip linting such projects altogether.

env
---

Set additional environment variables.

.. code-block:: json

    {
        "env": "{'GEM_HOME': '~/foo/bar'}"
    }

If you want to edit your PATH, note that we support :ref:`Settings Expansion
<settings-expansion>` here, as everywhere else, as it is very convenient in
this case. For example:

.. code-block:: json

    {
        "env": {
            "PATH": "~/path/to/bin:$PATH"
        }
    }


excludes
--------
This setting specifies a list of path patterns to exclude from linting.
If there is only a single pattern, the value may be a string.
Otherwise it must be an array of patterns.

Patterns are matched against a file's **absolute path** with all symlinks/shortcuts resolved.
This means to match a filename, you must match everything in the path before the filename.
For example, to exclude any python files whose name begins with “foo”, you would use this pattern:

.. code-block:: json

    {
        "excludes": "*/foo*.py"
    }

The default value is `nil`, not-set.

Untitled views can be ignored with ``<untitled>``.
Use ``!`` to negate a pattern.

For example, exclude everything outside of the main window folder:

.. code-block:: json

    {
        "excludes": "!${folder}*",
    }

Note that :ref:`Settings Expansion <settings-expansion>` can be used here as well.


executable
----------
At any time you can manually set the executable a linter should use. This can
be a string or a list.

.. code-block:: json

    {
        "executable": "${folder}/node_modules/bin/eslint",
        "executable": ["py", "-3", "-m", "flake8"],
        "executable": ["nvm", "exec", "8.9", "eslint"]
    }

See :ref:`Settings Expansion <settings-expansion>` for more info on using variables.


python - *Python only*
~~~~~~~~~~~~~~~~~~~~~~

When configuring Python-based linters, you have the option to use the `python` setting instead of `executable`. The `python` setting allows you to specify a path to a Python binary on your system or, alternatively, a version string. If you provide a version string, SublimeLinter will attempt to locate a Python binary matching that version in your system's PATH (except on Windows, where `py.exe` is used directly if installed).

.. code-block:: json

    {
        "python": "3.10"
    }

With this configuration, SublimeLinter will execute commands such as `/path/to/python310/python -m flake8` or `py -3.10 -m mypy`.


filter_errors
-------------

This defines a post filter to suppress some problems a linter might report.
(Useful if the linter cannot be configured very well.)

The value may be a string or an array of strings. Each string is handled as
a case-insensitive regex pattern, and then matched against the error type, code (or rule), and message of a particular lint problem. If it matches, the lint error will be thrown away.

.. note::

    This will completely suppress the matching errors. If you only want to visually demote some errors, take a look at the :ref:`styles <linter_styles>` section below.

Some examples:

.. code-block:: javascript

    {
        // suppress all warnings
        "filter_errors": "warning: ",

        // suppress a specific eslint rule
        "filter_errors": "no-trailing-spaces: ",

        // suppress some flake8/pyflakes rules,
        "filter_errors": "W3\\d\\d: ",

        // typical html tidy message
        "filter_errors": "missing <!DOCTYPE> declaration"
    }

Be aware of special escaping since what you're writing must be valid JSON.

Technical note: For each reported problem we construct a string "``<error_type>: <error_code>: <error_message``". We then match each regex pattern against that virtual line. We throw away the error if *any* of the patterns match, otherwise we keep it.

lint_mode
---------
Lint Mode determines when the linter is run.

- `background`: asynchronously on every change
- `load_save`: when a file is opened and every time it's saved
- `manual`: only when calling the Lint This View command
- `save`: only when a file is saved


.. _selector:

selector
--------
This defines if when given linter is activated for specific file types.
It should be a string containing a list of comma separated selectors.

For example, by default yamllint is activated only for YAML files (``source.yaml``)
files. But we also want to activate it for ansible files, which have the
``source.ansible`` scope.

To do that, we can override the selector for this linter:

.. code-block:: json

    {
        "linters": {
            "yamllint":
            {
                "selector": "source.yaml, source.ansible"

            },
        }
    }

To find out what selector to use for given file type, use the
"Tools > Developer > Show Scope Name" menu entry.

It's also possible to exclude scopes using the ``-`` operator.
E.g. to disable embedded code in situation where linting doesn't make sense.
ESLint can be disabled for HTML `script` tags with the following:

.. code-block:: json

    {
        "selector": "source.js - text.html.basic"
    }


.. note::

    The selector setting takes precedence over the deprecated `syntax` property.


.. _linter_styles:

styles
------
Styles can be set per linter.

You can change the color (via `scope`), style (`"mark_style"`) or icon per linter, for errors or warnings or other error `types`,
and even for different error `codes` ("rule names") if the plugin reports them.

Example: this changes the appearance of shellcheck warnings:

.. code-block:: json

    {
        "linters": {
            "shellcheck": {
                "styles": [
                    {
                        "mark_style": "stippled_underline",
                        "scope": "region.bluish",
                        "types": ["warning"]
                    }
                ]
            }
        }
    }

Example: this changes the appearance of whitespace warnings in flake8:

.. code-block:: json

    {
        "linters": {
            "flake8": {
                "styles": [
                    {
                        "mark_style": "outline",
                        "scope": "comment",
                        "icon": "none",
                        "codes": ["W291", "W292", "W293"]
                    }
                ]
            }
        }
    }

Note `codes` are actually prefix matchers, so the above could be simplified to
`["W29"]` or even `["W"]`.

.. note::

    If you set both "mark_style" and "icon" to "none", you get a less noisy view and still can see those errors in the panel.

Besides the icons and squiggles (`mark_style`) SublimeLinter also supports
annotations on the right hand side of the view that can reveal the error message
on hover:

.. image:: https://user-images.githubusercontent.com/8558/248409197-1702fd9d-1653-455d-8a3b-3ad74fe5269f.png

.. image:: https://user-images.githubusercontent.com/8558/248409230-4928e75a-592e-49b5-9765-83eecb4e86e4.png

Example: this adds an annotation that reveals more information on hover:

.. code-block:: json

    {
        "linters": {
            "flake8": {
                "styles": [
                    {
                        "annotation": "{code}<br>&nbsp;&nbsp;{msg}",
                    }
                ]
            }
        }
    }

Inline phantoms are also enabled just using styles per linter, per `error_type`, and/or per error `code`:

.. image:: https://user-images.githubusercontent.com/8558/248411042-76e5fc69-d226-4758-8907-0110d2c898ba.png

Example: this adds a so-called phantom, inline and just below the error

.. code-block:: json

    {
        "linters": {
            "flake8": {
                "styles": [
                    {
                        "phantom": "{msg}",
                    }
                ]
            }
        }
    }


working_dir
-----------

The `working_dir` setting specifies the working directory of the subprocess in which the linter runs. It should be a string representing a valid directory path.

As an example, the default is:

.. code-block:: json

    {
        "working_dir": "${project_root:${folder:$file_path}}"
    }

With this configuration, the working directory is determined from left to right using the following precedence: "project_root" (if available), the folder containing the file (if the window is attached to a folder), or the path to the open file. If none of these values are available, the fallback is an empty string, resulting in the working directory being the working directory of Sublime Text's process.

For more information on using variables, please refer to the :ref:`Settings Expansion <settings-expansion>` section.

