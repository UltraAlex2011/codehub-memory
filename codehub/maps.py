# Making and keeping maps: which file belongs to which topic, with one line of
# description. Costs no tokens - topics come from the project's docs (docs/,
# Doku/, Doku/Bauteile/: the title is the topic, the files it mentions belong
# to it), descriptions from each file's header comment. What is already in a
# map (by hand or hub_map_update) stays.
import os
import re
import subprocess
import tempfile

from . import i18n, projects, search, store, system, text, vault

TEXT = {'.qml', '.js', '.mjs', '.cjs', '.ts', '.tsx', '.jsx', '.py', '.sh', '.bash', '.zsh', '.fish',
        '.lua', '.frag', '.vert', '.glsl', '.conf', '.txt', '.json', '.md', '.nix', '.toml', '.yaml',
        '.yml', '.css', '.scss', '.html', '.desktop', '.service', '.timer', '.rules', '.ini', '.cfg',
        '.c', '.h', '.cpp', '.hpp', '.rs', '.go', '.java', '.kt', '.rb', '.php', '.sql', '.kdl',
        '.vim', '.el', '.mk', '.cmake', '.ron', '.mcmeta', '.properties', '.xml', '.zon', '.zig',
        '.swift', '.cs', '.vue', '.svelte', '.dart', '.ex', '.exs', '.scala', '.ps1'}
NAMES = {'Makefile', 'Dockerfile', 'PKGBUILD', 'CMakeLists.txt', 'justfile', 'Justfile'}
LARGE = 400_000          # larger files are data, not programs
MOST = 5000              # projects with more text files get no map
GENERIC = 60             # a doc naming more files is an overview, not a topic
# overviews by name (folded): they name many files but are no topic
OVERVIEWS = {'chronik', 'changelog', 'start', 'readme', 'regeln', 'rules', 'index', 'uebersicht',
             'overview', 'abhaengigkeiten', 'ram-budget', 'einstellungen-plan', 'todo', 'roadmap'}
LEAST = 0.2              # below this no main topic, only a side topic
SKIP_DIRS = ('node_modules', '__pycache__', 'target', 'build', 'dist', 'venv', '.venv')

LINE_COMMENT = {'#': {'.py', '.sh', '.bash', '.zsh', '.fish', '.conf', '.toml', '.yaml', '.yml', '.nix', '.txt',
                      '.cfg', '.rules', '.service', '.timer', '.desktop', '.mk', '.cmake', '.ini', '.properties',
                      '.rb', '.ex', '.exs', '.ps1', ''},
                '--': {'.lua', '.sql'},
                '//': {'.qml', '.js', '.mjs', '.cjs', '.ts', '.tsx', '.jsx', '.frag', '.vert', '.glsl', '.c', '.h',
                       '.cpp', '.hpp', '.rs', '.go', '.java', '.kt', '.kdl', '.php', '.zig', '.zon', '.scss',
                       '.ron', '.swift', '.cs', '.dart', '.scala'},
                ';': {'.ini', '.el', '.cfg', '.conf'},
                '"': {'.vim'}}
# lines before the header comment that describe nothing
PREAMBLE = re.compile(r'^\s*(#!|# -\*-|pragma |\.pragma|import |from \S+ import|#version|#extension|'
                      r'precision |["\']use strict|#include|#pragma|//!|<\?xml|<!DOCTYPE|@import|'
                      r'---\s*$|module |package |using )')
LICENSE = re.compile(r'(SPDX|copyright|license|lizenz|vim:|eslint|noqa|type: ignore|@ts-|prettier|'
                     r'^-\*-|^\s*TODO\b)', re.I)
CODE = re.compile(r'[;{}]$|^(var|let|const|property|function|def|return|if|for|while|import|local|'
                  r'readonly|signal|class|export)\b|^[\w.]+\s*(=[^=]|\+=|:=)')
ABBREVIATION = re.compile(r'(?i)(\b(z|d|u|o|s|v|i)\.\s?[a-zäöü]|bzw|ggf|usw|evtl|inkl|vgl|ca|nr|bsp|max|min|etc|'
                          r'e\.g|i\.e|vs|ff|sog|zzgl|ehem)\.$')
