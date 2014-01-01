.. include:: defines.inc

Lint Modes
============
Which events trigger linting depends on the **lint mode**. The lint mode is a :ref:`global setting <lint-mode>` that applies to all views in all windows. Which mode you choose is a matter of preference.


The modes
----------
There are four lint modes in |sl|: :ref:`background <background-lint-mode>`, :ref:`load/save <load-save-lint-mode>`, :ref:`save only <save-only-lint-mode>`, and :ref:`manual <manual-lint-mode>`.

.. _background-lint-mode:

Background
~~~~~~~~~~~
In **background** mode, lint requests are generated for every modification of a view. This is the default mode. Remember that lint requests only trigger a lint if the associated view has not been modified when the request is pulled off the queue.

**Pros**

- Immediate feedback on errors.

**Cons**

- If the delay is too short, you will end up with a lot of false positives.

- Some linters are unavoidably slow and can affect the performance of editing. In such cases you may want to use a different lint mode.

----

.. _load-save-lint-mode:

Load/Save
~~~~~~~~~~~
In **load/save** mode, a file is linted and errors are marked whenever it is loaded and saved. After loading or saving, any modifications to the file clear all marks.

**Pros**

- There are no distractions from error marks while typing, since errors are only displayed when you are ready to save your work.

- This mode avoids performance issues resulting from slow linters.

**Cons**

- You have to manually go through the errors, unless the :ref:`"show_errors_on_save" <show_errors_on_save>` setting is on. For more information on that setting, see `Showing errors on save`_ below.

----

.. _save-only-lint-mode:

Save only
~~~~~~~~~~~
**save only** mode is the same as **load/save** mode, but linting only occurs when a file is saved, not when it is loaded.

**Pros**

- If you have very large files that are relatively slow to lint, and you tend to leave many files open when quitting |st|, in **background** or **load/save** mode, those files will be linted when |st| starts up, which potentially could take several seconds. **save only** mode avoids this problem by linting only when saving a file.

**Cons**

- Your files will not be linted when loaded.

----

.. _manual-lint-mode:

Manual
~~~~~~~~~~~
In **manual** mode, linting only occurs when you manually initiate a lint. After linting, any modifications to the file clear all marks.

**Pros**

- If you are fairly confident in your coding and only want to lint occasionally, this is the mode for you.

**Cons**

- You may forget to lint!

----

.. _choosing-a-lint-mode:

Choosing a lint mode
---------------------
There are three ways to select a lint mode:

**Command Palette**
:raw-html:`<br>`
Bring up the |_cmd| and type :kbd:`mode`. Among the commands you should see ``SublimeLinter: Choose Lint Mode``. If that command is not highlighted, use the keyboard or mouse to select it. A list of the available lint modes appears with the current mode highlighted. Type or click to select the lint mode you would like to use.

**Tools menu**
:raw-html:`<br>`
At the bottom of the |st| ``Tools`` menu, you will see a ``SublimeLinter`` submenu. Select ``SublimeLinter > Lint Modes`` and then select a mode from the submenu.

**Context menu**
:raw-html:`<br>`
If you right-click (or Control-click on OS X) within a file view, you will see a ``SublimeLinter`` submenu at the bottom of the context menu. Select ``SublimeLinter > Lint Modes`` and then select a mode from the submenu.

Once you have selected a new lint mode, all of the open views are redrawn: if the mode is **background**, all views are linted, otherwise all errors marks are cleared. The lint mode you select is saved in your user settings, so it will still be active after restarting Sublime Text.


.. _manually-linting:

Manually linting
----------------
If you select **manual** lint mode, you must manually lint your files. To do so, do one of the following:

**Command Palette**
:raw-html:`<br>`
Bring up the |_cmd| and type :kbd:`lint`. Among the commands you should see ``SublimeLinter: Lint This View``. If that command is not highlighted, use the keyboard or mouse to select it.

**Tools menu**
:raw-html:`<br>`
At the bottom of the Sublime Text ``Tools`` menu, you will see a ``SublimeLinter`` submenu. Select ``SublimeLinter > Lint This View``.

**Context menu**
:raw-html:`<br>`
If you right-click (or Control-click on OS X) within a file view, you will see a ``SublimeLinter`` submenu at the bottom of the context menu. Select ``SublimeLinter > Lint This View``.

**Keyboard**
:raw-html:`<br>`
On Mac OS X, press :kbd:`Command+Control+L`. On Linux/Windows, press :kbd:`Control+K, Control+L`.


.. _showing-errors-on-save:

Showing errors on save
----------------------
When the lint mode is not **background**, you may wish to automatically lint a file and display any errors whenever it is saved. |sl| makes it easy to do this with the :ref:`"show_errors_on_save" <show_errors_on_save>` setting. By default, this setting is off. To turn this setting on, do one of the following:

**Command Palette**
:raw-html:`<br>`
Bring up the |_cmd| and type :kbd:`show`. Among the commands you should see ``SublimeLinter: Show Errors on Save``. If that command is not highlighted, use the keyboard or mouse to select it.

**Tools menu**
:raw-html:`<br>`
At the bottom of the Sublime Text ``Tools`` menu, you will see a ``SublimeLinter`` submenu. If that item is not checked, select ``SublimeLinter > Show Errors on Save``.

**Context menu**
:raw-html:`<br>`
If you right-click (or Control-click on OS X) within a file view, you will see a ``SublimeLinter`` submenu at the bottom of the context menu. If that item is not checked, select ``SublimeLinter > Show Errors on Save``.

.. note::

   As of this writing, the Linux version of |st| does not check menu items, so you cannot tell by examining the menu item whether this option is on or off.

Once you have turned ``"show_errors_on_save"`` on, every time a file is saved, it is linted and any errors are displayed in the :ref:`Show All Errors <showing-all-errors>` Quick Panel.

To turn ``"show_errors_on_save"`` off, follow the instructions above for turning it on, but you will see “Don’t Show Errors on Save” instead of “Show Errors on Save”.
