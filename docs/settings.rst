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
#. :ref:`Project settings <project>` (only "linters" settings)


Styles (colors)
---------------
Colors are applied to highlights and gutter icons using **scopes**.

Scopes are how Sublime Text manages color.
Regions of code (and sections of the gutter) are labelled with scopes.
You can think of scopes as class names in an HTML file.
These scopes then receive color from the color scheme, which is kinda like a CSS stylesheet.

SublimeLinter expects the scopes ``markup.warning`` and ``markup.error`` to get
correct colors from most color schemes.
We use scopes like ``region.redish`` for color schemes that don't provide colors for these scopes.

To change the colors, you can use region.colorish scopes:
redish, orangish, yellowish, greenish, bluish, purplish, pinkish

Or you can `customize your color scheme <https://www.sublimetext.com/docs/color_schemes.html#customization>`_.


.. _project:

Project settings
----------------
Only the "linters" settings plus a ":ref:`kill-switch <the_kill_switch>`" can be changed in a project.
All other settings can only be changed in your user settings.

.. note::

    Read more about project setting in
    `Sublime Text's documentation <https://www.sublimetext.com/docs/projects.html>`_.

Here is an example project settings file where the flake8 linter has been disabled:

.. code-block:: json

    {
        "folders":
        [
            {
                "path": "."
            }
        ],
        "settings":
        {
            "SublimeLinter.linters.flake8.disable": true
        }
    }

Notice that, what is a nested object hierarchy in the user settings file, becomes
a flat key in the project settings.

.. note::

    Since project settings are effectively *view* settings that are just automatically applied to all views in that projects window, SublimeLinter also supports different settings per view.

For example, disable `flake8` for a single, specific view:

.. code:: python

    view.settings().set("SublimeLinter.linters.flake8.disable", true)

Building on that, here is a sketch for a plugin that automatically disables a
linter for big files:

.. code:: python

    class MaybeDisableRubocop(sublime_plugin.EventListener):
        def on_loaded(self, view):
            view.settings().set("SublimeLinter.linters.rubocopy.disable", view.size() > 1_000_000)


.. _the_kill_switch:

The kill-switch
~~~~~~~~~~~~~~~

You can turn off SublimeLinter per view or per project using the key ``SublimeLinter.enabled?`` (since: 4.19.0). This flag has *three* (!) states: `null/not-set` (the default), `true`, and `false`.

.. attention::

    It is not recommended to blindly set `true` to enable SublimeLinter. (But you can blindly set `false` to disable it.)  `true` forces a run and bypasses other checks.

.. _settings-expansion:

Settings Expansion
------------------

After merging the settings, SublimeLinter proceeds to iterate over all the settings values and expands any strings. This process utilizes Sublime Text's `expand_variables` API, which is also employed in Sublime's build system. You can refer to the `build systems documentation <https://www.sublimetext.com/docs/build_systems.html#variables>`_ for a comprehensive list and explanation of all available variables. Some commonly used variables include `file`, `file_path`, `file_name`, and `folder`. Please note that we enhance the value of `folder` by not blindly returning the first open folder, but rather by considering the first folder that contains the view (provided the view has a filename and is part of the project). In Node and Python projects, we may also set `project_root` if we find one.  (This typically the directory where your "package.json" or "pyproject.toml" is placed.)

In addition to the standard variables, **all** environment variables are also accessible. Furthermore, the tilde character, ``~``, represents your home directory and is expanded using the `os.path.expanduser <https://docs.python.org/3/library/os.path.html#os.path.expanduser>`_ function.

To reference a variable, you can use either ``$var_name`` or ``${var_name}``. Placeholders are supported using the syntax ``${folder:.}``, and they are resolved recursively. For example, you can use expressions like ``${XDG_CONFIG_HOME:$HOME/.config}`` or ``${file_name:$folder}``.

If you need to insert a literal ``$`` character, you can use ``\\$`` to escape it.

