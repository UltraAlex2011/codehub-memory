# What the views show, independent of how they are drawn: the graph,
# live feed, numbers, details, token use, vaults and documents. Both views
# use this - the Quickshell view through bridge.py (JSON lines on stdio), the
# web view through server.py (HTTP + server-sent events).
#
# Messages out (dicts with "type"): graph, stats, history, event, detail,
# saved, created, tokens, vaults, tree, document, doc_saved, doc_new,
# doc_error, settings. Commands in (dicts with "cmd"): graph, detail, open,
# layout, save, new, settings, settings_set, vaults, vault_select, vault_new,
# vault_add, vault_remove, doc_read, doc_save, doc_new, doc_rename,
# doc_delete, doc_open.
import json
import os
import re
import sys
import threading
import time
from urllib.parse import quote

from . import config, events, i18n, install, notes, projects, search, store, system, tail, tokens, vault, vaults

SESSION_FILES = 8       # edges session -> most edited files
HISTORY = 250


def layout_file():
    return os.path.join(vault.INTERNAL, 'layout.json')


# ---- Graph ---------------------------------------------------------------------------

def graph():
    search.update()
    c = store.db()
    try:
        with open(layout_file(), encoding='utf-8') as f:
            saved = json.load(f)
    except (OSError, ValueError):
        saved = {}
    nodes, edges, ids = [], [], set()
    general = vault.general()

    def node(nid, kind, name, group, **more):
        if nid in ids:
            return
        ids.add(nid)
        n = {'id': nid, 'kind': kind, 'name': name, 'group': group}
        n.update(more)
        if nid in saved:
            n['xyz'] = saved[nid]
        nodes.append(n)

    def edge(a, b, s=1.0):
        if a in ids and b in ids and a != b:
            edges.append([a, b, s])

    for name, _ in projects.all_projects():
        node('p:' + name, 'p', name, name)
    side = []
    for project, path, topic, _, also in c.execute(
            'SELECT project, path, topic, description, also FROM files ORDER BY project, topic, path'):
        tid = f't:{project}:{topic}'
        if tid not in ids:
            node(tid, 't', topic, project)
            edge('p:' + project, tid, 1.0)
        fid = f'd:{project}:{path}'
        node(fid, 'd', os.path.basename(path), project, path=path, md=path.endswith('.md'))
        edge(tid, fid, 1.0)
        side += [(fid, f't:{project}:{t}') for t in (also or '').split('|') if t]
    for fid, tid in side:
        edge(fid, tid, 0.25)
    # notes (without sessions and project notes)
    by_title = {}
    found = c.execute("SELECT path, project, kind, title, links, files FROM notes "
                      "WHERE kind NOT IN ('session', 'project')").fetchall()
    for path, project, kind, title, _, _ in found:
        if '/' not in path:
            continue        # README, Start
        nid = 'n:' + path
        node(nid, 'n', title, project or general, note=kind)
        by_title[os.path.splitext(os.path.basename(path))[0]] = nid
    if any(n['group'] == general for n in nodes) or c.execute(
            'SELECT 1 FROM sessions WHERE project=? LIMIT 1', (general,)).fetchone():
        node('p:' + general, 'p', general, general)
    names = {n['name'] for n in nodes if n['kind'] == 'p'}
    for path, project, kind, title, links, files in found:
        nid = 'n:' + path
        if nid not in ids:
            continue
        edge(nid, 'p:' + (project if project in names else general), 0.6)
        for link in (links or '').split('|'):
            if link in by_title:
                edge(nid, by_title[link], 0.5)
            elif link in names:
                edge(nid, 'p:' + link, 0.6)
        for f in (files or '').split('|'):
            for p in names:
                edge(nid, f'd:{p}:{f}', 0.5)
    # sessions: on the project, as a chain, and on their most edited files
    previous = {}
    for sid, project, title, start, last, state in c.execute(
            'SELECT id, project, title, start, last, state FROM sessions WHERE note IS NOT NULL ORDER BY start'):
        nid = 's:' + sid
        node(nid, 's', title or sid[:8], project or general, time=last or start, active=state == 'active')
        edge(nid, 'p:' + (project or general), 0.4)
        if project in previous:
            edge(previous[project], nid, 0.6)
        previous[project] = nid
        for p, rel in c.execute("SELECT project, path FROM traces WHERE session=? AND kind='edited' "
                                "AND project IS NOT NULL ORDER BY n DESC LIMIT ?", (sid, SESSION_FILES)):
            edge(nid, f'd:{p}:{rel}', 0.3)
    return {'type': 'graph', 'nodes': nodes, 'edges': edges}


