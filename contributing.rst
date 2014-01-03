.. include:: defines.inc

Contributing
========================
If you would like to submit a fix or enhancement to |sl|, thank you!

**BEFORE** you submit a pull request, please be sure you have followed these steps:

#. Fork the |sl| repo if you haven’t already.

#. Create an upstream remote if you haven’t already:

   .. code-block:: none

      git remote add -t master -m master -f upstream git@github.com:SublimeLinter/SublimeLinter3.git

#. Create a new branch from the upstream master:

   .. code-block:: none

      git checkout --no-track -b fix upstream/master

   Feel free to change “fix” to something more descriptive, like “fix-no-args”.

#. Make your changes. Please follow the :ref:`coding guidelines <guidelines>` below.

#. Commit your changes.

#. When you are ready to push, merge upstream again to make sure your changes will merge cleanly:

   .. code-block:: none

      git pull --rebase upstream/master

   If there are merge conflicts, fix them, commit the changes, and do this step again until it merges cleanly.

#. Push your branch to your fork:

   .. code-block:: none

      git push -u origin fix

   Substitute your branch name for “fix”.

#. Go to your fork on github and make a pull request. Please give as much information in the description as possible, including the conditions under which the bug occurs, what OS you are using, which linters are affected, sample code which caused the error, etc.


.. _guidelines:

Coding guidelines
-----------------
I’m a total fanatic about clean code that reads like a story, so please follow these guidelines when writing code for inclusion in |sl|:

- Indent is 4 spaces.

- Code should pass flake8 and pep257 linters.

- Vertical whitespace helps readability, don’t be afraid to use it. I especially like to separate any control structures (if/elif, loops, try/except, etc.) from surrounding code by a blank line above and below.

- Please use descriptive variable names, no abbreviations unless it's well known.

