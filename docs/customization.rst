Customiztation
===============

Besides installing plugins and changing settings,
several other aspects of SublimeLinter can be customized.

Context Menu
------------

Removing context menu entries works via ST's standard override protocol.

- In Packages create a directory with the same name as the package you want to override
  (in this case "SublimeLinter", but this also works for AlignTab or ColorConvert to name a few).
- Using [PackageResourceViewer](https://packagecontrol.io/packages/PackageResourceViewer)
  open the Context.sublime-menu file from that package,
  and save it in the new directory you just created.
- This file will now replace the one from the installed package.
  By the way, you can override every single file in any package this way.
- To remove the context menu, change the ``children`` key to an empty array ``[]``.

To add entries, create a Context.sublime-menu file in the Packages/User directory (aka the "User package").
Create an entry that mirrors the provided menu from SublimeLinter.
Make sure the ``id``` that matches. Now create a child entry you want to add.
You don't have to repeat the existing entries, Sublime Text will merge your context menu into ours.

This example add an entry for the command ``sublime_linter_panel_toggle``:

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
