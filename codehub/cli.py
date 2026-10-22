# Command line: "codehub <command>". Hooks, MCP server and the Quickshell
# bridge use the same entry, so there is one way to start everything.
import sys
import time

from . import VERSION, config, i18n, system, vault


def _ask(question, default, choices=None):
    # only when a person sits at the terminal; otherwise the default
    if not sys.stdin.isatty():
        return default
    while True:
        answer = input(f'{question} [{default}]: ').strip() or default
        if not choices or answer in choices:
            return answer


def _option(args, name, default=None):
    if name in args:
        i = args.index(name)
        if i + 1 < len(args):
            value = args[i + 1]
            del args[i:i + 2]
            return value
    return default


def _flag(args, name):
    if name in args:
        args.remove(name)
        return True
    return False


def cmd_install(args):
    from . import install
    lang = _option(args, '--lang')
    days = _option(args, '--days')
    path = _option(args, '--vault')
    if not lang and not vault.LANG:
        lang = _ask(i18n.t('install.ask_language'), i18n.system_language(), i18n.LANGUAGES)
    if lang:
        i18n.use(lang)
    if not path and not vault.is_ready():
        path = _ask(i18n.t('install.ask_vault'), system.tilde(vault.ROOT))
    if path and system.resolve(path) != vault.ROOT:
        config.put('vault', system.resolve(path))
        vault.configure(system.resolve(path))
    if lang:
        config.put('language', lang)
    install.install(lang, int(days or 30))
    return 0


def cmd_uninstall(args):
    from . import install
    install.uninstall()
    return 0


def _need_vault():
    if not vault.is_ready():
        print(i18n.t('cli.no_vault'), file=sys.stderr)
        sys.exit(1)


def cmd_lookup(args):
    from . import search
    _need_vault()
    project = _option(args, '--project')
    print(search.lookup(' '.join(args), project)[0])
    return 0


def cmd_search(args):
    from . import search
    _need_vault()
    print(search.fulltext(' '.join(args)))
    return 0


def cmd_add(args):
    from . import maps
    _need_vault()
    name = _option(args, '--name')
    if not args:
        print(i18n.t('cli.add_usage'), file=sys.stderr)
        return 2
    print(maps.add_project(args[0], name))
    return 0


def cmd_map(args):
    from . import maps, projects, search
    _need_vault()
    fresh = _flag(args, '--fresh')
    if args:
        project = projects.name(args[0]) or args[0]
        print(maps.make(project, system.resolve(args[1]) if len(args) > 1 else None, fresh=fresh))
    else:
        for name, root in projects.all_projects():
            print(maps.make(name, root, fresh=fresh))
    search.update()
    return 0


def cmd_index(args):
    from . import search, store
    _need_vault()
    search.update(rebuild=_flag(args, '--rebuild'))
    c = store.db()
    print(i18n.t('cli.index', files=c.execute('SELECT count(*) FROM files').fetchone()[0],
                 notes=c.execute('SELECT count(*) FROM notes').fetchone()[0], fts=store.FTS))
    return 0


def cmd_import(args):
    from . import sessions
    _need_vault()
    n = sessions.import_recent(int(_option(args, '--days', 30)))
    print(i18n.t('install.imported', n=n))
    return 0


def cmd_tokens(args):
    from . import tokens
    _need_vault()
    c = tokens.connect()
    tokens.scan(c)
    o = tokens.overview(c)
    for key in ('today', 'week', 'month', 'total'):
        s = o[key]
        print(f'{i18n.t("tokens." + key):10} {tokens.number(s["tokens"]):>9}  '
              + i18n.t('cli.tokens_line', cache=tokens.number(s['cache']), answers=s['answers']))
    if o['since']:
        print(i18n.t('cli.tokens_since', day=o['since']))
    return 0


