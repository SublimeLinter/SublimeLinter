SublimeLinter
=============

[![tests](https://github.com/SublimeLinter/SublimeLinter/actions/workflows/test.yml/badge.svg)](https://github.com/SublimeLinter/SublimeLinter/actions/workflows/test.yml)

The code linting framework for [Sublime Text](http://sublimetext.com/).
No linters included: get them via [Package Control](https://packagecontrol.io/search/SublimeLinter).

<img width="785" src="https://raw.githubusercontent.com/SublimeLinter/SublimeLinter/master/docs/screenshot.png"/>


## Installation 

> [!NOTE]
> The current stable version of Sublime Text, Build 4169, has a bug and cannot install
> SublimeLinter without requiring a restart.  You're fine if you have a later dev build, e.g.
> build 4173.

> [!NOTE]
>
> We're in a transition phase to the newer ST4 plugin host.  Unless we have
> more experience for the process, it _may_ be necessary to restart Sublime Text
> after installing or upgrading _helper packages_.  Just check if everything works
> or if the console shows permanent errors.  On my machine, no restarts were
> necessary.


Probably don't get fancy and just install SublimeLinter via [Package Control](https://packagecontrol.io/search/SublimeLinter).
Refer <https://www.sublimelinter.com/en/latest/installation.html> for further information,
but, spoiler!,
usually you install SublimeLinter, the plugin you're currently looking at,
some command line tools, these are the actual linters (e.g. _eslint_ or _flake8_),
and then some plugins/adapters between both.
These are typically named after the linter and should be installed via Package Control
as well, examples would be [SublimeLinter-eslint](https://packagecontrol.io/packages/SublimeLinter-eslint) or [SublimeLinter-flake8](https://packagecontrol.io/packages/SublimeLinter-flake8).

By default, SublimeLinter will run in the background and most linters support this
mode so you should get squiggles immediately.

Note that you find all commands we're installing using the Command Palette (<kbd>ctrl<em>+</em>shift<em>+</em>p</kbd>). Just search for `SublimeLinter`. You may find <https://github.com/kaste/SublimeLinter-addon-toggler>
and/or <https://github.com/kaste/SublimeLinter-addon-goto-flash> useful.


## Settings

Settings are documented in the [default settings](https://github.com/SublimeLinter/SublimeLinter/blob/master/SublimeLinter.sublime-settings). 
Open the settings using the Command Palette (<kbd>ctrl<em>+</em>shift<em>+</em>p</kbd>) searching for `Preferences: SublimeLinter Settings` (mnemonic: `sls`).

When you open the SublimeLinter settings you'll see the defaults on the left
or top. Usually that's all that is needed for end-users but some additional information
is in our docs at [sublimelinter.com](https://www.sublimelinter.com/en/latest/linter_settings.html).


## Key Bindings

SublimeLinter comes with some pre-defined keyboard shortcuts. You can customize these via the Package Settings menu.

| Command | Linux & Windows | MacOS |
|---|---|---|
| Lint this view | <kbd>Ctrl</kbd> + <kbd>k</kbd>, <kbd>l</kbd> | <kbd>Ctrl</kbd> + <kbd>⌘</kbd> + <kbd>l</kbd> |
| Open diagnostics panel | <kbd>Ctrl</kbd> + <kbd>k</kbd>, <kbd>a</kbd> | <kbd>Ctrl</kbd> + <kbd>⌘</kbd> + <kbd>a</kbd> |
| Goto next error | <kbd>Ctrl</kbd> + <kbd>k</kbd>, <kbd>n</kbd> | <kbd>Ctrl</kbd> + <kbd>⌘</kbd> + <kbd>e</kbd> |
| Goto prev error | <kbd>Ctrl</kbd> + <kbd>k</kbd>, <kbd>p</kbd> | <kbd>Ctrl</kbd> + <kbd>⌘</kbd> + <kbd>Shift</kbd> + <kbd>e</kbd> |

Take also a look at the [default bindings](<https://github.com/SublimeLinter/SublimeLinter/blob/master/keymaps/Default (Windows).sublime-keymap>) because
we document other commands and have usually some tricks in there too.

For example, it is very advisable to bind `sublime_linter_quick_actions`, e.g.

```jsonc
    // To trigger a quick action
    // { "keys": ["ctrl+k", "ctrl+f"],
    //   "command": "sublime_linter_quick_actions"
    // },
```


## Quick Actions/Fixers

As we do *just* linting SublimeLinter naturally does not come with fixers 
and/or code formatters. However, we have a fixer API, see the Command Palette: `SublimeLinter: Quick Action`, and ship (mostly) 
"fix by ignoring" actions. These allow you to quickly ignore specific error messages *inline* and ad hoc.[1]

SublimeLinter currently ships actions for
[eslint](https://github.com/SublimeLinter/SublimeLinter-eslint),
[stylelint](https://github.com/SublimeLinter/SublimeLinter-stylelint),
[flake8](https://github.com/SublimeLinter/SublimeLinter-flake8),
[mypy](https://github.com/fredcallaway/SublimeLinter-contrib-mypy),
shellcheck,
[codespell](https://github.com/kaste/SublimeLinter-contrib-codespell)
and
[phpcs](https://github.com/SublimeLinter/SublimeLinter-phpcs).

Want to see actions for your favourite linter? Please open a PR with your addition to
[quick_fix.py](https://github.com/SublimeLinter/SublimeLinter/blob/master/lint/quick_fix.py).
We have [tests](https://github.com/SublimeLinter/SublimeLinter/tree/master/tests/test_ignore_fixers.py) for them!

[1]  Why this limitation though? Well it is usually easy to add a semicolon here and a space there, but the inline ignore rules and syntaxes are very cumbersome to type and to remember. And there is basically no project of any size where you don't have to ignore ad-hoc something somewhere once.


## Support & Bugs

Yeah, totally! Often if it doesn't work, Sublime will have something in the
console (*View -> Show Console*). Warnings will go there by default.

You can enable `debug` mode in the settings to get much more information about what's going on.
Especially seeing the exact command and working dir SublimeLinter will use
should be noted and helpful.

As some code only runs on startup, it is good practice to restart Sublime Text
and to examine the console output for anything odd.

If your issue is specific to a particular linter, please report it on that linter's repository,
otherwise open it right [here](https://github.com/SublimeLinter/SublimeLinter/issues).


## Hack on it

Sure, you're welcome! Just clone the repository into your Packages folder (*Preferences -> Browse Packages*).

```shell
> git clone https://github.com/SublimeLinter/SublimeLinter.git
> subl SublimeLinter
```

This will overrule the installed package straight away.  Just delete the folder
to reverse the process.  The dev requirements can be read in the `pyproject.toml` file.
Just use `rye` and install them:

```shell
> rye sync
```


## Creating a linter plugin

Use the [template](https://github.com/SublimeLinter/SublimeLinter-template) to get started on your plugin.
It contains a how-to with all the information you need. Refer to <https://www.sublimelinter.com/en/master/linter_plugin.html> for more detailed information. Of course, take a look at a similar linter plugin and let it inspire you.


## Also Support ❤️

SublimeLinter is the kind of software that needs active maintenance all the time.
If you find SublimeLinter helpful and would like to show your appreciation, you can support
its development by buying me a coffee! 😄☕️ <https://paypal.me/herrkaste>

😏
