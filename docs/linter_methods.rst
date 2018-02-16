Linter Methods
========================
The ``Linter`` class is designed to allow interfacing with most linter
executables/libraries through the configuration of class attributes.
Some linters, however, will need to set up the environment for the linter executable,
or may do the linting directly in the linter plugin itself.

In those cases, you will need to override one or more methods.
SublimeLinter provides a set of methods that are designed to be overridden.


cmd
---
.. code-block:: python

   cmd(self)

If you need to dynamically generate the command line that is executed in order to lint,
implement this method in your ``Linter`` subclass.
Return a tuple/list with separate arguments.
The first argument in the result should be the full path to the linter executable.


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

