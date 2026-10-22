# Claude Code hooks ("codehub hook <event>", JSON of the event on stdin).
# Every event becomes a line in the live feed; files get traces, new files a
# map entry, sessions their note. SessionStart and UserPromptSubmit run
# synchronously and return short context, everything else is async and
# never holds Claude up. Never block, never fail: without a vault, or on any
# error, a hook ends silently.
import json
import os
import re
import sys
import time

from . import config, events, i18n, projects, search, store, system, text, vault

FREE_SEARCH = re.compile(r'(^|[;&|]\s*)(grep|rg|find|fd|ag|ack|locate)\s|(^|\s)ls\s+-\w*R')
AUTO_MOST = 6
WAITING = ('permission_prompt', 'idle_prompt', 'elicitation_dialog')


def agent(d):
    if d.get('agent_id'):
        return f"{d.get('agent_type') or 'subagent'}#{d['agent_id'][:6]}"
    return 'main'


def target(name, args):
    # what the tool touches, short for the feed
    if not isinstance(args, dict):
        return ''
    for k in ('file_path', 'notebook_path'):
        if isinstance(args.get(k), str):
            return args[k]
    if name == 'Bash':
        return text.short(args.get('description') or args.get('command'), 160)
    for k in ('pattern', 'query', 'url', 'skill', 'description', 'prompt', 'path', 'command'):
        if isinstance(args.get(k), str):
            return text.short(args[k], 160)
    return ''


def base(ev, **more):
    # fields every feed line has
    fields = {'s': ev.get('session_id', '')[:8], 'a': agent(ev)}
    fields.update(more)
    return fields


def _context(event, content):
    return {'hookSpecificOutput': {'hookEventName': event, 'additionalContext': content}} if content else None


# ---- Session -----------------------------------------------------------------------

def session_start(d):
    from . import sessions
    sessions.begin(d)
    events.event('start', **base(d, x=d.get('source'), d=system.tilde(d.get('cwd') or '')))
    events.set_status(d['session_id'], agent='main', last=i18n.t('status.started'), state='waiting',
                      title=d.get('session_title') or '')
    # sessions left open are closed in the background, at most once an hour
    if time.time() - float(store.meta('cleaned') or 0) > 3600:
        store.meta('cleaned', time.time())
        system.detach([*system.command(), 'tidy'])
    return _context('SessionStart', start_context(d))


def start_context(d):
    # as short as possible: projects and (on a fresh start) the last session
    if not config.get('startContext'):
        return ''
    c = store.db()
    search.update()
    found = c.execute('SELECT project, count(*) FROM files GROUP BY project ORDER BY 2 DESC LIMIT 6').fetchall()
    if not found:
        return ''
    lines = [i18n.t('hook.start', projects=', '.join(f'{p} ({n})' for p, n in found))]
    if d.get('source') in ('startup', 'clear'):
        project = None
        if d.get('cwd') not in (None, '', '/', system.HOME):
            project = projects.of(d['cwd'])[0]
        # only finished ones: for running (parallel) sessions the last answer
        # is an intermediate state, not a summary
        sql = '''SELECT project, title, last, answer, compact FROM sessions WHERE id<>? AND note IS NOT NULL
                 AND state='ended' AND (answer<>'' OR compact<>'') {} ORDER BY last DESC LIMIT 1'''
        r = None
        if project:
            r = c.execute(sql.format('AND project=?'), (d['session_id'], project)).fetchone()
        r = r or c.execute(sql.format(''), (d['session_id'],)).fetchone()
        if r:
            proj, title, last, answer, compact = r
            content = re.sub(r'[#*`>|]+', ' ', answer or compact or '')
            lines.append(i18n.t('hook.last', project=proj, when=vault.now(last, i18n.t('format.short')),
                                title=text.short(title, 60), text=text.short(content, 260)))
    return '\n'.join(lines)


def prompt(d):
    from . import sessions
    sid = d['session_id']
    task = sessions.prompt_text(d.get('prompt') or '')
    if task:
        c = store.db()
        c.execute('INSERT INTO prompts VALUES(?,?,?)', (sid, time.time(), task))
        c.execute('UPDATE sessions SET last=? WHERE id=?', (time.time(), sid))
    events.event('prompt', **base(d, d=task))
    events.set_status(sid, agent='main', last=text.short(task, 60), state='working')
    if d.get('source') not in (None, 'user') or not config.get('autoLookup'):
        return None
    return _context('UserPromptSubmit', auto_lookup(sid, task))


def auto_lookup(sid, task):
    # matching files for the prompt - only for a clear hit and only files
    # this session has not been told about yet
    terms = text.terms(task)
    if not terms or len(task) < 12:
        return ''
    search.update()
    c = store.db()
    rare = set()
    if store.FTS:
        for b in terms:
            n = c.execute('SELECT count(*) FROM search WHERE search MATCH ?', (f'"{b}"*',)).fetchone()[0]
            if 0 < n <= 12:
                rare.add(b)
    told = {p for (p,) in c.execute('SELECT path FROM suggestions WHERE session=?', (sid,)).fetchall()}
    chosen = []
    for h in search.find(terms, ('file',), None, 20):
        found = round(h['coverage'] * len(terms))
        if found < 2 and not (found == 1 and len(terms) <= 3 and any(b in rare for b in terms)):
            continue
        root = projects.root_of(h['project'])
        if not root or os.path.join(root, *h['ref'].split('/')) in told:
            continue
        r = c.execute('SELECT description FROM files WHERE project=? AND path=?', (h['project'], h['ref'])).fetchone()
        chosen.append((h['project'], h['ref'], r[0] if r else ''))
        if len(chosen) >= AUTO_MOST:
            break
    if not chosen:
        return ''
    search.remember(sid, [os.path.join(projects.root_of(p), *rel.split('/')) for p, rel, _ in chosen])
    store.count('auto')
    events.event('lookup', s=sid[:8], a='hub', d=text.short(task, 80), n=len(chosen), x='auto')
    lines = [i18n.t('hook.auto')]
    last = None
    for project, rel, description in chosen:
        if project != last:
            lines.append(f'{project} ({system.tilde(projects.root_of(project))}):')
            last = project
        lines.append(f'{rel} — {text.short(description, 80)}' if description else rel)
    return '\n'.join(lines)


def stop(d):
    from . import sessions
    sid = d['session_id']
    answer = d.get('last_assistant_message') or ''
    if answer:
        store.db().execute('UPDATE sessions SET answer=?, last=? WHERE id=?', (answer[:8000], time.time(), sid))
    sessions.catch_up(sid)
    sessions.write_note(sid)
    events.event('stop', **base(d, x=text.short(answer, 160)))
    events.set_status(sid, agent='main', last=i18n.t('status.done'), state='waiting')


def compact_before(d):
    events.event('compact', **base(d, x=d.get('trigger')))


def compact_after(d):
    from . import sessions
    sid = d['session_id']
    store.db().execute('UPDATE sessions SET compact=? WHERE id=?', (d.get('compact_summary') or '', sid))
    sessions.write_note(sid)
    events.event('compact', **base(d, x='done'))


def session_end(d):
    sid = d['session_id']
    events.event('end', **base(d, x=d.get('reason')))
    events.set_status(sid, state='ended')
    # note, map refresh and commit take time - detached, Claude ends at once
    system.detach([*system.command(), 'close', sid])


def notification(d):
    events.event('notify', **base(d, x=text.short(d.get('message'), 160), w=d.get('notification_type')))
    if d.get('notification_type') in WAITING:
        events.set_status(d['session_id'], last=text.short(d.get('message'), 60), state='waiting')


# ---- Subagents -----------------------------------------------------------------------

def subagent_start(d):
    sid, aid, kind = d['session_id'], d.get('agent_id') or '', d.get('agent_type') or 'subagent'
    task = store.meta(f'task:{sid}:{kind}') or ''
    store.db().execute('INSERT OR REPLACE INTO subagents VALUES(?,?,?,?,?,?,?)',
                       (sid, aid, kind, task, '', time.time(), None))
    events.event('sub+', **base(d, w=kind, d=task))
    events.set_status(sid, agent=f'{kind}#{aid[:6]}', last=text.short(task or i18n.t('status.subagent'), 60),
                      state='working')


def subagent_stop(d):
    from . import sessions
    sid, aid = d['session_id'], d.get('agent_id') or ''
    result = d.get('last_assistant_message') or ''
    c = store.db()
    c.execute('UPDATE subagents SET result=?, end=? WHERE session=? AND id=?',
              (text.short(result, 1500), time.time(), sid, aid))
    # the subagent's tokens are in its own transcript
    path = d.get('agent_transcript_path')
    if path:
        s = sessions.summarize(sessions.read_from(path)[0])
        if any(s['tokens']):
            c.execute('UPDATE sessions SET t_in=t_in+?, t_out=t_out+?, t_cache_read=t_cache_read+?, '
                      't_cache_write=t_cache_write+? WHERE id=?', (*s['tokens'], sid))
            sessions.count_tokens(s['tokens'])
    events.event('sub-', **base(d, w=d.get('agent_type'), x=text.short(result, 200)))
    events.set_status(sid, agent='main', last=i18n.t('status.subagent_done', kind=d.get('agent_type') or 'Subagent'),
                      state='working')


# ---- Tools ------------------------------------------------------------------------------

def _path(args):
    return (args.get('file_path') or args.get('notebook_path')) if isinstance(args, dict) else None


def tool_before(d):
    name, args = d.get('tool_name') or '', d.get('tool_input') or {}
    fields = base(d, w=name, d=target(name, args), id=d.get('tool_use_id', '')[-12:])
    path = _path(args)
    if path:
        project, rel = projects.of(path)
        if project:
            fields.update(p=project, r=rel)
    if name in ('Agent', 'Task') and isinstance(args, dict):
        # keep the task until SubagentStart brings the id
        store.meta(f'task:{d["session_id"]}:{args.get("subagent_type") or "general-purpose"}',
                   text.short(args.get('description') or args.get('prompt'), 120))
    events.event('pre', **fields)
    events.set_status(d['session_id'], agent=agent(d), state='working',
                      last=text.short(f'{name} {os.path.basename(path) if path else fields.get("d", "")}', 60))


def tool_after(d, ok=True):
    from . import sessions
    name, args = d.get('tool_name') or '', d.get('tool_input') or {}
    sid = d['session_id']
    fields = base(d, w=name, d=target(name, args), id=d.get('tool_use_id', '')[-12:], ok=ok)
    if d.get('duration_ms'):
        fields['ms'] = d['duration_ms']
    path = _path(args)
    if path and ok:
        kind = 'edited' if name in sessions.EDIT_TOOLS else 'read' if name == 'Read' else None
        project, rel = sessions.trace(sid, path, kind) if kind else projects.of(path)
        if project:
            fields.update(p=project, r=rel)
        if name in sessions.EDIT_TOOLS and project:
            new_file(sid, project, rel)
        if name == 'Read':
            store.count('read')
            if store.db().execute('SELECT 1 FROM suggestions WHERE session=? AND path=?',
                                  (sid, system.resolve(path))).fetchone():
                store.count('hit')
                fields['h'] = 1
        if name in sessions.EDIT_TOOLS and system.inside(system.resolve(path), vault.ROOT):
            search.update()         # Claude changed a vault note directly
    elif name in ('Grep', 'Glob'):
        store.count('free')
    elif name == 'Bash' and isinstance(args, dict):
        if FREE_SEARCH.search(args.get('command') or ''):
            store.count('free')
        response = d.get('tool_response')
        output = response.get('stdout', '') if isinstance(response, dict) else str(response or '')
        if 'git' in (args.get('command') or '') and ok:
            for h, msg in sessions.COMMIT.findall(output or ''):
                store.db().execute('INSERT OR IGNORE INTO commits VALUES(?,?,?,?)', (sid, time.time(), h[:7], msg))
    elif name == 'mcp__codehub__hub_lookup' and ok:
        # files it named: read afterwards = a hit
        response = d.get('tool_response')
        content = response if isinstance(response, str) else json.dumps(response, ensure_ascii=False)
        paths = []
        for _, root in projects.all_projects():
            for rel in re.findall(r'(?:^|\\n|\n)([\w./+-]+\.\w{1,8}) —', content):
                full = os.path.join(root, *rel.split('/'))
                if os.path.exists(full):
                    paths.append(full)
        search.remember(sid, paths)
    if not ok:
        fields['x'] = text.short(d.get('error') or '', 200)
    events.event('post' if ok else 'error', **fields)


def new_file(sid, project, rel):
    # a file not yet in the map: add it with its header comment
    from . import maps
    root = projects.root_of(project)
    search.update()
    if store.db().execute('SELECT 1 FROM files WHERE project=? AND path=?', (project, rel)).fetchone():
        return
    if not maps.is_text(root, rel) or any(x.startswith('.') for x in rel.split('/')[:-1]):
        return
    if maps.ignored(root, rel):
        return
    topic, _ = maps.set_entry(project, rel, maps.describe(root, rel), only_new=True)
    events.event('map', s=sid[:8], a='hub', p=project, r=rel, x=topic)


HANDLERS = {
    'SessionStart': session_start, 'UserPromptSubmit': prompt, 'PreToolUse': tool_before,
    'PostToolUse': tool_after, 'PostToolUseFailure': lambda d: tool_after(d, ok=False),
    'SubagentStart': subagent_start, 'SubagentStop': subagent_stop, 'Stop': stop, 'Notification': notification,
    'PreCompact': compact_before, 'PostCompact': compact_after, 'SessionEnd': session_end,
}


def main(event_name=''):
    if os.environ.get('CODEHUB_OFF') or not vault.is_ready():
        return
    # bytes, not text: Windows consoles would decode UTF-8 as cp1252
    try:
        d = json.loads(sys.stdin.buffer.read().decode('utf-8', 'replace'))
    except ValueError:
        return
    handler = HANDLERS.get(d.get('hook_event_name') or event_name) if isinstance(d, dict) else None
    if not handler or not d.get('session_id'):
        return
    out = handler(d)
    if out:
        sys.stdout.buffer.write(json.dumps(out, ensure_ascii=False).encode('utf-8'))


def run(event_name=''):
    try:
        main(event_name)
    except Exception:
        if os.environ.get('CODEHUB_DEBUG'):
            raise
