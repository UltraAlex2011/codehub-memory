# Search index over maps and notes, and the two questions Claude asks:
# lookup (which files are responsible for a topic) and fulltext (decisions,
# bugs, notes, sessions, docs). The index follows the Markdown files - it is
# brought up to date before every answer and only touched when they changed.
import os
import re
import time

from . import i18n, projects, store, system, text, vault

NOTE_SKIP = ('03_Logs', '00_Index')


# ---- Index ---------------------------------------------------------------------------

def index_file(c, project, path, topic, description, also=''):
    c.execute('INSERT OR REPLACE INTO files VALUES(?,?,?,?,?)', (project, path, topic, description, also))
    c.execute('DELETE FROM search WHERE kind=? AND project=? AND ref=?', ('file', project, path))
    words = text.fold(text.split(path + ' ' + topic + ' ' + (also or '').replace('|', ' ')))
    body = description
    if path.endswith('.md'):
        # the project's own docs are searchable with their content
        root = projects.root_of(project)
        if root:
            body += ' ' + vault.read(os.path.join(root, path), 12000)
    c.execute('INSERT INTO search VALUES(?,?,?,?,?,?)',
              ('file', project, path, text.fold(text.split(os.path.basename(path))), words, text.fold(body)))


def index_map(c, project, path, also=None):
    # also = {path: "topic|topic"} from map generation; otherwise keep the old ones
    _, topics = projects.read_map(path)
    if also is None:
        also = dict(c.execute('SELECT path, also FROM files WHERE project=?', (project,)).fetchall())
    c.execute('DELETE FROM files WHERE project=?', (project,))
    c.execute('DELETE FROM search WHERE kind=? AND project=?', ('file', project))
    for topic, entries in topics.items():
        for p, description in entries:
            index_file(c, project, p, topic, description, also.get(p) or '')


def note_data(rel):
    head, body = vault.front(vault.read(os.path.join(vault.ROOT, rel)))
    m = re.search(r'^# (.+)$', body, re.M)
    title = m.group(1).strip() if m else os.path.splitext(os.path.basename(rel))[0]
    parts = rel.split('/')
    project = head.get('project') or (parts[1] if parts[0] == '01_Projects' and len(parts) > 2 else '')
    kind = head.get('kind') or ('snippet' if parts[0] == '02_Code_Library' else 'note')
    tags = head.get('tags') or []
    if isinstance(tags, str):
        tags = [x for x in re.split(r'[,\s]+', tags) if x]
    links = sorted(set(x.split('|')[0].split('#')[0].strip() for x in re.findall(r'\[\[([^\]]+)\]\]', body)))
    files = sorted(set(re.findall(r'`([\w.~/-]+/[\w.-]+\.\w{1,8})`', body)))
    return {'project': project, 'kind': kind, 'title': title, 'tags': tags, 'links': links, 'files': files,
            'body': body}


def index_note(c, rel, mtime=None):
    n = note_data(rel)
    c.execute('INSERT OR REPLACE INTO notes VALUES(?,?,?,?,?,?,?,?)',
              (rel, n['project'], n['kind'], n['title'], ' '.join(n['tags']), '|'.join(n['links']),
               '|'.join(n['files']), mtime or os.path.getmtime(os.path.join(vault.ROOT, rel))))
    c.execute('DELETE FROM search WHERE ref=? AND kind<>?', (rel, 'file'))
    c.execute('INSERT INTO search VALUES(?,?,?,?,?,?)',
              (n['kind'], n['project'], rel, text.fold(n['title']), text.fold(' '.join(n['tags'])),
               text.fold(n['body'][:40000])))


def drop_note(c, rel):
    c.execute('DELETE FROM notes WHERE path=?', (rel,))
    c.execute('DELETE FROM search WHERE ref=? AND kind<>?', (rel, 'file'))


def notes_in_vault():
    # files at the top (README, Start) explain the vault and are no notes
    for root, folders, names in os.walk(vault.ROOT):
        folders[:] = [f for f in folders if not f.startswith('.') and f not in NOTE_SKIP]
        if root == vault.ROOT:
            continue
        for n in names:
            if n.endswith('.md'):
                yield vault.rel(os.path.join(root, n))


