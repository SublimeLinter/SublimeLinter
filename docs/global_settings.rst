.. include:: defines.inc


.. _paths-setting:

paths
-----
This setting provides extra paths to be searched when :ref:`locating system executables <how-linter-executables-are-located>`.

.. note::

   Instead of using this setting, consider :ref:`setting up your PATH correctly <debugging-path-problems>` in your shell.

   This setting works like the |path| environment variable; you provide **directories**, relative or absolute, that will be searched for executables (e.g. ``"/opt/bin"``), **not** paths to specific executables.

   If you give a relative path to a directory, it is considered relative to the |st| executable.

You may provide separate paths for each platform on which |st| runs. The default value is empty path lists.

.. code-block:: json

    {
        "paths": {
            "linux": [],
            "osx": [],
            "windows": []
        }
    }


python_paths
------------
When |sl| starts up, it reads ``sys.path`` from the system python 3 (if it is available), and adds those paths to the |sl| ``sys.path``. So you should never need to do anything special to access a python module within a linter. However, if for some reason ``sys.path`` needs to be augmented, you may do so with this setting. Like the ``"paths"`` setting, you may provide separate paths for each platform on which |st| runs. The default value is empty path lists.

