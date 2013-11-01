SublimeLinter3
=========

A framework for code linting in the [Sublime Text](http://sublimetext.com "Sublime Text") editor.

## We need your help

This is a work in progress! We want to finish this project quickly so you can get all of the benefits of Sublime Text 3. But to make that happen, we need your help. If SublimeLinter is critical to your workflow, then consider making a donation to accelerate its development.

[![Donate](http://www.aparajitaworld.com/cappuccino/Donate-button.png?v=1)](https://www.paypal.com/cgi-bin/webscr?cmd=_s-xclick&hosted_button_id=55KC77W2MU9VW)

<a class="coinbase-button" data-code="3265d1a223f01885e92514751e45cc55" data-button-style="custom_large" href="https://coinbase.com/checkouts/3265d1a223f01885e92514751e45cc55">Donate Bitcoins</a><script src="https://coinbase.com/assets/button.js" type="text/javascript"></script>

**UPDATE**: Through October 31, we have raised $3143 (after fees) from 253 donations. Thank you for your support! Development has started, and I’m very excited about this new version! But there is still a [lot of work to do](https://github.com/SublimeLinter/SublimeLinter3/issues/4), and I’m getting new ideas every day.

So if you are one of the thousands of happy SublimeLinter users who has not donated yet, it isn’t too late to contribute. Please consider making a small donation. Open source software is not free! It is we the developers who usually end up paying for it.

## What’s new

SublimeLinter3 is a complete rewrite with the following goals:

### Flexibility

[SublimeLinter2][sl2] is a monolothic plugin. All of the linters are part of SublimeLinter2, which means you have to wait for us to release a new version to get updates for a single linter. That’s a real bummer when you want to take advantage of a new feature or bug fix in an underlying linter like [jshint](http://jshint.org/about).

We want to break that dependency, and to do that we changed the architecture of SublimeLinter3 so that every linter is a **separate** Sublime Text 3 plugin. By doing that, we get some real wins:

- They can be hosted in completely separate repos.

- They can be located, installed, updated and removed via [Package Control](https://sublime.wbond.net), independently of SublimeLinter3 itself.

- They can be maintained entirely by those who have an active interest in them — which usually isn’t us — which lets us focus on maintaining and extending the core functionality of SublimeLinter3 instead of a whole universe of linters.

- They can have their own settings.

- They can and should be based on binaries/libraries installed separately by the user, which allows them to update to the latest version independently of the SublimeLinter3.

### Performance

SublimeLinter3 takes advantage of the new asynchronous plugin API in Sublime Text 3. This means that linting your 100K-line documents won’t affect your ability to edit a document smoothly.

### Features

SublimeLinter3 will have a number of new features to make it easier to use, including:

- Mark style chooser
- Gutter mark theme chooser
- Updater to insert SublimeLinter styles into the current color scheme

### Better support

SublimeLinter3 is based on pioneering work done by Ryan Hileman, the author of [sublimelint](https://github.com/lunixbochs/sublimelint), on which SublimeLinter was originally based. We want to join forces with Ryan and merge sublimelint and SublimeLinter3, so we can have more resources available to support the community.

SublimeLinter3 will have *much* better online documentation.

### Help make it happen

Did we mention that we need [your help](#we-need-your-help) to get SublimeLinter3 done? :-)

[sl2]: https://github.com/SublimeLinter/SublimeLinter
