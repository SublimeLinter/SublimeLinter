.. include:: defines.inc

Linter Attributes
========================
All linter plugins must be subclasses (direct or indirect) of ``SublimeLinter.lint.Linter``. The Linter class provides the attributes and methods necessary to make linters work within the |sl| framework.

The Linter class is designed to allow interfacing with most linter executables/libraries through the configuration of class attributes, with no coding necessary. Some linters, however, will need to do more work to set up the environment for the linter executable, or may do the linting directly in the linter plugin itself. In that case, you will need to read the :doc:`linter method documentation <linter_methods>`.


.. _cmd:

cmd
---
**Mandatory.** A string, list, tuple or :ref:`callable <cmd-method>` that returns a string, list or tuple, containing the command line (with arguments) used to lint. If a string, it should be as if it were entered on a command line, and is parsed by `shlex.split`_.

If ``cmd`` is ``None``, it is assumed the plugin overrides the :ref:`run` method.

A ``@`` argument will be replaced with the filename, which allows you to guarantee that certain arguments will be passed after the filename. When :ref:`tempfile_suffix` is set, the filename will be the temp filename.

A ``*`` argument will be replaced with the arguments built from the linter settings, which allows you to guarantee that certain arguments will be passed at the end of the argument list.

.. note::

   If the linter executable is python-based, there is a special form you should use for the ``cmd`` attribute. See :doc:`Python-based linters <python_linter>` for more information.

Examples
~~~~~~~~
Here is the ``cmd`` attribute used for the `csslint`_ linter plugin:

.. code-block:: python

    cmd = 'csslint --format=compact'

For the `jshint`_ linter plugin:

.. code-block:: python

    cmd = 'jshint --verbose -'

For the `flake8`_ linter plugin:

.. code-block:: python

    cmd = ('flake8@python', '*', '-')

Note how ``'*'`` is used as a placeholder for arguments built from settings, to ensure that ``'-'`` is passed as the last argument, which tells `flake8`_ to use ``stdin``.


.. _comment_re:

comment_re
----------
If the :ref:`inline_settings` or :ref:`inline_overrides` attribute is set, this attribute must be set to a `regex pattern`_ that matches the beginning of a comment. If you are subclassing from :doc:`PythonLinter <python_linter>` or :doc:`RubyLinter <ruby_linter>`, this attribute is set for you.

For example, to specify a match for JavaScript comments, you would use the pattern ``r'\s*/[/*]'``.


config_file
-----------
Many linters look for a config file in the linted file’s directory and in all parent directories up to the root directory. However, some of them will not do this if receiving input from ``stdin``, and others use temp files, so looking in the temp file directory doesn’t work.

If this attribute is set to a tuple of a config file argument and the name of the config file, the linter will automatically try to find the config file, and if it is found, add the config file argument to the executed command.

For example, if ``config_file`` is set to:

.. code-block:: python

    config_file = ('--config', '.jshintrc')

when |sl| builds the argument list for the command line, if the file being linted has been saved to disk, |sl| will look in the file’s directory for :file:`.jshintrc` and in all parent directories up to the root. If :file:`.jshintrc` is found, |sl| adds:

.. code-block:: none

    --config /path/to/.jshintrc

to the command line that runs the linter executable. Note that this facility works correctly when ``'*'`` is used as an argument placeholder in :ref:`cmd`.

You may also pass an arbitrary number of auxiliary directories to search after the second element, and ``~`` is expanded in those paths. If the hierarchy search fails, the auxiliary directories are checked in the order they are declared.

.. note::

   When checking auxiliary directories, the hierarchy is **not** traversed. Only those directories are checked for the given filename.

Going back to the :file:`.jshintrc` example above, to search in the file hierarchy and then in the user’s home directory for a :file:`.jshintrc` file, we would use this:

.. code-block:: python

    config_file = ('--config', '.jshintrc', '~')

The default value for ``config_file`` is ``None``.


default_type
------------
As noted in the :ref:`regex` documentation, you use the ``error`` and ``warning`` named capture groups to classify linter errors. If the linter output does not provide information which can be captured with those groups, this attribute is used to determine how to classify the linter error. The value should be ``highlight.ERROR`` or ``highlight.WARNING``. The default value is ``highlight.ERROR``.


.. _defaults:

defaults
--------
If you want to provide default settings for the linter, set this attribute to a dict of setting names and values.

If a setting will be passed as an argument to the linter executable, you may specify the format of the argument here and the setting will automatically be passed as an argument to the executable. The format specification is as follows:

