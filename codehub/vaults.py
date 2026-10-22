# Several vaults like in Obsidian: create one, add an existing folder, file
# tree, read/write/rename/delete documents. A vault is a folder of Markdown;
# .obsidian/ inside makes Obsidian open it. The list = the Code Hub vault,
# our own list and the vaults Obsidian knows. Nothing is deleted for good:
# files move to <vault>/.trash as in Obsidian.
import json
import os
import re
import secrets
import time

from . import i18n, search, system, text, vault

LIST = os.path.join(system.config_dir(), 'vaults.json')
NEW_IN = os.path.join(system.HOME, 'Vaults')
HIDDEN = ('.obsidian', '.hub', '.git', '.trash')
MOST_ENTRIES = 4000
# in the Code Hub vault the hub rewrites these files itself - read only
HUB_PROTECTED = re.compile(r'^(00_Index|03_Logs)/|' + vault.SESSION_FOLDERS.pattern)


class Error(Exception):
    pass


def _load():
    try:
        with open(LIST, encoding='utf-8') as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(d):
    vault.write(LIST, json.dumps(d, ensure_ascii=False, indent=1))


def _obsidian_vaults():
    try:
        with open(system.obsidian_config(), encoding='utf-8') as f:
            return [v['path'] for v in json.load(f).get('vaults', {}).values() if v.get('path')]
    except (OSError, ValueError, AttributeError):
        return []


def _obsidian_add(path):
    # so the new vault is in Obsidian's vault list too
    target = system.obsidian_config()
    try:
        with open(target, encoding='utf-8') as f:
            d = json.load(f)
    except (OSError, ValueError):
        return
    known = d.setdefault('vaults', {})
    if any(v.get('path') == path for v in known.values()):
        return
    known[secrets.token_hex(8)] = {'path': path, 'ts': int(time.time() * 1000)}
    vault.write(target, json.dumps(d))


def listing():
    d = _load()
    hidden = set(d.get('hidden', []))
    main = vault.ROOT
    out = [{'name': 'Code Hub', 'path': main, 'hub': True}]
    seen = {main}
    for path in [v.get('path') for v in d.get('vaults', [])] + _obsidian_vaults():
        if not path:
            continue
        real = system.resolve(path)
        if real in seen or real in hidden or not os.path.isdir(real):
            continue
        seen.add(real)
        out.append({'name': os.path.basename(real), 'path': real, 'hub': False})
    last = d.get('last') if d.get('last') in seen else main
    return {'type': 'vaults', 'list': out, 'last': last}


def remember(path):
    d = _load()
    d['last'] = path
    _save(d)


def _take(path):
    d = _load()
    d['hidden'] = [p for p in d.get('hidden', []) if p != path]
    if not any(v.get('path') == path for v in d.setdefault('vaults', [])):
        d['vaults'].append({'path': path})
    d['last'] = path
    _save(d)


def create(name):
    if not (name or '').strip():
        raise Error(i18n.t('vault.needs_name'))
    path = os.path.join(NEW_IN, text.file_name(name))
    if os.path.exists(path):
        raise Error(i18n.t('vault.exists', path=system.tilde(path)))
    os.makedirs(os.path.join(path, '.obsidian'))
    _take(path)
    _obsidian_add(path)
    return path


def add(path):
    real = system.resolve(path or '')
    if not os.path.isdir(real):
        raise Error(i18n.t('vault.no_folder', path=path))
    if real in (system.HOME, os.path.abspath(os.sep)):
        raise Error(i18n.t('vault.too_big'))
    os.makedirs(os.path.join(real, '.obsidian'), exist_ok=True)
    _take(real)
    _obsidian_add(real)
    return real


def remove(path):
    # only from the list - the folder stays
    if system.resolve(path) == vault.ROOT:
        raise Error(i18n.t('vault.keep_hub'))
    d = _load()
    d['vaults'] = [v for v in d.get('vaults', []) if v.get('path') != path]
    d.setdefault('hidden', []).append(path)
    if d.get('last') == path:
        d['last'] = vault.ROOT
    _save(d)


