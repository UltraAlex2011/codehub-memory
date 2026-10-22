# The live feed and the live status. Every hook event is one line in
# 03_Logs/<day>.jsonl (short keys: t time, e event, s session, a agent, w tool,
# d target, p project, r path in project, x extra, n count, ok, ms, id). The
# status file in the runtime dir holds, per session, the agent and its last
# action - for small widgets such as the A-Shell's island.
import glob
import json
import os
import time

from . import config, system, vault

STATUS = os.path.join(system.runtime_dir(), 'codehub-status.json')
KEEP_STATUS = 3 * 3600


def event(kind, **fields):
    # a single write() with O_APPEND: parallel hooks never interleave
    line = {'t': round(time.time(), 3), 'e': kind}
    line.update({k: v for k, v in fields.items() if v not in (None, '', [], {})})
    data = json.dumps(line, ensure_ascii=False, separators=(',', ':'))
    try:
        os.makedirs(vault.LOGS, exist_ok=True)
        fd = os.open(os.path.join(vault.LOGS, vault.today() + '.jsonl'),
                     os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(fd, (data + '\n').encode())
        finally:
            os.close(fd)
    except OSError:
        pass
    return line


def set_status(session, **values):
    # state: working | waiting | ended (ended removes the session)
    try:
        with vault.lock('status'):
            try:
                with open(STATUS, encoding='utf-8') as f:
                    everything = json.load(f)
            except (OSError, ValueError):
                everything = {}
            now = time.time()
            if values.get('state') == 'ended':
                everything.pop(session, None)
            else:
                entry = everything.setdefault(session, {})
                entry.update(values)
                entry['t'] = now
            everything = {k: v for k, v in everything.items() if now - v.get('t', 0) < KEEP_STATUS}
            vault.write(STATUS, json.dumps(everything, ensure_ascii=False))
    except OSError:
        pass


def read_status():
    try:
        with open(STATUS, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def clean_logs():
    days = int(config.get('logDays') or 30)
    limit = time.time() - days * 86400
    for path in glob.glob(os.path.join(vault.LOGS, '*.jsonl')):
        try:
            if os.path.getmtime(path) < limit:
                os.remove(path)
        except OSError:
            pass


def recent(n=250):
    # the last n events of yesterday and today
    lines = []
    for day in (vault.now(time.time() - 86400, '%Y-%m-%d'), vault.today()):
        lines += vault.read(os.path.join(vault.LOGS, day + '.jsonl')).splitlines()
    out = []
    for line in lines[-n:]:
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out