def signature():
    # changes as soon as maps, notes or sessions are added
    search.update()
    c = store.db()
    return (c.execute("SELECT count(*), group_concat(v) FROM meta WHERE k LIKE 'map:%'").fetchone(),
            c.execute('SELECT count(*), max(mtime) FROM notes').fetchone(),
            c.execute("SELECT count(*), sum(state='active') FROM sessions WHERE note IS NOT NULL").fetchone())


# ---- Numbers ----------------------------------------------------------------------------

def stats(follower=None):
    c = store.db()
    days = [vault.now(time.time() - i * 86400, '%Y-%m-%d') for i in range(6, -1, -1)]
    z = {d: {} for d in days}
    for day, kind, n in c.execute('SELECT day, kind, n FROM counters WHERE day>=?', (days[0],)):
        z[day][kind] = n
    active = [{'id': sid, 'title': title or sid[:8], 'project': project or '', 'last': last,
               'tokens': (t_in or 0) + (t_out or 0) + (t_write or 0)}
              for sid, title, project, last, t_in, t_out, t_write in c.execute(
                  "SELECT id, title, project, last, t_in, t_out, t_cache_write FROM sessions "
                  "WHERE state='active' AND last>? ORDER BY last DESC", (time.time() - 3 * 3600,))]
    status = events.read_status()
    for a in active:
        s = status.get(a['id'], {})
        a.update(state=s.get('state', ''), agent=s.get('agent', ''), action=s.get('last', ''))
    if follower:
        active = follower.active()
    push = (store.meta('push') or '').split(' ', 1)
    return {
        'type': 'stats',
        'today': z[days[-1]],
        'days': [{'day': d[5:], 'hub': z[d].get('lookup', 0) + z[d].get('auto', 0) + z[d].get('search', 0),
                  'free': z[d].get('free', 0),
                  'tokens': sum(z[d].get(k, 0) for k in ('tok_in', 'tok_out', 'tok_cache_write')),
                  'cache': z[d].get('tok_cache_read', 0)} for d in days],
        'active': active,
        'hooks': not follower,
        'counts': {'files': c.execute('SELECT count(*) FROM files').fetchone()[0],
                   'notes': c.execute("SELECT count(*) FROM notes WHERE kind NOT IN ('session','project')").fetchone()[0],
                   'sessions': c.execute('SELECT count(*) FROM sessions WHERE note IS NOT NULL').fetchone()[0],
                   'projects': len(projects.all_projects())},
        'push': {'time': float(push[0]) if push[0] else 0, 'text': push[1] if len(push) > 1 else ''},
    }


# ---- Detail and opening -------------------------------------------------------------------

def link_targets(c):
    # [[target]] -> node id, by the same rules as the edges in graph()
    found = {}
    for name, _ in projects.all_projects():
        found[name] = found[name + ' MAP'] = 'p:' + name
    found[vault.general()] = 'p:' + vault.general()
    for sid, note in c.execute('SELECT id, note FROM sessions WHERE note IS NOT NULL'):
        found[os.path.splitext(os.path.basename(note))[0]] = 's:' + sid
    for path, in c.execute("SELECT path FROM notes WHERE kind NOT IN ('session', 'project')"):
        if '/' in path:
            found[os.path.splitext(os.path.basename(path))[0]] = 'n:' + path
    return found


def linked(content, found):
    # Obsidian links as Markdown links hub:<id>; links into nothing stay text
    def replace(m):
        goal, shown = m.group(1).split('#')[0].strip(), (m.group(2) or m.group(1)).strip()
        nid = found.get(goal)
        return f'[{shown}](hub:{quote(nid)})' if nid else f'*{shown}*'
    return re.sub(r'\[\[([^\]|]+)(?:\|([^\]]+))?\]\]', replace, content)