REF = re.compile(r'[~\w./+-]*[\w+-]\.(?:qml|js|mjs|ts|tsx|jsx|py|sh|lua|frag|vert|glsl|conf|json|md|nix|txt|'
                 r'desktop|service|css|toml|ya?ml|kdl|rules|c|h|cpp|rs|go|swift|cs|java|kt|rb|php|vue)(?![\w])')
DOCS = re.compile(r'(?i)^(doku/bauteile|doku|docs?|documentation)/[^/]+\.md$')


# ---- Files and descriptions --------------------------------------------------------

def _git(root, *args, timeout=30):
    return subprocess.run(['git', '-C', root, *args], capture_output=True, timeout=timeout,
                          stdin=subprocess.DEVNULL)


def files_of(root):
    listing = None
    try:
        # tracked + new (not yet committed), without ignored files
        r = _git(root, 'ls-files', '-z', '--cached', '--others', '--exclude-standard')
        if r.returncode == 0:
            listing = sorted(set(p for p in r.stdout.decode('utf-8', 'replace').split('\0') if p))
    except (OSError, subprocess.SubprocessError):
        pass
    if listing is None:
        listing = []
        for folder, subs, names in os.walk(root):
            subs[:] = [s for s in subs if not s.startswith('.') and s not in SKIP_DIRS]
            listing += [system.posix(os.path.relpath(os.path.join(folder, n), root)) for n in names]
            if len(listing) > MOST * 4:
                break
    # hidden folders (.obsidian, .github ...) are settings, not code
    return sorted((p for p in listing if not any(x.startswith('.') for x in p.split('/')[:-1])
                   and is_text(root, p)), key=str.lower)


def is_text(root, rel):
    name = os.path.basename(rel)
    ext = os.path.splitext(name)[1].lower()
    path = os.path.join(root, rel)
    if ext not in TEXT and name not in NAMES:
        if ext or not os.path.isfile(path):
            return False
        try:
            with open(path, 'rb') as f:
                if f.read(2) != b'#!':      # script without extension
                    return False
        except OSError:
            return False
    try:
        return os.path.getsize(path) < LARGE or os.path.islink(path)
    except OSError:
        return False


def ignored(root, rel):
    # files git ignores (runtime, state ...) do not belong in the map
    try:
        return _git(root, 'check-ignore', '-q', rel, timeout=5).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def describe(root, rel):
    path = os.path.join(root, rel)
    if os.path.islink(path):
        return i18n.t('map.link', vault.lang(), target=os.readlink(path))
    try:
        with open(path, 'rb') as f:
            raw = f.read(6000)
    except OSError:
        return ''
    if b'\0' in raw:
        return ''
    content = raw.decode('utf-8', 'replace')
    ext = os.path.splitext(os.path.basename(rel))[1].lower()
    if ext == '.md':
        return _markdown(content)
    if ext in ('.desktop', '.service', '.timer'):
        m = re.search(r'^(?:Comment|Description)=(.+)$', content, re.M)
        if m:
            return text.short(m.group(1), 140)
    return _header_comment(content, ext)


def _markdown(content):
    _, body = vault.front(content)
    title, paragraph = '', []
    for line in body.splitlines():
        z = line.strip()
        if not title and z.startswith('# '):
            title = z[2:].strip()
            continue
        if paragraph and not z:
            break
        if z and not z.startswith(('#', '|', '!', '<', '```', '---', '>')) and not re.match(r'^[-*+] |^\d+\. ', z):
            paragraph.append(re.sub(r'[*_`]|\[\[?([^\]|]+)(?:\|[^\]]*)?\]\]?(?:\([^)]*\))?', r'\1', z))
    sentence = _first_sentence(' '.join(paragraph))
    return text.short(f'{title}: {sentence}' if title and sentence else title or sentence, 150)


