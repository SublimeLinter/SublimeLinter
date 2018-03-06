Settings
========

The settings are documented in the default settings file, so you can refer to
them while editing your settings.

.. note::

    Settings are checked for correctness, a message will display with errors.
    You need to fix or remove incorrect settings, like typos and deprecated settings.

This page covers some extra tricks and how to work with project specific settings.

Settings stack
--------------
SublimeLinter merges settings from several sources to calculate the value.
Settings are merged in the following order:

#. Default settings
#. User settings
#. Project settings


Project settings
----------------
Only the "linters" settings in can be changed in a project.
All other settings can only be changed in your user settings.

SublimeLinter project settings are defined by a ``"SublimeLinter"`` object
within Sublime Text’s sublime-project file.

.. note::

    Read more about project setting in
    `Sublime Text's documentation <https://www.sublimetext.com/docs/3/projects.html>`_.

Here is an example project settings file where the flake8 linter has been disabled:

.. code-block:: json

    {
        "folders":
        [
            {
                "path": "."
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

    Do not put the ``"SublimeLinter"`` object inside a ``"settings"`` object,
    or anywhere else but directly in the root object of the sublime-project file.


.. _settings-expansion:

Settings Expansion
------------------
After the settings have been merged, SublimeLinter iterates over all settings values and expands any strings.
This uses Sublime Text's `expand_variables` API,
which uses the ``${varname}`` syntax and supports placeholders (``${varname:placeholder}``).
Placeholders are resolved recursively (e.g. ``${XDG_CONFIG_HOME:$HOME/.config}``).

To insert a literal ``$`` character, use ``\\$``.

The following case-sensitive variables are provided:

- ``packages``
- ``platform``
- ``file``
- ``file_path``
- ``file_name``
- ``file_base_name``
- ``file_extension``
- ``folder``
- ``project``
- ``project_path``
- ``project_name``
- ``project_base_name``
- ``project_extension``
- all environment variables

.. note::

    See the `documentation on build systems <https://www.sublimetext.com/docs/3/build_systems.html#variables>`_
    for an explanation of what each variable contains.

We enhanced the expansion for ``folder``.
It now attempts to guess the correct folder if you have multiple folders open in a window.

Additionally, ``~`` will get expanded using
`os.path.expanduser <https://docs.python.org/3/library/os.path.html#os.path.expanduser>`_.

