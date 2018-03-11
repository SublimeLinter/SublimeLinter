RubyLinter class
======================
If your linter plugin interfaces with a linter that is written in ruby,
you should subclass from ``SublimeLinter.lint.RubyLinter``.

By doing so, you get support for `rbenv`_ and `rvm`_ (via rvm-auto-ruby).


rbenv and rvm support
----------------------
During class construction, SublimeLinter attempts to locate the gem and ruby specified in :ref:`cmd <cmd>`.

The following forms are valid for the first argument of ``cmd``:

.. code-block:: python

    gem@ruby
    gem
    ruby

If ``rbenv`` is installed and the gem is also under ``rbenv`` control,
the gem will be executed directly. Otherwise ``(ruby [, gem])`` will be executed.

If ``rvm-auto-ruby`` is installed, ``(rvm-auto-ruby [, gem])`` will be executed.

Otherwise ``ruby`` or ``gem`` will be executed.

.. _rbenv: https://github.com/rbenv/rbenv
.. _rvm: http://rvm.io
