SublimeLinter
=============

[![tests](https://github.com/SublimeLinter/SublimeLinter/actions/workflows/test.yml/badge.svg)](https://github.com/SublimeLinter/SublimeLinter/actions/workflows/test.yml)

The code linting framework for [Sublime Text](http://sublimetext.com/).
No linters included: get them via [Package Control](https://packagecontrol.io/search/SublimeLinter).

<img src="https://raw.githubusercontent.com/SublimeLinter/SublimeLinter/master/docs/screenshot.png" width="785">


## Installation 

Install SublimeLinter and linters via [Package Control](https://packagecontrol.io/search/SublimeLinter). 


## Settings

Settings are documented in the [default settings](https://github.com/SublimeLinter/SublimeLinter/blob/master/SublimeLinter.sublime-settings). 
Open the settings using the Command Palette (`ctrl+shift+P`) searching for `Preferences: SublimeLinter Settings` (mnemonic: `sls`).

When you open the SublimeLinter settings you'll see the defaults on the left
or top.  Usually that's all that is needed for end-users but some additional information is in our docs at [sublimelinter.com](http://sublimelinter.com/).


## Quick Actions/Fixers

As we do *just* linting SublimeLinter naturally does not come with fixers 
and/or code formatters.  However, we have a fixer API and ship (mostly) 
"fix by ignoring" actions.  These allow you to quickly ignore specific error messages *inline* and ad hoc.[1]

SublimeLinter currently ships actions for [eslint](https://github.com/SublimeLinter/SublimeLinter-eslint), [stylelint](https://github.com/SublimeLinter/SublimeLinter-stylelint), [flake8](https://github.com/SublimeLinter/SublimeLinter-flake8), [mypy](https://github.com/fredcallaway/SublimeLinter-contrib-mypy), shellcheck, [codespell](https://github.com/kaste/SublimeLinter-contrib-codespell) and [phpcs](https://github.com/SublimeLinter/SublimeLinter-phpcs).

Want to see actions for your favourite linter? Please open a PR with your addition to [quick_fix.py](https://github.com/SublimeLinter/SublimeLinter/blob/master/lint/quick_fix.py). We have [tests](https://github.com/SublimeLinter/SublimeLinter/tree/master/tests/test_ignore_fixers.py) for them!

[1]  Why this limitation though?  Well it is usually easy to add a semicolon here and a space there, but the inline ignore rules and syntaxes are very cumbersome to type and to remember.  And there is basically no project of any size where you don't have to ignore ad-hoc something somewhere once.


## Key Bindings

SublimeLinter comes with some pre-defined keyboard shortcuts. You can customize these via the Package Settings menu.

| Command                | Linux & Windows  | MacOS                  |
|------------------------|------------------|------------------------|
| Lint this view         | CTRL + K, L      | CTRL + CMD + L         |
| Open diagnostics panel | CTRL + K, A      | CTRL + CMD + A         |
| Goto next error        | CTRL + K, N      | CTRL + CMD + E         |
| Goto prev error        | CTRL + K, P      | CTRL + CMD + SHIFT + E |

Take also a look at the [default bindings](<https://github.com/SublimeLinter/SublimeLinter/blob/master/keymaps/Default (Windows).sublime-keymap>) because
we document other commands and have usually some tricks in there too.

For example, it is very advisable to bind `sublime_linter_quick_actions`, e.g.

```
    // To trigger a quick action
    // { "keys": ["ctrl+k", "ctrl+f"],
    //   "command": "sublime_linter_quick_actions"
    // },
```


## Support & Bugs

Please use the [debug mode](http://www.sublimelinter.com/en/stable/troubleshooting.html#debug-mode)
and include all console output, and your settings in your
[bug report](https://github.com/SublimeLinter/SublimeLinter/issues/new).
If your issue is specific to a particular linter, please report it on that linter's repository instead.


## Creating a linter plugin

Fork the [template](https://github.com/SublimeLinter/SublimeLinter-template) to get started on your plugin.
It contains a howto with all the information you need.