def cmd_stats(args):
    from . import store
    _need_vault()
    c = store.db()
    since = vault.now(time.time() - 6 * 86400, '%Y-%m-%d')
    n = dict(c.execute('SELECT kind, sum(n) FROM counters WHERE day>=? GROUP BY kind', (since,)).fetchall())
    asked = n.get('lookup', 0) + n.get('auto', 0) + n.get('search', 0)
    free = n.get('free', 0)
    reads, hits = n.get('read', 0), n.get('hit', 0)
    print(i18n.t('cli.stats_title'))
    print(i18n.t('cli.stats_asked', asked=asked, free=free,
                 share=f'{100 * asked / (asked + free):.0f}' if asked + free else '–'))
    print(i18n.t('cli.stats_hits', hits=hits, reads=reads,
                 share=f'{100 * hits / reads:.0f}' if reads else '–'))
    return 0


def cmd_doctor(args):
    import subprocess
    from . import install, store
    ok = True

    def line(good, text):
        nonlocal ok
        ok = ok and good
        print(('✓ ' if good else '✗ ') + text)

    line(sys.version_info >= (3, 9), f'Python {sys.version.split()[0]} ({system.python()})')
    line(vault.is_ready(), i18n.t('doctor.vault', path=system.tilde(vault.ROOT)))
    if vault.is_ready():
        try:
            store.db()
            line(True, i18n.t('doctor.index', fts=store.FTS))
        except store.NoIndex as e:
            line(False, i18n.t('doctor.no_index', error=e))
    line(install.installed(), i18n.t('doctor.hooks'))
    claude = install.claude_cli()
    if claude:
        r = subprocess.run([claude, 'mcp', 'get', 'codehub'], capture_output=True, text=True)
        line(r.returncode == 0, i18n.t('doctor.mcp'))
    else:
        line(False, i18n.t('doctor.no_claude'))
    from . import events
    last = events.recent(1)
    if last:
        print('  ' + i18n.t('doctor.last_event', when=vault.now(last[-1]['t'], i18n.t('format.datetime'))))
    print('  ' + i18n.t('doctor.language', language=i18n.language()))
    return 0 if ok else 1


def cmd_config(args):
    if not args:
        for k, v in config.all_settings().items():
            print(f'{k} = {v!r}')
        return 0
    if len(args) == 1:
        print(repr(config.get(args[0])))
        return 0
    value = args[1]
    low = value.lower()
    parsed = True if low in ('true', 'on', 'yes', 'ja') else False if low in ('false', 'off', 'no', 'nein') else \
        int(value) if value.isdigit() else value
    config.put(args[0], parsed)
    return 0


def cmd_remote(args):
    _need_vault()
    if not args:
        print(vault.git('remote', 'get-url', 'origin').stdout.strip() or i18n.t('cli.no_remote'))
        return 0
    if vault.git('remote').stdout.strip():
        vault.git('remote', 'set-url', 'origin', args[0])
    else:
        vault.git('remote', 'add', 'origin', args[0])
    print(i18n.t('cli.remote_set', url=args[0]))
    return 0


def cmd_open(args):
    from . import server
    _need_vault()
    return server.open_view()


def cmd_serve(args):
    from . import server
    _need_vault()
    quiet = _flag(args, '--quiet')
    server.serve(_option(args, '--port'), quiet)
    return 0


def cmd_bench(args):
    from . import premium
    _need_vault()
    m = premium.module()
    if not m:
        print(i18n.t('premium.needed', feature='codehub bench'))
        return 1
    from codehub_premium import bench
    return bench.main(args)


