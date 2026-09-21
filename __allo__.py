from pathlib import Path
import zipfile

import sublime

from typing import Callable, Iterable, List, Sequence, Set, Tuple


pp = Path(sublime.packages_path())
ipp = Path(sublime.installed_packages_path())
Task = Tuple[Callable[[str], None], str]


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
    host_33_disabled = plugin_host_33_disabled()
    removals = [
        path.stem
        for path in ipp.glob("SublimeLinter*")
        if (
            p__is_lift(path.stem)
            and (
                host_33_disabled
                or ip__has_python_version_file(path)
            )
        )
    ] + [
        path.name
        for path in pp.glob("SublimeLinter*")
        if (
            p__is_lift(path.name)
            and not (ipp / f"{path.name}.sublime-package").exists()
        )
    ]
    additions = [] if host_33_disabled else sorted(
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

    run_tasks(additions)
    safely_remove_lifts(removals)

    if additions:
        print("SublimeLinter-lift: If in doubt, reload. 😐")


def plugin_host_33_disabled() -> bool:
    setting = sublime.load_settings(
        "Preferences.sublime-settings"
    ).get("disable_plugin_host_3.3")
    if setting is None:
        return int(sublime.version()) >= 4205
    return bool(setting)


def safely_remove_lifts(packages: Sequence[str]) -> None:
    if not packages:
        return

    # Removing the marker from a loaded package can make Sublime reload it in
    # the 3.3 host even if the installed archive has its own 3.8 marker.
    # Ignoring it first unloads it and detaches the package file watcher.
    settings = sublime.load_settings("Preferences.sublime-settings")
    ignored_packages: List[str] = list(
        settings.get("ignored_packages", [])
    )
    already_ignored = sorted(set(packages) & set(ignored_packages))
    run_tasks(
        (remove_python_version_file, package)
        for package in already_ignored
    )

    newly_ignored = sorted(set(packages) - set(ignored_packages))
    if newly_ignored:
        settings.set("ignored_packages", ignored_packages + newly_ignored)
        sublime.save_settings("Preferences.sublime-settings")
        sublime.set_timeout(
            lambda: remove_lifts_and_reenable(newly_ignored),
            1000
        )


def remove_lifts_and_reenable(packages: Sequence[str]) -> None:
    run_tasks(
        (remove_python_version_file, package)
        for package in packages
    )
    sublime.set_timeout(lambda: reenable_packages(packages), 1000)


def reenable_packages(packages: Sequence[str]) -> None:
    settings = sublime.load_settings("Preferences.sublime-settings")
    ignored_packages: List[str] = settings.get("ignored_packages", [])
    to_enable = set(packages)
    settings.set(
        "ignored_packages",
        [package for package in ignored_packages if package not in to_enable]
    )
    sublime.save_settings("Preferences.sublime-settings")


def run_tasks(tasks: Iterable[Task]) -> None:
    for fn, package in tasks:
        print(f'SublimeLinter-lift: {fn.__name__}("{package}"), ', end="")
        try:
            fn(package)
        except Exception as e:
            print(e)
        else:
            print("ok.")


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

    try:
        import package_control
        if package_control.events.remove('SublimeLinter'):
            check_all_plugins()
    except ImportError:
        pass


def on_change() -> None:
    global INSTALLED_PLUGINS
    previous_state, next_state = INSTALLED_PLUGINS, installed_sl_plugins()
    additions = next_state - previous_state
    deletions = previous_state - next_state

    # We're pessimistic here and assume every plugin needs the lift
    # because we want to be early and before PC has actually installed
    # the package.
    # A later `check_all_plugins` call cleans up for us if this step was in
    # fact unnecessary.
    if plugin_host_33_disabled():
        additions = set()
    else:
        run_tasks(
            (create_python_version_file, package)
            for package in additions
        )

    if additions or deletions:
        sublime.set_timeout(check_all_plugins, 5000)

    INSTALLED_PLUGINS = next_state


def installed_sl_plugins() -> Set[str]:
    return {  # type: ignore[var-annotated]
        p for p in package_control_settings().get('installed_packages', [])
        if p.startswith("SublimeLinter-")
    }
