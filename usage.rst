.. include:: defines.inc

Usage
============
|sl| is designed to work well out of the box, but there are many ways to customize it to your taste. Before we get to that, though, let’s take a look at how |sl| works.

.. _startup-actions:


Startup actions
---------------
When |sl| is loaded by |st|, it performs a number of actions to initialize its environment:


Settings
~~~~~~~~
The default settings are loaded from the plugin and merged with the settings in :file:`Packages/User/SublimeLinter.sublime-settings`. For more information on |sl| settings, see :doc:`Settings <settings>`.


Color scheme
~~~~~~~~~~~~
SublimeLinter has to convert color schemes for its use. For more information, see :ref:`Choosing color schemes <choosing-color-schemes>`.


Customized syntax definitions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
|sl| supports linting of embedded syntaxes, such as JavaScript and CSS within an HTML file, by specifying a scope to which the linter is limited. Unfortunately the stock syntax definitions that ship with |st| incorrectly classify the scope of embedded languages, which leads to false errors during linting. To solve this problem, at load time |sl| installs fixed versions of the ``HTML`` and ``HTML (Rails)`` syntax packages in the :file:`Packages` directory.

.. note::

   The first time the fixed syntaxes are installed, you may need to restart |st| for them to be applied to source files in those syntaxes.

Assigning linters
-----------------
When a file is opened in |st|, |sl| checks the syntax assigned to the file (Python, JavaScript, etc.), and then uses that name (lowercased) to locate any linters (there may be several) that have advertised they can lint that syntax. Any found linters are assigned to that *view* of the file. |sl| assigns separate linter instances to each view, even if there are multiple views of the same file.

.. _usage-linting:

Linting
-------
Here’s where the magic happens.

When you activate or make any modifications to a file, the following sequence of events occurs:

- |sl| checks to see if the syntax of the file has changed; and if so, reassigns linters to the view.

- If the **lint mode** is ``background``, a lint request is added to a threaded queue with a delay. The delay is there to prevent lints from occurring instantly on every keystroke — you don’t want the linter complaining too much while you are typing, it quickly becomes annoying. The delay is there to allow a little idle time before a lint occurs.

  For more information on lint modes, see :doc:`Lint Modes <lint_modes>`. The delay can be configured, for more information see :ref:`Global Settings <delay>`.

- The lint request is eventually pulled off the queue after the given delay. If the view it belongs to has been modified since the lint request was made, the request is discarded, since another lint request was generated when the view was modified.

- Each of the linters assigned to the base syntax of the view is run with the current text of the view. The linter calls an external linter binary (such as `jshint`_), or if the linter is python-based (such as `flake8`_), it may directly call a python linting library.

- If any linters assigned to the view support embedded code and that embedded code is found, the linters are run with the appropriate embedded code.

- Each linter adds a set of regions indicating the portions of the source code that generated errors or warnings.

- When all of the linters have finished, if the view has still not been modified since the initial lint request, all of the error and warning regions are aggregated and drawn according to the currently configured :doc:`mark style <mark_styles>` and :doc:`gutter theme <gutter_themes>`. Errors and warnings are marked with separate colors and gutter icons to make it easy to see which is which.


.. _how-linter-executables-are-located:

How linter executables are located
----------------------------------
When calling a system linter binary, the user’s |path| environment variable is used to locate the binary. On Windows, the |path| environment variable is used as is. On Mac OS X and Linux, if the user’s shell is ``bash``, ``zsh``, or ``fish``, a login shell is used to get the |path| value. If you are using a shell other than the ones just mentioned, |path| effectively becomes:

.. code-block:: none

  /bin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/php/bin:/usr/local/php5/bin

.. warning::

   On Mac OS X and Linux, special care must be taken to ensure your |path| is set up in such a way that |sl| can read it. For more information, see :ref:`Debugging PATH problems <debugging-path-problems>`.

In addition to the |path| |sl| reads from the system, any directories in the global ``"paths"`` setting for the current platform are searched when attempting to locate a binary. For more information, see the :ref:`Global Settings <paths-setting>` documentation.


Python paths
~~~~~~~~~~~~
When locating python and python scripts such as `flake8`_, |sl| goes through a special process. For more information, see :ref:`the @python meta setting <python-meta-setting>`.


.. _disabling-all-linters:

Disabling all linters
---------------------
There may be times when you want to turn off all linting. To do so, bring up the |_cmd| and type :kbd:`disable`. Among the commands you should see ``SublimeLinter: Disable Linting``. If that command is not highlighted, use the keyboard or mouse to select it.

Once you do this, all linters are disabled and all error marks are cleared from all views. To re-enable linting, follow the same steps as above, but select ``SublimeLinter: Don’t Disable Linting``. Note that this does not enable all linters; if you have :ref:`disabled individual linters <disable-linter-setting>` in the settings, they will remain disabled.


.. _toggling-linters:

Toggling linters
----------------
You can quickly toggle a linter on or off. To do so:

#. Bring up the |cmd| and type :kbd:`toggle`, :kbd:`disable`, or :kbd:`enable` according to what you want to view all linters, only enabled linters, or only disabled linters.

#. Among the commands you should see ``SublimeLinter: Toggle Linter``, ``SublimeLinter: Disable Linter`` or ``SublimeLinter: Enable Linter``, depending on what you typed. If the command is not highlighted, use the keyboard or mouse to select it.

#. Once you select the command, a list of the relevant linters appears. If you chose ``SublimeLinter: Disable Linter``, only the enabled linters appear in the list. If you chose ``SublimeLinter: Enable Linter``, only the disabled linters appear.

#. Select a linter from the list. It will be toggled, disabled or enabled, depending on the command you chose.


.. _choosing-color-schemes:

Choosing color schemes
----------------------
In order to color errors, warnings and gutter icons correctly, |sl| relies on specific named colors being available in the current color scheme. Whenever a color scheme is loaded — either implicitly at startup or by selecting a color scheme — |sl| checks to see if the color scheme contains its named colors. If not, it adds those colors to a copy of the color scheme, writes it to the :file:`Packages/User/SublimeLinter` directory with a “ (SL)” suffix added to the filename, and switches to the modified color scheme.

For example, if you select ``Preferences > Color Scheme > Color Scheme - Default > Monokai``, |sl| will convert it, write the converted color scheme to :file:`Packages/User/SublimeLinter/Monokai (SL).tmTheme`, and switch to that color scheme. If you then open the ``Preferences > Color Scheme`` menu, ``User > SublimeLinter > Monokai (SL)`` is checked.

.. warning::

   If you choose an unconverted color scheme and an existing converted color scheme exists in :file:`Packages/User/SublimeLinter`, it will be overwritten.

.. note::

   If you ever want to clean up, and delete all the |sl| made color schemes not being used in the settings, simply use the ``SublimeLinter: Clear Color Scheme Folder`` command from the Command Pallete, Tools menus, or Context menu.

For more information on customizing the colors used by |sl|, see :doc:`Global Settings <global_settings>`.


User interface
--------------
There are four main aspects to the |sl| user interface:

- :doc:`Lint mode <lint_modes>` — The lint mode determines when linting occurs.

- :doc:`Mark style <mark_styles>` — The mark style determines how errors are marked in the text.

- :doc:`Gutter theme <gutter_themes>` — The gutter theme determines how lines with errors are marked in the gutter.

- :doc:`Navigating errors <navigating>` — Once linters find errors in your code, you can quickly and easily navigate through them.
