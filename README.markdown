Sublime Lint
=========

A framework for inline lint highlighting in the [Sublime Text 2](http://sublimetext.com "Sublime Text 2") editor.

Supports the following languages:

* Python - native, moderately-complete lint

NOTE: the following languages may require you to install additional binaries and place them within your PATH (environment variable)

* C - validation via `clang`
* C++ - validation via `clang++`
* CoffeeScript - validation via `coffee --compile`
* CSS - linting via `csslint`
* Go - validation via `go build` in a temporary folder
* HAML - checking via `haml -c`
* Java - linting via Eclipse command-line `eclim`
* JavaScript - linting via JSLint command-line `jsl`
* Lua - syntax checking via `luac -p`
* NASM - validation via `nasm` and a temporary file
* Perl - syntax+deprecation checking via `perl -c`
* PHP - syntax checking via `php -l`
* Ruby - syntax checking via `ruby -wc`
* XML - linting via `xmllint`

It's incredibly easy to add your own Linter. Take a look at `languages/extras.py`, `languages/python.py`, and `languages/go.py` for some examples.

Installation
-----

Find it in [Package Control](http://wbond.net/sublime_packages/package_control "Package Control").