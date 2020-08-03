Customization
===============

Besides installing plugins and changing settings,
several other aspects of SublimeLinter can be customized.

Context Menu
------------

**To remove** context menu entries you use ST's standard override protocol.

- Install `PackageResourceViewer <https://packagecontrol.io/packages/PackageResourceViewer>`_
  if you don't have it already.
- Use "PackageResourceViewer: Open Resource" to open the Context.sublime-menu
  file from the package you want to override ("SublimeLinter" in this case).
- Saving the file will create a Context.sublime-menu file in
  Packages/<package name>/.
- This file will now replace the one from the installed package.
  By the way, you can override every single file in any package this way.
- To remove the context menu, change the content of this file to an empty array: ``[]``.

**To add** entries, create a Context.sublime-menu file in the Packages/User/ directory (aka the "User package").

This example adds an entry for the command ``sublime_linter_panel_toggle``:

.. code-block:: json

    [
        {
            "caption": "Show Linter Panel",
            "command": "sublime_linter_panel_toggle"
        }
    ]


Key bindings
------------

SublimeLinter ships with a number of key bindings
(please refer to the `README <https://github.com/SublimeLinter/SublimeLinter>`_).
Because there are only so many keys on the keyboard we never add more bindings,
even though for some commands they would definitely be useful.
However, the default "keymap" file has several suggestions that you can use.
Simply go through the Package Settings menu to open the SublimeLinter Key Bindings,
and copy the commented-out suggestions from the left hand file, to your personal "keymap" on the right.
