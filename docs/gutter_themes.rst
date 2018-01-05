.. include:: defines.inc

Gutter Themes
===============
When linting is done, SublimeLinter marks errors in two ways: the suspect code itself is :doc:`marked <mark_styles>`, and the line on which the code occurs is marked in the gutter. Code marks and gutter marks are configured separately.


Gutter theme structure
----------------------
There are actually two types of gutter marks: errors and warnings. This helps you to visually identify which marks are errors and which are warnings.

Gutter marks are drawn using PNG images. If a theme is :ref:`colorized <creating-a-gutter-theme>`, the images are tinted with the current :ref:`"error_color" <error_color>` or :ref:`"warning_color" <warning_color>` colors in your settings. Otherwise the images are drawn as is.


.. _creating-a-gutter-theme:

Creating a gutter theme
-----------------------
With SublimeLinter, you are free to create or install new gutter themes.

A gutter theme is simply a directory that contains the following three files:

**<name>.gutter-theme**
:raw-html:`<br>`
This file is what |sl| uses to locate gutter themes, and **<name>** (without the < >) is used for the gutter theme name (the parent directory name can be anything). If a gutter theme is colorized, this file should contain the following JSON:

.. code-block:: json

    {
        "colorize": true
    }

If the gutter theme is not colorized, the file may be empty, or it may include the same JSON but set ``"colorized"`` to ``false``.


Gutter images
~~~~~~~~~~~~~
|st| scales gutter images to 16 x 16. For best results with Retina displays, gutter images should be 32 x 32 at 72dpi.

If your gutter icons will be colorized, they should be mostly white, with shades of gray used to create shadow areas. The entire image should be grayscale, so that the error and warning colors do not change when they are applied to the icons.


Installing gutter themes
~~~~~~~~~~~~~~~~~~~~~~~~
Third party gutter themes may be searched for and installed via |_pc|, or if you have created your own gutter theme, by placing the gutter theme directory in the |st| :file:`Packages` or :file:`Packages/User` directory.
