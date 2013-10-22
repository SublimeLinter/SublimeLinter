SublimeLinter3
=========

A framework for code linting in the [Sublime Text](http://sublimetext.com "Sublime Text") editor.

## We need your help

This is a work in progress! We want to finish this project quickly so you can get all of the benefits of Sublime Text 3. But to make that happen, we need your help. If SublimeLinter is critical to your workflow, then consider making a donation to accelerate its development.

[![Donate](http://www.aparajitaworld.com/cappuccino/Donate-button.png)](https://www.paypal.com/cgi-bin/webscr?cmd=_s-xclick&hosted_button_id=55KC77W2MU9VW)

Thank you for your support!

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

### Better support

SublimeLinter3 is based on pioneering work done by Ryan Hileman, the author of [sublimelint](https://github.com/lunixbochs/sublimelint), on which SublimeLinter was originally based. We want to join forces with Ryan and merge sublimelint and SublimeLinter3, so we can have more resources available to support the community.

### Help make it happen

Did we mention that we need [your help](#we-need-your-help) to get SublimeLinter3 done? :-)

[sl2]: https://github.com/SublimeLinter/SublimeLinter