# ---- Files in a vault ---------------------------------------------------------------

def _valid(v):
    real = system.resolve(v or '')
    if real not in {system.resolve(x['path']) for x in listing()['list']}:
        raise Error(i18n.t('vault.unknown'))
    return real


def resolve(v, rel):
    # a path inside the vault; nothing outside (../, symlinks out)
    root = _valid(v)
    p = os.path.realpath(os.path.join(root, rel or ''))
    if not system.inside(p, root):
        raise Error(i18n.t('vault.outside'))
    return root, p


def is_hub(v):
    return system.resolve(v) == vault.ROOT


def protected(v, rel):
    if is_hub(v) and HUB_PROTECTED.search(rel):
        return i18n.t('vault.protected')
    return ''


def _visible(root, folder, names):
    # subfolders shown in the tree; the hub's raw events (03_Logs, growing
    # with every tool call) stay out
    return [n for n in names if n not in HIDDEN and not n.startswith('.')
            and not (n == '03_Logs' and folder == root and is_hub(root))]


def signature(v):
    # changes as soon as something is added, removed or saved
    n, newest = 0, 0.0
    try:
        root = _valid(v)
    except Error:
        return None
    for w, folders, names in os.walk(root):
        folders[:] = _visible(root, w, folders)
        for x in folders + names:
            n += 1
            try:
                newest = max(newest, os.stat(os.path.join(w, x)).st_mtime)
            except OSError:
                pass
    return n, newest


def tree(v):
    root = _valid(v)
    entries = []

    def walk(folder, depth):
        try:
            found = sorted(os.scandir(folder), key=lambda e: (not e.is_dir(), e.name.lower()))
        except OSError:
            return
        for e in found:
            if len(entries) >= MOST_ENTRIES:
                return
            if e.name.endswith('.tmp') or e.name.startswith('.') or (e.is_dir() and not _visible(root, folder, [e.name])):
                continue
            rel = vault_rel(root, e.path)
            if e.is_dir():
                entries.append({'rel': rel, 'name': e.name, 'depth': depth, 'folder': True})
                walk(e.path, depth + 1)
            else:
                entries.append({'rel': rel, 'name': e.name[:-3] if e.name.endswith('.md') else e.name,
                                'depth': depth, 'folder': False, 'md': e.name.endswith('.md')})
    walk(root, 0)
    return {'type': 'tree', 'vault': root, 'entries': entries, 'full': len(entries) >= MOST_ENTRIES}


def vault_rel(root, path):
    return system.posix(os.path.relpath(path, root))


def _targets(root):
    # [[name]] -> rel, like Obsidian: file name without .md, also with folders
    found = {}
    for w, folders, names in os.walk(root):
        folders[:] = _visible(root, w, folders)
        for n in names:
            rel = vault_rel(root, os.path.join(w, n))
            bare = rel[:-3] if n.endswith('.md') else rel
            found.setdefault(os.path.basename(bare), rel)
            found[bare] = rel
    return found


def rendered(content, root, name=''):
    # reading mode: no frontmatter, no heading equal to the file name (it is
    # the title above already), [[links]] as doc:/new: links
    from urllib.parse import quote
    _, body = vault.front(content)
    first = body.lstrip('\n').split('\n', 1)
    if name and first[0].strip() == '# ' + name:
        body = first[1] if len(first) > 1 else ''
    targets = _targets(root)

    def replace(m):
        goal = m.group(1).split('#')[0].strip()
        shown = (m.group(2) or m.group(1)).strip()
        rel = targets.get(goal)
        return f'[{shown}]({"doc:" + quote(rel) if rel else "new:" + quote(goal)})'
    return re.sub(r'!?\[\[([^\]|]+)(?:\|([^\]]+))?\]\]', replace, body)


def _title(rel):
    return os.path.splitext(os.path.basename(rel))[0]


