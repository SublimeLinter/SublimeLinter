.. include:: defines.inc

Creating a Linter Plugin
========================

#. Fork the SublimeLinter-template repo to bootstrap your new linter

#. Clone it into Packages

#. Change a few :doc:`attributes <linter_attributes>` in the linter class.

#. Update the user documentation and all other placeholders

#. Open a PR to have it added to package_control:
   https://github.com/SublimeLinter/package_control_channel


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

