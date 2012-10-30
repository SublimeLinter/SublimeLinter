Sublime Lint
=========

A framework for inline lint highlighting in the [Sublime Text 2](http://sublimetext.com "Sublime Text 2") editor.

Supports the following languages:

* Python - native, moderately-complete lint

NOTE: the following languages may require you to install additional binaries and place them within your PATH (environment variable)

* Coffescript - validation via `coffee --compile`
* CSS - linting via `csslint`
* Go - validation via `go build` in a temporary folder
* HAML - checking via `haml -c`
* JavaScript - linting via JSLint command-line `jsl`
* Lua - syntax checking via `luac -p`
* NASM - validation via `nasm` and a temporary file
* PHP - syntax checking via `php -l`
* Perl - syntax+deprecation checking via `perl -c`
* Ruby - syntax checking via `ruby -wc`
* XML - linting via `xmllint`

It's incredibly easy to add your own Linter. Take a look at `languages/extras.py`, `languages/python.py`, and `languages/go.py` for some examples.

Installing
-----

*Without Git:* Download the latest source and extract as a folder to your Sublime Text Packages directory (`Packages/SublimeLint/`).

*With Git:* Clone the repository into your Sublime Text Packages directory.

    git clone git://github.com/lunixbochs/sublimelint.git

----

The "Packages" directory is located here:

* Windows:
    `%APPDATA%/Sublime Text 2/Packages/`
* OS X:
    `~/Library/Application Support/Sublime Text 2/Packages/`
* Linux:
    `~/.Sublime Text 2/Packages/`

You can also go to `Preferences -> Browse Packages` from inside Sublime Text.