def _header_comment(content, ext):
    marks = [z for z, endings in LINE_COMMENT.items() if ext in endings] or ['#', '//']
    lines, in_block, done = [], False, False
    for i, line in enumerate(content.splitlines()[:60]):
        z = line.strip()
        if in_block:
            end = '*/' in z
            z = z.split('*/')[0].lstrip('*').strip()
            if z:
                lines.append(z)
            if end:
                in_block = False
                done = bool(lines)
            continue
        if done and (not z or not z.startswith(tuple(marks) + ('/*',))):
            break
        if not z:
            if lines:
                done = True
            continue
        if z.startswith('/*'):
            in_block = '*/' not in z
            inner = z[2:].split('*/')[0].strip('* ').strip()
            if inner:
                lines.append(inner)
            continue
        if ext == '.py' and re.match(r'^[rRbBuU]?("""|\'\'\')', z) and not lines:
            return _docstring(content, i)
        if PREAMBLE.match(line) and not lines:
            continue
        comment = next((z[len(k):] for k in sorted(marks, key=len, reverse=True) if z.startswith(k)), None)
        if comment is None:
            if lines or i > 25:
                break
            continue
        comment = comment.strip().strip('-=*#~_/ ').strip()
        if not comment or LICENSE.search(comment):
            if lines and not comment:
                done = True
            continue
        if CODE.search(comment) and not lines:
            continue        # commented-out code
        lines.append(comment)
        if len(' '.join(lines)) > 220:
            break
    return text.short(_first_sentence(' '.join(lines)), 140)


def _docstring(content, start):
    m = re.search(r'("""|\'\'\')(.*?)(\1|$)', '\n'.join(content.splitlines()[start:]), re.S)
    if not m:
        return ''
    paragraph = m.group(2).strip().split('\n\n')[0]
    return text.short(_first_sentence(' '.join(paragraph.split())), 140)


def _first_sentence(content):
    # up to the first full stop, but not shorter than ~30 characters;
    # "z.B.", "e.g." and the like end no sentence
    for m in re.finditer(r'[.!?](\s|$)', content):
        if m.end() >= 30 and not ABBREVIATION.search(content[max(0, m.start() - 6):m.start() + 1]):
            return content[:m.end()].strip()
    return content.strip()


# ---- Topics from the docs ------------------------------------------------------------

def doc_topics(root, every):
    # -> {path: [(topic, score), ...]} best first
    suffixes = {}
    for p in every:
        parts = p.split('/')
        for i in range(len(parts)):
            suffixes.setdefault('/'.join(parts[i:]), []).append(p)
    topics_of = {}
    names = set()
    folded = [text.fold(p) for p in every]
    for doc in (p for p in every if DOCS.match(p)):
        content = vault.read(os.path.join(root, doc))
        m = re.search(r'^# (.+)$', content, re.M)
        topic = (m.group(1).strip() if m else os.path.splitext(os.path.basename(doc))[0])
        topic = re.sub(r'[`*_]', '', topic)[:60]
        if topic in names:
            topic += f' ({os.path.splitext(os.path.basename(doc))[0]})'
        names.add(topic)
        unique, ambiguous = {}, []
        for token in REF.findall(content):
            parts = token.lstrip('~./').split('/')
            for i in range(len(parts)):
                candidates = suffixes.get('/'.join(parts[i:]))
                if not candidates:
                    continue
                if len(candidates) == 1:
                    unique[candidates[0]] = unique.get(candidates[0], 0) + 1
                elif i == len(parts) - 1:
                    ambiguous.append(candidates)
                break
        # ambiguous names (shell.qml ...) only when the doc names their folder too
        folders = {os.path.dirname(p) for p in unique}
        for candidates in ambiguous:
            fitting = [k for k in candidates if os.path.dirname(k) in folders]
            if len(fitting) == 1:
                unique[fitting[0]] = unique.get(fitting[0], 0) + 1
        unique[doc] = unique.get(doc, 0) + 1000        # the doc itself
        # title words found in more than 10 % of all paths ("shell" in
        # quickshell/...) say nothing about belonging
        words = {w for w in text.terms(topic + ' ' + os.path.basename(doc)[:-3])
                 if len(w) >= 4 and sum(w in f for f in folded) < 0.1 * len(folded)}
        n = len(unique)
        overview = n > GENERIC or text.fold(os.path.basename(doc)[:-3]) in OVERVIEWS
        for path, mentions in unique.items():
            score = mentions / (1 + n / 25)
            base = text.fold(os.path.splitext(os.path.basename(path))[0])
            bonus = any(w in text.fold(path) for w in words) or (
                len(base) >= 5 and any(w.startswith(base) or base.startswith(w) for w in words))
            if overview and path != doc and not bonus:
                score = min(score, 0.05)        # overview (changelog ...): side topic only
            elif bonus:
                score += 3
            topics_of.setdefault(path, []).append((topic, score))
    for path in topics_of:
        topics_of[path].sort(key=lambda x: -x[1])
    return topics_of