.. code-block:: none

    <prefix><name><joiner>[<sep>[+]]

- **prefix** – Either ‘@’, ‘-’ or ‘--’.

- **name** – The name of the setting.

- **joiner** – Either ‘=’ or ‘:’. If ``prefix`` is ‘@’, this attribute is ignored (but may not be omitted). Otherwise, if this is ‘=’, the setting value is joined with ``name`` by ‘=’ and passed as a single argument. If ‘:’, ``name`` and the value are passed as separate arguments.

- **sep** – If the argument accepts a list of values, ``sep`` specifies the character used to delimit the list (usually ‘,’).

- **+** – If the setting can be a list of values, but each value must be passed as a separate argument, terminate the setting with ‘+’.

After the format is parsed, the prefix and suffix are removed and the setting key is replaced with ``name``.

.. note::

   When building the list of arguments to pass to the linter, if the setting value evaluates to ``False`` (``None``, zero, ``False``, or an empty sequence), the argument is not passed to the linter.


Examples
~~~~~~~~
The `flake8`_ linter accepts many command line options, but the ones we want to configure and pass to the linter are ``--select``, ``--ignore``, ``--max-line-length``, and ``--max-complexity``. So we define the ``defaults`` attribute as follows:

.. code-block:: python

    defaults = {
        '--select=,': '',
        '--ignore=,': '',
        '--max-line-length=': None,
        '--max-complexity=': -1
    }

Here’s how the ``--select=,`` default is parsed by |sl|:

.. code-block:: none

    prefix: --
    name: select
    joiner: =
    sep: ,

So ``--select=,`` accepts a list of values separated by ‘,’, the default value list is ``""``, and when passed to the linter it will be passed as one argument, with the values joined to ``--select`` by ‘=’. After parsing, ``--select=,`` is changed to ``select``.

The user sees these settings in their user settings:

.. code-block:: json

    {
        "flake8": {
            "@disable": false,
            "args": [],
            "excludes": [],
            "ignore": "",
            "max-complexity": -1,
            "max-line-length": null,
            "select": ""
        }
    }

Given those values, the arguments passed to ``flake8`` are:

.. code-block:: none

    --max-complexity=-1

If the user changes the settings to this:

.. code-block:: json

    {
        "flake8": {
            "@disable": false,
            "args": [],
            "excludes": [],
            "ignore": "W291,W293",
            "max-complexity": -1,
            "max-line-length": 120,
            "select": ""
        }
    }

the arguments passed to ``flake8`` are:

.. code-block:: none

    --ignore=W291,W293 --max-complexity=-1 --max-line-length=120

--------------

Here are the ``defaults`` for the `gjslint`_ linter plugin:

.. code-block:: python

    defaults = {
        '--jslint_error:,+': '',
        '--disable:,': '',
        '--max_line_length:': None
    }

Here’s how the ``--jslint_error:,+`` default is parsed by |sl|:

.. code-block:: none

    prefix: --
    name: jslint_error
    joiner: :
    sep: ,
    +: present

So ``--jslint_error:,+`` accepts a list of values separated by ‘,’, the default value list is ``""``, and when passed to the linter each value will be passed as a separate argument. After parsing, ``--jslint_error:,+`` is changed to ``jslint_error``.

The user sees these settings in their user settings:

.. code-block:: json

    {
        "gjslint": {
            "@disable": false,
            "args": [],
            "disable": "",
            "excludes": [],
            "jslint_error": "",
            "max_line_length": null
        }
    }

Given those values, no arguments are passed to `gjslint`_.

If the user changes the settings to this:

.. code-block:: json

    {
        "gjslint": {
            "@disable": false,
            "args": [],
            "disable": "0131,02",
            "excludes": [],
            "jslint_error": "indentation,unused_private_members",
            "max_line_length": 120
        }
    }

the arguments passed to ``gjslint`` are:

.. code-block:: none

    --disable 0131,02 --jslint_error indentation --jslint_error unused_private_members --max_line_length 120

--------------

Here is an example of using the ‘@’ prefix. The `phpmd`_ linter does not use named arguments, and it takes as the last argument a comma-delimited list of rulesets to use. We want these rulesets to be a setting and an inline override. To accomplish this, we define the linter attributes like this:

.. code-block:: python

    cmd = ('phpmd', '@', 'text')
    defaults = {
        '@rulesets:,': 'cleancode,codesize,controversial,design,naming,unusedcode'
    }
    inline_overrides = 'rulesets'
    comment_re = r'\s*<!--'

