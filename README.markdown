Sublime Lint
=========

A code-validating plugin with inline highlighting for the [Sublime Text 2](http://sublimetext.com "Sublime Text 2") editor.

Supports the following languages:

* Python - native, moderately-complete lint
* PHP - syntax checking via "php -l"
* Perl - syntax+deprecation checking via "perl -c"
* Ruby - syntax checking via "ruby -wc"

Installing
-----

*Without Git:* Download the latest source and copy sublimelint_plugin.py and the sublimelint/ folder to your Sublime Text "User" packages directory.

*With Git:* Clone the repository in your Sublime Text Packages directory (located one folder above the "User" directory)

> git clone git://github.com/lunixbochs/sublimelint.git

----

The "User" packages directory is located at:

* Windows:
    %APPDATA%/Sublime Text 2/Packages/User/
* OS X:
    ~/Library/Application Support/Sublime Text 2/Packages/User/
* Linux:
    ~/.config/sublime-text-2/User

You can also use the Preferences menu to open Package directories.