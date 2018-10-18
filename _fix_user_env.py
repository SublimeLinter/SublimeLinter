from contextlib import contextmanager
from functools import partial, wraps
import os
import re
import subprocess
import time
import threading
import traceback

import sublime


DEFAULT_SHELL = '/bin/bash'
DELIMITER = '_SHELL_ENV_DELIMITER_'
ANSI_COLOR_RE = re.compile(r'\033\[[0-9;]*m')

State = {
    'ready': False,
    'callbacks': []
}


def synchronized(lock):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            with lock:
                return fn(*a, **kw)

        return wrapper
    return decorator


atomic = synchronized(threading.RLock())


def eat_errors_and_resolve(fn):
    @wraps(fn)
    def wrapper(sink):
        try:
            return fn(sink)
        except Exception:
            traceback.print_exc()
            sink({})
            return

    return wrapper


def strip_ansi(str):
    return ANSI_COLOR_RE.sub('', str)


def plugin_loaded():
    read_and_update_env_async()


def read_and_update_env_async():
    threading.Thread(target=partial(read_env, update_env)).start()


@eat_errors_and_resolve
def read_env(sink):
    if sublime.platform() == 'windows':
        sink({})
        return

    executable = os.environ.get('SHELL') or DEFAULT_SHELL
    cmd = [
        executable,
        '-ilc',
        'echo -n "{0}"; env; echo -n "{0}"; exit'.format(DELIMITER)
    ]

    print("<> Running: '{} -ilc env'".format(executable))
    with print_runtime('<> Finished in {:.2f}s'):
        stdout = subprocess.check_output(cmd)

    output = stdout.decode('utf8').replace('\r\n', '\n').replace('\r', '\n')
    output = strip_ansi(output)

    user_env = {}
    for line in output.split(DELIMITER)[1].split('\n'):
        try:
            key, value = line.split('=', maxsplit=1)
        except ValueError:
            continue

        user_env[key] = value

    sink(user_env)


@atomic
def update_env(user_env):
    print_dict_changes(user_env, os.environ)
    os.environ.update(user_env)

    for callback in State['callbacks']:
        safe_call(callback)

    State.update({'ready': True, 'callbacks': []})


@atomic
def on_ready(fn):
    if State['ready']:
        safe_call(fn)
    else:
        State['callbacks'].append(fn)


def safe_call(fn):
    sublime.set_timeout_async(fn)


def print_dict_changes(current, previous):
    common_keys = current.keys() & previous.keys()

    added = current.keys() - common_keys
    changed = [k for k in common_keys if current[k] != previous[k]]

    if added or changed:
        print('<> Environment will change!')
    else:
        print('<> Environment already ok!')

    if added:
        print('-> Added:')
        for k in added:
            print('{}={}'.format(k, current[k]))

    if changed:
        print('-> Changed:')
        for k in changed:
            print('{}={}'.format(k, current[k]))
            print('{}|{} (previous value)'.format(' ' * len(k), previous[k]))


@contextmanager
def print_runtime(msg):
    start_time = time.time()

    yield

    end_time = time.time()
    runtime = end_time - start_time
    print(msg.format(runtime))
