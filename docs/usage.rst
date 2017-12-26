.. include:: defines.inc

Usage
============
|sl| is designed to work well out of the box, but there are many ways to customize it to your taste. Before we get to that, though, let’s take a look at how |sl| works.


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

