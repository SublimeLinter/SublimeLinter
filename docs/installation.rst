Installation
==================

SublimeLinter and corresponding linter plugins should be installed using `PackageControl <https://packagecontrol.io/installation>`_.

First install PackageControl and refer its `usage <https://packagecontrol.io/docs/usage>`_,
then, *spoiler!*, execute `Install Package` from the Command Palette.

.. image:: https://user-images.githubusercontent.com/8558/248385523-c81c89d6-181b-4b4f-9109-a6ced8617e46.png

Please note that SublimeLinter is only the framework and does not come with any adapters for any existing linters.
These have to be installed separately.  That means, (a) you usually need to install linters, the same linters
that work on the command line, if you haven't done so already, and (b) you need to install adapters for these linters
that bridge to SublimeLinter.  
These adapters are ordinary `plugins <https://packagecontrol.io/search/SublimeLinter>`_ usually named after the linter
and are also listed on PackageControl. They're to be installed just like SublimeLinter itself.

Most plugins depend on command line programs to be installed on your system, be
sure to read the installation instructions for each linter plugin you install.  How
a specific linter works is typically not part of that documentation though so
further reading and studying might be necessary - especially when you're not familiar
with a specific linter or programming language eco-system

That warning aside SublimeLinter will typically just work out-of-the box and
do the linting in the background as you type.  Most linters support this mode.
For the few other SublimeLinter will run after you save a file.

Please note the commands we're installing using Sublime's Command Palette (``ctrl+shit+p``).
Just search for `SublimeLinter` here:

.. image:: https://github.com/SublimeLinter/SublimeLinter/assets/8558/f970eb78-8cae-4e40-829b-66b27facf60d.png


It's a good idea to subscribe to releases on GitHub.

.. image:: https://user-images.githubusercontent.com/8558/248387350-09b05e57-f2c0-41ab-8fda-5f06b48f6c32.png
  :target: https://github.com/SublimeLinter/SublimeLinter

These messages are rare 🤞, but inform you about upcoming changes and help you 
avoid surprises on the next restart of Sublime Text.

Support 
~~~~~~~~~~~

SublimeLinter is the kind of software that needs active maintenance all the time.  
If you find SublimeLinter helpful and would like to show your appreciation, you can support its development 
by buying me a coffee! 😄☕️ `<https://paypal.me/herrkaste>`_

❤️