def backlinks(c, nid, found):
    # notes pointing here with [[..]] (or `path` for files)
    names = {z for z, k in found.items() if k == nid}
    if nid.startswith('d:'):
        f = nid.split(':', 2)[2]
        rows = c.execute("SELECT path, title, kind FROM notes WHERE '|' || files || '|' LIKE ?",
                         (f'%|{f}|%',)).fetchall()
    else:
        rows = [r for name in names for r in c.execute(
            "SELECT path, title, kind FROM notes WHERE '|' || links || '|' LIKE ?", (f'%|{name}|%',))]
    # own notes first, then sessions, newest on top
    rows.sort(key=lambda r: (r[2] == 'session', [-ord(ch) for ch in r[0]]))
    out, seen = [], set()
    for path, title, kind in rows:
        goal = found.get(os.path.splitext(os.path.basename(path))[0])
        if goal and goal != nid and goal not in seen:
            seen.add(goal)
            out.append({'id': goal, 'title': title, 'kind': kind})
    return out[:30]


def editable(nid, path):
    # own notes and project notes; session notes are rewritten by sessions.py
    return nid[:2] in ('n:', 'p:') and bool(path) and system.inside(path, vault.ROOT) and os.path.isfile(path)


def detail(nid):
    c = store.db()
    kind, _, rest = nid.partition(':')
    out = {'type': 'detail', 'id': nid}
    found = link_targets(c)
    if kind == 'd':
        project, _, path = rest.partition(':')
        r = c.execute('SELECT topic, description, also FROM files WHERE project=? AND path=?',
                      (project, path)).fetchone()
        full = os.path.join(projects.root_of(project) or '', *path.split('/'))
        out.update(title=os.path.basename(path), sub=f'{project} · {path}', path=full,
                   topic=r[0] if r else '', text=r[1] if r else '', also=(r[2] or '').replace('|', ' · ') if r else '')
        try:
            st = os.stat(full)
            out['info'] = i18n.t('detail.file_info', size=f'{st.st_size / 1024:.1f}',
                                 when=vault.now(st.st_mtime, i18n.t('format.datetime')))
            out['preview'] = vault.read(full, 2400)
        except OSError:
            out['info'] = i18n.t('detail.file_missing')
        out['sessions'] = [{'title': t or s[:8], 'time': vault.now(z, i18n.t('format.short')), 'n': n, 'id': 's:' + s}
                           for s, t, z, n in c.execute(
                               "SELECT s.id, s.title, tr.time, tr.n FROM traces tr JOIN sessions s ON s.id=tr.session "
                               "WHERE tr.project=? AND tr.path=? AND tr.kind='edited' ORDER BY tr.time DESC LIMIT 6",
                               (project, path))]
    elif kind == 't':
        project, _, topic = rest.partition(':')
        files = c.execute('SELECT path, description FROM files WHERE project=? AND topic=? ORDER BY path',
                          (project, topic)).fetchall()
        out.update(title=topic, sub=i18n.t('detail.topic', project=project, n=len(files)),
                   text='\n'.join(f'- `{p}` — {d}' if d else f'- `{p}`' for p, d in files[:60]),
                   path=projects.map_file(project), markdown=True)
    elif kind == 'p':
        root = projects.root_of(rest)
        n = c.execute('SELECT count(*), count(DISTINCT topic) FROM files WHERE project=?', (rest,)).fetchone()
        recent = c.execute('SELECT title, last FROM sessions WHERE project=? ORDER BY last DESC LIMIT 5',
                           (rest,)).fetchall()
        path = notes.project_note(rest)
        body = vault.front(vault.read(path))[1]
        body = '\n'.join(z for z in body.splitlines() if not z.startswith('# ')).strip()
        out.update(title=rest, markdown=True, path=path,
                   sub=(system.tilde(root) if root else i18n.t('detail.no_folder')) + ' · '
                   + i18n.t('detail.project', files=n[0], topics=n[1]),
                   text=body + f'\n\n**{i18n.t("detail.recent")}**\n\n'
                   + '\n'.join(f'- {vault.now(z, i18n.t("format.short"))} {t}' for t, z in recent))
    elif kind in ('n', 's'):
        if kind == 's':
            r = c.execute('SELECT note FROM sessions WHERE id=?', (rest,)).fetchone()
            rest = r[0] if r and r[0] else ''
        head, body = vault.front(vault.read(os.path.join(vault.ROOT, rest)))
        title = next((z[2:] for z in body.splitlines() if z.startswith('# ')), os.path.basename(rest)[:-3])
        body = '\n'.join(z for z in body.splitlines() if not z.startswith('# '))
        sub = ' · '.join(str(head[k]) for k in ('kind', 'project', 'start', 'tokens', 'modified') if head.get(k))
        out.update(title=title, sub=sub, text=body.strip()[:12000], markdown=True,
                   path=os.path.join(vault.ROOT, rest))
    if out.get('markdown'):
        out['text'] = linked(out.get('text', ''), found)
    out['backlinks'] = backlinks(c, nid, found)
    if editable(nid, out.get('path')):
        out['raw'] = vault.read(out['path'])
        out['stamp'] = str(os.stat(out['path']).st_mtime_ns)
    return out


