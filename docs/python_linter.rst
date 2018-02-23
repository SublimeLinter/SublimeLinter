PythonLinter class
==================
If your linter plugin interfaces with a linter that is written in python,
you should subclass from ``SublimeLinter.lint.PythonLinter``.

By doing so, you get the following features:

-  Use correct environment using a ``python`` setting.
-  Automatically find an environment using ``pipenv``