def folder_inheritance(every, topics_of):
    # folder -> topic, when the docs give most mentioned files in it (and
    # below) one topic: atelier/shader/*.frag belong to the Atelier even if the
    # docs name only a few. From depth 2, so a top folder does not land
    # completely in the biggest topic.
    votes = {}
    for path, proposal in topics_of.items():
        if not proposal or proposal[0][1] < LEAST:
            continue
        parts = path.split('/')[:-1]
        for depth in range(2, len(parts) + 1):
            folder = '/'.join(parts[:depth])
            votes.setdefault(folder, {}).setdefault(proposal[0][0], 0)
            votes[folder][proposal[0][0]] += 1
    inherit = {}
    for folder in {os.path.dirname(p) for p in every}:
        parts = folder.split('/')
        # from the deepest folder upwards until one level is clear
        for depth in range(len(parts), 1, -1):
            v = votes.get('/'.join(parts[:depth]))
            if v:
                topic, n = max(v.items(), key=lambda x: x[1])
                if n >= 3 and n >= 0.4 * sum(v.values()):
                    inherit[folder] = topic
                    break
    return inherit


# ---- Make and keep up to date -----------------------------------------------------------

def make(project, root=None, fresh=False):
    # create a map or bring it in line with the repo -> short report
    lang = vault.lang()
    root = root or projects.root_of(project)
    if not root or not os.path.isdir(root):
        return i18n.t('map.no_root', lang, project=project)
    every = files_of(root)
    if len(every) > MOST:
        return i18n.t('map.too_big', lang, project=project, n=len(every))
    path = projects.map_file(project)
    old = {} if fresh else {p: (t, d) for t, entries in projects.read_map(path)[1].items() for p, d in entries}
    topics_of = doc_topics(root, every)
    topics, also = {}, {}
    new = 0
    inherit = folder_inheritance(every, topics_of)
    for p in every:
        proposal = topics_of.get(p, [])
        if p in old and (old[p][1] or not fresh):
            topic, description = old[p]
            if not description:
                description = describe(root, p)
        else:
            topic = proposal[0][0] if proposal and proposal[0][1] >= LEAST else None
            description = describe(root, p)
            new += 1
        if not topic:
            topic = inherit.get(os.path.dirname(p)) or (projects.next_topic(topics, p) if old
                                                         else projects.folder_topic(p))
        topics.setdefault(topic, []).append((p, description))
        more = [t for t, _ in proposal if t != topic][:4]
        if more:
            also[p] = '|'.join(more)
    removed = len(set(old) - set(every))
    # doc topics alphabetically, folders after them; the old map's order stays
    order = list(dict.fromkeys(t for t, _ in old.values())) if old else []
    for t in sorted(topics, key=lambda t: (projects.is_folder_topic(t), t.lower())):
        if t not in order:
            order.append(t)
    ordered = {t: sorted(topics[t], key=lambda e: e[0].lower()) for t in order if t in topics}
    with vault.lock('map'):
        projects.write_map(project, root, ordered)
        try:
            with store.transaction() as c:
                search.index_map(c, project, path, also)
                store.meta('map:' + project, os.path.getmtime(path))
        except store.NoIndex:
            pass
    from . import notes
    notes.project_note(project)
    write_overview()
    blank = sum(1 for e in ordered.values() for _, d in e if not d)
    return i18n.t('map.report', lang, project=project, files=len(every), topics=len(ordered), new=new,
                  removed=removed, blank=blank)


def refresh(project):
    # quick check after a session: new files in, deleted ones out
    root = projects.root_of(project)
    if not root:
        return
    every = set(files_of(root))
    _, topics = projects.read_map(projects.map_file(project))
    known = {p for entries in topics.values() for p, _ in entries}
    if every - known or known - every:
        make(project, root)


