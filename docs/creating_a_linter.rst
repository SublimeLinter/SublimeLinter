.. include:: defines.inc

Creating a Linter Plugin
========================
|sl| makes it easy to create a linter plugin in a few steps:

#. Using the ``Create Linter Plugin`` command, create a template plugin complete with user documentation.

#. Change a few :doc:`attributes <linter_attributes>` in the linter class.

#. Update the user documentation.

#. Submit it for review.

On this page we’ll cover Step 1.


.. _create-linter-plugin-command:

Creating a template plugin
--------------------------
Before creating your plugin, it’s important to understand the naming convention.

.. note::

   Linter plugins must be named after the linter **binary** they use, **not** the language they lint (unless the language binary itself is used to lint). For example, to lint ``python`` with ``pylint``, the linter name you will enter must be ``pylint``, **not** ``python``.

Got it? Okay, here we go:

#. Bring up the |_cmd| and type ``plugin``. Among the commands you should see ``SublimeLinter: Create Linter Plugin``. If that command is not highlighted, use the keyboard or mouse to select it.

#. A dialog will appear explaining the naming convention for linter plugins. If you understand, click “I understand”. If you click “I understand” and still name the linter plugin after the language instead of the linter binary, you will have to pay me $1,000,000. |smiley|

#. An input field will appear at the bottom of the window. Enter the name of the linter binary — **not** the language — that the plugin will interface with and press :kbd:`Return`.

#. You will be asked what language the linter is based on. The linter **plugin** is always python-based, the question here is what language the linter executable (such as `jshint`_) itself is based on. If you select a language, |sl| will fill out the template plugin, copy it to the |st| :file:`Packages` directory with the name :file:`SublimeLinter-contrib-<linter>`, initialize it as a git repository if ``git`` is available, and then open it in a new window.

   .. note::

      Do **not** rename the plugin directory unless absolutely necessary. The directory name **must** come after “|sl|” alphabetically to ensure |sl| loads before the linter plugins. Also, user-created linter plugins use the “-contrib” prefix to distinguish them from “official” plugins that have been vetted and moved into the SublimeLinter org on github.

#. The plugin directory will be opened in |st|. You can then start modifying the linter plugin (``linter.py``) according to your needs.


Coding guidelines
-----------------
For the benefit of all users, I try to maintain a consistently high standard in all third party SublimeLinter plugins. This is enforced by maintaining control over the channel Package Control uses for all SublimeLinter-related repos. If you would like your linter plugin to be published to Package Control, you must follow these guidelines:

-  Indent is 4 spaces.

-  Install the `flake8`_ and `pep257`_ linters to check your code and fix all errors.

-  Vertical whitespace helps readability, don’t be afraid to use it.

-  Please use descriptive variable names, no abbrevations unless they are very well known.

.. _pep257: https://github.com/GreenSteam/pep257


Updating class attributes
--------------------------
Template linter plugins are created with almost all of the Linter class attributes filled in with the default values. To make your new linter plugin functional, at the very least you need to do the following:

- Change the :ref:`syntax` attribute to indicate the syntax (or syntaxes) that the linter lints.

- Change the :ref:`cmd` attribute to include the executable and arguments you want to include on every run. Or if you are going to implement a :ref:`cmd <cmd-method>` method, set the attribute to ``None`` and set the :ref:`executable` attribute to the name of the linter executable.

- Change the :ref:`regex` attribute to correctly capture the error output from the linter.

- Change the :ref:`multiline` attribute to ``True`` if the regex parses multiline error messages.

- Determine the minimum/maximum versions of the linter executable that will work with your plugin and change the :ref:`version_args`, :ref:`version_re` and :ref:`version_requirement` attributes accordingly.

- If the linter executable does not accept input via ``stdin``, set the :ref:`tempfile_suffix` attribute to the filename suffix of the temp files that will be created.

These are the minimum requirements to make a linter plugin functional. However, depending on the features of the linter executable, you may need to configure other class attributes.

- If the linter outputs errors only on ``stderr`` or ``stdout``, set :ref:`error_stream` to ``util.STREAM_STDERR`` or ``util.STREAM_STDOUT`` respectively.

- If you wish to support :ref:`inline settings <inline-settings>` and/or :ref:`inline overrides <inline-overrides>`, add them to the :ref:`inline_settings` and :ref:`inline_overrides` attributes and be sure to set the :ref:`comment_re` attribute, unless you are subclassing from :doc:`PythonLinter <python_linter>` or :doc:`RubyLinter <ruby_linter>`, which do that for you.

- If you wish to support embedded syntaxes, set the :ref:`selectors` attribute accordingly.

- If the linter subclasses from :doc:`PythonLinter <python_linter>`, remove the :ref:`module <module>` attribute if you do not plan to use the linter’s python API. If you do, you will need to implement the :ref:`check <check-method>` method.

You should remove attributes that you do not change, as their values will be provided by the superclass.

.. note::

   Please read the :doc:`linter attributes <linter_attributes>` documentation to learn more about these attributes before changing them blindly! You should also look at the existing collection of linter plugins in the |_org| for reference.


Updating documentation
-----------------------
|sl| creates a fairly complete set of template documentation for you, but you will need to fill in a few things.

#. Open :file:`README.md` and do the following:

   - Change ``__linter_homepage__`` to the URL where users can find info about the linter.

   - Change ``__syntax__`` to the syntax name or names that the plugin will lint. Syntax names are the **internal** syntax names used by |st|. See :ref:`Syntax names <syntax-names>` for more information.

   - If necessary, complete the linter installation instructions. Try to be as complete as possible, listing all necessary prerequisites (with links) and instructions for all platforms if they differ.

   - If your linter plugin does not define the :ref:`defaults` attribute, remove the two paragraphs beginning with “In addition to the standard |sl| settings”. If your linter plugin does define the :ref:`defaults` attribute, document their values.

   - If any of the values in the :ref:`defaults` attribute are also used in :ref:`inline_settings` or :ref:`inline_overrides`, add a checkmark to the appropriate column in the template linter settings table. A checkmark is the html entity ``&#10003;``. If you are not using :ref:`inline_settings` or :ref:`inline_overrides`, remove those columns in the linter settings table.

#. Open :file:`messages/install.txt` and change the repo URL to be the correct URL for your plugin’s repository.

#. Follow your own instructions! Try following the installation instructions in the README — if possible on Mac OS X, Linux and Windows — to see if you missed any important information or possibilities for confusion.


.. _preparing-for-publication:

Preparing for publication
-------------------------
When you have followed all of the steps above and you think your plugin is ready for release, post a message on the |_group| with a link to your repo and it will be reviewed for correctness and completeness.

   .. warning::

      Do **NOT** make a pull request on `wbond/package_control_channel <https://github.com/wbond/package_control_channel>`_. All SublimeLinter plugins must go through `SublimeLinter/package_control_channel <https://github.com/SublimeLinter/package_control_channel>`_.

Once your plugin has been reviewed and all issues have been fixed, you need to tag the final commit with a version number before publishing to Package Control:

.. code-block:: none

   git tag 1.0.0
   git push origin 1.0.0

After the plugin is published to Package Control, every time you make a change, you must increment the version and tag the commit you want to publish. If it is a bug fix, increment the last number in the version. If you add functionality, increment the middle number. Then do the steps above with the new version.
