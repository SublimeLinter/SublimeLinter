from pathlib import Path
import zipfile

import sublime

from typing import Set


pp = Path(sublime.packages_path())
ipp = Path(sublime.installed_packages_path())


def ip__has_python_version_file(package: Path) -> bool:
    with zipfile.ZipFile(package) as zfile:
        try:
            zfile.getinfo(".python-version")
        except KeyError:
            return False
        else:
            return True


def p__has_python_version_file(package: str) -> bool:
    fpath = pp / package
    return (fpath / ".python-version").exists()


def p__is_lift(package: str) -> bool:
    fpath = pp / package
    return (
        (fpath / ".python-version").exists()
        and len(list(fpath.glob("*"))) == 1
    )


def create_python_version_file(package: str) -> None:
    fpath = pp / package
    fpath.mkdir(exist_ok=True)
    (fpath / ".python-version").write_text("3.8\n")


def remove_python_version_file(package: str) -> None:
    fpath = pp / package
    (fpath / ".python-version").unlink(missing_ok=True)
    if not list(fpath.glob("*")):
        fpath.rmdir()


def check_all_plugins() -> None:
    removals = [
        (remove_python_version_file, path.stem)
        for path in ipp.glob("SublimeLinter*")
        if (
            ip__has_python_version_file(path)
            and p__is_lift(path.stem)
        )
    ] + [
        (remove_python_version_file, path.name)
        for path in pp.glob("SublimeLinter*")
        if (
            p__is_lift(path.name)
            and not (ipp / f"{path.name}.sublime-package").exists()
        )
    ]
    additions = sorted(
        [
            (create_python_version_file, path.stem)
            for path in ipp.glob("SublimeLinter*")
            if (
                not ip__has_python_version_file(path)
                and not p__has_python_version_file(path.stem)
            )
        ] + [
            (create_python_version_file, path.name)
            for path in pp.glob("SublimeLinter*")
            if not p__has_python_version_file(path.name)
        ],
        key=lambda x: x[1]
    )

    tasks = removals + additions
    for fn, package in tasks:
        print(f'SublimeLinter-lift: {fn.__name__}("{package}"), ', end="")
        try:
            fn(package)
        except Exception as e:
            print(e)
        else:
            print("ok.")

    if additions:
        print("SublimeLinter-lift: If in doubt, reload. 😐")


check_all_plugins()  # <== side-effect on module load!  🕺


PACKAGE_CONTROL_PREFERENCES_FILE = 'Package Control.sublime-settings'
OBSERVER_KEY = '302e8c92-64a9-4483-b7a7-3a04d2ee641d'
INSTALLED_PLUGINS = set()


def package_control_settings() -> sublime.Settings:
    return sublime.load_settings(PACKAGE_CONTROL_PREFERENCES_FILE)


def plugin_loaded() -> None:
    global INSTALLED_PLUGINS
    package_control_settings().add_on_change(OBSERVER_KEY, on_change)
    INSTALLED_PLUGINS = installed_sl_plugins()


def plugin_unloaded() -> None:
    package_control_settings().clear_on_change(OBSERVER_KEY)


def on_change() -> None:
    global INSTALLED_PLUGINS
    previous_state, next_state = INSTALLED_PLUGINS, installed_sl_plugins()
    additions = next_state - previous_state
    deletions = previous_state - next_state

    # We're pessimistic here and assume every plugin needs the lift
    # because we want to be early and before PC has actually installed
    # the package.
    # We call `check_all_plugins` unconditionally which will clean up
    # for us if this step was in fact unnecessary.
    for package in additions:
        create_python_version_file(package)

    if additions or deletions:
        sublime.set_timeout(check_all_plugins, 5000)

    INSTALLED_PLUGINS = next_state


def installed_sl_plugins() -> Set[str]:
    return set(
        p for p in package_control_settings().get('installed_packages', [])  # type: ignore[union-attr]  # stub error
        if p.startswith("SublimeLinter-")
    )