def set_entry(project, path, description=None, topic=None, only_new=False):
    # Add or change one entry. description None = keep it; only_new = leave
    # existing entries alone (hooks: a description set by hand or with
    # hub_map_update wins over the header comment).
    # -> (topic, description) as it now stands in the map
    root = projects.root_of(project)
    if not root:
        raise ValueError(i18n.t('map.unknown', project=project))
    with vault.lock('map'):
        _, topics = projects.read_map(projects.map_file(project))
        old_topic, old_text = None, ''
        for t, entries in topics.items():
            for i, (p, d) in enumerate(entries):
                if p == path:
                    if only_new:
                        return t, d
                    old_topic, old_text = t, d
                    del entries[i]
                    break
            if old_topic:
                break
        if not topic:
            topic = old_topic or projects.next_topic(topics, path)
        description = old_text if description is None else text.short(description, 160)
        topics.setdefault(topic, []).append((path, description))
        topics[topic].sort(key=lambda e: e[0].lower())
        projects.write_map(project, root, topics)
        # update the index right away and note the new mtime - otherwise the
        # next lookup would index the whole map again
        try:
            with store.transaction() as c:
                r = c.execute('SELECT also FROM files WHERE project=? AND path=?', (project, path)).fetchone()
                search.index_file(c, project, path, topic, description, r[0] if r else '')
                store.meta('map:' + project, os.path.getmtime(projects.map_file(project)))
        except store.NoIndex:
            pass
    return topic, description


def write_overview():
    # 00_Index/<Projects>.md: overview for Obsidian, rewritten every time
    try:
        c = store.db()
    except store.NoIndex:
        return
    lang = vault.lang()
    t = lambda key: i18n.t(key, lang)
    title = vault.layout('overview')
    lines = [f'# {title}', '', f'| {t("overview.project")} | {t("overview.map")} | {t("overview.files")} | '
             f'{t("overview.topics")} | {t("overview.sessions")} | {t("overview.last")} |', '|---|---|---|---|---|---|']
    for name, _ in sorted(projects.all_projects()):
        n, topics = c.execute('SELECT count(*), count(DISTINCT topic) FROM files WHERE project=?', (name,)).fetchone()
        s, last = c.execute('SELECT count(*), max(last) FROM sessions WHERE project=?', (name,)).fetchone()
        lines.append(f'| [[{name}]] | [[{name} MAP]] | {n} | {topics} | {s} | '
                     f'{vault.now(last, t("format.date")) if last else "–"} |')
    general = vault.general()
    without = c.execute('SELECT count(*) FROM sessions WHERE project=?', (general,)).fetchone()[0]
    if without:
        lines += ['', f'{t("overview.without")}: [[{general}]] ({without})']
    vault.write(os.path.join(vault.MAPS, title + '.md'), '\n'.join(lines) + '\n')


# ---- New projects ------------------------------------------------------------------------

OUTSIDE = ('.cache', '.local/share', '.local/state', '.claude', '.npm', '.cargo', '.rustup', 'go/pkg',
           'Library', 'AppData')


def git_root(path):
    p = system.resolve(path)
    if not os.path.isdir(p):
        p = os.path.dirname(p)
    while system.inside(p, system.HOME) and p != system.HOME:
        if os.path.exists(os.path.join(p, '.git')):
            return p
        p = os.path.dirname(p)
    return None


def project_for(path):
    # A known project - or a new one for a git repo in the home folder, as soon
    # as Claude creates or changes a file there. -> (project, rel)
    name, rel = projects.of(path)
    if name:
        return name, rel
    root = git_root(path)
    if not root or root == vault.ROOT:
        return None, path
    within = system.posix(os.path.relpath(root, system.HOME))
    if within.startswith(OUTSIDE) or system.inside(root, system.resolve(tempfile.gettempdir())):
        return None, path
    name = os.path.basename(root)
    if projects.name(name):
        name = f'{name} ({os.path.basename(os.path.dirname(root))})'
    make(name, root)
    projects.reload()
    return projects.of(path)


def add_project(root, name=None):
    # "codehub add <folder>": map any folder, git repo or not
    root = system.resolve(root)
    if not os.path.isdir(root):
        raise ValueError(i18n.t('map.no_folder', path=root))
    name = name or os.path.basename(root)
    report = make(name, root)
    projects.reload()
    return report
