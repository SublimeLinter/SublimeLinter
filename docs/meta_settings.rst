.. include:: defines.inc

Meta Settings
=============
Meta settings are special global settings that can be used both at the global and linter level. When used globally, they are applied to every linter and override a linter meta setting. Meta setting names always begin with “@”.

The following meta settings are supported:


.. _disable-meta-setting:

@disable
~~~~~~~~
This boolean setting disables linters, preventing them from running. If this setting is present globally, it forces all linters to be disabled if ``true`` or forces all linters to be enabled if ``false``.

If you want to disable all linters, rather than change this setting manually, you are better off using the user interface to :ref:`disable all linters <disabling-all-linters>`.

.. note::

   Setting ``@disable`` to ``false`` enables **all** linters, regardless of whether you have set ``@disable`` to ``true`` for an individual linter. If you want to disable linters individually, you must remove the global ``@disable`` setting. Setting the global ``@disable`` setting through the user interface does this for you.


.. _python-meta-setting:

@python
~~~~~~~
Because new versions of python are potentially backwards-incompatible with earlier versions, dealing with python-based linters can be tricky:

- The linter itsef may only run on a specific major.minor version of python (or later).

- It may be necessary to run it on a version of python compatible with the version in which the code to be linted was written.

- When a linter provides a python 3-compatible API, a linter plugin will usually want to use the API directly instead of calling an external binary.

The ``@python`` meta setting is a floating point number that specifies the python version that should be used when running python-based linters. This is especially useful when used in project settings or :ref:`.sublimelinterrc settings <sublimelinterrc-settings>` to specify that the files in a particular project or directory should be treated as a particular version of python.

For example, let’s say you are working on a project called “Widget” that is written in python 3, and you want to make sure it is treated as such by linters such as `flake8`_. In the project settings, you would do this:

.. code-block:: json

    {
        "folders":
        [
            {
                "follow_symlinks": true,
                "path": "/Users/aparajita/Projects/Widget"
            }
        ],
        "SublimeLinter":
        {
            "@python": 3
        }
    }

That’s all there is to it. Of course, beneath the hood a lot of magic is happening.


.. _resolving-python-versions:

Resolving python versions
~~~~~~~~~~~~~~~~~~~~~~~~~
What happens when SublimeLinter is asked to resolve a ``@python`` version depends on the linter plugin and the platform.

- If the linter plugin indicates that a specific version of python must be used, that version will always be used, regardless of your ``@python`` setting.

- If the linter plugin indicates that any version of python may be used, the default python is used, unless the linter plugin specifies that the linter executable is sensitive to python versions, in which case the version you specify with the ``@python`` setting will be used.

The following algorithm is used both when resolving a python version for a linter plugin and when resolving a python version you specify with the ``@python`` meta setting.

**Mac OS X/Linux**
:raw-html:`<br>`
On Posix systems, python is installed with binaries (or symlinks to binaries) for both the major.minor version and the major version. When a specific version is requested, the following happens:

- First the exact version is located. For example, if the requested version is ``2.7``, SublimeLinter attempts to locate an executable named ``python2.7``.

- If the exact version cannot be located, the major version of the requested version is located. For example, if the requested version is ``2.7``, SublimeLinter attempts to locate an executable named ``python2``.

- If the major version is not available, SublimeLinter attempts to locate ``python``.

**Windows**
:raw-html:`<br>`
On Windows, python is usually installed in the root volume in a directory called “Python”, where ``<major>`` and ``<minor>`` are the major and minor python version. When a specific version is requested, the following happens:

- Directories whose names begin with “Python” in the root volume are iterated. The remainder of the directory name is used as the version.

- If the exact requested version does not match any of the directory versions, SublimeLinter attempts to match the major requested version.

- If the major requested version does not match any of the directory versions, SublimeLinter attempts to ``python``.


Version matching
~~~~~~~~~~~~~~~~
Once an available version of python is located, its full version is matched against the requested version. An available version satisfies a version request if one of the following is true:

- The requested version has no minor version and the available major version matches.

- The requested major version matches the available major version and the requested minor version is <= the available minor version.

If the available version satisfies the requested version, its path (or the built-in python) is used. Otherwise the request fails and the linter will not run.
