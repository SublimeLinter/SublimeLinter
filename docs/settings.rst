.. include:: defines.inc

.. _settings-stack:

Settings stack
--------------
When |sl| (or a linter plugin) asks for a setting value, |sl| merges settings from several sources to calculate the value.

.. code-block:: none

    Default settings
    User settings
    Project settings


Setting types
-------------
There are three distinct types of settings:

Global
~~~~~~
Global settings control |sl|’s behavior and apply to all views. Defaults for all global settings are defined in the |sl| default settings and may be modified with the user settings.

Linter
~~~~~~
Linter settings apply only to a specific named linter. Linter settings are always defined within a ``"linters"`` object whose subobjects are named according to the lowercase class name of the linter. For an example, see the `user settings`_ sample below.

Project settings
~~~~~~~~~~~~~~~~
|sl| project settings are defined by a ``"SublimeLinter"`` object within Sublime Text’s project settings. Here you can change linter settings for a project.

Project settings are opened from the ``Project > Edit Project`` menu. Here is an example project settings file where the flake8 linter has been disabled:

.. code-block:: json

    {
        "folders":
        [
            {
                "follow_symlinks": true,
                "path": "/Users/aparajita/Projects/SublimeLinter"
            }
        ],
        "SublimeLinter":
        {
            "linters":
            {
                "flake8": {
                    "disable": true
                }
            }
        }
    }

.. note::

    Be sure you are **not** putting the ``"SublimeLinter"`` object inside the ``settings`` object. They should be sibling objects in the root document.


.. _settings-tokens:

Setting tokens
--------------
After the default, user and project settings are merged, SublimeLinter iterates over all settings values and replaces the following tokens with their current values:

=================== =========================================================================
Token               Value
=================== =========================================================================
${sublime}          The full path to the Sublime Text packages directory.
${project}          The full path to the project file's parent directory, if available.
${root}             The full path to the root folder of the current view in project or folder mode. Falls back to `${directory}` in single file mode.
${directory}        The full path to the parent directory of the current view’s file.
${home}             The full path to the current user’s home directory.
${env:x}            The environment variable 'x'.
=================== =========================================================================

Please note:

- Directory paths do **not** include a trailing directory separator.

- ``${project}``, ``${root}`` and ``${directory}`` expansions are dependent on a file being open in a window, and thus may not work when running lint reports.

- The environment variables available to the ``${env:x}`` token are those available within the Sublime Text python context, which is a very limited subset of those available within a command line shell.

Project, root and parent directory paths are especially useful if you want to load specific configuration files for a linter.
For example, you could use the ``${project}`` and ``${home}`` tokens in your project settings:

.. code-block:: json

    {
        "folders":
        [
            {
                "follow_symlinks": true,
                "path": "/Users/tinytim/Projects/Tulips"
            }
        ],
        "SublimeLinter":
        {
            "linters":
            {
                "phpcs": {
                    "standard": "${project}/build/phpcs/MyPHPCS"
                },
                "phpmd": {
                    "args": ["${home}/phpmd-ruleset.xml"]
                }
            }
        }
    }

After token replacement, SublimeLinter sees the linter settings as:

.. code-block:: json

    {
        "linters":
        {
            "phpcs": {
                "standard": "/Users/tinytim/Projects/Tulips/build/phpcs/MyPHPCS"
            },
            "phpmd": {
                "args": ["/Users/tinytim/phpmd-ruleset.xml"]
            }
        }
    }
