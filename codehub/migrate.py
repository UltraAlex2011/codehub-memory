# One-time move from the first version (German table, column and event
# names, 2026-10) to the current one. Runs by itself when an old vault is
# opened; nothing in the vault's Markdown changes.
import glob
import json
import os

from . import vault

OLD_TABLES = ('dateien', 'notizen', 'sitzungen', 'spuren', 'auftraege', 'commits', 'subagenten',
              'vorschlaege', 'zaehler')
COUNTERS = {'hubsuche': 'search', 'frei': 'free', 'gelesen': 'read', 'treffer': 'hit', 'tok_ein': 'tok_in',
            'tok_aus': 'tok_out', 'tok_cache': 'tok_cache_read', 'tok_neu': 'tok_cache_write'}
EVENTS = {'fehler': 'error', 'kompakt': 'compact', 'ende': 'end', 'meldung': 'notify', 'notiz': 'note',
          'karte': 'map'}
AGENTS = {'haupt': 'main'}


def set_aside(c):
    # -> names of the renamed old tables (empty for a new database)
    names = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'sitzungen' not in names:
        return []
    old = [t for t in OLD_TABLES if t in names]
    for t in old:
        c.execute(f'ALTER TABLE {t} RENAME TO v1_{t}')
    if 'suche' in names:
        c.execute('DROP TABLE suche')        # search index: rebuilt from the Markdown
    return old


def copy(c, old):
    def has(t):
        return t in old

    if has('dateien'):
        # side topics exist only here (map generation), not in the map files;
        # the search rows are rebuilt from the maps with them
        c.execute('INSERT OR REPLACE INTO files SELECT projekt, pfad, thema, beschreibung, neben FROM v1_dateien')
    if has('sitzungen'):
        c.execute('''INSERT OR REPLACE INTO sessions SELECT id, projekt, titel, start, letzte, ende, cwd,
                     transkript, versatz, letzte_nachricht, t_ein, t_aus, t_cache, t_neu, kompakt, antwort, notiz,
                     CASE zustand WHEN 'aktiv' THEN 'active' WHEN 'ende' THEN 'ended' ELSE zustand END
                     FROM v1_sitzungen''')
    if has('spuren'):
        c.execute('''INSERT OR REPLACE INTO traces SELECT sitzung, projekt, pfad,
                     CASE art WHEN 'bearbeitet' THEN 'edited' WHEN 'gelesen' THEN 'read' ELSE art END, n, zeit
                     FROM v1_spuren''')
    if has('auftraege'):
        c.execute('INSERT INTO prompts SELECT sitzung, zeit, text FROM v1_auftraege')
    if has('commits'):
        c.execute('INSERT OR REPLACE INTO commits SELECT sitzung, zeit, hash, text FROM v1_commits')
    if has('subagenten'):
        c.execute('''INSERT OR REPLACE INTO subagents SELECT sitzung, id, typ, auftrag, ergebnis, start, ende
                     FROM v1_subagenten''')
    if has('vorschlaege'):
        c.execute('INSERT OR REPLACE INTO suggestions SELECT sitzung, pfad, zeit FROM v1_vorschlaege')
    if has('zaehler'):
        for day, kind, n in c.execute('SELECT tag, art, n FROM v1_zaehler').fetchall():
            c.execute('INSERT INTO counters VALUES(?,?,?) ON CONFLICT(day, kind) DO UPDATE SET n=n+excluded.n',
                      (day, COUNTERS.get(kind, kind), n))
    for t in old:
        c.execute(f'DROP TABLE v1_{t}')
    # map stand-ins are rebuilt, subagent tasks are short-lived
    c.execute("DELETE FROM meta WHERE k LIKE 'karte:%' OR k LIKE 'auftrag:%'")
    c.execute("UPDATE meta SET k='cleaned' WHERE k='aufgeraeumt'")
    logs()
    vault_list()
    old_layout = os.path.join(vault.INTERNAL, 'lage.json')
    if os.path.exists(old_layout):
        os.replace(old_layout, os.path.join(vault.INTERNAL, 'layout.json'))


def logs():
    # event names in the raw log, so the live feed reads old days the same way
    for path in glob.glob(os.path.join(vault.LOGS, '*.jsonl')):
        lines, changed = [], False
        for line in vault.read(path).splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            for key, names in (('e', EVENTS), ('a', AGENTS)):
                if e.get(key) in names:
                    e[key] = names[e[key]]
                    changed = True
            lines.append(json.dumps(e, ensure_ascii=False, separators=(',', ':')))
        if changed:
            vault.write(path, '\n'.join(lines) + '\n')


def vault_list():
    # the vault list lived in the A-Shell's state folder
    from . import system, vaults
    old = os.path.join(system.HOME, '.local', 'state', 'quickshell', 'codehub-vaults.json')
    if os.path.exists(vaults.LIST) or not os.path.exists(old):
        return
    try:
        with open(old, encoding='utf-8') as f:
            d = json.load(f)
    except (OSError, ValueError):
        return
    vault.write(vaults.LIST, json.dumps({'vaults': [{'path': v.get('pfad')} for v in d.get('vaults', [])
                                                    if v.get('pfad')],
                                         'hidden': d.get('versteckt', []), 'last': d.get('zuletzt')},
                                        ensure_ascii=False, indent=1))


def tokens(c):
    # tokens.db of the first version -> current table names
    names = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'tage' not in names:
        return
    c.execute('INSERT OR REPLACE INTO files SELECT pfad, versatz FROM dateien')
    c.execute('INSERT OR IGNORE INTO messages SELECT id FROM nachrichten')
    c.execute('INSERT OR REPLACE INTO days SELECT tag, projekt, ein, aus, cache, neu, n FROM tage')
    for t in ('dateien', 'nachrichten', 'tage'):
        c.execute(f'DROP TABLE {t}')
