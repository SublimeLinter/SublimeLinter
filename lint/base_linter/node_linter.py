"""This module exports the NodeLinter subclass of Linter."""

from functools import lru_cache
from itertools import chain
import json
import os
import shutil

from .. import linter, util


MYPY = False
if MYPY:
    from typing import Any, Dict, Iterator, List, Optional, Tuple, Union


def smart_paths_upwards(start_dir):
    # type: (str) -> Iterator[str]
    # This is special as we also may yield HOME.  This is so because
    # we might have "global" installations there; we don't expect to
    # find a marker file (e.g. "package.json") at HOME.
    return (
        chain(util.paths_upwards_until_home(start_dir), [util.HOME])
        if os.path.commonprefix([start_dir, util.HOME]) == util.HOME
        else util.paths_upwards(start_dir)
    )


def is_yarn_project(path, manifest):
    # type: (str, Dict[str, Any]) -> bool
    package_manager = manifest.get('packageManager')
    if isinstance(package_manager, str):
        # When this field was being adopted and hadn't been standardised yet
        # package managers could have scoped names, i.e. `@<scope>/<package>`
        name = package_manager.rsplit('@', 1)[0]
        return name == 'yarn' or name == '@yarnpkg/berry'

    yarn_files = ['yarn.lock', '.yarnrc.yml', '.yarnrc']
    if any(os.path.exists(os.path.join(path, file)) for file in yarn_files):
        return True

    return os.path.exists(os.path.join(path, 'node_modules', '.yarn-integrity'))


# `read_json_file` is maybe used by plugins. Check `eslint` and
# `xo` for example.
def read_json_file(path):
    # type: (str) -> Dict[str, Any]
    return _read_json_file(path, os.path.getmtime(path))


@lru_cache(maxsize=4)
def _read_json_file(path, _mtime):
    # type: (str, float) -> Dict[str, Any]
    with open(path, 'r', encoding='utf8') as f:
        return json.load(f)


class NodeLinter(linter.Linter):
    """
    This Linter subclass provides NodeJS-specific functionality.

    Linters installed with npm should inherit from this class.
    By doing so, they automatically get the following features:

    """
    __abstract__ = True

    def context_sensitive_executable_path(self, cmd):
        # type: (List[str]) -> Tuple[bool, Union[None, str, List[str]]]
        """
        Attempt to locate the npm module specified in cmd.

        Searches the local node_modules/.bin folder first before
        looking in the global system node_modules folder. return
        a tuple of (have_path, path).
        """
        # The default implementation will look for a user defined `executable`
        # setting.
        success, executable = super().context_sensitive_executable_path(cmd)
        if success:
            self.logger.info(
                "Note: manually setting 'executable' disables looking for a "
                "\"project_root\" or reading any 'package.json' file.\n"
                "This for example changes how SublimeLinter computes the "
                "working dir."
            )
            return True, executable

        npm_name = cmd[0]
        start_dir = self.get_start_dir()
        if start_dir:
            self.logger.info(
                "Searching executable for '{}' starting at '{}'."
                .format(npm_name, start_dir)
            )
            local_cmd = self.find_local_executable(start_dir, npm_name)
            if local_cmd:
                return True, local_cmd

        if self.settings.get('disable_if_not_dependency', False):
            self.logger.info(
                "Skipping '{}' since it is not installed locally.\n"
                "You can change this behavior by setting 'disable_if_not_dependency' to 'false'."
                .format(self.name)
            )
            self.notify_unassign()
            raise linter.PermanentError('disable_if_not_dependency')

        return False, None

    def get_start_dir(self):
        # type: () -> Optional[str]
        return (
            self.context.get('file_path') or
            self.get_working_dir()
        )

    def find_local_executable(self, start_dir, npm_name):
        # type: (str, str) -> Union[None, str, List[str]]
        paths = smart_paths_upwards(start_dir)
        for path in paths:
            executable = shutil.which(npm_name, path=os.path.join(path, 'node_modules', '.bin'))
            if executable:
                self.context['project_root'] = path
                return executable

            manifest_file = os.path.join(path, 'package.json')
            if os.path.exists(manifest_file):
                try:
                    manifest = read_json_file(manifest_file)
                except Exception as err:
                    self.logger.warning(
                        "We found a 'package.json' at {}; however, reading it raised\n  {}"
                        .format(path, str(err))
                    )
                    self.notify_failure()
                    raise linter.PermanentError()

                # Edge case: when hacking on the linter itself it is not installed
                # but must run as a normal script. E.g. `/usr/bin/env node eslint.js`
                try:
                    script = os.path.normpath(os.path.join(path, manifest['bin'][npm_name]))
                except (KeyError, TypeError):
                    pass
                else:
                    if not os.path.exists(os.path.join(path, 'node_modules', '.bin')):
                        self.logger.warning(
                            "We want to execute 'node {}'; but you should first "
                            "'npm install' this project.".format(script)
                        )
                        self.notify_failure()
                        raise linter.PermanentError()

                    node_binary = self.which('node')
                    if node_binary:
                        self.context['project_root'] = path
                        return [node_binary, script]

                    self.logger.warning(
                        "We want to execute 'node {}'; however, finding a node executable "
                        "failed.".format(script)
                    )
                    self.notify_failure()
                    raise linter.PermanentError()

                is_dep = bool(manifest.get('dependencies', {}).get(npm_name))
                is_dev_dep = bool(manifest.get('devDependencies', {}).get(npm_name))
                if is_dep or is_dev_dep:
                    self.context['project_root'] = path

                    # Perhaps this is a Yarn project?
                    if is_yarn_project(path, manifest):
                        # https://yarnpkg.com/advanced/rulebook#user-scripts-shouldnt-hardcode-the-node_modulesbin-folder
                        yarn_binary = shutil.which('yarn')
                        if yarn_binary:
                            return [yarn_binary, 'run', '--silent', npm_name]

                        self.logger.warning(
                            "This seems like a Yarn project. However, finding "
                            "a Yarn executable failed. Make sure to install Yarn first."
                        )
                        self.notify_failure()
                        raise linter.PermanentError()

                    # Since we've found a valid 'package.json' as our 'project_root'
                    # exhaust outer loop looking just for installations.
                    for path_ in paths:
                        executable = shutil.which(
                            npm_name, path=os.path.join(path_, 'node_modules', '.bin')
                        )
                        if executable:
                            return executable

                    self.logger.warning(
                        "Skipping '{}' for now which is listed as a {} "
                        "in {} but not installed.  Forgot to 'npm install'?"
                        .format(
                            npm_name,
                            'dependency' if is_dep else 'devDependency',
                            manifest_file
                        )
                    )
                    self.notify_failure()
                    raise linter.PermanentError()

        return None

    def run(self, cmd, code):
        # type: (Optional[List[str]], str) -> Union[util.popen_output, str]
        result = super().run(cmd, code)

        if cmd and cmd[1:3] == ['run', '--silent'] and len(cmd) >= 4:
            npm_name = cmd[3]
            if 'error Command "{}" not found'.format(npm_name) in (
                result.stderr or ''
                if isinstance(result, util.popen_output)
                else result
            ):
                self.logger.warning(
                    "We did execute 'yarn run --silent {0}' but "
                    "'{0}' cannot be found.  Forgot to 'yarn install'?"
                    .format(npm_name)
                )
                self.notify_failure()
                raise linter.PermanentError()

        return result
