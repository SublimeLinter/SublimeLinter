SublimeLinter
=============

[![Build Status](https://img.shields.io/travis/SublimeLinter/SublimeLinter3/master.svg)](https://travis-ci.org/SublimeLinter/SublimeLinter3)

**Linters not included**

SublimeLinter is a framework for interactive code linting in [Sublime Text 3](http://sublimetext.com/3).

[Documentation on readthedocs.org](https://sublimelinter.readthedocs.org).


## SublimeLinter 4 beta

We're making big improvements to how SublimeLinter works. You can read more about it [here](https://github.com/SublimeLinter/SublimeLinter3/blob/next/messages/4.0.0-rc.1.txt) and track our progress in [PR #666](https://github.com/SublimeLinter/SublimeLinter3/pull/666). PRs with contributions are welcome on the `next` branch.

Participate in the beta right now by editing your Package Control preferences and adding SublimeLinter to the "install_prereleases" key:  
```json
"install_prereleases":
[
  "SublimeLinter"
]
```

If you want to use **SublimeLinter-flake8** during the beta, you need to add it to the "install_prereleases" as well. Most other linter plugins should be compatible.

*Disclaimer: there will be bugs and we will make changes that will break your workflow, but it's pretty awesome otherwise*


## Key Bindings

SublimeLinter comes with several pre-defined keyboard shortcuts. You can customize these via the Package Settings menu\*. Read more about keybindings in [the unofficial documentation](http://docs.sublimetext.info/en/latest/customization/key_bindings.html)

| Command         | Linux & Windows  | MacOS                  |
|-----------------|------------------|------------------------|
| Lint            | CTRL + K, L      | CTRL + CMD + L         |
| Next Error      | CTRL + K, N      | CTRL + CMD + E         |
| Prev. Error     | CTRL + K, P      | CTRL + CMD + SHIFT + E |
| Show All Errors | CTRL + K, A      | CTRL + CMD + A         |
| Toggle Linter   | CTRL + K, T      | CTRL + CMD + T         |


## Support & Bugs

Please use the debug mode and include all console output, and your settings in your bug report. If your issue is specific to a particular linter, please report it on that linter's repository instead.


## Contributing linter plugins
Please see the documentation on [creating linter plugins](https://sublimelinter.readthedocs.org/en/latest/creating_a_linter.html) for more information.

---------------------------

If you use SublimeLinter and feel it is making your coding life better and easier, please consider making a donation to help fund development and support. Thank you!

Donate via: 
* [**Paypal**](https://www.paypal.com/cgi-bin/webscr?cmd=_s-xclick&hosted_button_id=FK7SKD3X8N7BU)
* [**Bitcoin (Coinbase)**](https://www.coinbase.com/groteworld)

