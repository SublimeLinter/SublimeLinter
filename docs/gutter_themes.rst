Creating a gutter theme
=======================

Use one of the existing gutter themes as a starting point.
You can find them in the repo_.

To colorize icons the .gutter-theme file should contain:
``{ "colorize": true }``.
In this case your icons should be mostly white, (with shades of gray).

If you set colorize to false, Sublime Text will still colorize them.
To maintain the original color we colorize them using a scope that should get
a white color: ``region.whitish``.
If this results in incorrectly colored icons, this scope needs to be added to
your color scheme.

Gutter images are scaled to to 16 x 16.
For best results with Retina displays, gutter images should be 32 x 32.

To install your theme place the directory in Packages/User.

.. _repo: https://github.com/SublimeLinter/SublimeLinter/tree/master/gutter-themes
