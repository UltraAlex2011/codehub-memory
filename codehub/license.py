# Premium license: a key bought at Lemon Squeezy or Gumroad, activated once
# per computer through the shop's own license API - no server of ours.
# A key works on at most `devices` computers (shop.json); the activation is
# bound to this machine, checked online every 14 days and keeps working 30
# days without a connection. Refunded or disabled purchases stop working.
#
# Honest limit: code that runs on the buyer's computer can be changed by a
# determined person. This makes sharing keys and copying folders useless and
# keeps the premium code itself out of public reach (premium.py).
import json
import os
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

from . import VERSION, i18n, system

STATE = os.path.join(system.data_dir(), 'license.json')
RECHECK = 14 * 86400
GRACE = 30 * 86400
LEMON = 'https://api.lemonsqueezy.com/v1/licenses/'
GUMROAD = 'https://api.gumroad.com/v2/licenses/verify'
GUMROAD_KEY = re.compile(r'^[0-9A-F]{8}(-[0-9A-F]{8}){3}$')

_shop = None
_valid = None


class Problem(Exception):
    pass


def shop():
    global _shop
    if _shop is None:
        with open(os.path.join(system.PACKAGE, 'shop.json'), encoding='utf-8') as f:
            _shop = json.load(f)
    return _shop


def ready():
    # is there anywhere to buy yet?
    s = shop()
    return bool(s['lemonsqueezy'].get('checkout') or s['gumroad'].get('url'))


def _post(url, fields):
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(url, data=data, method='POST', headers={
        'Accept': 'application/json', 'Content-Type': 'application/x-www-form-urlencoded',
        'User-Agent': f'CodeHub/{VERSION}'})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read() or b'{}')
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read() or b'{}')
        except ValueError:
            return {'error': f'HTTP {e.code}'}
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise ConnectionError(str(e)) from e


def _read():
    try:
        with open(STATE, encoding='utf-8') as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(d):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    tmp = f'{STATE}.{os.getpid()}.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(d, f, indent=1)
    os.replace(tmp, STATE)
    if not system.WINDOWS:
        os.chmod(STATE, 0o600)


def _forget():
    global _valid
    _valid = None
    try:
        os.remove(STATE)
    except OSError:
        pass


# ---- the two shops --------------------------------------------------------------

def _lemon_activate(key):
    conf = shop()['lemonsqueezy']
    d = _post(LEMON + 'activate', {'license_key': key, 'instance_name': f'{socket.gethostname()} (Code Hub)'})
    if not d.get('activated'):
        raise Problem(d.get('error') or i18n.t('license.rejected'))
    meta = d.get('meta') or {}
    if meta.get('store_id') != conf['store_id'] or meta.get('product_id') != conf['product_id']:
        # a key of another product: give the activation back at once
        _post(LEMON + 'deactivate', {'license_key': key, 'instance_id': d['instance']['id']})
        raise Problem(i18n.t('license.other_product'))
    return {'shop': 'lemonsqueezy', 'instance': d['instance']['id'], 'email': meta.get('customer_email', ''),
            'name': meta.get('customer_name', '')}


def _lemon_check(state):
    d = _post(LEMON + 'validate', {'license_key': state['key'], 'instance_id': state['instance']})
    status = (d.get('license_key') or {}).get('status')
    return bool(d.get('valid')) and status not in ('disabled', 'expired')


def _gumroad_verify(key, count):
    conf = shop()['gumroad']
    d = _post(GUMROAD, {'product_id': conf.get('product_id', ''), 'license_key': key,
                        'increment_uses_count': 'true' if count else 'false'})
    if not d.get('success'):
        raise Problem(d.get('message') or i18n.t('license.rejected'))
    purchase = d.get('purchase') or {}
    if purchase.get('refunded') or purchase.get('chargebacked') or purchase.get('disputed'):
        raise Problem(i18n.t('license.refunded'))
    return d.get('uses', 0), purchase


def _gumroad_activate(key):
    uses, purchase = _gumroad_verify(key, True)
    if uses > shop()['devices']:
        raise Problem(i18n.t('license.too_many', n=shop()['devices']))
    return {'shop': 'gumroad', 'instance': str(uses), 'email': purchase.get('email', ''), 'name': ''}


def _gumroad_check(state):
    try:
        _gumroad_verify(state['key'], False)
        return True
    except Problem:
        return False


# ---- public ---------------------------------------------------------------------

def activate(key):
    # -> state; raises Problem with a message for people, ConnectionError offline
    global _valid
    key = ' '.join(str(key).split()).strip()
    if len(key) < 16:
        raise Problem(i18n.t('license.format'))
    # a shop counts only with its ids: without them any key of any store would pass
    conf = shop()
    order = []
    if conf['lemonsqueezy'].get('store_id') and conf['lemonsqueezy'].get('product_id'):
        order.append(_lemon_activate)
    if conf['gumroad'].get('product_id'):
        order.append(_gumroad_activate)
    if GUMROAD_KEY.match(key.upper()):
        order.sort(key=lambda f: f is not _gumroad_activate)     # its key format: ask Gumroad first
    if not order:
        raise Problem(i18n.t('license.no_shop'))
    errors = []
    for attempt in order:
        try:
            state = attempt(key)
            break
        except Problem as e:
            errors.append(str(e))
    else:
        raise Problem(errors[0])
    now = time.time()
    state.update(key=key, machine=system.machine_id(), activated=now, checked=now, ok=True)
    _write(state)
    _valid = True
    return state


def deactivate():
    state = _read()
    if state.get('shop') == 'lemonsqueezy' and state.get('instance'):
        try:
            _post(LEMON + 'deactivate', {'license_key': state['key'], 'instance_id': state['instance']})
        except ConnectionError:
            pass        # the slot frees itself only online; the local activation goes anyway
    _forget()


def status():
    state = _read()
    return {'active': valid(), 'email': state.get('email', ''), 'shop': state.get('shop', ''),
            'key': (state.get('key', '')[:4] + '…' + state.get('key', '')[-4:]) if state.get('key') else '',
            'checked': state.get('checked', 0)}


def valid():
    # cached for the process; checks online when due
    global _valid
    if _valid is not None:
        return _valid
    state = _read()
    if not state.get('ok') or state.get('machine') != system.machine_id():
        _valid = False
        return False
    now = time.time()
    if now - state.get('checked', 0) < RECHECK:
        _valid = True
        return True
    try:
        good = _lemon_check(state) if state.get('shop') == 'lemonsqueezy' else _gumroad_check(state)
    except ConnectionError:
        _valid = now - state.get('checked', 0) < GRACE        # offline: keep working for a while
        return _valid
    state.update(checked=now, ok=good)
    _write(state)
    _valid = good
    return good
