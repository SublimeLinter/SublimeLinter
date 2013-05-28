from urllib.request import urlopen
import json
import os
from io import BytesIO
import time
from zipfile import ZipFile

from . import persist
from .modules import Modules

API_ENDPOINT = 'https://api.github.com/repos/{}/commits'
UPDATE_ZIP = 'https://github.com/{}/archive/master.zip'
REPO = 'lunixbochs/linters'

def fetch_url(url):
    return urlopen(url).read()

def get_head_sha(repo):
    data = fetch_url(API_ENDPOINT.format(repo)).decode('utf8')
    update = json.loads(data)
    return update[0]['sha']

def read_safe(name):
    try:
        with open(name) as f:
            return f.read().strip()
    except Exception:
        return None

def extract_update(zip_text, base, revision=None):
    version_file = os.path.join(base, '.version')
    z = ZipFile(BytesIO(zip_text))
    version = z.comment or revision
    if version:
        with open(version_file, 'w') as f:
            f.write(version.decode('utf8'))

    for path in z.namelist():
        if path.endswith('.py'):
            data = z.read(path)
            name = os.path.split(path)[1]
            target = os.path.join(base, name)
            with open(target, 'wb') as f:
                f.write(data)

def install_update(base, head=None):
    zip_text = fetch_url(UPDATE_ZIP.format(REPO))
    extract_update(zip_text, base, head)
    persist.modules = Modules(base).load_all()

def touch(path):
    with open(path, 'a') as f:
        os.utime(path, None)

def update(base):
    if not os.path.exists(base):
        os.makedirs(base)

    version_file = os.path.join(base, '.version')
    # don't check more often than every 15 minutes
    elapsed = 0
    if os.path.exists(version_file):
        elapsed = time.time() - os.path.getmtime(version_file)
        if elapsed < 15 * 60:
            return

    if os.path.exists(version_file):
        touch(version_file)

        persist.debug('Checking for linter updates (last: {}s).'.format(elapsed))
        if os.path.exists(base):
            version = read_safe(version_file)
            head = get_head_sha(REPO)
            if head != version:
                persist.debug('Newer version found. Updating to {}.'.format(head))
                install_update(base, head)
    else:
        persist.debug('First run: downloading linters.')
        touch(version_file)
        install_update(base)
