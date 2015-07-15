.. include:: defines.inc

Welcome to SublimeLinter 3
==========================
|_sl| is a plugin for |_st| that provides a framework for linting code. Whatever language you code in, |sl| can help you write cleaner, better, more bug-free code. |sl| has been designed to provide maximum flexibility and usability for users and maximum simplicity for linter authors.

The documentation for |sl| is divided into two sections: one for users, and one for developers who would like to create their own linter plugins.

`User Documentation`_ |bar_sep| `Developer Documentation`_

The |sl| source is available `on github`_.


Support
=======
Please use the |_group| for support and bug reporting but before opening a new ticket, verify there isn't already a ticket in the |_group| or the now deprecated `SublimeLinter google group`_.

.. _SublimeLinter google group: https://groups.google.com/forum/#!forum/sublimelinter
.. _on github: https://github.com/SublimeLinter/SublimeLinter3


Be Part of the Team
===================
Hundreds of hours have been spent writing and documenting |sl| to make it the best it can be — easy to use, easy to configure, easy to update, easy to extend. If you depend on |sl| to make your coding life better and easier, please consider making a donation to help fund development and support. Thank you!

|Donate Paypal|
|Donate Gratipay|

.. |Donate PayPal| image:: http://grotewold.me/assets/button-paypal.png
   :target: https://www.paypal.com/cgi-bin/webscr?cmd=_s-xclick&hosted_button_id=FK7SKD3X8N7BU

.. |Donate Gratipay| image:: http://grotewold.me/assets/button-gratipay.png
   :target: https://gratipay.com/skj3gg


User Documentation
==========================
.. toctree::
    :maxdepth: 3

    about
    installation
    usage
    lint_modes
    mark_styles
    gutter_themes
    navigating
    settings
    global_settings
    meta_settings
    linter_settings
    troubleshooting

Developer Documentation
==========================
.. toctree::
    :maxdepth: 3

    creating_a_linter
    linter_attributes
    linter_methods
    python_linter
    ruby_linter
    contributing
    acknowledgements