By default, the following arguments are passed to ``phpmd``:

.. code-block:: none

    /path/to/temp/file text cleancode,codesize,controversial,design,naming,unusedcode

The user can turn off individual rulesets inline, like this:

.. code-block:: none

    <!-- [SublimeLinter phpmd-rulesets:-controversial,-codesize] -->

which results in these arguments being passed to ``phpmd``:

.. code-block:: none

    /path/to/temp/file text cleancode,design,naming,unusedcode


.. _error_stream:

error_stream
------------
Some linters report errors on ``stdout``, some on ``stderr``. For efficiency reasons there is no point in parsing non-error output, so by default |sl| ignores ``stderr`` since most linters report errors on ``stdout``.

However, it’s very important that you capture errors generated by the linter itself, for example a bad command line argument or some internal error. Usually linters will report their own errors on ``stderr``. To ensure you capture both regular linter output and internal linter errors, you need to determine on which stream the linter writes reports and errors.

For example, with jshint we would do the following, using a file ``test.js`` that we know has errors:

.. code-block:: none

    >> jshint test.js
    test.js: line 4, col 13, Unnecessary semicolon.

    1 error

So far so good. Now we turn off ``stdout`` to see where this is coming from.

.. code-block:: none

    >> jshint test.js > /dev/null

.. note::

   On Windows, replace ``/dev/null`` with ``nul``.

So now we see that linter report is on ``stdout``. Now let’s force an error and see what happens.

.. code-block:: none

    >> jshint foo.js > /dev/null
    ERROR: Can't open foo.js

Since ``stdout`` is off, that means internal jshint errors are on ``stderr``. So to capture both reports and errors we need to set ``error_stream`` to ``util.STREAM_BOTH``.

Let’s look at another example:

.. code-block:: none

    >> csslint test.css
    csslint: There are 2 problems in /Users/aparajita/test.css.

    test.css
    1: warning at line 1, col 1
    Don't use IDs in selectors.
    #foo {

    test.css
    2: warning at line 2, col 10
    Values of 0 shouldn't have units specified.
      width: 0px;

    >> csslint test.css > /dev/null

    # It was empty, meaning it uses stdout for reporting
    >> csslint foo.css > /dev/null

    # Still empty, errors might be on stdout
    >>> csslint foo.css
    csslint: Could not read file data in /Users/aparajita/foo.css. Is the file empty?

    # Errors are also on stdout

So in this case, we set ``error_stream`` to ``util.STREAM_STDOUT``. In this case, since there is no output on ``stderr``, we could also leave it at the default of ``util.STREAM_BOTH``, but for other linters there is unwanted output on a stream, so it’s better to get in the habit of setting this to the exact value necessary.

With your linter, you will need to go through this process and set ``error_stream`` accordingly. Of course, you can be lazy and just set it to ``util.STREAM_BOTH``, but I recommend against it, because it might not always work the way you expect.

Here are the possibilities:

====== ====== ==================
Output Errors error_stream
====== ====== ==================
stdout stderr util.STREAM_BOTH
stdout stdout util.STREAM_STDOUT
stderr stdout util.STREAM_BOTH
stderr stderr util.STREAM_STDERR
====== ====== ==================


.. _executable:

executable
----------
If the name of the executable cannot be determined by the first element of ``cmd`` (for example when ``cmd`` is a method that dynamically generates the command line arguments), this can be set to the name of the executable used to do linting. Once the executable’s name is determined, its existence is checked in the user’s path. If it is not available, the linter is deactivated.

.. note::

   If the ``cmd`` attribute is a string, list or tuple whose first element is the linter executable name, you do **not** need to define this attribute.


.. _inline_overrides:

inline_overrides
----------------
This attribute is exactly like :ref:`inline_settings`, but defines a tuple/list of settings that can be used as :ref:`inline overrides <inline-overrides>`.


.. _inline_settings:

inline_settings
---------------
This attribute defines a tuple/list of settings that can be specified :ref:`inline <inline-settings>`. If an inline setting is used as an argument to the linter executable, be sure to define the setting as an argument in :ref:`defaults`. If this attribute is defined, you must define :ref:`comment_re` as well, unless you are subclassing from :doc:`PythonLinter <python_linter>` or :doc:`RubyLinter <ruby_linter>`, which does that for you.

Within a file, the actual inline setting name is ``<linter>-setting``, where ``<linter>`` is the lowercase name of the linter class. For example, the ``Flake8`` linter class defines the following:

