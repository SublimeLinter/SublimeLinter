Troubleshooting
===============

.. _debug-mode:

Debug mode
----------
If you are having trouble installing or configuring SublimeLinter, you can turn on **debug mode**. In debug mode, SublimeLinter prints additional information about what is happening internally to the console.


The linter doesn’t work!
-------------------------
The first thing you should do when a linter does not work is to test it from the command line (Terminal in Mac OS X/Linux, Command Prompt in Windows). If it does not work from the command line, it definitely won’t work in SublimeLinter.

Here are the most common reasons why a linter does not work:

- The linter binary is not installed. Be sure to install the linter as documented in the linter plugin’s README.

- The linter binary is installed, but its path is not available to SublimeLinter. Follow the steps in :ref:`debugging-path-problems` below to ensure the binary’s path is available to SublimeLinter.

- The linter binary is installed, but it does not fulfill the plugin’s version requirements.

- A python-based linter binary is installed, but it does not work with python 2 or python 3 code. In that case, follow the steps in :ref:`debugging-python-based-linters` below.


.. _debugging-path-problems:

Debugging PATH problems
-----------------------
In order for SublimeLinter to use linter executables, it must be able to find them on your system. There are two possible sources for executable path information:

#. The PATH environment variable.

#. The :ref:`"paths" <paths-setting>` global setting.

At startup SublimeLinter queries the system to get your PATH and merges that with paths in the :ref:`"paths" <paths-setting>` setting. In :ref:`debug mode <debug-mode>` SublimeLinter prints the computed path to the console under the heading ``SublimeLinter: computed PATH <source>:``. You can use that information to help you determine why a linter executable cannot be found.

If a linter’s executable cannot be found when the linter plugin is loaded, the plugin is disabled and you will see a message like this in the console:

.. code-block:: none

    SublimeLinter: WARNING: jshint deactivated, cannot locate 'jshint'

On the other hand, if the linter plugin’s executable can be found at load time, but later on it becomes unavailable, when you try to use that linter you will see a message like this in the console:

.. code-block:: none

    SublimeLinter: ERROR: could not launch ['/usr/local/bin/jshint', '--verbose', '-']
    SublimeLinter: reason: [Errno 2] No such file or directory: '/usr/local/bin/jshint'
    SublimeLinter: PATH: <your PATH here>

Another possibility is that an executable called by the linter executable is missing. For example, if `jshint`_ is available but `node`_ is not, you would see something like this in the console:

.. code-block:: none

    SublimeLinter: jshint output:
    env: node: No such file or directory

.. note::

   On Windows, linter errors messages will not always appear. It appears to be a bug in python.

Unlike the other error messages mentioned earlier, you would not see this message unless debug mode was turned on, because it isn’t an error message detected by SublimeLinter, it is the output captured from the `jshint`_ executable. So if you aren’t seeing any errors or warnings in the console and the linter isn’t working, turn on debug mode to see if you can find the source of the problem.


Finding a linter executable
~~~~~~~~~~~~~~~~~~~~~~~~~~~
If SublimeLinter says it cannot find a linter executable, there are several steps you should take to locate the source of the problem.

First you need to see if the linter executable is in your PATH. Enter the following at a command prompt, replacing ``linter`` with the linter executable name:

.. code-block:: none

    # Mac OS X, Linux
    hash -r
    which linter

    # Windows
    where linter

If the result says that the linter could not be found, that means the linter executable is in a directory which is not in your PATH, and SublimeLinter will not be able to find it. At this point you will have to find out what directory the executable was installed in from the linter’s documentation. Once you find that, you will need to augment your PATH by following the steps in :ref:`Augmenting PATH <augmenting-path>` below.

If the result of ``which`` displays a path, this means the executable is in your PATH, but you are on Mac OS X or Linux and the path to the executable is exported in a shell startup file that SublimeLinter does not read. This means you must add the parent directory of the executable to your PATH by following the steps in :ref:`Augmenting PATH <augmenting-path>` below.


.. _augmenting-path:

Augmenting PATH
~~~~~~~~~~~~~~~
If the path to an executable’s parent directory is not available to SublimeLinter, you have two choices:

#. Add the path to the :ref:`"paths" <paths-setting>` global setting.

#. On Mac OS X or Linux, adjust your shell startup files. On Windows, add the directory to your PATH environment variable.

.. note::

   Paths in the :ref:`"paths" <paths-setting>` setting will be searched before system paths.


Adding to the "paths" setting
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
This approach is the quickest and usually the easiest, but means that you will have to maintain paths both in your system and in SublimeLinter. In addition, it isn’t always obvious what path to add without consulting the documentation for software you install.

Once you determine a path that needs to be added, :ref:`open your user settings <opening-user-settings>` and add the path to the ``"paths"`` array for your platform. For example, let’s say you are using `rbenv`_ on Mac OS X, which adds the path :file:`~/.rbenv/shims` to your PATH. You would change the ``"paths"`` setting like this:

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


