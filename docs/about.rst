.. include:: defines.inc

About |sl|
===========
|sl| is a linting framework. The actual linting is done by separate |st| plugins, which can be installed via |_pc|.

What is a linter?
-----------------
A linter is a small program that checks code for stylistic or programming errors. Linters are available for most syntaxes, from Python to HTML. Here is a sample list of syntaxes and their linters:

========== ===================
**Syntax** **Linter**
========== ===================
Python     `flake8`_
JavaScript `jshint`_
CSS        `csslint`_
Ruby       :command:`ruby -wc`
========== ===================

|sl| does not do the linting itself; it acts as a host for linting plugins. The linting plugins themselves usually do not perform linting either; they just act as a bridge between the code you type in Sublime Text and the actual linter.

Note that |sl| is not limited to a single linter plugin per syntax — you are free to install multiple linter plugins for a syntax, and all of them will run when you edit a file in that syntax.

In addition, |sl| supports multiple syntaxes in a single file, which is common when editing HTML. For example, a single HTML file may contain embedded CSS, JavaScript, and PHP. |sl| will lint all of the embedded code using the appropriate linter plugin.

Why do I need a linter?
-----------------------
Programming is hard. We are bound to make mistakes. The big advantage of using |sl| is that your code can be linted **as you type** (before saving your changes) and any errors are highlighted **immediately**, which is considerably easier than saving the file, switching to a terminal, running a linter, reading through a list of errors, then switching back to Sublime Text to locate the errors!

In addition, linters can help to enforce coding standards, find unused variables, and even make coffee for you — okay, so maybe they can’t make coffee. But they are an invaluable part of your programming toolkit.

Ready to get started? The next step is to :doc:`install SublimeLinter <installation>` and the linter plugins you need.
