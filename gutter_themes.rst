.. include:: defines.inc

Gutter Themes
===============
When linting is done, SublimeLinter marks errors in two ways: the suspect code itself is :doc:`marked <mark_styles>`, and the line on which the code occurs is marked in the gutter. Code marks and gutter marks are configured separately.


Gutter theme structure
----------------------
There are actually two types of gutter marks: errors and warnings. This helps you to visually identify which marks are errors and which are warnings.

Gutter marks are drawn using PNG images. If a theme is :ref:`colorized <creating-a-gutter-theme>`, the images are tinted with the current :ref:`"error_color" <error_color>` or :ref:`"warning_color" <warning_color>` colors in your settings. Otherwise the images are drawn as is.


Standard gutter themes
----------------------
Which gutter theme you use is a matter of taste. Below is a list of the built in gutter themes that come with SublimeLinter. (The names come from the third party icon set from which the icons were chosen.) If none of these suit you, you can easily :ref:`create your own <creating-a-gutter-theme>`.

.. note::

   Colorized icons are in fact mostly white; they are displayed here as they appear when drawn by SublimeLinter, tinted with the error or warning color. Creating the icons white allows the tint color to come through unchanged.


.. |bc_e| image:: images/Blueberry/cross/error.png
    :width: 16
    :height: 16
.. |bc_w| image:: images/Blueberry/cross/warning.png
    :width: 16
    :height: 16

.. |br_e| image:: images/Blueberry/round/error.png
    :width: 16
    :height: 16
.. |br_w| image:: images/Blueberry/round/warning.png
    :width: 16
    :height: 16

.. |cir_e| image:: images/Circle/circle-error.png
    :width: 16
    :height: 16
.. |cir_w| image:: images/Circle/circle-warning.png
    :width: 16
    :height: 16

.. |dr_e| image:: images/DanishRoyalty/error.png
    :width: 16
    :height: 16
.. |dr_w| image:: images/DanishRoyalty/warning.png
    :width: 16
    :height: 16

.. |def_e| image:: images/Default/default-error.png
    :width: 16
    :height: 16
.. |def_w| image:: images/Default/default-warning.png
    :width: 16
    :height: 16

.. |h_e| image:: images/Hands/error.png
    :width: 16
    :height: 16
.. |h_w| image:: images/Hands/warning.png
    :width: 16
    :height: 16

.. |k1_e| image:: images/Knob/simple/error.png
    :width: 16
    :height: 16
.. |k1_w| image:: images/Knob/simple/warning.png
    :width: 16
    :height: 16

.. |k2_e| image:: images/Knob/symbol/error.png
    :width: 16
    :height: 16
.. |k2_w| image:: images/Knob/symbol/warning.png
    :width: 16
    :height: 16

.. |ko_e| image:: images/Koloria/error.png
    :width: 16
    :height: 16
.. |ko_w| image:: images/Koloria/warning.png
    :width: 16
    :height: 16

.. |pi_e| image:: images/ProjectIcons/error.png
    :width: 16
    :height: 16
.. |pi_w| image:: images/ProjectIcons/warning.png
    :width: 16
    :height: 16

.. |s| unicode:: 0xA0 0xA0 0xA0
   :trim:

=================== ===================
Name                Error/Warning
=================== ===================
Blueberry - cross   |bc_e| |s| |bc_w|
Blueberry - round   |br_e| |s| |br_w|
Circle              |cir_e| |s| |cir_w| |s| [colorized]
Danish Royalty      |dr_e| |s| |dr_w|
Default             |def_e| |s| |def_w| |s| [colorized]
Hands               |h_e| |s| |h_w|
Knob - simple       |k1_e| |s| |k1_w|
Knob - symbol       |k2_e| |s| |k2_w|
Koloria             |ko_e| |s| |ko_w|
ProjectIcons        |pi_e| |s| |pi_w|
=================== ===================

.. _choosing-a-gutter-theme:

Choosing a gutter theme
-----------------------
There are three ways to choose a gutter theme:

**Command Palette**
:raw-html:`<br>`
Bring up the |_cmd| and type :kbd:`gutter`. Among the commands you should see ``SublimeLinter: Choose Gutter Theme``. If that command is not highlighted, use the keyboard or mouse to select it.

A list of the available gutter themes appears with the current gutter theme highlighted. Below each gutter theme name is an indication of whether the theme is a standard |sl| theme or a user theme, as well as whether the theme is colorized.

If you type or use the arrow keys to move through the list, the current gutter theme will change dynamically to the currently selected theme. If you have a view open with gutter marks, this allows you to preview other themes. Pressing :kbd:`Return/Enter` or clicking on a theme will commit that change. Pressing :kbd:`Escape` will revert to the theme in use before the Command Palette opened.

**Tools menu**
:raw-html:`<br>`
At the bottom of the |st| ``Tools`` menu, you will see a ``SublimeLinter`` submenu. Select ``SublimeLinter > Choose Gutter Theme...`` and then follow the instructions for selecting from the Command Palette.

**Context menu**
:raw-html:`<br>`
If you right-click (or Control-click on OS X) within a file view, you will see a ``SublimeLinter`` submenu at the bottom of the context menu. Select ``SublimeLinter > Choose Gutter Theme...`` and then follow the instructions for selecting from the Command Palette.

Once you have selected a new gutter theme, all of the open views are redrawn with the new theme. The gutter theme you select is saved in your user settings, so it will still be active after restarting |st|.


.. _creating-a-gutter-theme:

Creating a gutter theme
-----------------------
With SublimeLinter, you are free to create or install new gutter themes. You can mix and match the existing images, or use entirely new images. SublimeLinter’s built in gutter themes can be found in :file:`Packages/SublimeLinter/gutter-themes`.

A gutter theme is simply a directory that contains the following three files:

**<name>.gutter-theme**
:raw-html:`<br>`
This file is what |sl| uses to locate gutter themes, and **<name>** (without the < >) is used for the gutter theme name (the parent directory name can be anything). If a gutter theme is colorized, this file should contain the following JSON:

.. code-block:: json

    {
        "colorized": true
    }

If the gutter theme is not colorized, the file may be empty, or it may include the same JSON but set ``"colorized"`` to ``false``.

**error.png**
:raw-html:`<br>`
This image is displayed in the gutter on any line that has errors.

**warning.png**
:raw-html:`<br>`
This image is displayed in the gutter on any line that has warnings but no errors; errors always have precedence over warnings.

When you choose a gutter theme, |sl| looks for any directory with these three files within :file:`Packages`, :file:`Packages/User`, or :file:`Installed Packages`. Within :file:`Installed Packages`, the gutter theme must be somewhere within a compressed :file:`.sublime-package` file.


Gutter images
~~~~~~~~~~~~~
|st| scales gutter images to 16 x 16. For best results with Retina displays, gutter images should be 32 x 32 at 72dpi.

If your gutter icons will be colorized, they should be mostly white, with shades of gray used to create shadow areas. The entire image should be grayscale, so that the error and warning colors do not change when they are applied to the icons.


Installing gutter themes
~~~~~~~~~~~~~~~~~~~~~~~~
Third party gutter themes may be searched for and installed via |_pc|, or if you have created your own gutter theme, by placing the gutter theme directory in the |st| :file:`Packages` or :file:`Packages/User` directory. Once you have installed the new gutter theme, follow the instructions above to :ref:`choose the theme <choosing-a-gutter-theme>`. That’s all there is to it!
