.. include:: defines.inc

Settings
==================
Most of the settings that affect |sl|’s user interface are available through commands and menu items. But there are some |sl| settings that can only be changed manually in settings files. In addition to |sl|’s settings, each linter may define its own settings, which usually must be changed manually as well.


.. _settings-stack:

Settings stack
--------------
When |sl| (or a linter plugin) asks for a setting value, |sl| merges settings from several sources to calculate the value. The settings sources can be visualized as a stack, with settings at the top taking precedence over settings lower down:

.. code-block:: none

    Inline overrides
    Inline settings
    Project settings
    User settings
    Default settings

After the default, user, and project settings are merged, :ref:`tokens <settings-tokens>` are replaced within the settings. Each of the settings sources is covered in detail :ref:`below <settings-sources>`.


Setting types
-------------
There are three distinct types of settings:

Global
~~~~~~
Global settings control |sl|’s behavior and apply to all views. For example, the ``"error_color"`` setting determines the color of error marks and applies to all views. Defaults for all global settings are defined in the |sl| default settings and may only be modified within the user settings.

Linter
~~~~~~
Linter settings apply only to a specific named linter. Linter settings are always defined within a ``"linters"`` object whose subobjects are named according to the lowercase class name of the linter. For an example, see the `user settings`_ sample below.

Meta
~~~~
Meta settings are special settings whose names begin with ``"@"``. When defined at the global level, their value is applied to the settings of every linter. For example, when you select the :ref:`Disable Linting <disabling-all-linters>` command, |sl| sets the meta setting ``"@disable"`` to ``true`` at the global level, which is applied to all linters.

Meta settings may also be set within a single linter’s settings, and in that case they apply only to that linter.

.. note::

   A meta setting at the global level overrides the same linter meta setting. For example, even if ``"@disable"`` is ``true`` within a linter’s settings, setting ``"@disable"`` to ``false`` at the global level will override the linter setting and enable that linter.


.. _settings-sources:

Settings sources
----------------
Let’s take a look at each of the settings sources in the stack, starting from the base level and working our way up.


Project settings
~~~~~~~~~~~~~~~~
|sl| project settings are defined by a ``"SublimeLinter"`` object within Sublime Text’s project settings. These settings apply to all files within the project.

.. note::

   Only meta-settings and linter settings are recognized in project settings.

Project settings are opened from the ``Project > Edit Project`` menu. Here is an example project settings file with some |sl| settings:

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
                    "excludes": [
                        "*/test/**"
                    ],
                    "ignore": "W"
                }
            }
        }
    }

.. note::

    Be sure you are **not** putting the ``"SublimeLinter"`` object inside the ``settings`` object. They should be sibling objects in the root document.

Unlike user settings, project settings are not filled in by |sl|; you are responsible for adding any settings you wish to apply to files in the project.


.. _settings-tokens:

Setting tokens
--------------
After the default, user and project settings are merged, SublimeLinter iterates over all settings values and replaces the following tokens with their current values:

=================== =========================================================================
Token               Value
=================== =========================================================================
${sublime}          The full path to the Sublime Text packages directory
${project}          The full path to the project’s parent directory, if available.
${directory}        The full path to the parent directory of the current view’s file.
${home}             The full path to the current user’s home directory.
${env:x}            The environment variable 'x'.
=================== =========================================================================

Please note:

- Directory paths do **not** include a trailing directory separator.

- ``${project}`` and ``${directory}`` expansion are dependent on a file being open in a window, and thus may not work when running lint reports.

- The environment variables available to the ``${env:x}`` token are those available within the Sublime Text python context, which is a very limited subset of those available within a command line shell.

Project and parent directory paths are especially useful if you want to load specific configuration files for a linter.
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
