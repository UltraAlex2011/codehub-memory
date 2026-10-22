# Settings: <config dir>/config.json, written by "codehub config" and the web
# view. A host shell may keep its own copy - the A-Shell stores "codehub.*"
# in its settings.json and edits them in its settings window; those win.
import json
import os

from . import system

FILE = os.path.join(system.config_dir(), 'config.json')
HOST_FILES = (os.path.join(system.HOME, '.local', 'state', 'quickshell', 'settings.json'),)
DEFAULTS = {
    'language': '',          # '' = vault language, then system language
    'vault': '',             # '' = ~/CodeHub
    'autoLookup': True,      # matching files with every prompt
    'startContext': True,    # short overview when a session starts
    'push': True,            # push the vault after every session
    'logDays': 30,           # keep raw events this long
    'port': 7341,            # web view
}
# Older names the host shell still uses
HOST_NAMES = {'startContext': ('startKontext',), 'logDays': ('logTage',)}

_own = None
_host = None


def _load(path):
    try:
        with open(path, encoding='utf-8') as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def reload():
    global _own, _host
    _own, _host = None, None


def get(name):
    # both caches are built aside and assigned complete (threads read them too)
    global _own, _host
    own, host = _own, _host
    if own is None:
        host = {}
        for path in HOST_FILES:
            for k, v in _load(path).items():
                if k.startswith('codehub.'):
                    host[k[8:]] = v
        own = _load(FILE)
        _own, _host = own, host
    for key in (name, *HOST_NAMES.get(name, ())):
        if host.get(key) is not None:
            return host[key]
    value = own.get(name)
    return DEFAULTS.get(name) if value is None else value


def all_settings():
    return {k: get(k) for k in DEFAULTS}


def put(name, value):
    # Written where it is read from: a value the host shell holds goes back to
    # the host, so both settings windows always show the same thing
    if name not in DEFAULTS:
        raise KeyError(name)
    path, key = FILE, name
    for host in HOST_FILES:
        d = _load(host)
        for k in (name, *HOST_NAMES.get(name, ())):
            if 'codehub.' + k in d:
                path, key = host, 'codehub.' + k
                break
        if path != FILE:
            break
    d = _load(path)
    d[key] = value
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f'{path}.{os.getpid()}.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(d, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)
    reload()
