.. include:: defines.inc

PythonLinter class
==================
If your linter plugin interfaces with a linter that is written in python, you should subclass from ``SublimeLinter.lint.PythonLinter``.

.. note::

   This is done for you if you use the :ref:`Create Linter Plugin <create-linter-plugin-command>` command and select ``Python`` as the linter language.

By doing so, you get the following features:

- :ref:`comment_re` is defined correctly for python.

- :ref:`@python <python-meta-setting>` is added to :ref:`inline_settings`.

- :ref:`shebang_match` is set to a method that returns a python shebang as the ``@python:<version>`` meta setting.

-  Execution directly via a python module method or via an external executable.

`SublimeLinter-flake8`_, `SublimeLinter-pep8`_, and `SublimeLinter-pyflakes`_ are good examples of python-based linters.


.. _check-method:

check (method)
--------------
.. code-block:: python

   check(self, code, filename)

If your ``PythonLinter`` subclass sets the :ref:`module <module>` attribute, you must implement this method.

This method is called if:

- You set the :ref:`module <module>` attribute.

-  The named module is successfully imported.

-  :ref:`Version matching <resolving-python-versions>` allows the use of |st|’s built-in python.

This method should perform linting and return a string with one more lines per error, an array of strings, or an array of objects that can be converted to strings. Here is the ``check`` method from the ``Flake8`` class, which is a good template for your own ``check`` implementations:

.. code-block:: python

    def check(self, code, filename):
        """Run flake8 on code and return the output."""

        options = {
            'reporter': Report
        }

        type_map = {
            'select': [],
            'ignore': [],
            'max-line-length': 0,
            'max-complexity': 0
        }

        self.build_options(options, type_map, transform=lambda s: s.replace('-', '_'))

        if persist.settings.get('debug'):
            persist.printf('{} options: {}'.format(self.name, options))

        checker = self.module.get_style_guide(**options)

        return checker.input_file(
            filename=os.path.basename(filename),
            lines=code.splitlines(keepends=True)
        )

A few things to note:

- We use the :ref:`build_options` method to build the options expected by the ``get_style_guide`` method.

- We print the options to the console if we are in debug mode.


.. _check_version:

check_version (class attribute)
-------------------------------
Some python-based linters are version-sensitive; the python version they are run with has to match the version of the code they lint. If you define the :ref:`module <module>` attribute, this attribute should be set to ``True`` if the linter is version-sensitive.


cmd (class attribute)
---------------------
When using a python-based linter, there is a special form that should be used for the ``cmd`` attribute:

.. code-block:: none

    script@python[version]

*script* is the name of the linter script, and *version* is the optional version of python required by the script.

For example, the `SublimeLinter-pyflakes`_ linter plugin defines ``cmd`` as:

.. code-block:: python

    cmd = 'pyflakes@python'

This tells |sl| to locate the ``pyflakes`` script and run it on the system python or the version of python configured in settings.

When using the ``script@python`` form, |sl| does the following:

-  Locates *script* in a cross-platform way. Python scripts are installed differently on Windows than they are on Mac OS X and Linux.

-  Does version matching between the version specified in the ``cmd`` attribute and the version specified by settings.

-  Defers to using the built-in python if possible.


.. _module:

module (class attribute)
------------------------
If you want to import a python module and run a method directly in order to lint, this attribute should be set to the module name, suitable for passing to `importlib.import_module`_. During class construction, the named module will be imported, and if successful, the attribute will be replaced with the imported module.

.. note::

   Because the module is going to run within |st|, it must be compatible with python 3.3 or later. If not, do not define this attribute.

For example, the ``Flake8`` linter class defines:

.. code-block:: python

    module = 'flake8.engine'

Later, when it wants to use the method ``flake8.engine.get_style_guide``, it does so like this:

.. code-block:: python

    checker = self.module.get_style_guide(**options)

If the module attribute is defined and is successfully imported, whether it is used depends on the following algorithm:

- If the :ref:`check_version <check_version>` attribute is ``False``, the module will be used because the module is not version-sensitive.

- If the :ref:`"@python" <python-meta-setting>` setting is set and |st|’s built-in python satisfies that version, the module will be used.

- If the :ref:`cmd` attribute specifies ``@python`` and |st|’s built-in python satisfies that version, the module will be used. Note that this check is done during class construction.

- Otherwise the external linter executable will be used with the python specified in the :ref:`"@python" <python-meta-setting>` setting, the :ref:`cmd` attribute, or the default system python.

If you set the ``module`` attribute, you must implement the :ref:`check <check-method>` in your ``PythonLinter`` subclass in order to use the module to do the linting.

.. _importlib.import_module: http://docs.python.org/3/library/importlib.html?highlight=importlib.import_module#importlib.import_module
.. _SublimeLinter-flake8: https://github.com/SublimeLinter/SublimeLinter-flake8
.. _SublimeLinter-pep8: https://github.com/SublimeLinter/SublimeLinter-pep8
.. _SublimeLinter-pyflakes: https://github.com/SublimeLinter/SublimeLinter-pyflakes
