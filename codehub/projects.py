# Projects and their maps. A project is a folder (usually a git repo) with a
# map in 00_Index/<project> MAP.md: topic -> files with a one-line
# description. The frontmatter of each map names the project and its root.
import glob
import os
import re

from . import i18n, system, text, vault

ENTRY = re.compile(r'^- `([^`]+)`(?:\s+[—–-]\s*(.*?))?\s*$')
FOLDER_PREFIXES = tuple(d['folder'] + ' ' for d in vault.LAYOUTS.values())

_projects = None


def map_file(project):
    return os.path.join(vault.MAPS, text.file_name(project) + ' MAP.md')


def all_projects():
    # (name, root) from every map; longest root first so nested projects win.
    # Built aside and assigned when complete: the views count tokens in a
    # thread, and a half-filled list would make the index drop every file.
    global _projects
    found = _projects
    if found is None:
        found = []
        for path in glob.glob(os.path.join(vault.MAPS, '*MAP.md')):
            head = vault.front(vault.read(path, 1500))[0]
            if head.get('project') and head.get('root'):
                found.append((head['project'], system.resolve(head['root'])))
        found.sort(key=lambda p: -len(p[1]))
        _projects = found
    return found


def reload():
    global _projects
    _projects = None


def of(path):
    # -> (project, path relative to its root with "/") or (None, absolute path)
    if not path:
        return None, path
    p = system.resolve(path)
    for name, root in all_projects():
        if system.inside(p, root):
            return name, system.posix(os.path.relpath(p, root))
    return None, p


def root_of(project):
    for name, root in all_projects():
        if name == project:
            return root
    return None


def name(value):
    # case does not matter: "a-shell" -> "A-Shell"
    wanted = str(value or '').strip().lower()
    for n, _ in all_projects():
        if n.lower() == wanted:
            return n
    return None


def read_map(path):
    # -> (head, {topic: [(path, description), ...]}) in file order
    head, body = vault.front(vault.read(path))
    topics, topic = {}, None
    for line in body.splitlines():
        if line.startswith('## '):
            topic = line[3:].strip()
            topics.setdefault(topic, [])
            continue
        m = ENTRY.match(line)
        if m and topic:
            topics[topic].append((m.group(1), (m.group(2) or '').strip()))
    return head, topics


def write_map(project, root, topics):
    head = {'project': project, 'root': system.tilde(root), 'updated': vault.now(), 'kind': 'map'}
    n = sum(len(e) for e in topics.values())
    lang = vault.lang()
    parts = [vault.front_text(head), f'# {project} MAP', '',
             i18n.t('map.intro', lang, n=n, root=system.tilde(root)),
             f'{i18n.t("note.project", lang)}: [[{project}]]', '']
    for topic, entries in topics.items():
        if not entries:
            continue
        parts.append(f'## {topic}')
        for path, description in entries:
            parts.append(f'- `{path}` — {description}' if description else f'- `{path}`')
        parts.append('')
    vault.write(map_file(project), '\n'.join(parts))
    reload()


def is_folder_topic(topic):
    return topic.startswith(FOLDER_PREFIXES)


def folder_topic(path):
    parts = path.split('/')[:-1][:2]
    return f'{vault.layout("folder")} ' + ('/'.join(parts) if parts else i18n.t('map.root', vault.lang()))


def next_topic(topics, path):
    # a new file: the topic most common in its folder
    folder = os.path.dirname(path)
    votes = {}
    for topic, entries in topics.items():
        for p, _ in entries:
            if os.path.dirname(p) == folder:
                votes[topic] = votes.get(topic, 0) + 1
    if votes:
        return max(votes, key=votes.get)
    return folder_topic(path)
