.. include:: defines.inc

RubyLinter class
======================
If your linter plugin interfaces with a linter that is written in ruby, you should subclass from ``SublimeLinter.lint.RubyLinter``.

.. note::

   This is done for you if you use the :ref:`Create Linter Plugin <create-linter-plugin-command>` command and select ``Ruby`` as the linter language.

By doing so, you get the following features:

- :ref:`comment_re` is defined correctly for ruby.

- Support for `rbenv`_ and `rvm`_ (via rvm-auto-ruby).


rbenv and rvm support
----------------------
During class construction, |sl| attempts to locate the gem and ruby specified in :ref:`cmd`.

The following forms are valid for the first argument of ``cmd``:

.. code-block:: none

    gem@ruby
    gem
    ruby

If ``rbenv`` is installed and the gem is also under ``rbenv`` control,
the gem will be executed directly. Otherwise ``(ruby [, gem])`` will be executed.

If ``rvm-auto-ruby`` is installed, ``(rvm-auto-ruby [, gem])`` will be executed.

Otherwise ``ruby`` or ``gem`` will be executed.

.. _rbenv: https://github.com/sstephenson/rbenv
.. _rvm: http://rvm.io