.. code-block:: python

    inline_settings = ('max-line-length', 'max-complexity')

This means that ``flake8-max-line-length`` and ``flake8-max-complexity`` are recognized as inline settings.


line_col_base
-------------
This attribute is a tuple that defines the number base used by linters in reporting line and column numbers. Linters usually report errors with a line number, and some report a column number as well. In general, most linters use one-based line numbers and column numbers, so the default value is ``(1, 1)``. If a linter uses zero-based line numbers or column numbers, the linter class should define this attribute accordingly.

For example, if the linter reports one-based line numbers but zero-based column numbers, the value of this attribute should be ``(1, 0)``.


.. _multiline:

multiline
---------
This attribute determines whether the :ref:`regex` attribute parses multiple lines. The linter may output multiline error messages, but if :ref:`regex` only parses single lines, this attribute should be ``False`` (the default). It is important that you set this attribute correctly; it does more than just add the ``re.MULTILINE`` flag when it compiles the :ref:`regex` pattern.

If ``multiline`` is ``False``, the linter output is split into lines (using `str.splitlines`_ and each line is matched against :ref:`regex` pattern.

If ``multiline`` is ``True``, the linter output is iterated over using `re.finditer`_ until no more matches are found.


.. _re_flags:

re_flags
--------
If you wish to add custom `re flags`_ that are used when compiling the ``regex`` pattern, you may specify them here.

For example, if you want the pattern to be case-insensitive, you could do this:

.. code-block:: python

    re_flags = re.IGNORECASE

As noted in the :ref:`examples <re-flags-example>`, these flags can also be included within the :ref:`regex` pattern itself. It’s up to you which technique you prefer.


.. _regex:

regex
-----
**Mandatory.** A `python regular expression`_ pattern used to extract information from the linter’s output. The pattern must contain at least the following named capture groups:

======= ===========================================
Name    Description
======= ===========================================
line    The line number on which the error occurred
message The error message
======= ===========================================

Actually the pattern doesn’t *have* to have these named capture groups, but if it doesn’t you must override the :ref:`split_match <split_match>` method and provide those values yourself.

In addition to the above capture groups, the pattern should contain the following named capture groups when possible:

+-----------+--------------------------------------------------------+
| Name      | Description                                            |
+===========+========================================================+
| col       | The column number where the error occurred, or         |
|           | a string whose length provides the column number       |
+-----------+--------------------------------------------------------+
| error     | If this is not empty, the error will be marked         |
|           | as an error by |sl|                                    |
+-----------+--------------------------------------------------------+
| warning   | If this is not empty, the error will be marked         |
|           | as a warning by |sl|                                   |
+-----------+--------------------------------------------------------+
| near      | If the linter does not provide a column number but     |
|           | mentions a name, match the name with this capture      |
|           | group and |sl| will attempt to highlight that name.    |
|           | Enclosing single or double quotes will be stripped,    |
|           | you may include them in the capture group. If the      |
|           | linter provides a column number, you may still use     |
|           | this capture group and |sl| will highlight that text   |
|           | (stripped of quotes) exactly.                          |
+-----------+--------------------------------------------------------+


Examples
~~~~~~~~
The output from the `flake8`_ linter looks like this:

.. code-block:: none

    test.py:12:8: W601 .has_key() is deprecated, use 'in'
    test.py:15:11: E271 multiple spaces after keyword
    test.py:22:11: E225 missing whitespace around operator
    test.py:25:16: F821 undefined name 'barrrrr'

The structure of the output is:

.. code-block:: none

    <file>:<line>:<col> <error code> <message>

We translate that into this ``regex``:

.. code-block:: python

    regex = (
        r'^.+?:(?P<line>\d+):(?P<col>\d+): '
        r'(?:(?P<error>[EF])|(?P<warning>[WCN]))\d+ '
        r'(?P<message>.+)'
    )

A few things to note about this pattern:

- We are using the trick of enclosing multiple strings in parentheses to split the string up visually. Python concatenates them into one string.

- We don’t bother capturing the filename (``^.+?:``), it isn’t used by |sl|.

- To capture **either** an error or a warning, those capture groups are wrapped in a non-capturing group with alternation.

- Based on the letter prefix of the error code, the linter plugin decides whether to report it to |sl| as an error or a warning.

--------------

Here is the output from `jsl <http://www.javascriptlint.com/>`__:

.. code-block:: none

    (2): lint warning: empty statement or extra semicolon
     b =0;;
    ......^

    (6): warning: variable bar hides argument
        var bar = 'this is a really long string that should be too long';
    ........^

    (10): lint warning: unreachable code
        var i = 0;
    ....^

The structure of the output is:

.. code-block:: none

    (<line>): <type>: <message>
    <code>
    <position marker>^

.. _re-flags-example:

We translate that structure into this ``regex``:

.. code-block:: python

    regex = r'''(?xi)
        # First line is (lineno): type: error message
        ^\((?P<line>\d+)\):.*?(?:(?P<warning>warning)|(?P<error>error)):\s*(?P<message>.+)$\r?\n

        # Second line is the line of code
        ^.*$\r?\n

        # Third line is a caret pointing to the position of the error
        ^(?P<col>[^\^]*)\^$
    '''
    multiline = True

A few things to note:

- The :ref:`multiline` attribute is set to ``True``, because each error message occupies more than one line.

- We set the pattern to be case-insensitive and verbose with ``(?xi)``. This could have been done with the :ref:`re_flags` attribute, but doing it within the regex pattern is easier.

- We use ``\r?\n`` at the end of a line to ensure Windows CRLF is matched.

- By capturing the dots before the caret with the ``(?P<col>[^\^]*)`` pattern, we get the column position of the error on the line.

.. note::

   |re-try|


.. _selectors:

selectors
---------
If a linter can be used with embedded code, you need to tell |sl| which portions of the source code contain the embedded code by specifying the embedded `scope selectors`_. This attribute maps syntax names to embedded scope selectors.

For example, the HTML syntax uses the scope ``source.js.embedded.html`` for embedded JavaScript. To allow a JavaScript linter to lint that embedded JavaScript, you would set this attribute to:

.. code-block:: python

    selectors = {
        'html': 'source.js.embedded.html'
    }


.. _shebang_match:

shebang_match
-------------
Some linters may want to turn a shebang into an inline setting. To do so, set this attribute to a callback which receives the first line of code and returns a tuple/list which contains the name and value for the inline setting, or ``None`` if there is no match.

For example, the ``SublimeLinter.lint.PythonLinter`` class defines the following:

.. code-block:: python

    @staticmethod
    def match_shebang(code):
        """Convert and return a python shebang as a @python:<version> setting."""

        match = PythonLinter.SHEBANG_RE.match(code)

        if match:
            return '@python', match.group('version')
        else:
            return None

    shebang_match = match_shebang


.. _syntax:

syntax
------
**Mandatory.** This attribute is the primary way that |sl| associates a linter plugin with files of a given syntax. See :ref:`Syntax names <syntax-names>` below for info on how to determine the correct syntax names to use.

This may be a single string, or a list/tuple of strings. If the linter supports multiple syntaxes, you may either use a list/tuple of strings, or a single string which begins with ``^``, in which case it is compiled as a regular expression pattern which is matched against a syntax name.

If the linter supports embedded syntaxes, be sure to make this attribute a list/tuple or regex pattern which includes the embedding syntax, one of whose values should match one of the keys in the :ref:`selectors <selectors>` dict. For example, ``CSSLint`` defines the ``syntax`` and ``selectors`` attributes as:

.. code-block:: python

    syntax = ('css', 'html')
    selectors = {
        'html': 'source.css.embedded.html'
    }


.. _syntax-names:

Syntax names
~~~~~~~~~~~~
The syntax names |sl| uses are based on the **internal** syntax name used by |st|, which does not always match the display name. The internal syntax name can be found by doing the following:

#. Open a file which has the relevant syntax, or alternately create a new file and set the syntax in the ``View > Syntax`` menu.

#. Open the |st| console and enter :kbd:`view.settings().get('syntax')`. The result will be a path to a :file:`.tmLanguage` file, for example :file:`'Packages/JavaScript/JavaScript.tmLanguage'`.

#. The lowercase filename without the extension (.e.g. :file:`javascript`) is the syntax name |sl| uses.


.. _tempfile_suffix:

tempfile_suffix
---------------
This attribute configures the behavior of linter executables that cannot receive input from ``stdin``.

If the linter executable require input from a file, |sl| can automatically create a temp file from the current code and pass that file to the linter executable. To enable automatic temp file creation, set this attribute to the suffix of the temp file name (with or without a leading ‘.’).

For example, `csslint`_ cannot use ``stdin``, so the linter plugin does this:

.. code-block:: python

    tempfile_suffix = 'css'

If the suffix needs to be mapped to the syntax of a file, you may make this attribute a dict that maps syntax names (all lowercase, as used in the :ref:`syntax` attribute), to temp file suffixes. The name used to lookup the suffix is the mapped syntax, after using :ref:`"syntax_map" <syntax_map>` in settings. If the view’s syntax is not in this map, the class’ syntax will be used.

For example, here is a ``tempfile_suffix`` map for a linter that supports three different syntaxes:

.. code-block:: python

    tempfile_suffix = {
        'haskell': 'hs',
        'haskell-sublimehaskell': 'hs',
        'literate haskell': 'lhs'
    }


File-only linters
~~~~~~~~~~~~~~~~~
Some linters can only work from an actual disk file, because they rely on an entire directory structure that cannot be realistically be copied to a temp directory (e.g. ``javac``). In such cases, you can mark a linter as “file-only” by setting ``tempfile_suffix`` to ``'-'``.

File-only linters will only run on files that have not been modified since their last save, ensuring that what the user sees and what the linter executable sees is in sync.


.. _version_args:

version_args
---------------
This attribute defines the arguments that should be passed to the linter executable to get its version. It may be a string, in which case it may contains multiple arguments separated by spaces, or it may be a list or tuple containing one argument per element.

For example, most linter executables return the current version when passed ``--version`` as an argument:

.. code-block:: python

    version_args = '--version'

.. note::

   This attribute should **not** include the linter executable name or path.


.. _version_re:

version_re
---------------
This attribute should be a regex pattern or compiled regex used to match the numeric portion of the version returned by executing the linter binary with :ref:`version_args`. It must contain a named capture group called “version” that captures only the version, including dots but excluding a prefix such as “v”.

For example, ``jshint --version`` returns ``jshint v2.4.1``, so the ``version_re`` is:

.. code-block:: python

   version_re = r'\bv(?P<version>\d+\.\d+\.\d+)'

Note that we did not try to match “jshint ” at the beginning, just in case that text changes in the future.

.. note::

   In general, it is best to make the regex as lenient as possible to allow for changes in the way linter executables format version output.


.. _version_requirement:

version_requirement
--------------------
This attribute should be a string which describes the version requirements, suitable for passing to the `distutils.versionpredicate.VersionPredicate constructor`_.

.. note::

   Only the version requirements (what is inside the parens) should be specified here, do not include the package name or parens.

.. _distutils.versionpredicate.VersionPredicate constructor: http://epydoc.sourceforge.net/stdlib/distutils.versionpredicate.VersionPredicate-class.html

For example, the SublimeLinter-jsl plugin requires version 0.3.x of ``jsl``, and will not work with a minor version higher than 3. So the version requirement is:

.. code-block:: python

   version_requirement = '>= 0.3.0, < 0.4.0'

Note that if you were actually constructing a ``VersionPredicate``, you would have to pass a string like this:

.. code-block:: python

   predicate = VersionPredicate('SublimeLinter.jsl (>= 0.3.0, < 0.4.0)')

In the case of ``version_requirement`` however, you only need to specify what is inside the parentheses. |sl| fills in the rest.


word_re
-------
If a linter reports a column position, |sl| highlights the nearest word at that point. By default, |sl| uses the regex pattern ``r'^([-\w]+)'`` to determine what is a word. You can customize the regex used to highlight words by setting this attribute to a pattern string or a compiled regex.

For example, the `csslint`_ linter plugin defines:

.. code-block:: python

    word_re = r'^(#?[-\w]+)'

This allows an id selector such as “#foo” to be highlighted as one word. Without the custom pattern, only the “#” would be highlighted.

.. _shlex.split: http://docs.python.org/3/library/shlex.html?highlight=shlex.split#shlex.split
.. _str.splitlines: http://docs.python.org/3/library/stdtypes.html?highlight=splitlines#str.splitlines
.. _regex pattern: http://docs.python.org/3/library/re.html?highlight=re#regular-expression-syntax
.. _re.finditer: http://docs.python.org/3/library/re.html?highlight=finditer#re.finditer
.. _re flags: http://docs.python.org/3/library/re.html?highlight=finditer#re.compile
.. _scope selectors: http://docs.sublimetext.info/en/latest/extensibility/syntaxdefs.html#scopes-and-scope-selectors
.. _gjslint: https://developers.google.com/closure/utilities/docs/linter_howto
.. _phpmd: http://phpmd.org/documentation/index.html
