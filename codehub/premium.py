# The premium package: 3D graph, token statistics, benchmark and themes. It
# is not part of the public code; buyers download it with their license key
# ("codehub-premium-<version>.zip"). It is installed only when its manifest
# is signed with the publisher's key and every file matches the manifest,
# and it is loaded only with a valid license (license.py).
#
#   codehub-premium-<version>.zip
#     MANIFEST.json   {"version", "files": {path: sha256}}
#     MANIFEST.sig    Ed25519 signature of MANIFEST.json (hex)
#     codehub_premium/...
import glob
import hashlib
import io
import json
import os
import shutil
import sys
import zipfile

from . import ed25519, i18n, license, system

PUBLISHER = bytes.fromhex('06da5ea722775c2fdb6dda6054a62c4dc04e942205f685a81272d1f6a93dbcf2')
HOME = os.path.join(system.data_dir(), 'premium')
PACKAGE = os.path.join(HOME, 'codehub_premium')
MOST = 20_000_000           # a premium zip is far smaller; anything bigger is not ours

_module = None


class Problem(Exception):
    pass


def installed():
    return os.path.isfile(os.path.join(PACKAGE, '__init__.py'))


def version():
    try:
        with open(os.path.join(HOME, 'MANIFEST.json'), encoding='utf-8') as f:
            return json.load(f).get('version', '')
    except (OSError, ValueError):
        return ''


def intact():
    # the installed files still match the signed manifest - checked before every
    # load, so a patched copy (license check removed) does not run
    try:
        with open(os.path.join(HOME, 'MANIFEST.json'), 'rb') as f:
            raw = f.read()
        with open(os.path.join(HOME, 'MANIFEST.sig'), encoding='ascii') as f:
            signature = bytes.fromhex(f.read().strip())
        if not ed25519.verify(PUBLISHER, raw, signature):
            return False
        files = json.loads(raw)['files']
        found = set()
        for folder, subs, names in os.walk(PACKAGE):
            subs[:] = [x for x in subs if x != '__pycache__']
            for name in names:
                found.add(os.path.relpath(os.path.join(folder, name), HOME).replace(os.sep, '/'))
        if found != set(files):
            return False
        for name, digest in files.items():
            with open(os.path.join(HOME, *name.split('/')), 'rb') as f:
                if hashlib.sha256(f.read()).hexdigest() != digest:
                    return False
        return True
    except (OSError, ValueError, KeyError):
        return False


_intact = None


def active():
    global _intact
    if not installed() or not license.valid():
        return False
    if _intact is None:
        _intact = intact()
    return _intact


def module():
    # the premium package, or None without license or package
    global _module
    if _module is None and active():
        if HOME not in sys.path:
            sys.path.insert(0, HOME)
        try:
            import codehub_premium
            _module = codehub_premium
        except ImportError:
            return None
    return _module


def web_dir():
    return os.path.join(PACKAGE, 'web') if active() else None


def scripts():
    # files the web view loads when premium is active (order matters)
    folder = web_dir()
    if not folder:
        return []
    try:
        with open(os.path.join(folder, 'load.json'), encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def verify(data):
    # -> (manifest, zipfile) of a signed premium zip; raises Problem
    if len(data) > MOST:
        raise Problem(i18n.t('premium.not_ours'))
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        manifest_raw = z.read('MANIFEST.json')
        signature = bytes.fromhex(z.read('MANIFEST.sig').decode().strip())
    except (zipfile.BadZipFile, KeyError, ValueError):
        raise Problem(i18n.t('premium.not_ours')) from None
    if not ed25519.verify(PUBLISHER, manifest_raw, signature):
        raise Problem(i18n.t('premium.bad_signature'))
    manifest = json.loads(manifest_raw)
    names = {n for n in z.namelist() if not n.endswith('/')} - {'MANIFEST.json', 'MANIFEST.sig'}
    if names != set(manifest['files']):
        raise Problem(i18n.t('premium.bad_signature'))
    for name, digest in manifest['files'].items():
        if not name.startswith('codehub_premium/') or '..' in name.split('/'):
            raise Problem(i18n.t('premium.bad_signature'))
        if hashlib.sha256(z.read(name)).hexdigest() != digest:
            raise Problem(i18n.t('premium.bad_signature'))
    return manifest, z


def install(data):
    # verified zip bytes -> installed; the old version stays until the new one is complete
    manifest, z = verify(data)
    staging = HOME + '.new'
    shutil.rmtree(staging, ignore_errors=True)
    os.makedirs(staging)
    for name in manifest['files']:
        target = os.path.join(staging, *name.split('/'))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, 'wb') as f:
            f.write(z.read(name))
    for name in ('MANIFEST.json', 'MANIFEST.sig'):
        with open(os.path.join(staging, name), 'wb') as f:
            f.write(z.read(name))
    old = HOME + '.old'
    shutil.rmtree(old, ignore_errors=True)
    if os.path.exists(HOME):
        os.replace(HOME, old)
    os.replace(staging, HOME)
    shutil.rmtree(old, ignore_errors=True)
    global _intact
    _intact = None
    return manifest['version']


def install_file(path):
    with open(path, 'rb') as f:
        return install(f.read())


def find_download():
    # the newest premium zip in the usual download folders
    found = []
    for folder in (os.path.join(system.HOME, 'Downloads'), os.path.join(system.HOME, 'Download'),
                   os.path.join(system.HOME, 'Desktop'), system.HOME):
        found += glob.glob(os.path.join(folder, 'codehub-premium*.zip'))
    return max(found, key=os.path.getmtime) if found else None


def remove():
    shutil.rmtree(HOME, ignore_errors=True)
    license.deactivate()
