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
    .sublimelinterrc settings
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


Default settings
~~~~~~~~~~~~~~~~
Default settings are defined by |sl| and by each linter. You should **never** edit the default settings, as your changes may be overwritten the next time |sl| is updated. You should **always** edit the user settings (or other settings higher in the stack).


User settings
~~~~~~~~~~~~~
User settings are located in :file:`Packages/User/SublimeLinter.sublime-settings`. You should consider this to be the global settings for |sl| and its linters. To make it easier to remember what settings are available, whenever you open the user settings, they are filled in with any missing default settings from |sl| and from all installed linters.

Here is an example user settings file:

.. code-block:: json

    {
        "user": {
            "debug": false,
            "delay": 0.25,
            "error_color": "D02000",
            "gutter_theme": "Packages/SublimeLinter/gutter-themes/Knob/simple/Knob - simple.gutter-theme",
            "gutter_theme_excludes": [],
            "lint_mode": "background",
            "linters": {
                "csslint": {
                    "@disable": false,
                    "args": [],
                    "excludes": []
                },
                "flake8": {
                    "@disable": false,
                    "args": [],
                    "excludes": [],
                    "ignore": "",
                    "max-complexity": -1,
                    "max-line-length": null,
                    "select": ""
                }
            },
            "mark_style": "outline",
            "paths": {
                "*": [],
                "linux": [],
                "osx": [],
                "windows": []
            },
            "python_paths": {
                "linux": [],
                "osx": [],
                "windows": []
            },
            "rc_search_limit": 3,
            "show_errors_on_save": false,
            "show_marks_in_minimap": true,
            "syntax_map": {
                "php": "html"
            },
            "warning_color": "DDB700",
            "wrap_find": true
        }
    }

All of these values were initially filled in by |sl| when the file was first opened. After that, it’s just a matter of changing the settings.

.. _opening-user-settings:

There are three easy ways to open the user settings:

**Command Palette**
:raw-html:`<br>`
Bring up the |_cmd| and type :kbd:`prefs`. Among the commands you should see ``Preferences: SublimeLinter Settings - User``. If that command is not highlighted, use the keyboard or mouse to select it.

**Tools menu**
:raw-html:`<br>`
At the bottom of the Sublime Text ``Tools`` menu, you will see a ``SublimeLinter`` submenu. Select ``SublimeLinter > Open User Settings``.

**Context menu**
:raw-html:`<br>`
If you right-click (or Control-click on OS X) within a file view, you will see a ``SublimeLinter`` submenu at the bottom of the context menu. Select ``SublimeLinter > Open User Settings``.


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

Unlike user settings, project settings are not filled in by |sl|; you are responsible for adding any settings you wish to apply to files in the project.


.. _sublimelinterrc-settings:

.sublimelinterrc settings
~~~~~~~~~~~~~~~~~~~~~~~~~
Sometimes it is useful to apply settings to files in a particular directory (or subdirectory thereof). For example, you may want to apply specific settings to a directory that is not part of a Sublime Text project. Or you may wish to apply specific settings to a directory within a Sublime Text project.

|sl| allows per-directory settings through :file:`.sublimelinterrc` files (“rc” stands for “runtime configuration”).

.. note::

   Only meta-settings and linter settings are recognized in :file:`.sublimelinterrc` files.

When reading the settings for a given file, |sl| does the following:

- Searches in the file’s directory for a :file:`.sublimelinterrc` file.

- If it is not found, the parent directories are searched until the root directory is reached or until the maximum number of search directories (including the file’s directory) are searched.

The maximum number of search directories is determined by the :ref:`"rc_search_limit" setting <rc_search_limit>`. By default, the limit is 3. Setting ``"rc_search_limit"`` to ``null`` means the search will stop only at the root directory. Setting it to ``0`` disables the search for :file:`.sublimelinterrc` entirely for the scope of the settings file in which ``"rc_search_limit"`` is found. This can be useful for projects that are hosted on slow remote filesystems.

The first :file:`.sublimelinterrc` file found is used; |sl| does **not** merge multiple :file:`.sublimelinterrc` files in the search path together.

So, for example, let’s assume we have the following file structure:

.. code-block:: none

    Projects/
        Foobar/
            build/
                out.py
            src/
                foo/
                    foo.py
                    foobar.py
                    baz/
                        baz.py
                bar/
                    bar.py
            test/
                footest.py
                foobartest.py

Given an ``"rc_search_limit"`` of 3, placing a :file:`.sublimelinterrc` file within the following directories would have the following effects:

- **foo** – This would apply to :file:`foo.py`, :file:`foobar.py` and :file:`baz/baz.py`.

- **src** – This would apply to all of the files within :file:`foo`, :file:`foo/baz`, and :file:`bar`.

- **Foobar** – This would apply to all files within :file:`build`, :file:`src/foo`, :file:`src/bar`, and :file:`test` directories, but **not** to files within :file:`src/foo/baz`, because :file:`Foobar` is more than 3 directories from :file:`baz.py`. In this case you would have to increase ``"rc_search_limit"`` to at least 4.


