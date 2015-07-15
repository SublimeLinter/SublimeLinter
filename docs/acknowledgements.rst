.. include:: defines.inc

Acknowledgements
====================
|sl| has come full circle — twice. Here’s a basic timeline of how it evolved:

* `Ryan Hileman`_ released the `sublimelint`_ plugin for Sublime Text 2.
* `Germán Bravo`_ forked sublimelint, added features, and released it as |sl|.
* `Aparajita Fishman`_ rewrote the |sl| linter architecture and added more features.
* `Jake Swartwood`_ picked up the torch and did a lot of great work maintaining and extending SublimeLinter.
* Sublime Text 3 (ST3) arrived. SublimeLinter needed some work; it didn’t run on ST3, and had some serious architectural problems that were making maintenance difficult.
* Jake and Aparajita talked about what to do, and approached Ryan about merging sublimelint and SublimeLinter. Ryan pointed out the fantastic `ST3 version of sublimelint`_ he had done.
* Aparajita took one look at that code and realized it was a **way** better foundation for a new ST3 version of SublimeLinter than the existing SublimeLinter codebase.
* Realizing how big the task was, Aparajita solicited donations to fund the development of SublimeLinter 3. The SublimeLinter community responded!
* Aparajita `forked the sublimelint ST3 branch`_ and spent two months rewriting SublimeLinter to be better, faster, much easier to use, much easier to configure, and much easier to extend than the previous version.

Special thanks to the main developers and all those in the community who contributed code or money to make |sl| 3 possible!

.. _Ryan Hileman: https://github.com/lunixbochs
.. _sublimelint: https://github.com/lunixbochs/sublimelint
.. _Germán Bravo: https://github.com/Kronuz
.. _Aparajita Fishman: https://github.com/aparajita
.. _Jake Swartwood: https://github.com/jswartwood
.. _ST3 version of sublimelint: https://github.com/lunixbochs/sublimelint/tree/st3
.. _forked the sublimelint ST3 branch: https://github.com/SublimeLinter/SublimeLinter3
