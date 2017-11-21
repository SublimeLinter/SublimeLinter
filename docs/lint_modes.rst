.. include:: defines.inc

Lint Modes
============
Which events trigger linting depends on the **lint mode**. The lint mode is a :ref:`global setting <lint-mode>` that applies to all views in all windows. Which mode you choose is a matter of preference.


The modes
----------
There are four lint modes in |sl|: :ref:`background <background-lint-mode>`, :ref:`load_save <load-save-lint-mode>`, :ref:`save only <save-only-lint-mode>`, and :ref:`manual <manual-lint-mode>`.

.. _background-lint-mode:

Background
~~~~~~~~~~~
In **background** mode, lint requests are generated for every modification of a view, as well as on file loading and saving. This is the default mode. Remember that background lint requests only trigger a lint if the associated view has not been modified when the request is pulled off the queue (see :ref:`Linting <usage-linting>`).

**Pros**

- Immediate feedback on errors.

**Cons**

- If the delay is too short, you will end up with a lot of false positives.

- Some linters are unavoidably slow and can affect the performance of editing. In such cases you may want to use a different lint mode.

----

.. _load-save-lint-mode:

load_save
~~~~~~~~~~~
In **load_save** mode, a file is linted and errors are marked whenever it is loaded and saved. After loading or saving, any modifications to the file clear all marks.

**Pros**

- There are no distractions from error marks while typing, since errors are only displayed when you are ready to save your work.

- This mode avoids performance issues resulting from slow linters.

**Cons**

- You have to manually go through the errors, unless the :ref:`"show_errors_on_save" <show_errors_on_save>` setting is on. For more information on that setting, see `Showing errors on save`_ below.

----

.. _save-only-lint-mode:

Save only
~~~~~~~~~~~
**save only** mode is the same as **load_save** mode, but linting only occurs when a file is saved, not when it is loaded.

**Pros**

- If you have very large files that are relatively slow to lint, and you tend to leave many files open when quitting |st|, in **background** or **load_save** mode, those files will be linted when |st| starts up, which potentially could take several seconds. **save only** mode avoids this problem by linting only when saving a file.

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


.. _manually-linting:

Manually linting
----------------
If you select **manual** lint mode, you must manually lint your files. To do so, do one of the following:

**Command Palette**
:raw-html:`<br>`
Bring up the |_cmd| and type :kbd:`lint`. Among the commands you should see ``SublimeLinter: Lint This View``. If that command is not highlighted, use the keyboard or mouse to select it.

**Context menu**
:raw-html:`<br>`
If you right-click (or Control-click on OS X) within a file view, you will see a ``SublimeLinter`` submenu at the bottom of the context menu. Select ``SublimeLinter > Lint This View``.

**Keyboard**
:raw-html:`<br>`
On Mac OS X, press :kbd:`Command+Control+L`. On Linux/Windows, press :kbd:`Control+K, Control+L`.


.. _showing-errors-on-save:

Showing errors on save
----------------------
When the lint mode is not **background**, you may wish to automatically lint a file and display any errors whenever it is saved. |sl| makes it easy to do this with the :ref:`"show_errors_on_save" <show_errors_on_save>` setting. By default, this setting is off.

Once you have turned ``"show_errors_on_save"`` on, every time a file is saved, it is linted and any errors are displayed in the :ref:`Show All Errors <showing-all-errors>` Quick Panel.

