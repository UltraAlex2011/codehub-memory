# The vault: a folder of Markdown files (also an Obsidian vault and a git
# repo) that is the source of truth. Folder names and frontmatter keys follow
# the vault's language, fixed when it is created (codehub.json in the vault);
# reading understands every language, so a vault never breaks.
#
#   00_Index/          one "<project> MAP.md" per project, Projects overview
#   01_Projects/<p>/   project note, decisions, bugs, notes, sessions
#   02_Code_Library/   snippets
#   03_Logs/           raw events per day (JSONL, local only)
#   04_Own/            belongs to the user - Code Hub never writes there
#   .hub/              index and state (SQLite, local only, rebuildable)
import json
import os
import re
import subprocess
import time

from . import config, system

LAYOUTS = {
    'en': {'own': '04_Own', 'note': 'Notes', 'decision': 'Decisions', 'bug': 'Bugs', 'session': 'Sessions',
           'architecture': 'Architecture', 'open': 'Open', 'general': 'General', 'folder': 'Folder',
           'overview': 'Projects', 'own_readme': 'Read me.md'},
    'de': {'own': '04_Eigenes', 'note': 'Notizen', 'decision': 'Entscheidungen', 'bug': 'Bugs',
           'session': 'Sitzungen', 'architecture': 'Architektur', 'open': 'Offen', 'general': 'Allgemein',
           'folder': 'Ordner', 'overview': 'Projekte', 'own_readme': 'Lies mich.md'},
}
# Frontmatter: canonical (English) key -> key in the vault's language
FIELDS = {'de': {'project': 'projekt', 'root': 'wurzel', 'updated': 'stand', 'kind': 'art', 'created': 'erstellt',
                 'modified': 'geaendert', 'source': 'quelle', 'session': 'sitzung', 'end': 'ende'}}
KIND_NAMES = {'de': {'note': 'notiz', 'decision': 'entscheidung', 'architecture': 'architektur', 'open': 'offen',
                     'session': 'sitzung', 'project': 'projekt', 'map': 'karte'}}
# Every spelling hub_note accepts -> canonical kind
KINDS = {'note': 'note', 'notiz': 'note', 'decision': 'decision', 'adr': 'decision', 'entscheidung': 'decision',
         'bug': 'bug', 'fix': 'bug', 'snippet': 'snippet', 'architecture': 'architecture',
         'architektur': 'architecture', 'open': 'open', 'todo': 'open', 'offen': 'open',
         'session': 'session', 'sitzung': 'session'}
NOTE_KINDS = ('note', 'decision', 'bug', 'snippet', 'architecture', 'open')
COLLECTED = ('architecture', 'open')        # one note per project, one section per title

_FIELDS_BACK = {v: k for d in FIELDS.values() for k, v in d.items()}
_KINDS_BACK = {v: k for d in KIND_NAMES.values() for k, v in d.items()}

ROOT = INTERNAL = MAPS = PROJECTS = LIBRARY = LOGS = OWN = ''
LANG = None


def configure(root=None):
    # Vault location: argument, CODEHUB_VAULT, config, ~/CodeHub
    global ROOT, INTERNAL, MAPS, PROJECTS, LIBRARY, LOGS, LANG, OWN
    root = root or os.environ.get('CODEHUB_VAULT') or config.get('vault') or os.path.join(system.HOME, 'CodeHub')
    ROOT = system.resolve(root)
    INTERNAL = os.path.join(ROOT, '.hub')
    MAPS = os.path.join(ROOT, '00_Index')
    PROJECTS = os.path.join(ROOT, '01_Projects')
    LIBRARY = os.path.join(ROOT, '02_Code_Library')
    LOGS = os.path.join(ROOT, '03_Logs')
    LANG = _vault_language()
    OWN = os.path.join(ROOT, layout('own'))


def _vault_language():
    lang = _settings().get('language')
    if lang in LAYOUTS:
        return lang
    if os.path.isdir(os.path.join(ROOT, LAYOUTS['de']['own'])):
        return 'de'
    if os.path.isdir(os.path.join(ROOT, LAYOUTS['en']['own'])):
        return 'en'
    return None


def _settings():
    try:
        with open(os.path.join(ROOT, 'codehub.json'), encoding='utf-8') as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def lang():
    # Language for anything written into the vault
    if LANG:
        return LANG
    from . import i18n
    return i18n.language()


def layout(name):
    return LAYOUTS[lang()][name]


def general():
    # project name for sessions and notes without a project
    return layout('general')


def is_ready():
    return os.path.isdir(INTERNAL)


# ---- Files ---------------------------------------------------------------------------

def read(path, n=None):
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            return f.read() if n is None else f.read(n)
    except OSError:
        return ''


def write(path, text):
    # atomic: readers never see half a file
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f'{path}.{os.getpid()}.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    os.replace(tmp, path)


def lock(name):
    # Several sessions and hooks write at once - maps, status and git one at a time
    return system.file_lock(os.path.join(INTERNAL, name + '.lock'))


def rel(path):
    return system.posix(os.path.relpath(path, ROOT))


def now(t=None, form='%Y-%m-%d %H:%M'):
    return time.strftime(form, time.localtime(time.time() if t is None else t))


def today():
    return now(None, '%Y-%m-%d')