def update(rebuild=False):
    # Maps and notes changed since the last run. Reads first - writes (and
    # locks) only when something changed.
    c = store.db()
    if rebuild:
        # files stays: its side topics come from map generation and are not
        # in the map files; index_map() rebuilds the rows with them
        with store.transaction():
            for table in ('notes', 'search'):
                c.execute(f'DELETE FROM {table}')
            c.execute("DELETE FROM meta WHERE k LIKE 'map:%'")
    maps = {}
    for name, _ in projects.all_projects():
        try:
            maps[name] = os.path.getmtime(projects.map_file(name))
        except OSError:
            pass
    changed = [n for n, m in maps.items() if store.meta('map:' + n) != str(m)]
    gone = [p for (p,) in c.execute('SELECT DISTINCT project FROM files').fetchall() if p not in maps]
    known = dict(c.execute('SELECT path, mtime FROM notes').fetchall())
    notes = {}
    for rel in notes_in_vault():
        try:
            notes[rel] = os.path.getmtime(os.path.join(vault.ROOT, rel))
        except OSError:
            pass            # deleted while walking
    new = [rel for rel, m in notes.items() if known.get(rel) != m]
    removed = set(known) - set(notes)
    if not (changed or gone or new or removed):
        return
    with store.transaction():
        for name in changed:
            index_map(c, name, projects.map_file(name))
            store.meta('map:' + name, maps[name])
        for old in gone:
            c.execute('DELETE FROM files WHERE project=?', (old,))
            c.execute('DELETE FROM search WHERE kind=? AND project=?', ('file', old))
            c.execute('DELETE FROM meta WHERE k=?', ('map:' + old,))    # comes back = indexed anew
        for rel in new:
            index_note(c, rel, notes[rel])
        for rel in removed:
            drop_note(c, rel)


# ---- Search ----------------------------------------------------------------------------

def _fts_query(terms):
    return ' OR '.join(f'"{b}"*' for b in terms if re.fullmatch(r'[0-9a-z]+', b))


def find(terms, kinds=None, project=None, n=10):
    # -> [{kind, project, ref, coverage, rank, title_hits}] best first.
    # coverage = share of the terms found in the hit
    c = store.db()
    rows = []
    if store.FTS:
        query = _fts_query(terms)
        if not query:
            return []
        sql = ('SELECT kind, project, ref, ft, fw, fx, bm25(search, 0, 0, 0, 8.0, 4.0, 1.0) FROM search '
               'WHERE search MATCH ?')
        values = [query]
        if kinds:
            sql += f' AND kind IN ({",".join("?" * len(kinds))})'
            values += list(kinds)
        if project:
            sql += ' AND project=?'
            values.append(project)
        sql += ' ORDER BY 7 LIMIT ?'
        values.append(max(n * 4, 30))
        rows = c.execute(sql, values).fetchall()
    else:
        for r in c.execute('SELECT kind, project, ref, ft, fw, fx FROM search').fetchall():
            if (kinds and r[0] not in kinds) or (project and r[1] != project):
                continue
            rank = -sum(8 * (b in r[3]) + 4 * (b in r[4]) + (b in r[5]) for b in terms)
            if rank < 0:
                rows.append((*r, rank))
        rows.sort(key=lambda r: r[6])
        rows = rows[:max(n * 4, 30)]
    out = []
    for kind, proj, ref, ft, fw, fx, rank in rows:
        # for files only name, topic and description count (the description
        # leads fx) - otherwise every long doc that mentions all words wins
        everything = f'{ft} {fw} {fx[:240] if kind == "file" else fx}'
        found = sum(1 for b in terms if b in everything)
        out.append({'kind': kind, 'project': proj, 'ref': ref, 'rank': rank, 'coverage': found / len(terms),
                    'title_hits': sum(1 for b in terms if b in ft or b in fw)})
    # more terms first, then title hits, then bm25
    out.sort(key=lambda h: (-round(h['coverage'], 2), -h['title_hits'], h['rank']))
    return out[:n]


