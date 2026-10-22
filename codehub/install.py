# Setting Code Hub up for Claude Code, and removing it again: vault, import
# of recent sessions (projects come with them), hooks in
# ~/.claude/settings.json, the MCP server (user scope), permission for the
# hub's tools and a short section in ~/.claude/CLAUDE.md. Every step can be
# repeated; entries of other programs stay untouched.
import json
import os
import re
import shutil
import subprocess

from . import i18n, system, vault

SETTINGS = os.path.join(system.claude_dir(), 'settings.json')
RULES = os.path.join(system.claude_dir(), 'CLAUDE.md')
# our hooks, also those of the first version (hook.py, or any command
# starting its "py" wrapper - one copy of settings.json had a broken one)
MARK = re.compile(r'codehub["\']?\s+hook\s|CodeHub/hook\.py|codehub/hook\.py|/CodeHub/py["\']?\s')
# synchronous because they return context or must run before exit;
# all others are async and never hold Claude up
SYNC = {'SessionStart': 10, 'UserPromptSubmit': 10, 'SessionEnd': 10}
ASYNC = ('PreToolUse', 'PostToolUse', 'PostToolUseFailure', 'SubagentStart', 'SubagentStop', 'Stop',
         'Notification', 'PreCompact', 'PostCompact')
TOOL_EVENTS = ('PreToolUse', 'PostToolUse', 'PostToolUseFailure')
PERMISSION = 'mcp__codehub'
RULES_START, RULES_END = '<!-- codehub:start -->', '<!-- codehub:end -->'


def _shell_word(path):
    # quoted for the shell Claude Code runs hooks in; $HOME keeps the
    # settings valid when the home folder moves (new machine, USB stick)
    path = path.replace('\\', '/')
    home = system.HOME.replace('\\', '/')
    if not system.WINDOWS and (path == home or path.startswith(home + '/')):
        path = '$HOME' + path[len(home):]
    return f'"{path}"'


def hook_command(event):
    words = [_shell_word(p) if os.path.isabs(p) else p for p in system.command()]
    return ' '.join(words + ['hook', event])


def read_settings():
    try:
        with open(SETTINGS, encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def write_settings(d):
    backup = SETTINGS + '.before-codehub'
    if os.path.exists(SETTINGS) and not os.path.exists(backup):
        shutil.copy2(SETTINGS, backup)
    vault.write(SETTINGS, json.dumps(d, indent=2, ensure_ascii=False) + '\n')


def installed():
    try:
        d = read_settings()
    except (OSError, ValueError):
        return False
    return any(MARK.search(h.get('command', '')) for groups in (d.get('hooks') or {}).values()
               for g in groups for h in g.get('hooks', []))


def hooks_out(d):
    hooks = d.get('hooks') or {}
    for event in list(hooks):
        groups = hooks[event]
        for g in groups:
            g['hooks'] = [h for h in g.get('hooks', []) if not MARK.search(h.get('command', ''))]
        hooks[event] = [g for g in groups if g.get('hooks')]
        if not hooks[event]:
            del hooks[event]
    if 'hooks' in d and not d['hooks']:
        del d['hooks']


def hooks_in(d):
    hooks_out(d)        # repeating = updating
    hooks = d.setdefault('hooks', {})
    for event in (*SYNC, *ASYNC):
        h = {'type': 'command', 'command': hook_command(event), 'timeout': SYNC.get(event, 30)}
        if event not in SYNC:
            h['async'] = True
        group = {'matcher': '*', 'hooks': [h]} if event in TOOL_EVENTS else {'hooks': [h]}
        hooks.setdefault(event, []).append(group)


def permission(d, on):
    allowed = d.setdefault('permissions', {}).setdefault('allow', [])
    if on and PERMISSION not in allowed:
        allowed.append(PERMISSION)
    if not on:
        d['permissions']['allow'] = [e for e in allowed if e != PERMISSION]
        if not d['permissions']['allow']:
            del d['permissions']['allow']
        if not d['permissions']:
            del d['permissions']


def claude_cli():
    found = shutil.which('claude')
    if found:
        return found
    for candidate in (os.path.join(system.HOME, '.local', 'bin', 'claude'),
                      os.path.join(system.HOME, '.claude', 'local', 'claude')):
        if os.access(candidate, os.X_OK):
            return candidate
    return None


def mcp(on, say):
    claude = claude_cli()
    if not claude:
        say('! ' + i18n.t('install.no_claude', command=' '.join(system.command()) + ' mcp'))
        return False
    subprocess.run([claude, 'mcp', 'remove', 'codehub', '-s', 'user'], capture_output=True)
    if not on:
        return True
    r = subprocess.run([claude, 'mcp', 'add', '--scope', 'user', 'codehub', '--', *system.command(), 'mcp'],
                       capture_output=True, text=True)
    if r.returncode != 0:
        say('! claude mcp add: ' + (r.stderr or r.stdout).strip()[:300])
    return r.returncode == 0


def rules(on):
    content = vault.read(RULES)
    if RULES_START in content and RULES_END in content:
        before, rest = content.split(RULES_START, 1)
        content = before.rstrip('\n') + rest.split(RULES_END, 1)[1]
    content = content.rstrip('\n') + '\n' if content.strip() else ''
    if on:
        section = vault.read(os.path.join(system.PACKAGE, 'templates', 'claude.md')).strip()
        content += ('\n' if content else '') + section.replace('{vault}', system.tilde(vault.ROOT)) + '\n'
    vault.write(RULES, content)


def install(language=None, days=30, say=print):
    from . import maps, search, sessions, store
    say(i18n.t('install.title'))
    vault.create(language)
    say('✓ ' + i18n.t('install.vault', path=system.tilde(vault.ROOT)))
    if not store.meta('import'):
        say('… ' + i18n.t('install.importing', days=days))
        n = sessions.import_recent(days, report=lambda line: None)
        say('✓ ' + i18n.t('install.imported', n=n))
    search.update()
    maps.write_overview()
    say('✓ ' + i18n.t('install.index'))
    d = read_settings()
    hooks_in(d)
    permission(d, True)
    write_settings(d)
    say('✓ ' + i18n.t('install.hooks', path=system.tilde(SETTINGS)))
    if mcp(True, say):
        say('✓ ' + i18n.t('install.mcp'))
    rules(True)
    say('✓ ' + i18n.t('install.rules', path=system.tilde(RULES)))
    vault.backup(i18n.t('install.commit', vault.lang()), push=False)
    say('\n' + i18n.t('install.done'))


def uninstall(say=print):
    say(i18n.t('uninstall.title'))
    d = read_settings()
    hooks_out(d)
    permission(d, False)
    write_settings(d)
    say('✓ ' + i18n.t('uninstall.hooks'))
    if mcp(False, say):
        say('✓ ' + i18n.t('uninstall.mcp'))
    rules(False)
    say('✓ ' + i18n.t('uninstall.rules'))
