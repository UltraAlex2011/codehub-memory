# "codehub update": the newest published version replaces the installed
# copy (the installer puts it in <data dir>/app). A git checkout updates with
# git, a pipx install with pipx - both are only named, never run here.
import io
import os
import re
import shutil
import tarfile
import urllib.request

from . import VERSION, i18n, system

REPO = 'UltraAlex2011/codehub-memory'
APP = os.path.join(system.data_dir(), 'app')


def _get(url, accept='application/vnd.github+json'):
    req = urllib.request.Request(url, headers={'Accept': accept, 'User-Agent': f'CodeHub/{VERSION}'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def latest():
    # -> (version, tarball url) of what is published on main - every publish
    # is a release, so there are no tags to keep in step
    init = _get(f'https://raw.githubusercontent.com/{REPO}/main/codehub/__init__.py', 'text/plain').decode()
    version = re.search(r"VERSION = '([^']+)'", init).group(1)
    return version, f'https://codeload.github.com/{REPO}/tar.gz/refs/heads/main'


def newer(a, b):
    def parts(v):
        return [int(x) if x.isdigit() else 0 for x in v.split('.')]
    return parts(a) > parts(b)


def run(say=print):
    if not system.inside(system.ROOT, system.resolve(APP)):
        if os.path.isdir(os.path.join(system.ROOT, '.git')):
            say(i18n.t('update.git', path=system.tilde(system.ROOT)))
        else:
            say(i18n.t('update.pip'))
        return 1
    try:
        version, url = latest()
    except (OSError, ValueError, AttributeError) as e:
        say(i18n.t('update.offline', error=e))
        return 1
    if not newer(version, VERSION):
        say(i18n.t('update.current', version=VERSION))
        return 0
    say(i18n.t('update.loading', version=version))
    data = _get(url, 'application/octet-stream')
    staging = APP + '.new'
    shutil.rmtree(staging, ignore_errors=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as tar:
        top = tar.getmembers()[0].name.split('/')[0]
        for m in tar.getmembers():
            # only plain files and folders inside the release, nothing outside
            parts = m.name.split('/')[1:]
            if not parts or '..' in parts or not (m.isfile() or m.isdir()) or m.name.split('/')[0] != top:
                continue
            target = os.path.join(staging, *parts)
            if m.isdir():
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with tar.extractfile(m) as src, open(target, 'wb') as dst:
                shutil.copyfileobj(src, dst)
            if m.mode & 0o111:
                os.chmod(target, 0o755)
    if not os.path.isfile(os.path.join(staging, 'codehub', '__init__.py')):
        shutil.rmtree(staging, ignore_errors=True)
        say(i18n.t('update.broken'))
        return 1
    old = APP + '.old'
    shutil.rmtree(old, ignore_errors=True)
    os.replace(APP, old)
    os.replace(staging, APP)
    shutil.rmtree(old, ignore_errors=True)
    say(i18n.t('update.done', version=version))
    return 0
