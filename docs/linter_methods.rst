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

   split_match(self, match) -> LintMatch

This method extracts named capture groups from the :ref:`regex` into a
``LintMatch`` mapping. It parses line and column numbers and subtracts
:ref:`line_col_base`, but does not convert Unicode column units. Custom
parsers must likewise return zero-based columns in the declared units.

If subclasses need to modify the values returned by the regex,
they should override this method, call ``super().split_match(match)``,
then modify the values and return them.

For compatibility, ``LintMatch`` still supports seven-value tuple iteration
and positional construction: *match*, *line*, *col*, *error*, *warning*,
*message*, *near*. Additional fields do not alter that tuple contract.


.. _convert_column:

convert_column
--------------
.. code-block:: python

   convert_column(self, line: int, col: int, m: LintMatch, vv: VirtualView) -> int

Convert a column as reported by the linter to a code-point offset. The default uses
:ref:`column_unit`. Core calls this hook once for each present ``col`` and
``end_col`` in ``process_match``, before either positioning branch clamps
columns. Missing columns do not call the hook; zero columns do.

.. code-block:: python

    def convert_column(self, line, col, m, vv):
        if m.code.startswith("F"):
            return vv.col_from_utf8(line, col)
        return super().convert_column(line, col, m, vv)

``vv.col_from_utf8(line, col)`` and ``vv.col_from_utf16(line, col)`` convert
individual zero-based offsets.

For source-specific coordinates, reconstruct the tool's origin in the scalar
hook. For example, xmllint prints a window and its parser stores the caret's
zero-based byte offset as ``col``::

    def convert_column(self, line, col, m, vv):
        if m.context is not None:
            origin = max(vv.select_line(line).find(m.context), 0)
            window = VirtualView(m.context)
            return origin + window.col_from_utf8(0, col)
        return super().convert_column(line, col, m, vv)



reposition_match
----------------
.. code-block:: python

   reposition_match(self, line, col, m, vv) -> tuple[int, int, int]

For linters that only report a column this method is called to find a suitable
region to highlight.  Usually the :ref:`word<word_re>` at ``col`` is selected.
Returns ``(line, start, end)`` in code points.

``col`` has been converted and clamped, whereas ``m.col`` retains the raw adapter
column. This hook is not called when the linter already reports an ``end_col``.
Put selective unit conversion in :ref:`convert_column`, which covers both paths,
rather than converting an already-clamped column here.

