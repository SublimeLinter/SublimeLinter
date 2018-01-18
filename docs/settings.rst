Settings
========

Settings stack
--------------
SublimeLinter merges settings from several sources to calculate the value. Settings are merged in the following order:

1. Default settings
1. User settings
1. Project settings


Project settings
~~~~~~~~~~~~~~~~
SublimeLinter project settings are defined by a ``"SublimeLinter"`` object within Sublime Text’s project settings. Here you can change linter settings for a project.

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


.. _settings-expansion:

Settings Expansion
------------------
After the settings have been merged, SublimeLinter iterates over all settings values and expands any strings.
This uses Sublime Text's `expand_variables` API, which uses the ``${varname}`` syntax and supports placeholders (``${varname:placeholder}``), where placeholders are resolved recursively (e.g. ``${XDG_CONFIG_HOME:$HOME/.config}``).
To insert a literal ``$`` character, use ``\$`` (in JSON: ``\\$``).

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

See the `documentation on build systems <https://www.sublimetext.com/docs/3/build_systems.html#variables>`_ for an explanation of what each variable contains.

We enhanced the expansion for ``folder`` that attempts to guess the correct folder if you have multiple folders open in a window.

Additionally, ``~`` will get expanded using `os.path.expanduser <https://docs.python.org/3/library/os.path.html#os.path.expanduser>`_.

