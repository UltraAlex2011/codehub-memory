# Token use of all Claude Code sessions, per day and project. Reads every
# transcript under ~/.claude/projects (subagents too) from where it stopped
# last time. The daily sums stay in .hub/tokens.db even after Claude Code
# deletes old transcripts, so "total" keeps growing.
# Used = input + output + cache written; cache reads (the history, read again
# with every request) are counted separately.
import json
import os
import sqlite3
import time
from datetime import datetime

from . import projects, sessions, vault

SCHEMA = '''
CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY, offset INTEGER);
CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS days(day TEXT, project TEXT, input INTEGER, output INTEGER, cache_read INTEGER,
    cache_write INTEGER, n INTEGER, PRIMARY KEY(day, project));
'''


def connect():
    # own file and connection: the views run this in a thread
    os.makedirs(vault.INTERNAL, exist_ok=True)
    c = sqlite3.connect(os.path.join(vault.INTERNAL, 'tokens.db'), timeout=10, isolation_level=None,
                        check_same_thread=False)
    c.execute('PRAGMA journal_mode=WAL')
    c.executescript(SCHEMA)
    from . import migrate
    c.execute('BEGIN IMMEDIATE')
    migrate.tokens(c)
    c.execute('COMMIT')
    return c


def _transcripts():
    for root, _, names in os.walk(sessions.TRANSCRIPTS):
        for n in names:
            if n.endswith('.jsonl'):
                yield os.path.join(root, n)


def _read_file(c, path, offset, project_cache):
    # -> new offset. Every answer (message.id) counts once, across files too
    # (resumed sessions carry the old history into a new file)
    sums = {}
    with open(path, 'rb') as f:
        f.seek(offset)
        for raw in f:
            if not raw.endswith(b'\n'):
                break                       # line still being written
            offset += len(raw)
            if b'"usage"' not in raw:
                continue
            try:
                d = json.loads(raw)
                m = d['message']
                usage = m['usage']
                mid = m['id']
                day = datetime.fromisoformat(d['timestamp'].replace('Z', '+00:00')).astimezone().strftime('%Y-%m-%d')
            except (ValueError, KeyError, TypeError, AttributeError):
                continue
            if c.execute('INSERT OR IGNORE INTO messages VALUES(?)', (mid,)).rowcount != 1:
                continue
            cwd = d.get('cwd') or ''
            if cwd not in project_cache:
                project_cache[cwd] = projects.of(cwd)[0]
            s = sums.setdefault((day, project_cache[cwd] or vault.general()), [0, 0, 0, 0, 0])
            for i, k in enumerate(sessions.USAGE):
                s[i] += int(usage.get(k) or 0)
            s[4] += 1
    for (day, project), (t_in, t_out, read, write, n) in sums.items():
        c.execute('INSERT INTO days VALUES(?,?,?,?,?,?,?) ON CONFLICT(day, project) DO UPDATE SET '
                  'input=input+excluded.input, output=output+excluded.output, '
                  'cache_read=cache_read+excluded.cache_read, cache_write=cache_write+excluded.cache_write, '
                  'n=n+excluded.n', (day, project, t_in, t_out, read, write, n))
    return offset


def scan(c):
    # -> True when new answers were counted
    known = dict(c.execute('SELECT path, offset FROM files'))
    project_cache, new = {}, False
    for path in _transcripts():
        try:
            size = os.path.getsize(path)
        except OSError:
            continue
        old = known.get(path, 0)
        if size == old:
            continue
        if size < old:
            old = 0                         # rewritten: from the start, duplicate ids drop out
        c.execute('BEGIN IMMEDIATE')
        try:
            offset = _read_file(c, path, old, project_cache)
            c.execute('INSERT OR REPLACE INTO files VALUES(?,?)', (path, offset))
            c.execute('COMMIT')
        except (OSError, sqlite3.Error):
            c.execute('ROLLBACK')
            continue
        new = new or offset != old
    return new


def _sum(rows):
    s = {'tokens': 0, 'cache': 0, 'answers': 0}
    for t_in, t_out, read, write, n in rows:
        s['tokens'] += (t_in or 0) + (t_out or 0) + (write or 0)
        s['cache'] += read or 0
        s['answers'] += n or 0
    return s


def overview(c):
    # today, 7 days, 30 days, total; and the 30 days one by one, months, projects
    now = time.time()
    day = lambda ago: vault.now(now - ago * 86400, '%Y-%m-%d')
    rows = c.execute('SELECT day, project, input, output, cache_read, cache_write, n FROM days').fetchall()

    def since(limit):
        return _sum(r[2:] for r in rows if r[0] >= limit)

    days = []
    for ago in range(29, -1, -1):
        d = day(ago)
        s = _sum(r[2:] for r in rows if r[0] == d)
        days.append({'day': d, 'tokens': s['tokens'], 'cache': s['cache']})
    months, by_project = {}, {}
    for r in rows:
        months.setdefault(r[0][:7], []).append(r[2:])
        if r[0] >= day(29):
            by_project.setdefault(r[1], []).append(r[2:])
    return {
        'type': 'tokens',
        'today': since(day(0)), 'week': since(day(6)), 'month': since(day(29)), 'total': since(''),
        'since': min((r[0] for r in rows), default=''),
        'days': days,
        'months': [dict(_sum(v), month=m) for m, v in sorted(months.items(), reverse=True)][:12],
        'projects': sorted(({'project': p, **_sum(v)} for p, v in by_project.items()),
                           key=lambda p: -p['tokens'])[:8],
    }


def number(n):
    return f'{n / 1e6:.1f} M' if n >= 1e6 else f'{n / 1e3:.0f} k' if n >= 1e3 else str(n)
