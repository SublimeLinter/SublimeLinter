Test Package Control updates locally

The main process is also described (here)[https://github.com/SublimeLinter/SublimeLinter/wiki/Test-upgrade-locally].

What you have to do is, edit your PC settings, and add *this* folders `repo.json` as an additional
repo:

```json
{
    "auto_upgrade_frequency": 0,
    "bootstrapped": true,
    "in_process_packages":
    [
    ],
    "installed_packages":
    [
        "Package Control",
        "SublimeLinter",
        "SublimeLinter-eslint",
        "SublimeLinter-flake8"
    ],
    "repositories":
    [
        "<absolute path to this directory>\\repo.json"
    ]
}
```

The script `update_tester.py` assumes that your current working dir is the root of SublimeLinter.
(Its defaults assume that, you could of course pass all the arguments you want.)

On the cli you basically just execute

```
python scripts/update_tester.py
```

This should create the package, bump the version in "repo.json", and start serving it
using a simple local http server.  You can then ask PC to upgrade all packages and it
will see and install the new SL version.