def cmd_premium(args):
    # codehub premium                  status and where to buy
    # codehub premium <key> [zip]      activate, install the package (zip or Downloads)
    # codehub premium remove           give the activation back
    from . import license, premium
    if not args:
        s = license.status()
        if s['active']:
            print(i18n.t('premium.active', email=s['email'] or '–', key=s['key'], version=premium.version() or '–'))
            if not premium.installed():
                print(i18n.t('premium.no_package'))
        else:
            print(i18n.t('premium.offer', price=license.shop()['price']))
            _shops(print)
        return 0
    if args[0] == 'remove':
        premium.remove()
        print(i18n.t('premium.removed'))
        return 0
    key = args[1] if args[0] == 'activate' and len(args) > 1 else args[0]
    zip_path = next((a for a in args if a.lower().endswith('.zip')), None)
    try:
        state = license.activate(key)
    except license.Problem as e:
        print(i18n.t('premium.failed', error=e), file=sys.stderr)
        return 1
    except ConnectionError as e:
        print(i18n.t('premium.offline', error=e), file=sys.stderr)
        return 1
    print(i18n.t('premium.activated', email=state.get('email') or '–'))
    zip_path = zip_path or premium.find_download()
    if zip_path:
        try:
            print(i18n.t('premium.installed', version=premium.install_file(zip_path)))
        except (premium.Problem, OSError) as e:
            print(i18n.t('premium.failed', error=e), file=sys.stderr)
            return 1
    elif not premium.installed():
        print(i18n.t('premium.no_package'))
    return 0


def _shops(say):
    from . import license
    conf = license.shop()
    links = [('Lemon Squeezy', conf['lemonsqueezy'].get('checkout')), ('Gumroad', conf['gumroad'].get('url'))]
    links = [(name, url) for name, url in links if url]
    for name, url in links:
        say(f'  {name}: {url}')
    if not links:
        say('  ' + i18n.t('premium.soon', site=conf['site']))


def cmd_buy(args):
    from . import license
    system.open_external(license.shop()['site'] + '#pricing')
    _shops(print)
    return 0


def cmd_update(args):
    from . import update
    return update.run()


# ---- used by Claude Code and the views, not by people ----

def cmd_hook(args):
    from . import hooks
    hooks.run(args[0] if args else '')
    return 0


def cmd_mcp(args):
    from . import mcp
    mcp.main()
    return 0


def cmd_bridge(args):
    from . import bridge
    bridge.run()
    return 0


def cmd_close(args):
    from . import sessions
    if args and vault.is_ready():
        sessions.close(args[0])
    return 0


def cmd_tidy(args):
    from . import sessions
    if vault.is_ready():
        sessions.tidy()
    return 0


COMMANDS = {
    'install': cmd_install, 'uninstall': cmd_uninstall, 'open': cmd_open, 'serve': cmd_serve,
    'lookup': cmd_lookup, 'search': cmd_search, 'add': cmd_add, 'map': cmd_map, 'index': cmd_index,
    'import': cmd_import, 'tokens': cmd_tokens, 'stats': cmd_stats, 'bench': cmd_bench, 'doctor': cmd_doctor,
    'config': cmd_config, 'remote': cmd_remote, 'premium': cmd_premium, 'buy': cmd_buy, 'update': cmd_update,
    'hook': cmd_hook, 'mcp': cmd_mcp, 'bridge': cmd_bridge, 'close': cmd_close, 'tidy': cmd_tidy,
}
HIDDEN = ('hook', 'mcp', 'bridge', 'close', 'tidy')


def usage():
    print(f'Code Hub {VERSION}\n')
    print(i18n.t('cli.usage'))
    for name in COMMANDS:
        if name not in HIDDEN:
            print(f'  codehub {name:10} {i18n.t("cli.help." + name)}')


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    vault_path = _option(args, '--vault') if args and args[0] != 'install' else None
    if vault_path:
        vault.configure(vault_path)
    if not args or args[0] in ('-h', '--help', 'help'):
        usage()
        return 0
    if args[0] in ('-V', '--version', 'version'):
        print(VERSION)
        return 0
    command = COMMANDS.get(args[0])
    if not command:
        print(i18n.t('cli.unknown', command=args[0]), file=sys.stderr)
        usage()
        return 2
    return command(args[1:]) or 0
