Sublime Lint
=========

A framework for error highlighting in the [Sublime Text](http://sublimetext.com "Sublime Text") editor.

It's easy to add language support. Take a look at the [linter repository](http://github.com/lunixbochs/linters "Linter Repository") for examples.

Linters in your Sublime Text `User/linters` folder will be automatically used. Changes to linters in this folder will be overwritten on automatic update. If you want to change a builtin linter, disable it in the Sublime Lint preferences and copy the source to a new file/class name.

You can also import `Linter` and subclass it inside `plugin_loaded()` from any other Sublime plugin.

Installation
-----

You can install in ST3 by adding this repository to [Package Control](http://wbond.net/sublime_packages/package_control "Package Control"), which does automatic updates.

Alternatively, you can clone `sublimelint` into your Packages folder and switch to the `st3` branch manually, but you will need to update manually.
