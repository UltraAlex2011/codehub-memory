# Sessions: tokens and title from the transcript, the session note, closing
# (map refresh, commit) and importing older sessions. The summary costs no
# tokens: when compacting, Claude Code delivers its own (PostCompact or
# isCompactSummary in the transcript); otherwise the note is built from the
# prompts, changed files, commits and the last answer.
import glob
import json
import os
import re
import time
from datetime import datetime

from . import events, i18n, projects, search, store, system, text, vault

TRANSCRIPTS = os.path.join(system.claude_dir(), 'projects')
EDIT_TOOLS = {'Edit', 'Write', 'MultiEdit', 'NotebookEdit'}
AGENT_TOOLS = {'Agent', 'Task'}
COMMIT = re.compile(r'^\[[\w./-]+(?: \(root-commit\))? ([0-9a-f]{7,40})\] (.+)$', re.M)
IDLE = 3 * 3600         # this long without an event, a session counts as over
USAGE = ('input_tokens', 'output_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens')


# ---- Reading transcripts ---------------------------------------------------------------

def read_from(path, offset=0):
    # complete lines only -> (entries, new offset)
    try:
        with open(path, 'rb') as f:
            f.seek(offset)
            data = f.read()
    except OSError:
        return [], offset
    end = data.rfind(b'\n') + 1
    entries = []
    for raw in data[:end].splitlines():
        try:
            entries.append(json.loads(raw))
        except ValueError:
            pass
    return entries, offset + end


def timestamp(entry):
    try:
        return datetime.fromisoformat(entry['timestamp'].replace('Z', '+00:00')).timestamp()
    except (KeyError, ValueError, AttributeError, TypeError):
        return None