# ---- Frontmatter ----------------------------------------------------------------------

def front(text):
    # Small YAML subset ("key: value", lists as [a, b]) -> canonical keys and kinds
    if not text.startswith('---\n'):
        return {}, text
    end = text.find('\n---', 4)
    if end < 0:
        return {}, text
    head = {}
    for line in text[4:end].splitlines():
        if ':' in line and not line.startswith((' ', '-')):
            k, v = line.split(':', 1)
            v = v.strip()
            if v.startswith('[') and v.endswith(']'):
                v = [x.strip().strip('"\'') for x in v[1:-1].split(',') if x.strip()]
            head[_FIELDS_BACK.get(k.strip(), k.strip())] = v
    if isinstance(head.get('kind'), str):
        head['kind'] = _KINDS_BACK.get(head['kind'], head['kind'])
    rest = text[end + 4:]
    return head, rest[1:] if rest.startswith('\n') else rest


def front_text(head):
    # canonical keys -> the vault's language
    fields, kinds = FIELDS.get(lang(), {}), KIND_NAMES.get(lang(), {})
    lines = ['---']
    for k, v in head.items():
        if k == 'kind':
            v = kinds.get(v, v)
        if isinstance(v, (list, tuple)):
            v = '[' + ', '.join(str(x) for x in v) + ']'
        lines.append(f'{fields.get(k, k)}: {v}')
    return '\n'.join(lines + ['---', ''])


# ---- Create and back up ----------------------------------------------------------------

GITIGNORE = '''# Code Hub: index, locks and raw events stay local
.hub/
03_Logs/
.obsidian/workspace*.json
.obsidian/cache
.trash/
'''


def create(language=None):
    # An existing vault keeps its language; a new one gets the chosen one
    global LANG
    LANG = LANG or (language if language in LAYOUTS else lang())
    settings = os.path.join(ROOT, 'codehub.json')
    if not os.path.exists(settings):
        write(settings, json.dumps({'language': LANG}, indent=2) + '\n')
    configure(ROOT)
    for folder in (MAPS, PROJECTS, LIBRARY, LOGS, INTERNAL, OWN, os.path.join(ROOT, '.obsidian')):
        os.makedirs(folder, exist_ok=True)
    templates = os.path.join(system.PACKAGE, 'templates', LANG)
    for folder, _, names in os.walk(templates):
        for name in names:
            source = os.path.join(folder, name)
            target = os.path.join(ROOT, os.path.relpath(source, templates))
            if not os.path.exists(target):
                write(target, read(source))
    if not os.path.exists(os.path.join(ROOT, '.gitignore')):
        write(os.path.join(ROOT, '.gitignore'), GITIGNORE)
    app = os.path.join(ROOT, '.obsidian', 'app.json')
    if not os.path.exists(app):
        write(app, json.dumps({'userIgnoreFilters': ['03_Logs/'], 'showUnsupportedFiles': False}, indent=2))
    if not os.path.isdir(os.path.join(ROOT, '.git')):
        try:
            subprocess.run(['git', 'init', '-q', '-b', 'main', ROOT], capture_output=True)
        except OSError:
            pass            # without git there is no history, everything else works
    register_obsidian(ROOT)


def register_obsidian(path):
    # make the vault show up in Obsidian's vault list (only if Obsidian is installed)
    target = system.obsidian_config()
    try:
        with open(target, encoding='utf-8') as f:
            d = json.load(f)
    except (OSError, ValueError):
        return False
    vaults = d.setdefault('vaults', {})
    if any(v.get('path') == path for v in vaults.values()):
        return True
    vaults[os.urandom(8).hex()] = {'path': path, 'ts': int(time.time() * 1000)}
    write(target, json.dumps(d))
    return True


def git(*args, timeout=30, env=None):
    return subprocess.run(['git', '-C', ROOT, *args], capture_output=True, text=True, timeout=timeout,
                          stdin=subprocess.DEVNULL, env=env)


def _identity():
    # the user's own git identity; without one a neutral author
    if git('config', 'user.email').stdout.strip():
        return []
    return ['-c', 'user.name=Code Hub', '-c', 'user.email=codehub@localhost']


def backup(message, push=True):
    # Commit the vault (only when something changed) and push if a remote exists
    if not os.path.isdir(os.path.join(ROOT, '.git')):
        return False
    try:
        with lock('git'):
            git('add', '-A')
            if not git('status', '--porcelain').stdout.strip():
                return False
            git(*_identity(), 'commit', '-q', '-m', message)
            if push and config.get('push') and git('remote').stdout.strip():
                env = dict(os.environ, GIT_SSH_COMMAND='ssh -o BatchMode=yes -o ConnectTimeout=10',
                           GIT_TERMINAL_PROMPT='0')
                r = git('push', '-q', 'origin', 'HEAD', timeout=60, env=env)
                from . import store
                store.meta('push', f'{int(time.time())} {"ok" if r.returncode == 0 else r.stderr.strip()[:120]}')
        return True
    except Exception:       # a failed backup must never break a hook or the session
        return False


def is_own(path):
    return system.inside(system.resolve(path), OWN)


SESSION_FOLDERS = re.compile(r'(^|/)(' + '|'.join(re.escape(d['session']) for d in LAYOUTS.values()) + ')/')


configure()