Adjusting shell startup files
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
This approach is a little more complicated, but once you get it right then your PATH will be correct for command line usage and for SublimeLinter.

All shells read various files when they are run. Depending on the command line arguments, shells read a “profile/env” file of some sort and an “rc” (runtime configuration) file. For example, ``bash`` reads :file:`.bash_profile` and :file:`.bashrc` (among others) and ``zsh`` reads :file:`.zshenv` and/or :file:`.zprofile` (depending on the platform) and :file:`.zshrc` (among others).

If you aren’t sure what shell you are using, type this in a terminal:

.. code-block:: none

    echo $SHELL

When SublimeLinter starts up, it runs your shell as a **login shell** to get the PATH. This forces the shell to read the “profile/env” file, but for most shells the “rc” file is not read. There is a very good reason for this: performing initialization that only relates to interactive shells is not only wasteful, it will in many cases fail if there is no terminal attached to the process. By the same token, you should avoid putting code in the “profile/env” file that has any output (such as ``motd`` or ``fortune``), since that only works with interactive shells attached to a terminal.

The list of shells supported by SublimeLinter and the startup file that must contain PATH augmentations is shown in this table:

+----------------+-------------------------------------------+
| Shell          | File                                      |
+================+===========================================+
| bash           | ~/.bash_profile (or ~/.profile on Ubuntu) |
+----------------+-------------------------------------------+
| zsh (Mac OS X) | ~/.zprofile                               |
+----------------+-------------------------------------------+
| zsh (Linux)    | ~/.zshenv or ~/.zprofile                  |
+----------------+-------------------------------------------+
| fish           | ~/.config/fish/config.fish                |
+----------------+-------------------------------------------+

If you are using ``zsh`` on Linux, you need to determine which file is used in your flavor of Linux. To do so, follow these steps:

#. Open :file:`.zshenv` in an editor and insert ``echo env`` on the first line. If the file does not exist, create it.

#. Do the same for :file:`.zprofile`, but insert ``echo profile``.

#. In a terminal, enter ``$SHELL -l -c 'echo hello'``. If you see both “env” and “profile”, use :file:`.zshenv` for PATH augmentations. If you see only one of the two, use that file for PATH augmentations.

#. Remove or comment out the ``echo`` lines you added.

----

When you installed a linter executable, it may have augmented your PATH in the “rc” file. But for these path augmentations to be visible to SublimeLinter, you must move such augmentations to the “profile/env” file. For example, if you are using ``bash`` as your shell and you installed `rbenv`_, you would probably find this in your :file:`.bashrc` file:

.. code-block:: none

    eval "$(rbenv init -)"

For SublimeLinter to “see” this, however, you have to move that line from :file:`.bashrc` to the file that SublimeLinter will see, which is :file:`.bash_profile` from the table above.

If ``which`` or ``where`` cannot find a linter executable from the command line, you need to add the executable’s parent directory to your PATH. Assuming a directory of :file:`/opt/bin`, on Mac OS X or Linux the changes you would make are summarized in the following table:

+----------------+----------------------------+-----------------------------------+
| Shell          | File                       | Code                              |
+================+============================+===================================+
| bash           | ~/.bash_profile            | export PATH=/opt/bin:$PATH        |
+----------------+----------------------------+-----------------------------------+
| zsh (Mac OS X) | ~/.zprofile                | export PATH=/opt/bin:$PATH        |
+----------------+----------------------------+-----------------------------------+
| zsh (Linux)    | ~/.zshenv or ~/.zprofile   | export PATH=/opt/bin:$PATH        |
+----------------+----------------------------+-----------------------------------+
| fish           | ~/.config/fish/config.fish | set PATH /opt/bin $PATH           |
+----------------+----------------------------+-----------------------------------+


Special considerations for ``bash``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
If you are using ``bash`` as your shell, there is one more step you must take after augmenting your PATH in :file:`.bash_profile`.

- On Mac OS X, add this code to the **bottom** of :file:`.bash_profile`:

  .. code-block:: none

    case $- in
       *i*) source ~/.bashrc
    esac

  On Mac OS X, ``bash`` does **not** load :file:`.bashrc` unless explicitly run with the ``-i`` command line argument. On the other hand, :file:`.bash_profile` is loaded in each new interactive Terminal session and if ``bash`` is run as a login shell. So you must load :file:`.bashrc` in :file:`.bash_profile`, but should only do so if the shell is interactive, which is what the code above does.

- On Linux, add this code to the **top** of :file:`.bashrc`:

  .. code-block:: none

    source ~/.bash_profile

  On Linux, by default ``bash`` does **not** load :file:`.bash_profile` for an interactive session, but it does for a login shell. So if you move your PATH augmentations to :file:`.bash_profile` and source that in :file:`.bashrc`, your PATH augmentations will always be loaded.