def plain(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return '\n'.join(b.get('text', '') for b in content if isinstance(b, dict) and b.get('type') == 'text')
    return ''


def prompt_text(raw):
    # pasted text and system notes out, commands short: the gist of the
    # prompt in one line
    raw = re.sub(r'<pasted_content[^>]*>.*?</pasted_content[^>]*>', f' {i18n.t("session.pasted")} ', raw, flags=re.S)
    raw = re.sub(r'<system-reminder>.*?</system-reminder>', ' ', raw, flags=re.S)
    m = re.search(r'<command-name>([^<]+)</command-name>.*?(?:<command-args>([^<]*)</command-args>)?', raw, re.S)
    if m:
        raw = f'{m.group(1)} {m.group(2) or ""}'
    raw = re.sub(r'<[^>]{1,40}>', ' ', raw)
    return text.short(raw, 240)


def is_human(d, content):
    return (d.get('origin') or {}).get('kind') == 'human' or (
        'origin' not in d and isinstance(content, str) and not d.get('isMeta'))


def is_interruption(prompt):
    return prompt.startswith(('[Request interrupted', 'Caveat:'))


def new_summary():
    return {'title': '', 'prompts': [], 'edited': {}, 'read': {}, 'commits': [], 'agents': {},
            'tokens': [0, 0, 0, 0], 'messages': set(), 'answer': '', 'compact': '', 'start': None,
            'last': None, 'cwd': '', 'last_id': None}


def summarize(entries, s=None):
    # what the session note needs, from transcript entries.
    # tokens = [input, output, cache read, cache written]
    s = s or new_summary()
    for d in entries:
        kind = d.get('type')
        t = timestamp(d)
        if t:
            s['start'] = s['start'] or t
            s['last'] = t
        if kind == 'ai-title' and d.get('aiTitle'):
            s['title'] = d['aiTitle']
        elif kind == 'summary' and d.get('summary') and not s['title']:
            s['title'] = d['summary']
        if kind not in ('user', 'assistant'):
            continue
        s['cwd'] = s['cwd'] or d.get('cwd') or ''
        m = d.get('message') or {}
        content = m.get('content')
        if kind == 'user':
            if d.get('isCompactSummary'):
                s['compact'] = plain(content)
                continue
            if isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get('type') == 'tool_result':
                        result = plain(b.get('content'))
                        for h, msg in COMMIT.findall(result):
                            s['commits'].append((t, h[:7], msg))
                        a = s['agents'].get(b.get('tool_use_id'))
                        if a is not None and not a['result']:
                            a['result'] = text.short(result, 400)
            if is_human(d, content) and not d.get('isSidechain'):
                p = prompt_text(plain(content))
                if p and not is_interruption(p):
                    s['prompts'].append((t, p))
            continue
        # assistant: tokens once per message (every content block is a line
        # of its own with the same id)
        mid = m.get('id')
        usage = m.get('usage') or {}
        if mid:
            s['last_id'] = mid
        if mid and mid not in s['messages']:
            s['messages'].add(mid)
            for i, k in enumerate(USAGE):
                s['tokens'][i] += int(usage.get(k) or 0)
        if d.get('isSidechain') or not isinstance(content, list):
            continue
        for b in content:
            if not isinstance(b, dict):
                continue
            if b.get('type') == 'text' and b.get('text', '').strip():
                s['answer'] = b['text'].strip()
            elif b.get('type') == 'tool_use':
                name, args = b.get('name'), b.get('input') or {}
                path = args.get('file_path') or args.get('notebook_path')
                if name in EDIT_TOOLS and path:
                    s['edited'][path] = s['edited'].get(path, 0) + 1
                elif name == 'Read' and path:
                    s['read'][path] = s['read'].get(path, 0) + 1
                elif name in AGENT_TOOLS:
                    s['agents'][b.get('id')] = {'type': args.get('subagent_type') or 'general-purpose',
                                                'task': text.short(args.get('description') or args.get('prompt'), 120),
                                                'result': '', 'time': t}
    return s


def count_tokens(tokens, day=None):
    for kind, n in zip(store.TOKEN_COUNTERS, tokens):
        if n:
            store.count(kind, n, day)


# ---- Live: the session in the database -------------------------------------------------

def begin(d):
    c = store.db()
    now = time.time()
    c.execute('INSERT OR IGNORE INTO sessions(id, start, last, state) VALUES(?,?,?,?)',
              (d['session_id'], now, now, 'active'))
    c.execute("UPDATE sessions SET transcript=?, cwd=COALESCE(cwd, ?), last=?, state='active' WHERE id=?",
              (d.get('transcript_path') or '', d.get('cwd') or '', now, d['session_id']))


def trace(session, path, kind):
    # a file the session read or edited (for the note and the graph)
    project, rel = projects.of(path)
    if kind == 'edited' and not project:
        from . import maps
        project, rel = maps.project_for(path)
    c = store.db()
    c.execute('INSERT INTO traces VALUES(?,?,?,?,1,?) ON CONFLICT(session, path, kind) '
              'DO UPDATE SET n=n+1, time=excluded.time',
              (session, project, rel if project else system.resolve(path), kind, time.time()))
    c.execute('UPDATE sessions SET last=? WHERE id=?', (time.time(), session))
    return project, rel


def catch_up(session):
    # new transcript lines: tokens, title, compact summary. Tokens also go
    # into the daily counters.
    c = store.db()
    r = c.execute('SELECT transcript, offset, last_message FROM sessions WHERE id=?', (session,)).fetchone()
    if not r or not r[0]:
        return
    entries, offset = read_from(r[0], r[1] or 0)
    if not entries:
        return
    s = new_summary()
    if r[2]:
        s['messages'].add(r[2])      # already counted (block lines across the read boundary)
    summarize(entries, s)
    last = s['last_id'] or r[2]
    with store.transaction():
        c.execute('''UPDATE sessions SET offset=?, last_message=?, t_in=t_in+?, t_out=t_out+?,
                     t_cache_read=t_cache_read+?, t_cache_write=t_cache_write+?,
                     title=COALESCE(NULLIF(?, ''), title), compact=COALESCE(NULLIF(?, ''), compact)
                     WHERE id=?''', (offset, last, *s['tokens'], s['title'], s['compact'], session))
        count_tokens(s['tokens'])
        for t, h, msg in s['commits']:
            c.execute('INSERT OR IGNORE INTO commits VALUES(?,?,?,?)', (session, t, h, msg))


def project_of_session(session):
    c = store.db()
    r = c.execute('''SELECT project FROM traces WHERE session=? AND project IS NOT NULL GROUP BY project
                     ORDER BY SUM(n * CASE kind WHEN 'edited' THEN 3 ELSE 1 END) DESC LIMIT 1''',
                  (session,)).fetchone()
    if r:
        return r[0]
    cwd = (c.execute('SELECT cwd FROM sessions WHERE id=?', (session,)).fetchone() or [''])[0]
    if cwd and cwd not in ('/', system.HOME):
        return projects.of(cwd)[0] or vault.general()
    return vault.general()


# ---- Note ---------------------------------------------------------------------------------

def k(n):
    return f'{n / 1e6:.2f} M' if n >= 1e6 else f'{n / 1e3:.0f} k'


def tokens_text(t_in, t_out, cache_read, cache_write, lang=None):
    # used without cache reads (those only repeat the history), those behind
    used = t_in + t_out + cache_write
    if not used and not cache_read:
        return ''
    return i18n.t('session.tokens', lang, used=k(used), output=k(t_out), cache=k(cache_read))


def write_note(session):
    c = store.db()
    r = c.execute('''SELECT title, start, last, end, t_in, t_out, t_cache_read, t_cache_write, compact, answer, note
                     FROM sessions WHERE id=?''', (session,)).fetchone()
    if not r:
        return None
    title, start, last, end, t_in, t_out, cache_read, cache_write, compact, answer, old = r
    prompts = c.execute('SELECT time, text FROM prompts WHERE session=? ORDER BY time', (session,)).fetchall()
    edited = c.execute('''SELECT project, path, n FROM traces WHERE session=? AND kind='edited'
                          ORDER BY n DESC, path LIMIT 40''', (session,)).fetchall()
    if not prompts and not edited:
        return None
    lang = vault.lang()
    t = lambda key: i18n.t(key, lang)
    project = project_of_session(session)
    title = title or (prompts[0][1] if prompts else t('session.default_title'))
    name = text.file_name(f'{vault.now(start, "%Y-%m-%d %H-%M")} {text.short(title, 60)}')
    folder = os.path.join(vault.PROJECTS, text.file_name(project), vault.layout('session'))
    path = os.path.join(folder, name + '.md')
    if old and os.path.join(vault.ROOT, old) != path and os.path.exists(os.path.join(vault.ROOT, old)):
        # project or title were different before: move the note
        os.makedirs(folder, exist_ok=True)
        os.replace(os.path.join(vault.ROOT, old), path)
    before = c.execute('''SELECT note FROM sessions WHERE project=? AND start<? AND note IS NOT NULL
                          AND id<>? ORDER BY start DESC LIMIT 1''', (project, start, session)).fetchone()
    head = {'kind': 'session', 'project': project, 'session': session, 'start': vault.now(start),
            'end': vault.now(end or last)}
    tokens = tokens_text(t_in, t_out, cache_read, cache_write, lang)
    if tokens:
        head['tokens'] = tokens
    link = f'{t("note.project")}: [[{project}]]'
    if before:
        link += f' · {t("session.before")}: [[{os.path.basename(before[0])[:-3]}]]'
    parts = [vault.front_text(head), f'# {vault.now(start)} · {title}', '', link, '']
    if compact:
        parts += [f'## {t("session.summary")}', _trimmed(compact, 6000), '']
    if answer:
        parts += [f'## {t("session.answer")}', _trimmed(answer, 1800), '']
    if prompts:
        parts += [f'## {t("session.prompts")}'] + [f'- {vault.now(x, "%H:%M")} {p}' for x, p in prompts[-30:]] + ['']
    if edited:
        parts.append(f'## {t("session.changed")}')
        for proj, p, n in edited:
            prefix = '' if proj in (project, None) else f'{proj}: '
            parts.append(f'- {prefix}`{system.tilde(p) if not proj else p}`' + (f' ({n}×)' if n > 1 else ''))
        parts.append('')
    commits = c.execute('SELECT hash, text FROM commits WHERE session=? ORDER BY time', (session,)).fetchall()
    if commits:
        parts += [f'## {t("session.commits")}'] + [f'- `{h}` {text.short(msg, 120)}' for h, msg in commits] + ['']
    agents = c.execute('SELECT type, task, result FROM subagents WHERE session=? ORDER BY start',
                       (session,)).fetchall()
    if agents:
        parts.append(f'## {t("session.subagents")}')
        parts += [f'- {kind} „{task or "?"}“' + (f' — {text.short(res, 300)}' if res else '')
                  for kind, task, res in agents]
        parts.append('')
    from . import notes
    notes.project_note(project)
    vault.write(path, '\n'.join(parts))
    rel = vault.rel(path)
    with store.transaction():
        c.execute('UPDATE sessions SET note=?, project=? WHERE id=?', (rel, project, session))
        if old and old != rel:
            search.drop_note(c, old)
        search.index_note(c, rel)
    return rel


def _trimmed(content, n):
    # keep the answer's Markdown, but headings two levels deeper
    content = re.sub(r'(?m)^(#{1,4}) ', lambda m: '#' * min(6, len(m.group(1)) + 2) + ' ', content.strip())
    return content if len(content) <= n else content[:n].rsplit('\n', 1)[0] + '\n…'


def close(session):
    try:
        catch_up(session)
    except store.NoIndex:
        return None
    c = store.db()
    c.execute("UPDATE sessions SET state='ended', end=COALESCE(end, last, ?) WHERE id=?", (time.time(), session))
    rel = write_note(session)
    from . import maps
    for (project,) in c.execute('''SELECT DISTINCT project FROM traces WHERE session=? AND kind='edited'
                                   AND project IS NOT NULL''', (session,)).fetchall():
        try:
            maps.refresh(project)
        except Exception:
            pass        # a map that cannot be refreshed waits for the next session
    events.clean_logs()
    maps.write_overview()
    title = (c.execute('SELECT title FROM sessions WHERE id=?', (session,)).fetchone() or [''])[0]
    vault.backup(f'{i18n.t("session.commit", vault.lang())}: {text.short(title or session[:8], 70)}')
    return rel


def tidy():
    # sessions without SessionEnd (terminal closed, crash) are closed later
    c = store.db()
    for (sid,) in c.execute("SELECT id FROM sessions WHERE state<>'ended' AND last<?",
                            (time.time() - IDLE,)).fetchall():
        close(sid)


# ---- Import ----------------------------------------------------------------------------------

def import_recent(days=30, report=print):
    from . import maps
    c = store.db()
    limit = time.time() - days * 86400
    paths = sorted((p for p in glob.glob(os.path.join(TRANSCRIPTS, '*', '*.jsonl'))
                    if os.path.getmtime(p) >= limit), key=os.path.getmtime)
    done = 0
    for i, path in enumerate(paths, 1):
        sid = os.path.basename(path)[:-6]
        size = os.path.getsize(path)
        r = c.execute('SELECT offset FROM sessions WHERE id=?', (sid,)).fetchone()
        if r and (r[0] or 0) >= size:
            continue
        entries, offset = read_from(path)
        s = summarize(entries)
        del entries
        if not s['prompts'] and not s['edited']:
            continue
        running = time.time() - os.path.getmtime(path) < 600
        with store.transaction():
            for table in ('prompts', 'traces', 'subagents'):
                c.execute(f'DELETE FROM {table} WHERE session=?', (sid,))
            c.execute('''INSERT OR REPLACE INTO sessions(id, title, start, last, end, cwd, transcript, offset,
                         last_message, t_in, t_out, t_cache_read, t_cache_write, compact, answer, state)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                      (sid, s['title'], s['start'], s['last'], None if running else s['last'], s['cwd'], path,
                       offset, s['last_id'], *s['tokens'], s['compact'], s['answer'],
                       'active' if running else 'ended'))
            for t, p in s['prompts']:
                c.execute('INSERT INTO prompts VALUES(?,?,?)', (sid, t, p))
            for t, h, msg in s['commits']:
                c.execute('INSERT OR IGNORE INTO commits VALUES(?,?,?,?)', (sid, t, h, msg))
            for aid, a in s['agents'].items():
                c.execute('INSERT OR REPLACE INTO subagents VALUES(?,?,?,?,?,?,?)',
                          (sid, aid or '', a['type'], a['task'], a['result'], a['time'], a['time']))
            count_tokens(s['tokens'], vault.now(s['start'], '%Y-%m-%d'))
        for kind, found in (('edited', s['edited']), ('read', s['read'])):
            for p, n in found.items():
                project, rel = maps.project_for(p) if kind == 'edited' else projects.of(p)
                c.execute('INSERT OR REPLACE INTO traces VALUES(?,?,?,?,?,?)',
                          (sid, project, rel if project else p, kind, n, s['last']))
        write_note(sid)
        done += 1
        report(f'[{i}/{len(paths)}] {text.short(s["title"] or (s["prompts"][0][1] if s["prompts"] else sid), 70)}')
    search.update()
    maps.write_overview()
    store.meta('import', time.time())
    vault.backup(i18n.t('session.import_commit', vault.lang(), n=done, days=days), push=False)
    return done