# ---- Premium ---------------------------------------------------------------------------------

def license_message():
    from . import license, premium
    s = license.status()
    conf = license.shop()
    return {'type': 'license', 'active': s['active'], 'installed': premium.installed(), 'email': s['email'],
            'key': s['key'], 'version': premium.version(), 'price': conf['price'], 'devices': conf['devices'],
            'buy': {'lemonsqueezy': conf['lemonsqueezy'].get('checkout', ''), 'gumroad': conf['gumroad'].get('url', '')},
            'site': conf['site'], 'scripts': premium.scripts()}


def premium_command(cmd, b):
    # -> answer messages; a notice tells people what happened
    import base64
    from . import license, premium
    notice = ''
    try:
        if cmd == 'activate':
            state = license.activate(b.get('key', ''))
            notice = i18n.t('premium.activated', email=state.get('email') or '–')
            found = None if premium.installed() else premium.find_download()
            if found:
                notice = i18n.t('premium.installed', version=premium.install_file(found))
        elif cmd == 'deactivate':
            premium.remove()
            notice = i18n.t('premium.removed')
        elif cmd == 'premium_install':
            notice = i18n.t('premium.installed', version=premium.install(base64.b64decode(b.get('data', ''))))
    except (license.Problem, premium.Problem) as e:
        notice = str(e)
    except ConnectionError:
        notice = i18n.t('premium.offline', error='')
    except (ValueError, OSError) as e:
        notice = i18n.t('premium.failed', error=e)
    out = [license_message()]
    if notice:
        out.append({'type': 'notice', 'text': notice})
    return out


# ---- The session of one view ------------------------------------------------------------------

class TokenCounter(threading.Thread):
    # own thread: the first run reads every transcript
    def __init__(self):
        super().__init__(daemon=True)
        self.result = None              # newest overview, picked up by the main loop
        self.wake = threading.Event()

    def run(self):
        c = tokens.connect()
        first = True
        while True:
            try:
                if tokens.scan(c) or first:
                    self.result = tokens.overview(c)
            except Exception as e:      # a broken file or the like: next round
                sys.stderr.write(f'tokens: {e}\n')
            first = False
            self.wake.wait(10)
            self.wake.clear()


class LogFollower:
    # new lines of today's raw log
    def __init__(self):
        self.path = self._today()
        try:
            self.pos = os.path.getsize(self.path)
        except OSError:
            self.pos = 0
        self.rest = b''

    def _today(self):
        return os.path.join(vault.LOGS, vault.today() + '.jsonl')

    def read(self):
        today = self._today()
        if today != self.path:
            self.path, self.pos, self.rest = today, 0, b''
        try:
            size = os.path.getsize(self.path)
        except OSError:
            size = 0
        if size < self.pos:
            self.pos, self.rest = 0, b''
        if size <= self.pos:
            return []
        with open(self.path, 'rb') as f:
            f.seek(self.pos)
            data = self.rest + f.read(size - self.pos)
        self.pos = size
        *whole, self.rest = data.split(b'\n')
        out = []
        for raw in whole:
            try:
                out.append(json.loads(raw))
            except ValueError:
                pass
        return out


