Settings
========

Settings stack
--------------
SublimeLinter merges settings from several sources to calculate the value.

.. code-block:: none

    Default settings
    User settings
    Project settings


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


.. _settings-tokens:

Setting tokens
--------------
After the default, user and project settings are merged, SublimeLinter iterates over all settings values and replaces the  tokens with their current values. This uses Sublime Text's `expand_variables` API, which uses the `${varname}` syntax and supports placeholders (`${varname:placeholder}`):

- packages
- platform
- file
- file_path
- file_name
- file_base_name
- file_extension
- folder
- project
- project_path
- project_name
- project_base_name
- project_extension
- as well as all environment variables

We enhanced the expansion for 'folder' that attempts to guess the correct folder if you have multiple folders open in a window.

Additionally `~` will get expanded using `os.path.expanduser <https://docs.python.org/3/library/os.path.html#os.path.expanduser>`_.