def _from_maps(terms, project, n):
    # without an index (no sqlite3): read the maps directly
    hits = []
    for name, _ in projects.all_projects():
        if project and name != project:
            continue
        _, topics = projects.read_map(projects.map_file(name))
        for topic, entries in topics.items():
            for path, description in entries:
                f = text.fold(text.split(path + ' ' + topic) + ' ' + description)
                found = sum(1 for b in terms if b in f)
                if found:
                    hits.append((found, name, path, description, topic))
    hits.sort(key=lambda h: -h[0])
    return hits[:n]


def lookup(query, project=None, n=8, session=None):
    # -> (text for hub_lookup, absolute paths named)
    terms = text.terms(query)
    if not terms:
        return i18n.t('search.no_terms'), []
    project = projects.name(project) if project else None
    try:
        update()
        hits = [h for h in find(terms, ('file',), project, n) if h['coverage'] > 0]
        c = store.db()
        files = []
        for h in hits:
            r = c.execute('SELECT topic, description FROM files WHERE project=? AND path=?',
                          (h['project'], h['ref'])).fetchone()
            if r:
                files.append((h['project'], h['ref'], r[1], r[0]))
        notes = [h for h in find(terms, vault.NOTE_KINDS, project, 3) if h['coverage'] >= 0.5]
    except store.NoIndex:
        files = [(p, path, d, topic) for _, p, path, d, topic in _from_maps(terms, project, n)]
        notes = []
    if not files and not notes:
        return i18n.t('search.lookup_none', query=query), []
    lines, paths, last = [], [], None
    for proj, path, description, topic in files:
        root = projects.root_of(proj)
        if proj != last:
            lines.append(f'{proj} ({system.tilde(root or "")}):')
            last = proj
        lines.append(f'{path} — {text.short(description, 110) or i18n.t("search.no_description")} [{topic}]')
        if root:
            paths.append(os.path.join(root, *path.split('/')))
    if notes:
        lines.append(i18n.t('search.notes') + ': ' + ' · '.join(f'{note_title(h["ref"])} ({h["kind"]})' for h in notes))
    if session and paths:
        remember(session, paths)
    return '\n'.join(lines), paths


def note_title(rel):
    return os.path.splitext(os.path.basename(rel))[0]


TITLE_LINES = re.compile(r'(?m)^(# .*|(' + '|'.join({re.escape(i18n.t('note.project', lang))
                                                     for lang in i18n.LANGUAGES}) + r'): \[\[.*)$')


def fulltext(query, n=8):
    # text for hub_search: notes, decisions, sessions, docs
    terms = text.terms(query)
    if not terms:
        return i18n.t('search.no_terms')
    try:
        update()
        # code files are lookup's job; here notes, sessions and docs
        hits = [h for h in find(terms, None, None, n * 3) if h['kind'] != 'file' or h['ref'].endswith('.md')][:n]
    except store.NoIndex:
        return i18n.t('search.no_index')
    if not hits:
        return i18n.t('search.none', query=query)
    lines = []
    for h in hits:
        if h['kind'] == 'file':
            body = vault.read(os.path.join(projects.root_of(h['project']) or '', h['ref']), 12000)
            head = f'{h["project"]}: {h["ref"]}'
        else:
            body = vault.front(vault.read(os.path.join(vault.ROOT, h['ref'])))[1]
            head = f'{h["ref"]} ({h["kind"]})'
        # the title line and "Project: [[..]]" are already in the head
        body = TITLE_LINES.sub('', body)
        lines.append(f'{head}\n  {text.excerpt(body, terms)}' if body.strip() else head)
    return '\n'.join(lines)


def remember(session, paths):
    # files the hub named: read afterwards = a hit
    try:
        with store.transaction() as c:
            for p in paths:
                c.execute('INSERT OR REPLACE INTO suggestions VALUES(?,?,?)', (session, p, time.time()))
    except store.NoIndex:
        pass
