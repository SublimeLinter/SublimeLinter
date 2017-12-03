.. include:: defines.inc

About |sl|
===========
|sl| is a linting framework.

|sl| does not do the linting itself; it acts as a host for linting plugins. The linting plugins themselves usually do not perform linting either; they just act as a bridge between the code you type in Sublime Text and the actual linter.

Note that |sl| is not limited to a single linter plugin per syntax — you are free to install multiple linter plugins for a syntax, and all of them will run when you edit a file in that syntax.

In addition, |sl| supports multiple syntaxes in a single file, which is common when editing HTML. For example, a single HTML file may contain embedded CSS, JavaScript, and PHP. |sl| will lint all of the embedded code using the appropriate linter plugin.
