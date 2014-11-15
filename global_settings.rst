.. include:: defines.inc

Global Settings
==================
|sl| supports the following global settings:


debug
-----
If ``true``, |sl| prints information to the |st| console that may help in debugging problems with a linter. For example, the command passed to a linter and the output from the linter are logged to the console in debug mode. All of |sl|’s log messages are prefixed by “|sl|: ”. The default value is ``false``.

Rather than change this setting manually, you are better off using the user interface to :ref:`set the debug mode <debug-mode>`.


.. _delay:

delay
-----
When the :ref:`lint mode <background-lint-mode>` is ``"background"``, this setting determines how long |sl| will wait until acting on a lint request. The default value is 0.25 (seconds). For a discussion of this setting, see :ref:`Usage <usage-linting>`.


.. _error_color:

error_color
-----------
This setting determines the color used to mark errors in the text. It should be a six-digit hex RGB color (like those used in CSS), with or without a leading “#”. If this setting is changed, |sl| will offer to update all user color schemes with the new error color. The default value is ``"D02000"``.

Warnings are marked with `warning_color`_.


gutter_theme
------------
This setting should be the full :file:`Packages`-relative path to the :file:`.gutter-theme` file for the current gutter theme. Rather than changing this setting manually, you are better off using the user interface to :ref:`choose a gutter theme <choosing-a-gutter-theme>`. The default value is ``Packages/SublimeLinter/gutter-themes/Default.gutter-theme``.


gutter_theme_excludes
---------------------
If you wish to exclude one or more gutter themes from the list of available gutter themes, you can add one or more patterns to the array in this setting. The patterns are matched against the gutter theme name using |_fnmatch|. The default value is an empty array.

For example, if you wanted to exclude the “Blueberry” gutter themes that come with |sl|, you would use this setting:

.. code-block:: json

    {
        "gutter_theme_excludes": [
            "Blueberry*"
        ]
    }


.. _lint-mode:

lint_mode
---------
This setting determines the current :doc:`lint mode <lint_modes>`. Possible values are ``"background"``, ``"load/save"``, ``"save only"``, and ``"manual"``. The default value is ``"background"``.

Rather than change this setting manually, you are better off using the user interface to :ref:`choose a lint mode <choosing-a-lint-mode>`.


.. _mark_style:

mark_style
----------
This setting determines the current :doc:`mark style <mark_styles>`. Possible values are ``"fill"``, ``"outline"``, ``"solid underline"``, ``"squiggly underline"``, ``"stippled underline"``, and ``"none"``. The default value is ``"outline"``.

Rather than change this setting manually, you are better off using the user interface to :ref:`choose a mark style <choosing-a-mark-style>`.


.. _no-column-highlights-line:

no_column_highlights_line
-------------------------
This setting determines what happens when a linter reports an error with no column information. By default, a mark is put in the gutter but no text is highlighted. If this setting is ``true``, in addition to the gutter mark, the entire line is highlighted.

Rather than change this setting manually, you are better off using the user interface to :ref:`set the no-column highlight mode <no-column-mode>`.


.. _passive_warnings:

passive_warnings
----------------
This setting allows you the ability to hide warnings in the `"Show All Errors"` Quick Panel. See :doc:`Navigating Errors <navigating>` for more information on this setting. The default value is ``false``.

.. _paths-setting:

paths
-----
This setting provides extra paths to be searched when :ref:`locating system executables <how-linter-executables-are-located>`.

.. note::

   Instead of using this setting, consider :ref:`setting up your PATH correctly <debugging-path-problems>` in your shell.

   This setting works like the |path| environment variable; you provide **directories** that will be searched for executables (e.g. ``"/opt/bin"``), **not** paths to specific executables.

You may provide separate paths for each platform on which |st| runs. The default value is empty path lists.

.. code-block:: json

    {
        "paths": {
            "linux": [],
            "osx": [],
            "windows": []
        }
    }


python_paths
------------
When |sl| starts up, it reads ``sys.path`` from the system python 3 (if it is available), and adds those paths to the |sl| ``sys.path``. So you should never need to do anything special to access a python module within a linter. However, if for some reason ``sys.path`` needs to be augmented, you may do so with this setting. Like the ``"paths"`` setting, you may provide separate paths for each platform on which |st| runs. The default value is empty path lists.


.. _rc_search_limit:

rc_search_limit
---------------
This setting determines how many directories will be searched when looking for a :file:`.sublimelinterrc` settings file. The default value is 3. See :ref:`.sublimelinterrc settings <sublimelinterrc-settings>` for more information.


.. _shell_timeout:

shell_timeout
-------------
This setting determines the number of seconds that |sl| will wait when executing a shell command, for example when getting the value of PATH. The default value is 10. If the |sl| debug log says that shell commands are timing out, you may need to increase the value of this setting.


.. _show_errors_on_save:

show_errors_on_save
-------------------
This setting determines if a Quick Panel with all errors is displayed when a file is saved. The default value is ``false``.

Rather than change this setting manually, you are better off using the user interface to :ref:`change this setting <showing-errors-on-save>`.


show_marks_in_minimap
---------------------
This setting determines whether error marks are shown in the minimap. The default value is ``true``.


.. _syntax_map:

syntax_map
----------
This setting allows you to map one syntax **name** to another. Because linters are tied to a syntax name, this is useful when there are variations on a syntax that should use the same linter.

.. note::

  Syntax names are the name of the .tmLanguage file that defines the syntax. This is **not** the file extension of the files to be linted, and may not necessarily be what is in the ``View > Syntax`` menu and in the lower right of the status bar.

The syntax names in the map should be lowercase. The default value is:

.. code-block:: json

    {
        "python django": "python",
        "html 5": "html",
        "html (django)": "html",
        "html (rails)": "html",
        "php": "html"
    }

This means that any file that has the named syntax which is one of the keys will be linted by any linter than supports the named syntax corresponding to that key. For example, any file with the "python django" syntax will be linted by any linter that supports the "python" syntax.

Let’s say you install some fancy new syntax package for python named "Totally Awesome Python". To ensure |sl| will lint files that use that syntax, you would modify the ``"syntax_map"`` setting as follows:

.. code-block:: json

    {
        "totally awesome python": "python",
        "python django": "python",
        "html 5": "html",
        "html (django)": "html",
        "html (rails)": "html",
        "php": "html"
    }


.. _warning_color:

warning_color
-------------
This setting determines the color used to mark warnings in the text. It should be a six-digit hex RGB color (like those used in CSS), with or without a leading “#”. If this setting is changed, |sl| will offer to update all user color schemes with the new warning color. The default value is ``"DDB700"``.

Errors are marked with `error_color`_.


.. _wrap_find:

wrap_find
---------
This setting determines if the ``Next Error`` and ``Previous Error`` commands wrap around when reaching the end or beginning of the file. See :doc:`Navigating Errors <navigating>` for more information on those commands. The default value is ``true``.