Editing PATH on Windows
~~~~~~~~~~~~~~~~~~~~~~~~~
On Windows you need to edit your PATH environment variable directly. The easiest way to do this is with the `Path Editor`_, a free application. Once you install and launch Path Editor, follow these steps:

#. Click the Add button.

#. Select the parent directory of the linter executable and click OK.

#. Click OK at the bottom of the Path Editor window.

On any platform, after you have changed your PATH, you will need to restart SublimeText.


Validating your PATH
~~~~~~~~~~~~~~~~~~~~
To verify that SublimeLinter will be able to see the changes you made above, enter the following at a command prompt, replacing “linter” with the name of the linter executable which could not be found:

.. code-block:: none

    # Mac OS X, Linux
    > $SHELL -l -c '/usr/bin/which linter'

    # Windows
    > where linter

If your changes were correct, it will print the path to the linter executable. If the executable path is not printed, then do the following to see what PATH SublimeLinter will see:

.. code-block:: none

    # bash, zsh
    > $SHELL -l -c 'echo $PATH | tr : "\n"'

    # fish
    > fish -l -c 'for p in $PATH; echo $p; end'

    # Windows
    > path


.. _debugging-python-based-linters:

Debugging python-based linters
------------------------------
When using python-based linters, there are more possibilities for configuration problems:

- The version of python or the python script specified in the linter plugin may not be available.

- The version of python specified in your settings may not be available.

- The specified version of python may be available, but the linter module for that version may not be installed.

To understand how these might occur, it’s important to understand :ref:`how SublimeLinter resolves python versions <resolving-python-versions>`. Let’s look at the console output for each case to see how to spot these problems.


Linter’s python is not available
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
When a python-based linter plugin is loaded that does not support direct execution (the ``module`` attribute is ``None``), if the ``cmd`` attribute specifies ``script@python<version>``, where ``script`` is a python script such as ``flake8``, and ``<version>`` is a major[.minor] version, SublimeLinter attempts to :ref:`locate a version of python <resolving-python-versions>` that satisfies ``<version>``.

If no version of python can be found that satisfies the requested version, the linter plugin is disabled, and you will see the following message in the console (where “foo” is the linter name):

.. code-block:: none

    SublimeLinter: WARNING: foo deactivated, no available version of python or foo satisfies foo@python2


Setting python is not available
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
If the linter plugin does **not** specify a python version in the ``cmd`` attribute (e.g. ``flake8@python``), then SublimeLinter will tentatively enable the linter when it is loaded, even if no default python can be found, because the requested python version may change based on your settings.

For example, if there were no default version of python available for `flake8`_, you would see this in the console at startup:

.. code-block:: none

    SublimeLinter: flake8 activated: (None, None)

Now if you tried to use the `flake8`_ linter with code that did not have a specific python version set with the :ref:`@python meta setting <python-meta-setting>`, :ref:`inline setting <inline-settings>` or :ref:`shebang <shebangs>`, you would see this error in the console:

.. code-block:: none

    SublimeLinter: ERROR: flake8 cannot locate 'flake8@python'


Module not installed
~~~~~~~~~~~~~~~~~~~~
On the other hand, if ``python2`` is available and you have a ``@python: 2`` meta or inline setting, **but** you do not have `flake8`_ installed for python 2, you would see something like this in the console:

.. code-block:: none

    SublimeLinter: flake8: test.py ['/usr/bin/python2', '/usr/local/bin/flake8', '--max-complexity=-1', '-']
    SublimeLinter: flake8 output:
    Traceback (most recent call last):
      File "/usr/local/bin/flake8", line 5, in <module>
        from pkg_resources import load_entry_point
      File "/System/Library/Frameworks/Python.framework/Versions/2.7/Extras/lib/python/pkg_resources.py", line 2556, in <module>
        working_set.require(__requires__)
      File "/System/Library/Frameworks/Python.framework/Versions/2.7/Extras/lib/python/pkg_resources.py", line 620, in require
        needed = self.resolve(parse_requirements(requirements))
      File "/System/Library/Frameworks/Python.framework/Versions/2.7/Extras/lib/python/pkg_resources.py", line 518, in resolve
        raise DistributionNotFound(req)  # XXX put more info here
    pkg_resources.DistributionNotFound: flake8==2.1.0


Some good advice
~~~~~~~~~~~~~~~~
To ensure your python linters work well, always ensure:

- The versions of python you code in are available in your PATH.

- You install the linter module (using `easy_install`_ or `pip`_) for all versions of python you plan to use it with.

If you do that, you shouldn’t have any problems. But if you do, hopefully the troubleshooting guide above will help you understand what is wrong with your system configuration.

.. _Path Editor: http://patheditor2.codeplex.com
