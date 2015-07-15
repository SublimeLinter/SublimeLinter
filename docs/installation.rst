.. include:: defines.inc

Installation
============
|sl| itself is only a **framework** for linters. The linters are distributed as independent |st| plugins.

|sl| (and the linter plugins) can be installed via a plugin called |_pc| or from source. I **strongly** recommend that you use |pc|! Not only does it ease installation, but more importantly it automatically updates the plugins it installs, which ensures you will get the latest features and bug fixes.


Upgrading from previous versions
---------------------------------
If you are upgrading to |sl| 3 from a previous version (including an ST3 branch), please be aware that |sl| 3 is a complete rewrite and is **not** a drop-in replacement. The basic functionality is the same, but there are key differences:

- Linters are not included, you must install them — and the linter binaries they depend on — separately. Linters can be found in |_pc| with the name “|sl|-<linter>”, for example “|sl|-jshint”.

- :doc:`Settings <settings>` do not work in the same way.

- You no longer need to use path settings voodoo to find linter executables. Anything in your system |path| is :ref:`found automatically <how-linter-executables-are-located>`.

- Most settings can be configured :doc:`via menus and the Command Palette <usage>`, which you are encouraged to do.

- There are dozens of new features.

.. warning::

   SublimeLinter 3 is **not** a drop-in replacement for earlier versions. If you are coming from an earlier version of |sl| and don’t read the documentation, you will get confused and frustrated. **Read the docs.**


Installing via |pc|
------------------------------
To install |sl| via |_pc|, follow these steps:

#. Open the |cmd|.

#. Type :kbd:`install` and select ``Package Control: Install Package`` from the Command Palette. There will be a pause of a few seconds while |pc| finds the available packages.

#. When the list of available packages appears, type :kbd:`linter` and select ``SublimeLinter``. **Note:** The github repository name is “SublimeLinter3”, but the plugin name remains “SublimeLinter”.

#. After a few seconds |sl| will be installed and loaded. Depending on your setup, you may see some prompts from |sl|. For more information on |sl|’s startup actions, see :ref:`Startup actions <startup-actions>`.

#. You will see an install message. After reading the message, restart |st|.

If you have a previous installation of |sl| via |pc|, including “|sl| Beta”, it should be updated correctly from the new version. If something goes wrong, use |pc| to remove |sl| and then follow the steps above to install again.

.. note::

   |sl| 3 does **not** include linters, unlike earlier versions.
   You **must** install linter plugins separately. They can be found in |_pc|
   with the name “|sl|-<linter>”, for example “|sl|-jshint”.


Installing from source
----------------------
I **very strongly** discourage you from installing from source. There is **no** advantage to installing from source vs. using |pc|. In fact, there are several disadvantages, including no automatic updates, no update messages, etc.

If you insist on installing from source, please do not do so unless you are comfortable with the command line and know what you are doing. To install |sl| from source, do the following:

#. Quit Sublime Text.

#. If you have a previous source installation at :file:`Packages/SublimeLinter`, delete it.

#. Type in a terminal:

   .. code-block:: none

      cd '/path/to/Sublime Text 3/Packages'
      git clone https://github.com/SublimeLinter/SublimeLinter3.git SublimeLinter

#. Restart |st|.

Please consider using |pc| instead!


Linter plugins
--------------
Regardless of how you install |sl|, once it is installed you will want to install linters appropriate to the languages in which you will be coding.

.. warning::

   Linter plugins are **not** part of |sl| 3.

Linter plugins are separate |st| plugins that are hosted in separate repositories. There are a number of officially supported linter plugins in the |_org|. There are third party linters available as well.

Again, I **strongly** recommend that you use |pc| to locate and install linter plugins. To install linter plugins in |pc|, do the following:

#. Open the |cmd|.

#. Type :kbd:`install` and select ``Package Control: Install Package`` from the Command Palette. There will be a pause of a few seconds while |pc| finds the available packages.

#. When the list of available packages appears, type :kbd:`sublimelinter-`. You will see a list of plugins whose names begin with “|sl|-”. Click on the plugin you wish to install.

#. After a few seconds the plugin will be installed and loaded. You will then see an install message with instructions on what you should do to complete the installation.

#. After reading the instructions, restart |st|.

.. warning::

   Most linter plugins require you to install a linter binary or library and :ref:`configure your PATH <how-linter-executables-are-located>` so that |sl| can find it. You **must** follow the linter plugin’s installation instructions to successfully use it.

If you have problems installing or configuring |sl|. First read the :doc:`Troubleshooting guide <troubleshooting>`. Then if necessary, report your problem on the |_group|.


Read the docs!
--------------------------
An enormous amount of time and effort went into creating |sl| and this documentation. **Before** you launch |st| with |sl| installed, please take the time to read the :doc:`Usage <usage>` documentation to understand what happens when |sl| loads and how it works. Otherwise you won’t get the most out of it!
