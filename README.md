SublimeLinter
=============

[![Build Status](https://img.shields.io/travis/SublimeLinter/SublimeLinter/master.svg)](https://travis-ci.org/SublimeLinter/SublimeLinter)

A framework for interactive code linting in [Sublime Text 3](http://sublimetext.com/3).


## SublimeLinter 4 beta

We're making big improvements to how SublimeLinter works. You can read more about it [here](https://raw.githubusercontent.com/SublimeLinter/SublimeLinter/master/messages/4.0.0-rc.1.txt).

Participate in the beta right now by editing your Package Control preferences and adding SublimeLinter to the "install_prereleases" key:  
```json
"install_prereleases":
[
  "SublimeLinter"
]
```

<img src="https://raw.githubusercontent.com/SublimeLinter/SublimeLinter/master/docs/screenshot.png" width="848">


## Key Bindings

SublimeLinter comes with some pre-defined keyboard shortcuts. You can customize these via the Package Settings menu.

| Command         | Linux & Windows  | MacOS                  |
|-----------------|------------------|------------------------|
| Lint this view  | CTRL + K, L      | CTRL + CMD + L         |
| Show all errors | CTRL + K, A      | CTRL + CMD + A         |
| Goto next error | CTRL + K, N      | CTRL + CMD + E         |
| Goto prev error | CTRL + K, P      | CTRL + CMD + SHIFT + E |

Navigating to the next/previous error is done using the `next_result` and `prev_result` commands already built into Sublime Text.


## Support & Bugs

Please use the debug mode and include all console output, and your settings in your bug report. If your issue is specific to a particular linter, please report it on that linter's repository instead.


## Creating a linter plugin

Use the [template](https://github.com/SublimeLinter/SublimeLinter-template) to get started on your plugin. It contains a howto with all the information you need.

---------------------------


If you use SublimeLinter and feel it is making your coding life better and easier, please consider making a donation to help fund development and support. Thank you!

Donate via: 
* [**Paypal**](https://www.paypal.com/cgi-bin/webscr?cmd=_s-xclick&hosted_button_id=FK7SKD3X8N7BU)