.sublimelinterrc structure
^^^^^^^^^^^^^^^^^^^^^^^^^^
The contents of a :file:`.sublimelinterrc` file should be JSON settings in the same format as the ``"user"`` object in user settings. For example, here is a :file:`.sublimelinterrc` that sets the :ref:`"@python" meta setting <python-meta-setting>` for all linters and configures `flake8`_ to ignore all warnings:

.. code-block:: json

    {
        "@python": 3,
        "linters": {
            "flake8": {
                "ignore": "W"
            }
        }
    }


.. _inline-settings:

Inline settings
~~~~~~~~~~~~~~~
Sometimes you need to change the settings for a single file. Some linters may define one or more **inline settings**, which are settings that can specified directly in a file.

.. note::

   Inline settings must appear within a comment on the first two lines of a file to recognized.

The format for inline settings is as follows:

.. code-block:: none

    <comment> [SublimeLinter <linter>-<setting>:<value> ...]

Let’s break this down a bit:

``<comment>``
:raw-html:`<br>`
This represents the comment start characters for the linter’s language. This may be followed by any number of characters before the actual inline settings.

``[SublimeLinter``
:raw-html:`<br>`
This marks the beginning of the inline settings. “SublimeLinter” is not case-sensitive, so “Sublimelinter” and “sublimelinter” are also valid.

``<linter>``
:raw-html:`<br>`
The lowercase name of the linter to which the setting belongs, followed by “-”.

``<setting>:<value>``
:raw-html:`<br>`
The setting name and value. Any amount whitespace may be placed before or after the “:”. The value may not have any whitespace, as whitespace is used to delimit multiple settings.

``...]``
:raw-html:`<br>`
Any number of ``<linter>-<setting>:<value>`` settings may included before the terminating “]”.

Here is an example of an inline setting that sets two values for the `flake8`_ linter:

.. code-block:: none

    # [SublimeLinter flake8-max-line-length:100 flake8-max-complexity:10]

Those inline settings are the equivalent of the following in a settings file:

.. code-block:: json

    {
        "linters": {
            "flake8": {
                "max-line-length": 100,
                "max-complexity": 10
            }
        }
    }

But in the case of the inline settings, it applies only to the file in which they appear.

.. note::

   Please see the documentation for each linter to find out what inline settings it supports.


.. _shebangs:

shebangs
^^^^^^^^
Each linter has the option to turn a file’s ``shebang`` into an inline setting. For example, python-based linters turn this:

.. code-block:: none

    #!/usr/bin/env python3

into the inline setting ``@python: 3``.

.. note::

   Please see the documentation for each linter to find out if it supports a shebang inline setting.


.. _inline-overrides:

Inline overrides
~~~~~~~~~~~~~~~~
Often linters accept options with multiple values. For example, the `flake8`_ python linter has a ``select`` and ``ignore`` option that takes one or more values. Let’s assume you aren’t interested in warnings about trailing whitespace, since you have configured |st| to trim trailing whitespace when saving. In addition, you would like the default maximum line length to be 100 characters, and you don’t care about how many blank lines are before a method or class definition. So you have added the following to the `flake8`_ settings in the user or project settings:

.. code-block:: json

    {
        "linters": {
            "flake8": {
                "@disable": false,
                "args": [],
                "excludes": [],
                "ignore": "E302,W291,W293",
                "max-complexity": -1,
                "max-line-length": 100,
                "select": ""
            }
        }
    }

E302 will ignore PEP8 errors for the number of blank lines before a method or class definition. W291 and W293 will ignore trailing whitespace on a non-empty and empty line respectively.

This works great so far. But there is one file where you actually need to conform to PEP8 spacing rules for methods and classes, and you would like to ignore W601 warnings about ``has_key`` being deprecated. It would be nice if you could specify only the additions and subtractions to the ignore setting, without affecting the base setting you made lower in the settings stack.

Inline overrides provide this mechanism. Inline overrides are specified inline in exactly the same way as inline settings, but instead of replacing settings of the same name lower in the settings stack, they add or remove options within a setting.

So, for example, given the example above where we want to remove the E302 ignore, add a W601 ignore, and set the maximum line length to 120, you would do this:

.. code-block:: none

    # [SublimeLinter flake8-ignore:-E302,+W601 flake8-max-line-length:120]

A couple things to note:

-  A prefix of ``-`` removes that option.

-  A prefix of ``+`` adds that option.

-  No prefix adds that option, so ``-E302,+W601`` and ``-E302,W601`` are equivalent.

-  In the above example, ``flake8-ignore`` is an inline override, and ``flake8-max-line-length`` is an inline setting.

-  Each linter defines what settings are inline settings and which are inline overrides.

-  Each linter defines the separator you must use between multiple values in inline overrides.

In the example above, without the inline overrides, the ignore option passed to `flake8`_ would be ``E302,W291,W293``, which is taken from our base settings. With the inline overrides, the ignore option is ``W201,W293,W601``.

.. note::

   Please see the documentation for each linter to find out what inline overrides it supports.


.. _settings-tokens:

Setting tokens
--------------
After the default, user and project settings are merged, SublimeLinter iterates over all settings values and replaces the following tokens with their current values:

=================== =========================================================================
Token               Value
=================== =========================================================================
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
