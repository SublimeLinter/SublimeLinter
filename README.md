SublimeLinter
=============

[![Build Status](https://img.shields.io/travis/SublimeLinter/SublimeLinter/master.svg)](https://travis-ci.org/SublimeLinter/SublimeLinter)

The code linting framework for [Sublime Text](http://sublimetext.com/).
No linters included: get them via [Package Control](https://packagecontrol.io/search/SublimeLinter).

<img src="https://raw.githubusercontent.com/SublimeLinter/SublimeLinter/master/docs/screenshot.png" width="785">

## Installation 

Install SublimeLinter and linters via [Package Control](https://packagecontrol.io/search/SublimeLinter). 

## Settings

Settings are mostly documented in the [default settings](https://github.com/SublimeLinter/SublimeLinter/blob/master/SublimeLinter.sublime-settings). When you open the SublimeLinter settings you'll see them on the left.

- Additional information is in our docs at [sublimelinter.com](http://sublimelinter.com/).
- Read about all the changes between 3 and 4 [here](https://raw.githubusercontent.com/SublimeLinter/SublimeLinter/master/messages/4.0.0.txt). 

## Quick Actions (beta)

We're building a new feature called Quick Actions, that will allow you to quickly ignore specific error messages. At first SublimeLinter will ship actions for [eslint](https://github.com/SublimeLinter/SublimeLinter-eslint), [stylelint](https://github.com/SublimeLinter/SublimeLinter-stylelint), [flake8](https://github.com/SublimeLinter/SublimeLinter-flake8), [mypy](https://github.com/fredcallaway/SublimeLinter-contrib-mypy) and [phpcs](https://github.com/SublimeLinter/SublimeLinter-phpcs).

Want to see actions for your favourite linter? Please open a PR with your addition to [quick_fix.py](https://github.com/SublimeLinter/SublimeLinter/blob/master/lint/quick_fix.py). We have some [tests](https://github.com/SublimeLinter/SublimeLinter/tree/master/tests) you can add to as well. 

Eventually, as this feature becomes more stable, we will expose it as an API so that plugins can add their own actions.

## Key Bindings

SublimeLinter comes with some pre-defined keyboard shortcuts. You can customize these via the Package Settings menu.

| Command         | Linux & Windows  | MacOS                  |
|-----------------|------------------|------------------------|
| Lint this view  | CTRL + K, L      | CTRL + CMD + L         |
| Show all errors | CTRL + K, A      | CTRL + CMD + A         |
| Goto next error | CTRL + K, N      | CTRL + CMD + E         |
| Goto prev error | CTRL + K, P      | CTRL + CMD + SHIFT + E |


## Support & Bugs

Please use the [debug mode](http://www.sublimelinter.com/en/stable/troubleshooting.html#debug-mode)
and include all console output, and your settings in your
[bug report](https://github.com/SublimeLinter/SublimeLinter/issues/new).
If your issue is specific to a particular linter, please report it on that linter's repository instead.


## Creating a linter plugin

Fork the [template](https://github.com/SublimeLinter/SublimeLinter-template) to get started on your plugin.
It contains a howto with all the information you need.

---------------------------


If you use SublimeLinter and feel it is making your coding life better and easier,
please consider making a donation for all the coffee and beer involved in this project.
Thank you!

Donate via: 
* [**Paypal**](https://paypal.me/pools/c/82jmBQtUbY)
