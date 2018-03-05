SublimeLinter
=============

[![Build Status](https://img.shields.io/travis/SublimeLinter/SublimeLinter/master.svg)](https://travis-ci.org/SublimeLinter/SublimeLinter)

The code linting framework for [Sublime Text 3](http://sublimetext.com/3).


## Upgrading from SublimeLinter 3

You can read about all the changes [here](https://raw.githubusercontent.com/SublimeLinter/SublimeLinter/master/messages/4.0.0.txt). If you're not ready for this, you can manually install the last [SL3 release](https://github.com/SublimeLinter/SublimeLinter/releases/tag/v3.10.10).

Perhaps most important are changes to settings.
Inline settings and .sublimelinterrc configurations files no longer work. 
If you need inline or per-directory overrides, most linters provide features for that. 
[Project settings](https://github.com/SublimeLinter/SublimeLinter/blob/master/docs/settings.rst#project-settings) are still there though,
and you can use several [variables](https://github.com/SublimeLinter/SublimeLinter/blob/master/docs/settings.rst#settings-expansion) in them now.

There is no longer a global ["python"](https://github.com/SublimeLinter/SublimeLinter/blob/master/docs/linter_settings.rst#python) setting,
but it can be set per linter. 
Linters now also have ["executable"](https://github.com/SublimeLinter/SublimeLinter/blob/master/docs/linter_settings.rst#executable) settings,
and styles can be customized per linter (and even per error code).
The default settings have a lot of documentation in them to help you tweak them. Also be sure to check the keybindings, they have several options too.



<img src="https://raw.githubusercontent.com/SublimeLinter/SublimeLinter/master/docs/screenshot.png" width="848">


## Key Bindings

SublimeLinter comes with some pre-defined keyboard shortcuts. You can customize these via the Package Settings menu.

| Command         | Linux & Windows  | MacOS                  |
|-----------------|------------------|------------------------|
| Lint this view  | CTRL + K, L      | CTRL + CMD + L         |
| Show all errors | CTRL + K, A      | CTRL + CMD + A         |
| Goto next error | CTRL + K, N      | CTRL + CMD + E         |
| Goto prev error | CTRL + K, P      | CTRL + CMD + SHIFT + E |


## Support & Bugs

Please use the debug mode and include all console output, and your settings in your bug report.
If your issue is specific to a particular linter, please report it on that linter's repository instead.


## Creating a linter plugin

Fork the [template](https://github.com/SublimeLinter/SublimeLinter-template) to get started on your plugin.
It contains a howto with all the information you need.

---------------------------


If you use SublimeLinter and feel it is making your coding life better and easier,
please consider making a donation for all the coffee and beer involved in this project.
Thank you!

Donate via: 
* [**Paypal**](https://paypal.me/pools/c/82jmBQtUbY)
