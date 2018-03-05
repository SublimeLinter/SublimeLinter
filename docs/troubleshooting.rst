Troubleshooting
===============

.. _debug-mode:

Debug mode
----------
In debug mode, SublimeLinter prints additional information to Sublime Text's console.
Among other things it will list if a linter was able to run and its output.

To enable this mode, set ``"debug"`` to ``true`` in your SublimeLinter settings.


The linter doesn’t work!
------------------------
When a linter does not work try to run the program from the command line
(Terminal in Mac OS X/Linux, Command Prompt in Windows).
If it does not work there, it definitely won’t work in SublimeLinter.

Here are the most common reasons why a linter does not work:

- The syntax is a variation (e.g. ``"html (django)"``) that isn't mapped
  to a known syntax (e.g. ``"html"``). The detected syntax is printed to the
  console in debug mode.
  Also note that plugins should move to using the selector setting 
  instead of the old syntaxes attribute. You can use the "selector" linter
  setting right now instead of the "syntax_map".

- The linter binary is not installed.
  Be sure to install the linter as documented in the linter plugin’s README.

- The linter binary is installed,
  but its path is not available to SublimeLinter.
  Follow the steps in :ref:`debugging-path-problems` below.

- The linter binary is installed,
  but it does not fulfill the plugin’s version requirement.


.. _debugging-path-problems:

Debugging PATH problems
-----------------------
In order for SublimeLinter to use linter executables, it must be able to find them on your system.
There are two possible sources for this information:

#. The PATH environment variable.
#. The ``"paths"`` setting.

In :ref:`debug mode <debug-mode>` SublimeLinter prints the computed path to the console.
If a linter’s executable cannot be found, the debug output will include a ``cannot locate <linter>`` message.

A linter may have additional dependencies (e.g. NodeJS) that may be missing.
The console should also have information about that.

On macOS
~~~~~~~~

SublimeLinter can run before the environment variables have been loaded,
in which case it will not be able to find the right executable.
This is a known issue in Sublime Text (`#1877 <https://github.com/SublimeTextIssues/Core/issues/1877>`_).
There is currently no API that let's us wait for the environment.

- This problem goes away by itself, but you may get some error messages until it does.
- You can lunch Sublime Text from the console, the environment will then be available immediately.
- All linters take an executable setting. Setting that will allow SL to always find it, bypassing the PATH entirely.


Finding a linter executable
~~~~~~~~~~~~~~~~~~~~~~~~~~~
If a linter executable cannot be found, these are steps you can take to locate the source of the problem.

First check if the executable is in your PATH.
Enter the following at a command prompt, replacing ``<linter>`` with the correct name (e.g. ``eslint``):

.. code-block:: bash

    # Mac OS X, Linux
    which <linter>

    # Windows
    where <linter>


If this fails to output the executable's location it will not work.
Make sure the executable is installed and if necessary edit your PATH.
How to edit your PATH strongly depends on you operating system and its specific
configuration. The internet is full of HOWTO's on this subject.


Adding to the "paths" setting
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
If you cannot rely on the PATH environment variable, paths can be configured
in SublimeLinter's settings.

For example, let’s say you are using ``rbenv`` on macOS.
To add the path ``~/.rbenv/shims`` you would change the ``"paths"`` setting like this:

.. code-block:: json

    {
        "paths": {
            "linux": [],
            "osx": [
                "~/.rbenv/shims"
            ],
            "windows": []
        }
    }
