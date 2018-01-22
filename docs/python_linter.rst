PythonLinter class
==================
If your linter plugin interfaces with a linter that is written in python, you should subclass from ``SublimeLinter.lint.PythonLinter``.

.. note::

   This is done for you if you use the :ref:`Create Linter Plugin <create-linter-plugin-command>` command and select ``Python`` as the linter language.

By doing so, you get the following features:

-  Find correct environment using a ``python`` setting.
-  Automatically find an environment using ``pipenv``

`SublimeLinter-flake8`_ is a good example of s python-based linter.


.. _SublimeLinter-flake8: https://github.com/SublimeLinter/SublimeLinter-flake8
