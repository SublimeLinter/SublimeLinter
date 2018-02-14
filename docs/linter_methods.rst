Linter Methods
========================
The ``Linter`` class is designed to allow interfacing with most linter
executables/libraries through the configuration of class attributes.
Some linters, however, will need to set up the environment for the linter executable,
or may do the linting directly in the linter plugin itself.

In those cases, you will need to override one or more methods.
SublimeLinter provides a set of methods that are designed to be overridden.


build_options
-------------
.. code-block:: python

   build_options(self, options, type_map, transform=None)

This method builds a list of options to be passed directly to a linting method.
It is designed for use with linters that do linting directly in python code and need to pass a dict of options.
Usually you will call this within the ``PythonLinter.check`` method.

- ``options`` is the starting dict of options.
- ``type_map`` is a dict that maps an option name to a value of the desired type.
- If not ``None``, ``transform`` must be a method that takes an option name and returns a transformed name.

For each of the :ref:`default settings <defaults>` marked as an argument,
this method does the following:

- Checks if the setting name is in the view settings.
- If so, and the setting’s current value is non-empty, checks if the setting name is in *type_map*.
  If so, the value is converted to the type of the value in *type_map*.
- If *transform* is not ``None``, pass the setting name to it to get a transformed name.
- Adds the name/value pair to *options*.


cmd
---
.. code-block:: python

   cmd(self)

If you need to dynamically generate the command line that is executed in order to lint,
implement this method in your ``Linter`` subclass.
Return either a command line string or a tuple/list with separate arguments.
The first argument in the result should be the full path to the linter executable.
If the executable is the same as what you specified in the ``executable`` class attribute,
you can use ``self.executable_path``.
Otherwise, if you need to find some other executable, you should use the :ref:`which` method.


communicate
-----------
.. code-block:: python

   communicate(self, cmd, code)

This method runs an external executable using the command line specified by the tuple/list *cmd*,
passing *code* using ``stdin``.
The output of the command is returned.

Normally there is no need to call this method,
as it called automatically if the linter plugin does not define a value for :ref:`tempfile_suffix`.
If you override the :ref:`run` method you can use this method to execute
an external linter that accepts input via ``stdin``.


.. _run:

run
---
.. code-block:: python

   run(self, cmd, code)

This method does the actual linting.

- *cmd* is a tuple/list of the command to be executed (with arguments),
- *code* is the text to be linted.

If a linter plugin always uses built-in code
(as opposed to a subclass of :doc:`PythonLinter <python_linter>` that may use a ``module``),
it should override this method and return a string as the output.

If a linter plugin needs to do complicated setup it will need to override this method.


.. _split_match:

split_match
-----------
.. code-block:: python

   split_match(self, match)

This method extracts the named capture groups from the :ref:`regex` and
return a tuple of *match*, *line*, *col*, *error*, *warning*, *message*, *near*.

If subclasses need to modify the values returned by the regex,
they should override this method, call ``super().split_match(match)``,
then modify the values and return them.


tmpfile
-------
.. code-block:: python

   tmpfile(self, cmd, code, suffix='')

This method creates a temp file with the filename extension *suffix*,
writes *code* to the temp file, appends the temp file name to the sequence *cmd*,
runs the external executable (with arguments) specified by *cmd*,
and returns its output.

Normally there is no need to call this method, as it is called automatically
if the linter plugin defines a value for :ref:`tempfile_suffix`.
If you override the :ref:`run` method you can use this method to execute an
external linter that does not accept input via ``stdin``.


.. _which:

which
-----
.. code-block:: python

   which(cls, cmd)

This method returns the full path to the executable named in *cmd*.
If the executable cannot be found, ``None`` is returned.

If *cmd* is in the form ``script@python[version]``, this method gets
the ``module`` class attribute (which is ``None`` for non-:doc:`PythonLinter <python_linter>` subclasses) and does the following:
