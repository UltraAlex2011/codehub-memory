# Following Claude Code without hooks: reads the transcripts
# (~/.claude/projects/<folder>/<session>.jsonl) directly and turns them into
# the same feed lines the hooks would write, plus the list of running
# sessions. The views use this until the hooks are installed - so the live
# feed works from the first minute. Hub hits are counted by the hooks only
# (they need the moment of every tool call and the hub's suggestions).
import glob
import os
import time

from . import i18n, projects, sessions, store, text
from .hooks import target

OPEN = 2 * 3600             # this long after the last entry a session counts as open
WORKING = 45                # seconds: nothing new by then, it waits for you
START = 256 * 1024          # at first sight read only the end of a file


class Follower:
    def __init__(self):
        self.files = {}     # transcript -> state of its session

    def _new(self, path, size):
        sid = os.path.splitext(os.path.basename(path))[0]
        try:
            r = store.db().execute('SELECT title, t_in, t_out, t_cache_write FROM sessions WHERE id=?',
                                   (sid,)).fetchone()
        except store.NoIndex:
            r = None
        return {'sid': sid, 'pos': max(0, size - START), 'title': (r[0] if r else '') or '',
                'tokens_db': sum(x or 0 for x in r[1:]) if r else 0, 'tokens': 0, 'ids': set(),
                'cwd': '', 'last': 0, 'done': True, 'action': '', 'open': {}}

    def scan(self):
        # -> new feed lines of all open sessions, oldest first
        now = time.time()
        lines = []
        for path in glob.glob(os.path.join(sessions.TRANSCRIPTS, '*', '*.jsonl')):
            try:
                st = os.stat(path)
            except OSError:
                continue
            z = self.files.get(path)
            if z is None:
                if now - st.st_mtime > OPEN:
                    continue
                z = self.files[path] = self._new(path, st.st_size)
            if st.st_size < z['pos']:
                z['pos'] = 0
            if st.st_size == z['pos']:
                continue
            entries, z['pos'] = sessions.read_from(path, z['pos'])
            for d in entries:
                lines += self._entry(z, d)
        for path in [p for p, z in self.files.items() if z['last'] and now - z['last'] > OPEN]:
            del self.files[path]
        lines.sort(key=lambda e: e['t'])
        return lines

    def _entry(self, z, d):
        kind = d.get('type')
        t = sessions.timestamp(d) or time.time()
        if kind == 'ai-title' and d.get('aiTitle'):
            z['title'] = d['aiTitle']
        if kind not in ('user', 'assistant') or d.get('isSidechain'):
            return []
        z['last'] = max(z['last'], t)
        z['cwd'] = d.get('cwd') or z['cwd']
        base = {'t': round(t, 3), 's': z['sid'][:8], 'a': 'main'}
        m = d.get('message') or {}
        content = m.get('content')
        out = []
        if kind == 'user':
            if isinstance(content, list):
                for b in content:
                    if not isinstance(b, dict) or b.get('type') != 'tool_result':
                        continue
                    before = z['open'].pop(b.get('tool_use_id') or '', None)
                    if not before:
                        continue
                    e = dict(before, t=round(t, 3), ms=int((t - before['t']) * 1000))
                    if b.get('is_error'):
                        e.update(e='error', x=text.short(sessions.plain(b.get('content')), 200))
                    else:
                        e['e'] = 'post'
                    out.append(e)
            if sessions.is_human(d, content):
                p = sessions.prompt_text(sessions.plain(content))
                if p and not sessions.is_interruption(p):
                    out.append(dict(base, e='prompt', d=p))
                    z['title'] = z['title'] or text.short(p, 60)
                    z['done'] = False
                    z['action'] = text.short(p, 60)
            return out
        # assistant: tokens once per message, without cache reads
        mid = m.get('id')
        if mid and mid not in z['ids']:
            z['ids'].add(mid)
            usage = m.get('usage') or {}
            z['tokens'] += sum(int(usage.get(k) or 0) for k in
                               ('input_tokens', 'output_tokens', 'cache_creation_input_tokens'))
        z['done'] = m.get('stop_reason') == 'end_turn'
        if not isinstance(content, list):
            return out
        for b in content:
            if not isinstance(b, dict):
                continue
            if b.get('type') == 'tool_use':
                name, args = b.get('name') or '', b.get('input') or {}
                e = dict(base, e='pre', w=name, d=target(name, args), id=(b.get('id') or '')[-12:])
                path = (args.get('file_path') or args.get('notebook_path')) if isinstance(args, dict) else None
                if path:
                    project, rel = projects.of(path)
                    if project:
                        e.update(p=project, r=rel)
                z['open'][b.get('id') or ''] = e
                z['action'] = text.short(f'{name} {os.path.basename(path) if path else e["d"]}', 60)
                out.append(e)
            elif b.get('type') == 'text' and z['done'] and b.get('text', '').strip():
                out.append(dict(base, e='stop', x=text.short(b['text'], 160)))
                z['action'] = i18n.t('status.done')
        return out

    def active(self):
        # like the hooks' session list: newest first
        now = time.time()
        found = []
        for z in self.files.values():
            if not z['last'] or now - z['last'] > OPEN:
                continue
            working = not z['done'] and now - z['last'] < WORKING
            project = projects.of(z['cwd'])[0] if z['cwd'] else None
            found.append({'id': z['sid'], 'title': z['title'] or z['sid'][:8], 'project': project or '',
                          'last': z['last'], 'tokens': max(z['tokens'], z['tokens_db']),
                          'state': 'working' if working else 'waiting', 'agent': 'main',
                          'action': z['action'] if working else i18n.t('status.waiting')})
        return sorted(found, key=lambda a: -a['last'])