def read(v, rel):
    root, p = resolve(v, rel)
    if not os.path.isfile(p):
        raise Error(i18n.t('vault.gone'))
    raw = vault.read(p)
    return {'type': 'document', 'vault': root, 'rel': rel, 'raw': raw, 'view': rendered(raw, root, _title(rel)),
            'stamp': str(os.stat(p).st_mtime_ns), 'protected': protected(root, rel),
            'info': i18n.t('doc.info', words=len(raw.split()),
                           when=vault.now(os.path.getmtime(p), i18n.t('format.datetime')))}


def save(v, rel, content, stamp):
    # stamp "*" = overwrite despite a change made elsewhere
    root, p = resolve(v, rel)
    if protected(root, rel):
        raise Error(protected(root, rel))
    if not isinstance(content, str):
        raise Error(i18n.t('vault.no_text'))
    if stamp != '*' and os.path.exists(p) and str(os.stat(p).st_mtime_ns) != str(stamp):
        return {'type': 'doc_saved', 'vault': root, 'rel': rel, 'ok': False, 'reason': i18n.t('vault.changed')}
    vault.write(p, content)
    if is_hub(root):
        search.update()
    return {'type': 'doc_saved', 'vault': root, 'rel': rel, 'ok': True, 'stamp': str(os.stat(p).st_mtime_ns),
            'view': rendered(content, root, _title(rel))}


def _free(folder, name, ending=''):
    p = os.path.join(folder, name + ending)
    i = 1
    while os.path.exists(p):
        p = os.path.join(folder, f'{name} {i}{ending}')
        i += 1
    return p


def new(v, folder_rel, kind, name=''):
    root, folder = resolve(v, folder_rel)
    if not os.path.isdir(folder):
        folder = os.path.dirname(folder)
    if is_hub(root) and folder == root and kind != 'folder':
        folder = vault.OWN               # loose notes in the hub vault go to the user's folder
    if kind == 'folder':
        p = _free(folder, text.file_name(name or i18n.t('vault.new_folder')))
        os.makedirs(p)
    else:
        p = _free(folder, text.file_name(name or i18n.t('vault.untitled')), '.md')
        vault.write(p, '')
        if is_hub(root):
            search.update()
    return {'type': 'doc_new', 'vault': root, 'rel': vault_rel(root, p), 'folder': kind == 'folder'}


def rename(v, rel, name):
    # like Obsidian: [[old name]] is renamed in every note of the vault
    root, p = resolve(v, rel)
    if protected(root, rel) or p == root:
        raise Error(i18n.t('vault.cannot_rename'))
    md = os.path.isfile(p) and p.endswith('.md')
    name = text.file_name(name)
    goal = os.path.join(os.path.dirname(p), name + ('.md' if md else ''))
    if goal == p:
        return {'type': 'doc_new', 'vault': root, 'rel': rel, 'folder': not md}
    if os.path.exists(goal):
        raise Error(i18n.t('vault.name_taken', name=name))
    os.rename(p, goal)
    if md:
        old = os.path.basename(p)[:-3]
        pattern = re.compile(r'\[\[' + re.escape(old) + r'(?=[\]|#])')
        for w, folders, names in os.walk(root):
            folders[:] = _visible(root, w, folders)
            for n in names:
                if n.endswith('.md'):
                    q = os.path.join(w, n)
                    before = vault.read(q)
                    after = pattern.sub('[[' + name, before)
                    if after != before and not protected(root, vault_rel(root, q)):
                        vault.write(q, after)
    if is_hub(root):
        search.update()
    return {'type': 'doc_new', 'vault': root, 'rel': vault_rel(root, goal), 'folder': not md}


def delete(v, rel):
    root, p = resolve(v, rel)
    if protected(root, rel) or p == root:
        raise Error(i18n.t('vault.cannot_delete'))
    trash = os.path.join(root, '.trash')
    os.makedirs(trash, exist_ok=True)
    name, ending = os.path.splitext(os.path.basename(p))
    os.rename(p, _free(trash, name, ending))
    if is_hub(root):
        search.update()
