Sublime Lint
=========

A framework for inline lint highlighting in the [Sublime Text 2](http://sublimetext.com "Sublime Text 2") editor.

NOTE: You may to install additional binaries and place them within your PATH (environment variable) for some languages to work.

Supports the following languages:

* C - validation via `clang`
* C++ - validation via `clang++`
* CSS - linting via `csslint`
* CoffeeScript - validation via `coffee --compile`
* Go - validation via `go build` in a temporary folder
* HAML - checking via `haml -c`
* Java - linting via Eclipse command-line `eclim`
* JavaScript - linting via JSLint command-line `jsl`
* Lua - syntax checking via `luac -p`
* NASM - validation via `nasm` and a temporary file
* PHP - syntax checking via `php -l`
* Perl - syntax+deprecation checking via `perl -c`
* Python - native, moderately-complete lint
* Puppet - parsing via `puppet parser validate`
* Ruby - syntax checking via `ruby -wc`
* XML - linting via `xmllint`

It's incredibly easy to add your own Linter. Take a look at `languages/extras.py`, `languages/python.py`, and `languages/go.py` for some examples.

Installation
-----

Find it in [Package Control](http://wbond.net/sublime_packages/package_control "Package Control").
