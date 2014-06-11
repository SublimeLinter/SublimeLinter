.. include:: defines.inc

Linter Methods
========================
The ``SublimeLinter.lint.Linter`` class is designed to allow interfacing with most linter executables/libraries through the configuration of class attributes, with no coding necessary. Some linters, however, will need to do more work to set up the environment for the linter executable, or may do the linting directly in the linter plugin itself.

In those cases, you will need to override one or more methods. |sl| provides a well-defined set of methods that are designed to be overridden.


.. _build_options:

build_options
-------------
.. code-block:: python

   build_options(self, options, type_map, transform=None)

This method builds a list of options to be passed directly to a linting method. It is designed for use with linters that do linting directly in python code and need to pass a dict of options. Usually you will call this within the :ref:`PythonLinter.check <check-method>` method.

*options* is the starting dict of options. *type_map* is a dict that maps an option name to a value of the desired type. If not ``None``, *transform* must be a method that takes an option name and returns a transformed name.

For each of the :ref:`default settings <defaults>` marked as an argument, this method does the following:

- Checks if the setting name is in the view settings.

- If so, and the setting’s current value is non-empty, checks if the setting name is in *type_map*. If so, the value is converted to the type of the value in *type_map*.

- If *transform* is not ``None``, pass the setting name to it to get a transformed name.

- Adds the name/value pair to *options*.

For an example of how ``build_options`` is used, see the :ref:`check <check-method>` method documentation.


can_lint_syntax
---------------
.. code-block:: python

   can_lint_syntax(cls, syntax)

This method returns ``True`` if a linter can lint a given syntax.

Subclasses may override this if the built in mechanism in the ``can_lint`` method is not sufficient. When this method is called, ``cls.executable_path`` has been set to the path of the linter executable. If it is ``''``, that means the executable was not specified or could not be found.


.. _cmd-method:

cmd
---
.. code-block:: python

   cmd(self)

If you need to dynamically generate the command line that is executed in order to lint, implement this method in your ``Linter`` subclass. Return either a command line string or a tuple/list with separate arguments. The first argument in the result should be the full path to the linter executable. If the executable is the same as what you specified in the ``executable`` class attribute, you can use ``self.executable_path``. Otherwise, if you need to find some other executable, you should use the :ref:`which` method.

For example, the `coffeelint`_ linter plugin does the following:

.. code-block:: python

    def cmd(self):
        """Return a list with the command line to execute."""

        result = [self.executable_path, '--jslint', '--stdin']

        if persist.get_syntax(self.view) == 'coffeescript_literate':
            result.append('--literate')

        return result


communicate
-----------
.. code-block:: python

   communicate(self, cmd, code)

This method runs an external executable using the command line specified by the tuple/list *cmd*, passing *code* using ``stdin``. The output of the command is returned.

Normally there is no need to call this method, as it called automatically if the linter plugin does not define a value for :ref:`tempfile_suffix`. If you override the :ref:`run` method you can use this method to execute an external linter that accepts input via ``stdin``.


get_view_settings
-----------------
.. code-block:: python

   get_view_settings(self, inline=True)

If you need to get the :ref:`merged settings <settings-stack>` for a view, use this method. If *inline* is ``False``, inline settings will not be included with the merged settings.


.. _run:

run
---
.. code-block:: python

   run(self, cmd, code)

This method does the actual linting. *cmd* is a tuple/list of the command to be executed (with arguments), *code* is the text to be linted.

If a linter plugin always uses built-in code (as opposed to a subclass of :doc:`PythonLinter <python_linter>` that may use a :ref:`module <module>`), it should override this method and return a string as the output. Subclasses of ``PythonLinter`` that specify a ``module`` attribute should **not** override this method, but the :ref:`check <check-method>` method instead.

If a linter plugin needs to do complicated setup or will use the :ref:`tmpdir` method, it will need to override this method.


.. _split_match:

split_match
-----------
.. code-block:: python

   split_match(self, match)

This method extracts the named capture groups from the :ref:`regex` and return a tuple of *match*, *line*, *col*, *error*, *warning*, *message*, *near*.

If subclasses need to modify the values returned by the regex, they should override this method, call ``super().split_match(match)``, then modify the values and return them.

For example, the `csslint`_ linter plugin overrides ``split_match`` because it sometimes returns errors without a line number.

.. code-block:: python

    def split_match(self, match):
        """
        Extract and return values from match.

        We override this method so that general errors that do not have
        a line number can be placed at the beginning of the code.

        """

        match, line, col, error, warning, message, near = super().split_match(match)

        if line is None and message:
            line = 0
            col = 0

        return match, line, col, error, warning, message, near


.. _tmpdir:

tmpdir
------
.. code-block:: python

   tmpdir(self, cmd, files, code)

This method creates a temp directory, copies the files in the sequence *files* to the directory, appends the temp directory name to the sequence *cmd*, runs the external executable (with arguments) specified by *cmd*, and returns its output.

Normally there is no need to call this method, but if you override the :ref:`run` method you can use this method to execute an external linter that requires a group of files in a specific directory structure.


tmpfile
-------
.. code-block:: python

   tmpfile(self, cmd, code, suffix='')

This method creates a temp file with the filename extension *suffix*, writes *code* to the temp file, appends the temp file name to the sequence *cmd*, runs the external executable (with arguments) specified by *cmd*, and returns its output.

Normally there is no need to call this method, as it is called automatically if the linter plugin defines a value for :ref:`tempfile_suffix`. If you override the :ref:`run` method you can use this method to execute an external linter that does not accept input via ``stdin``.


.. _which:

which
-----
.. code-block:: python

   which(cls, cmd)

This method returns the full path to the executable named in *cmd*. If the executable cannot be found, ``None`` is returned.

If *cmd* is in the form ``script@python[version]``, this method gets the ``module`` class attribute (which is ``None`` for non-:doc:`PythonLinter <python_linter>` subclasses) and does the following:

- If not ``None``, *version* should be a string/numeric version of python to locate, e.g. “3” or “3.3”. Only major/minor versions are examined. This method then does its best to locate a version of python that satisfies the requested version. If :ref:`module <module>` is not ``None``, |st|’s python version is tested against the requested version.

-  If *version* is ``None``, the path to the default system python is used, unless :ref:`module <module>` is not ``None``, in which case “” is returned for the python path.

-  If not ``None``, *script* should be the name of a python script that is typically installed with `easy_install`_ or `pip`_, e.g. ``pep8`` or ``pyflakes``.

-  A tuple of the python path and script path is returned.

.. _coffeelint: https://github.com/SublimeLinter/SublimeLinter-coffeelint
