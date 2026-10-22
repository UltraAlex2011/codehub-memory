# MCP server "codehub" for Claude Code and its subagents (stdio, JSON-RPC
# 2.0, one message per line). Tool descriptions and answers are short on
# purpose: both land in every context and cost tokens.
import json
import os
import sys

from . import VERSION, config, events, i18n, notes, projects, search, store, text, vault

TOOLS = [
    {'name': 'hub_lookup',
     'description': 'Find the files responsible for a feature/topic (project MAP) BEFORE grepping or '
                    'opening files. Returns paths with 1-line descriptions and related notes.',
     'inputSchema': {'type': 'object', 'required': ['query'], 'properties': {
         'query': {'type': 'string', 'description': 'feature/topic words, e.g. "login form validation"'},
         'project': {'type': 'string', 'description': 'optional project name'}}},
     'annotations': {'readOnlyHint': True}},
    {'name': 'hub_search',
     'description': 'Full-text search in the Code Hub vault: decisions, solved bugs, notes, session logs, '
                    'project docs.',
     'inputSchema': {'type': 'object', 'required': ['query'], 'properties': {
         'query': {'type': 'string'}, 'limit': {'type': 'integer'}}},
     'annotations': {'readOnlyHint': True}},
    {'name': 'hub_note',
     'description': 'Save a vault note; same title replaces it. kind: decision | bug | note | snippet | '
                    'architecture | open (architecture/open = one section per title in a per-project note).',
     'inputSchema': {'type': 'object', 'required': ['project', 'title', 'content'], 'properties': {
         'project': {'type': 'string'}, 'title': {'type': 'string'},
         'content': {'type': 'string', 'description': 'Markdown, short'},
         'kind': {'type': 'string'}, 'tags': {'type': 'array', 'items': {'type': 'string'}}}}},
    {'name': 'hub_map_update',
     'description': "Set a file's 1-line description (and optional topic) in the project MAP, e.g. after "
                    'you had to search for it.',
     'inputSchema': {'type': 'object', 'required': ['file', 'description'], 'properties': {
         'file': {'type': 'string', 'description': 'absolute path, or relative to the project root'},
         'description': {'type': 'string'}, 'topic': {'type': 'string'},
         'project': {'type': 'string', 'description': 'needed only for relative paths'}}}},
    {'name': 'hub_log',
     'description': 'Post a milestone to the Code Hub live feed (tool calls are logged automatically).',
     'inputSchema': {'type': 'object', 'required': ['action'], 'properties': {
         'action': {'type': 'string'}, 'detail': {'type': 'string'}, 'agent': {'type': 'string'}}}},
]


def lookup(a):
    store.count('lookup')
    return search.lookup(a.get('query') or '', a.get('project'))[0]


def fulltext(a):
    store.count('search')
    try:
        n = max(1, min(int(a.get('limit') or 8), 20))
    except (TypeError, ValueError):
        n = 8
    return search.fulltext(a.get('query') or '', n)


def note(a):
    rel = notes.save(a.get('project') or vault.general(), a.get('title') or 'Note', a.get('content') or '',
                     a.get('kind') or 'note', a.get('tags') or ())
    events.event('note', a='claude', p=rel.split('/')[1] if rel.startswith('01_') else '', d=rel)
    return i18n.t('mcp.saved', path=rel)


def map_update(a):
    from . import maps
    path = str(a.get('file') or '').strip()
    project = projects.name(a.get('project'))
    if os.path.isabs(os.path.expanduser(path)):
        project, rel = maps.project_for(path)
        if not project:
            return i18n.t('mcp.no_project', path=path)
    elif project:
        rel = os.path.normpath(path).replace(os.sep, '/')
    else:
        return i18n.t('mcp.needs_project')
    if rel.startswith('..'):
        return i18n.t('mcp.outside', path=path, project=project)
    topic, _ = maps.set_entry(project, rel, a.get('description') or '', (a.get('topic') or '').strip() or None)
    events.event('map', a='claude', p=project, r=rel, x=topic)
    return f'MAP {project}: {rel} → {topic}'


def log(a):
    events.event('log', a=a.get('agent') or 'claude', w=text.short(a.get('action'), 80),
                 d=text.short(a.get('detail'), 300))
    return 'ok'


HANDLERS = {'hub_lookup': lookup, 'hub_search': fulltext, 'hub_note': note, 'hub_map_update': map_update,
            'hub_log': log}


def answer(nid, result):
    return {'jsonrpc': '2.0', 'id': nid, 'result': result}


def error(nid, code, message):
    return {'jsonrpc': '2.0', 'id': nid, 'error': {'code': code, 'message': message}}


def handle(n):
    if not isinstance(n, dict):
        return error(None, -32600, 'Invalid request')
    method, nid, params = n.get('method'), n.get('id'), n.get('params') or {}
    if nid is None:
        return None             # notification (initialized, cancelled ...)
    if method == 'initialize':
        return answer(nid, {'protocolVersion': params.get('protocolVersion') or '2025-06-18',
                            'capabilities': {'tools': {'listChanged': False}},
                            'serverInfo': {'name': 'codehub', 'version': VERSION}})
    if method == 'ping':
        return answer(nid, {})
    if method == 'tools/list':
        return answer(nid, {'tools': TOOLS})
    if method == 'tools/call':
        f = HANDLERS.get(params.get('name'))
        if not f:
            return error(nid, -32602, f'Unknown tool: {params.get("name")}')
        # other processes may have changed maps and settings meanwhile
        projects.reload()
        config.reload()
        try:
            content, failed = f(params.get('arguments') or {}), False
        except Exception as e:
            content, failed = f'{i18n.t("mcp.error")}: {e}', True
        return answer(nid, {'content': [{'type': 'text', 'text': content}], 'isError': failed})
    return error(nid, -32601, f'Not supported: {method}')


def main():
    # bytes in and out: the same on every system, whatever the console encoding
    stdin, stdout = sys.stdin.buffer, sys.stdout.buffer
    while True:
        line = stdin.readline()
        if not line:
            break
        if not line.strip():
            continue
        try:
            n = json.loads(line.decode('utf-8', 'replace'))
        except ValueError:
            out = error(None, -32700, 'Parse error')
        else:
            out = [x for x in map(handle, n) if x] if isinstance(n, list) else handle(n)
        if out:
            stdout.write(json.dumps(out, ensure_ascii=False).encode('utf-8') + b'\n')
            stdout.flush()
