Customization
===============

Besides installing plugins and changing settings,
several other aspects of SublimeLinter can be customized.

Context Menu
------------

**To remove** context menu entries you use ST's standard override protocol.

- Install `PackageResourceViewer <https://packagecontrol.io/packages/PackageResourceViewer>`_
  if you don't have it already.
- Using PackageResourceViewer open the Context.sublime-menu file
  from the package you want to override ("SublimeLinter" in this case).
- Saving the file will create a Context.sublime-menu file in
  Packages/<package name>/.
- This file will now replace the one from the installed package.
  By the way, you can override every single file in any package this way.
- To remove the context menu, change the ``children`` key to an empty array ``[]``.

**To add** entries, create a Context.sublime-menu file in the Packages/User directory (aka the "User package").
Create an entry that mirrors the `provided menu from SublimeLinter <https://github.com/SublimeLinter/SublimeLinter/blob/master/menus/Context.sublime-menu>`_.
Make sure the ``id`` matches. Now create a child entry you want to add.
You don't have to repeat the existing entries, Sublime Text will merge your context menu into ours.

This example adds an entry for the command ``sublime_linter_panel_toggle``:

.. code-block:: json

    [
        {
            "id": "sublimelinter",
            "caption": "Linter",
            "children": [
                {
                    "id": "sublimelinter-panel",
                    "caption": "Show Panel",
                    "command": "sublime_linter_panel_toggle"
                }
            ]
        }
    ]