class View:
    def __init__(self):
        # without hooks the view follows the transcripts itself
        self.follower = None if install.installed() else tail.Follower()
        self.counter = TokenCounter()
        self.log = LogFollower()
        self.open = {'vault': vault.ROOT, 'sig': None, 'rel': '', 'stamp': ''}
        self.sig = None
        self.check_graph = False
        self.times = {'graph': 0, 'stats': 0, 'vault': 0, 'scan': 0}

    def start(self):
        # -> the first messages
        self.counter.start()
        self.sig = signature()
        history = events.recent(HISTORY)
        if self.follower:
            history = (history + self.follower.scan())[-HISTORY:]
        self.times = dict.fromkeys(self.times, time.time())
        return [graph(), stats(self.follower), {'type': 'history', 'list': history}, vaults.listing(),
                self.settings(), license_message()]

    def settings(self):
        return {'type': 'settings', 'values': config.all_settings(), 'language': i18n.language(),
                'hooks': install.installed()}

    def poll(self):
        # -> messages since the last call; call a few times per second
        out = []
        now = time.time()
        for e in self.log.read():
            e['type'] = 'event'
            out.append(e)
            if e.get('e') in ('map', 'note', 'end', 'start', 'stop', 'compact'):
                self.check_graph = True
        if self.follower and now - self.times['scan'] >= 1:
            self.times['scan'] = now
            for e in self.follower.scan():
                e['type'] = 'event'
                out.append(e)
                if e['e'] in ('stop', 'prompt'):
                    self.times['stats'] = 0     # session list right away
        if self.check_graph or now - self.times['graph'] > 5:
            self.times['graph'], self.check_graph = now, False
            new = signature()
            if new != self.sig:
                self.sig = new
                out.append(graph())
                self.times['stats'] = 0
        if self.counter.result:
            out.append(self.counter.result)
            self.counter.result = None
        if now - self.times['vault'] > 2:
            self.times['vault'] = now
            out += self.vault_check()
        if now - self.times['stats'] > 4:
            self.times['stats'] = now
            if self.follower and install.installed():
                self.follower = None            # hooks just installed: they write the log from now on
            out.append(stats(self.follower))
        return out

    # ---- commands ----

    def handle(self, b):
        # -> answer messages
        cmd = str(b.get('cmd') or '')
        try:
            if cmd == 'vaults' or cmd.startswith(('vault_', 'doc_')):
                out = self.vault_command(cmd, b)
                if cmd != 'doc_read' and vaults.is_hub(self.open['vault']):
                    self.check_graph = True
                return out
            if cmd == 'graph':
                return [graph()]
            if cmd == 'detail':
                return [detail(b.get('id', ''))]
            if cmd == 'open':
                self.open_node(b.get('id', ''), b.get('how', ''))
            elif cmd == 'layout':
                self.save_layout(b.get('data'))
            elif cmd == 'new':
                return self.new_note()
            elif cmd == 'save':
                return self.save_note(b.get('id', ''), b.get('text'), b.get('stamp', ''))
            elif cmd == 'settings':
                return [self.settings()]
            elif cmd in ('license', 'activate', 'deactivate', 'premium_install'):
                return premium_command(cmd, b)
            elif cmd == 'settings_set':
                config.put(str(b.get('name')), b.get('value'))
                if b.get('name') == 'language':
                    i18n.use(i18n.detect())
                return [self.settings()]
        except (vaults.Error, OSError, KeyError, ValueError) as e:
            return [{'type': 'doc_error', 'text': str(e)}]
        return []

    def new_note(self):
        # an empty note in the user's own folder; the view selects it and opens the editor
        name = f'{i18n.t("view.note")} {vault.now(None, "%Y-%m-%d %H-%M-%S")}.md'
        path = os.path.join(vault.OWN, name)
        vault.write(path, vault.front_text({'kind': 'note', 'created': vault.now()})
                    + f'\n# {i18n.t("view.new_note")}\n\n')
        search.update()
        return [graph(), {'type': 'created', 'id': 'n:' + vault.rel(path)}]

    def save_note(self, nid, content, stamp):
        path = detail(nid).get('path')
        answer = {'type': 'saved', 'id': nid, 'ok': False}
        if not editable(nid, path) or not isinstance(content, str):
            answer['reason'] = i18n.t('view.not_editable')
        elif str(os.stat(path).st_mtime_ns) != str(stamp):
            answer['reason'] = i18n.t('view.changed')
        else:
            vault.write(path, content if content.endswith('\n') else content + '\n')
            search.update()
            answer['ok'] = True
            self.check_graph = True
        return [answer, detail(nid)]

    def open_node(self, nid, how):
        path = detail(nid).get('path')
        if not path:
            return
        if how == 'obsidian' or (system.inside(path, vault.ROOT) and how != 'file'):
            system.open_external('obsidian://open?path=' + quote(path))
        else:
            system.open_external(path)

    def save_layout(self, data):
        if isinstance(data, dict) and data:
            vault.write(layout_file(), json.dumps({k: [round(v, 1) for v in xyz] for k, xyz in data.items()},
                                                  separators=(',', ':')))

    def vault_command(self, cmd, b):
        v = b.get('vault') or self.open['vault']
        out = []
        if cmd == 'vaults':
            return [vaults.listing()]
        if cmd in ('vault_new', 'vault_add', 'vault_remove'):
            if cmd == 'vault_new':
                v = vaults.create(b.get('name', ''))
            elif cmd == 'vault_add':
                v = vaults.add(b.get('path', ''))
            else:
                vaults.remove(b.get('path', ''))
                v = vault.ROOT
            cmd = 'vault_select'
            out.append(vaults.listing())
        if cmd == 'vault_select':
            self.open.update(vault=system.resolve(v), sig=vaults.signature(v), rel='', stamp='')
            vaults.remember(self.open['vault'])
            out.append(vaults.tree(v))
        elif cmd == 'doc_read':
            d = vaults.read(v, b.get('rel', ''))
            self.open.update(rel=d['rel'], stamp=d['stamp'])
            out.append(d)
        elif cmd == 'doc_save':
            d = vaults.save(v, b.get('rel', ''), b.get('text'), b.get('stamp', ''))
            if d['ok'] and d['rel'] == self.open['rel']:
                self.open['stamp'] = d['stamp']
            out.append(d)
        elif cmd in ('doc_new', 'doc_rename'):
            d = (vaults.new(v, b.get('folder', ''), b.get('kind', 'note'), b.get('name', '')) if cmd == 'doc_new'
                 else vaults.rename(v, b.get('rel', ''), b.get('name', '')))
            self.open['sig'] = vaults.signature(v)
            out += [vaults.tree(v), d]
        elif cmd == 'doc_delete':
            vaults.delete(v, b.get('rel', ''))
            self.open['sig'] = vaults.signature(v)
            out.append(vaults.tree(v))
        elif cmd == 'doc_open':
            _, p = vaults.resolve(v, b.get('rel', ''))
            system.open_external('obsidian://open?path=' + quote(p) if b.get('how') == 'obsidian' else p)
        return out

    def vault_check(self):
        # Obsidian or Claude changed something in the open vault: tree and open
        # document follow (the view takes it over only without own changes)
        sig = vaults.signature(self.open['vault'])
        if sig == self.open['sig']:
            return []
        self.open['sig'] = sig
        out = [vaults.tree(self.open['vault'])]
        if self.open['rel']:
            try:
                d = vaults.read(self.open['vault'], self.open['rel'])
            except vaults.Error:
                return out
            if d['stamp'] != self.open['stamp']:
                self.open['stamp'] = d['stamp']
                d['external'] = True
                out.append(d)
        return out
