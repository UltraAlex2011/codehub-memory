# Tests of the core, standard library only:  python -m unittest discover tests
# Every test works in its own temporary home folder and vault; nothing of
# the real setup is read or changed.
import importlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, ROOT)


def fresh(home, lang='en'):
    # (re)load the package against a temporary home and vault
    os.environ.update(HOME=home, CODEHUB_VAULT=os.path.join(home, 'CodeHub'), XDG_CONFIG_HOME=os.path.join(home, '.config'),
                      XDG_DATA_HOME=os.path.join(home, '.local', 'share'),
                      XDG_RUNTIME_DIR=os.path.join(home, 'run'), CLAUDE_CONFIG_DIR=os.path.join(home, '.claude'),
                      TMPDIR=os.path.join(home, 'tmp'), LANG='de_DE.UTF-8' if lang == 'de' else 'en_US.UTF-8')
    for d in ('run', 'tmp', '.claude/projects'):
        os.makedirs(os.path.join(home, d), exist_ok=True)
    for name in sorted(m for m in sys.modules if m == 'codehub' or m.startswith('codehub.')):
        del sys.modules[name]
    import codehub.vault as vault
    vault.create(lang)
    return importlib.import_module('codehub')


def project(home, name='shop'):
    root = os.path.join(home, 'code', name)
    os.makedirs(os.path.join(root, 'src'), exist_ok=True)
    os.makedirs(os.path.join(root, 'docs'), exist_ok=True)
    subprocess.run(['git', 'init', '-q', root], check=True)
    files = {'docs/checkout.md': '# Checkout\n\nThe cart lives in `src/cart.py`, payment in `src/payment.py`.\n',
             'src/cart.py': '# Shopping cart: items, quantities and the total price.\nx = 1\n',
             'src/payment.py': '# Payment: charges the card and retries twice.\ny = 2\n',
             'src/login.py': '"""Login form: checks e-mail and password."""\n'}
    for rel, content in files.items():
        with open(os.path.join(root, rel), 'w') as f:
            f.write(content)
    return root


class Base(unittest.TestCase):
    lang = 'en'

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = self.tmp.name
        self.saved = dict(os.environ)
        fresh(self.home, self.lang)

    def tearDown(self):
        from codehub import store
        store.close()
        os.environ.clear()
        os.environ.update(self.saved)
        self.tmp.cleanup()


class Text(unittest.TestCase):
    def test_terms(self):
        from codehub import text
        self.assertEqual(text.terms('Die Farben im DeskCava.qml'), ['farb', 'deskcava', 'desk', 'cava', 'qml'])
        self.assertEqual(text.terms('please make the login'), ['login'])
        self.assertEqual(text.fold('Größe'), 'groesse')

    def test_file_name(self):
        from codehub import text
        self.assertEqual(text.file_name('a/b: [c]?'), 'a b c')
        self.assertEqual(text.file_name('   '), 'Untitled')


class Vault(Base):
    def test_front_roundtrip_english(self):
        from codehub import vault
        head = {'project': 'shop', 'kind': 'decision', 'tags': ['a', 'b']}
        self.assertEqual(vault.front(vault.front_text(head) + '# x\n')[0], head)

    def test_layout_english(self):
        from codehub import vault
        self.assertTrue(os.path.isdir(os.path.join(vault.ROOT, '04_Own')))
        self.assertEqual(vault.general(), 'General')


class VaultGerman(Base):
    lang = 'de'

    def test_front_german_keys(self):
        from codehub import vault
        content = vault.front_text({'project': 'shop', 'kind': 'decision'})
        self.assertIn('projekt: shop', content)
        self.assertIn('art: entscheidung', content)
        self.assertEqual(vault.front(content)[0], {'project': 'shop', 'kind': 'decision'})
        self.assertEqual(vault.general(), 'Allgemein')


class Maps(Base):
    def test_map_and_lookup(self):
        from codehub import maps, projects, search
        root = project(self.home)
        report = maps.add_project(root)
        self.assertIn('4', report)
        _, topics = projects.read_map(projects.map_file('shop'))
        self.assertIn('src/cart.py', [p for p, _ in topics['Checkout']])
        answer, paths = search.lookup('shopping cart total')
        self.assertIn('src/cart.py — Shopping cart', answer)
        self.assertEqual(paths[0], os.path.join(root, 'src', 'cart.py'))

    def test_map_entry_survives_regeneration(self):
        from codehub import maps, projects
        root = project(self.home)
        maps.add_project(root)
        maps.set_entry('shop', 'src/login.py', 'Hand-written description', 'Auth')
        maps.make('shop', root)
        _, topics = projects.read_map(projects.map_file('shop'))
        self.assertEqual(topics['Auth'], [('src/login.py', 'Hand-written description')])

    def test_rebuild_keeps_side_topics(self):
        from codehub import maps, search, store
        maps.add_project(project(self.home))
        store.db().execute("UPDATE files SET also='Extra' WHERE path='src/cart.py'")
        search.update(rebuild=True)
        self.assertEqual(store.db().execute("SELECT also FROM files WHERE path='src/cart.py'").fetchone()[0], 'Extra')

    def test_half_built_project_list_is_never_seen(self):
        # the index must not drop files while another thread builds the list
        from codehub import maps, projects
        maps.add_project(project(self.home))
        projects.reload()
        seen = projects.all_projects()
        self.assertEqual(len(seen), 1)
        self.assertIs(projects.all_projects(), seen)


class Notes(Base):
    def test_note_and_fulltext(self):
        from codehub import notes, search
        rel = notes.save('shop', 'Retries in payment', 'Two retries with backoff.', 'decision', ['payment'])
        self.assertTrue(rel.startswith('01_Projects/shop/Decisions/'))
        self.assertIn('Two retries', search.fulltext('backoff'))

    def test_collected_sections(self):
        from codehub import notes, vault
        notes.save('shop', 'Cache', 'first', 'open')
        rel = notes.save('shop', 'Cache', 'second', 'open')
        content = vault.read(os.path.join(vault.ROOT, rel))
        self.assertIn('second', content)
        self.assertNotIn('first', content)


class Mcp(Base):
    def test_protocol(self):
        from codehub import maps, mcp
        maps.add_project(project(self.home))
        self.assertEqual(mcp.handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})['result']['tools'][0]['name'],
                         'hub_lookup')
        r = mcp.handle({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call',
                        'params': {'name': 'hub_lookup', 'arguments': {'query': 'payment card'}}})
        self.assertIn('src/payment.py', r['result']['content'][0]['text'])
        self.assertIsNone(mcp.handle({'jsonrpc': '2.0', 'method': 'notifications/initialized'}))
        self.assertEqual(mcp.handle({'jsonrpc': '2.0', 'id': 3, 'method': 'nope'})['error']['code'], -32601)


class Install(Base):
    def test_hooks_idempotent_and_foreign_kept(self):
        from codehub import install
        d = {'hooks': {'PreToolUse': [{'matcher': 'x', 'hooks': [{'type': 'command', 'command': 'other-tool'}]},
                                      {'hooks': [{'type': 'command', 'command': '"$HOME/Programme/CodeHub/py" ... broken'}]}]}}
        install.hooks_in(d)
        install.hooks_in(d)
        commands = [h['command'] for gs in d['hooks'].values() for g in gs for h in g['hooks']]
        self.assertEqual(len([c for c in commands if ' hook ' in c]), 12)
        self.assertIn('other-tool', commands)
        self.assertFalse(any('broken' in c for c in commands))
        install.hooks_out(d)
        self.assertEqual([h['command'] for gs in d['hooks'].values() for g in gs for h in g['hooks']], ['other-tool'])

    def test_rules_section(self):
        from codehub import install, vault
        vault.write(install.RULES, '# Mine\n')
        install.rules(True)
        install.rules(True)
        content = vault.read(install.RULES)
        self.assertEqual(content.count('codehub:start'), 1)
        self.assertTrue(content.startswith('# Mine'))
        install.rules(False)
        self.assertEqual(vault.read(install.RULES), '# Mine\n')


class Migration(Base):
    lang = 'de'

    def test_v1_database(self):
        from codehub import store, vault
        store.close()
        path = os.path.join(vault.INTERNAL, 'hub.db')
        os.remove(path) if os.path.exists(path) else None
        c = sqlite3.connect(path)
        c.executescript('''
            CREATE TABLE meta(k TEXT PRIMARY KEY, v TEXT);
            CREATE TABLE dateien(projekt, pfad, thema, beschreibung, neben, PRIMARY KEY(projekt, pfad));
            CREATE TABLE notizen(pfad PRIMARY KEY, projekt, art, titel, tags, links, dateien, mtime);
            CREATE TABLE sitzungen(id PRIMARY KEY, projekt, titel, start, letzte, ende, cwd, transkript, versatz,
                letzte_nachricht, t_ein, t_aus, t_cache, t_neu, kompakt, antwort, notiz, zustand);
            CREATE TABLE spuren(sitzung, projekt, pfad, art, n, zeit, PRIMARY KEY(sitzung, pfad, art));
            CREATE TABLE auftraege(sitzung, zeit, text);
            CREATE TABLE commits(sitzung, zeit, hash, text, PRIMARY KEY(sitzung, hash));
            CREATE TABLE subagenten(sitzung, id, typ, auftrag, ergebnis, start, ende, PRIMARY KEY(sitzung, id));
            CREATE TABLE vorschlaege(sitzung, pfad, zeit, PRIMARY KEY(sitzung, pfad));
            CREATE TABLE zaehler(tag, art, n, PRIMARY KEY(tag, art));
            INSERT INTO sitzungen VALUES('s1','shop','Titel',1,2,3,'/','t',0,'',10,20,30,40,'','','n.md','ende');
            INSERT INTO spuren VALUES('s1','shop','src/a.py','bearbeitet',2,5);
            INSERT INTO zaehler VALUES('2026-10-01','hubsuche',4);
            INSERT INTO commits VALUES('s1',1,'abc1234','msg');
            INSERT INTO dateien VALUES('shop','src/a.py','Thema','Text','Neben');
            INSERT INTO meta VALUES('karte:shop','1'), ('aufgeraeumt','5'), ('import','7');
            PRAGMA user_version=1;''')
        c.close()
        with open(os.path.join(vault.LOGS, '2026-10-01.jsonl'), 'w') as f:
            f.write('{"t":1,"e":"fehler","a":"haupt"}\n')
        db = store.db()
        self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 2)
        self.assertEqual(db.execute('SELECT state, t_cache_write FROM sessions').fetchone(), ('ended', 40))
        self.assertEqual(db.execute('SELECT kind FROM traces').fetchone()[0], 'edited')
        self.assertEqual(db.execute('SELECT kind, n FROM counters').fetchone(), ('search', 4))
        self.assertEqual(db.execute('SELECT session, hash FROM commits').fetchone(), ('s1', 'abc1234'))
        self.assertEqual(db.execute('SELECT also FROM files').fetchone()[0], 'Neben')
        self.assertEqual(store.meta('cleaned'), '5')
        self.assertIsNone(store.meta('karte:shop'))
        self.assertEqual(vault.read(os.path.join(vault.LOGS, '2026-10-01.jsonl')).strip(), '{"t":1,"e":"error","a":"main"}')


class Hooks(Base):
    def test_session_flow(self):
        import io
        from codehub import events, hooks, maps, store
        root = project(self.home)
        maps.add_project(root)
        sid = 'abcdef12-0000'

        def run(event, **data):
            data.update(session_id=sid, hook_event_name=event)
            stdin = io.TextIOWrapper(io.BytesIO(json.dumps(data).encode()))
            out = io.BytesIO()
            stdout = io.TextIOWrapper(out)
            sys.stdin, sys.stdout = stdin, stdout
            try:
                hooks.main()
                stdout.flush()
                return out.getvalue().decode()
            finally:
                sys.stdin, sys.stdout = sys.__stdin__, sys.__stdout__

        start = run('SessionStart', source='startup', cwd=root, transcript_path='')
        self.assertIn('shop', start)
        context = run('UserPromptSubmit', prompt='fix the payment retries for the card')
        self.assertIn('src/payment.py', context)
        run('PostToolUse', tool_name='Read', tool_input={'file_path': os.path.join(root, 'src', 'payment.py')})
        counters = dict(store.db().execute('SELECT kind, n FROM counters').fetchall())
        self.assertEqual(counters.get('hit'), 1)
        self.assertEqual(events.read_status()[sid]['state'], 'working')


class Server(Base):
    def test_token_and_host(self):
        import threading
        import urllib.error
        import urllib.request
        from codehub import server
        srv = server.Server(('127.0.0.1', 0), server.Handler)
        srv.token = 'secret'
        srv.hub = server.Hub()
        threading.Thread(target=srv.hub.run, daemon=True).start()
        srv.hub.ready.wait(30)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f'http://127.0.0.1:{srv.server_address[1]}'
        try:
            def post(token, host=None):
                req = urllib.request.Request(base + '/api/cmd', data=b'{"cmd":"settings"}', method='POST',
                                             headers={'X-CodeHub-Token': token, 'Content-Type': 'application/json'})
                if host:
                    req.add_header('Host', host)
                try:
                    with urllib.request.urlopen(req, timeout=10) as r:
                        return r.status
                except urllib.error.HTTPError as e:
                    return e.code
            self.assertEqual(post('secret'), 200)
            self.assertEqual(post('wrong'), 403)
            self.assertEqual(post('secret', 'evil.example:80'), 403)
            with urllib.request.urlopen(base + '/forces.js', timeout=10) as r:
                self.assertIn(b'const Forces', r.read())
            with urllib.request.urlopen(base + '/', timeout=10) as r:
                self.assertIn(b'data-token="secret"', r.read())
        finally:
            srv.shutdown()
            srv.server_close()


class License(Base):
    # the shop is played by a function; nothing leaves the machine
    def shop(self, answers):
        from codehub import license
        license._shop = {'price': '10 €', 'devices': 3, 'site': 'https://example.invalid/',
                         'lemonsqueezy': {'checkout': 'x', 'store_id': 7, 'product_id': 9},
                         'gumroad': {'url': 'x', 'product_id': 'gum'}}
        self.calls = []

        def post(url, fields):
            self.calls.append((url.rsplit('/', 1)[-1], dict(fields)))
            return answers(url, fields)
        license._post = post
        license._valid = None
        return license

    def test_lemon_activation(self):
        lic = self.shop(lambda url, f: {'activated': True, 'instance': {'id': 'i1'},
                                        'meta': {'store_id': 7, 'product_id': 9, 'customer_email': 'a@b.c'}})
        state = lic.activate('38b1460a-5104-4067-a91d-77b872934d51')
        self.assertEqual((state['shop'], state['email']), ('lemonsqueezy', 'a@b.c'))
        lic._valid = None
        self.assertTrue(lic.valid())

    def test_key_of_other_product_is_refused(self):
        lic = self.shop(lambda url, f: {'activated': True, 'instance': {'id': 'i1'},
                                        'meta': {'store_id': 99, 'product_id': 9}} if url.endswith('activate')
                        else {'deactivated': True})
        with self.assertRaises(lic.Problem):
            lic.activate('38b1460a-5104-4067-a91d-77b872934d51')
        self.assertEqual([c[0] for c in self.calls][:2], ['activate', 'deactivate'])   # given back at once
        self.assertFalse(lic.valid())

    def test_gumroad_device_limit_and_refund(self):
        lic = self.shop(lambda url, f: {'success': True, 'uses': 4, 'purchase': {'email': 'x@y.z'}})
        with self.assertRaises(lic.Problem):
            lic.activate('A1B2C3D4-A1B2C3D4-A1B2C3D4-A1B2C3D4')
        lic = self.shop(lambda url, f: {'success': True, 'uses': 1, 'purchase': {'refunded': True}})
        with self.assertRaises(lic.Problem):
            lic.activate('A1B2C3D4-A1B2C3D4-A1B2C3D4-A1B2C3D4')

    def test_recheck_offline_grace_and_other_machine(self):
        import time
        lic = self.shop(lambda url, f: {'success': True, 'uses': 1, 'purchase': {'email': 'x@y.z'}})
        lic.activate('A1B2C3D4-A1B2C3D4-A1B2C3D4-A1B2C3D4')
        state = lic._read()

        def offline(url, f):
            raise ConnectionError('offline')
        for age, expected in ((20 * 86400, True), (40 * 86400, False)):
            lic._write(dict(state, checked=time.time() - age))
            self.shop(offline)
            self.assertEqual(lic.valid(), expected)
        lic._write(dict(state, machine='another computer'))
        lic._valid = None
        self.assertFalse(lic.valid())


class Premium(Base):
    def package(self):
        # a premium zip signed with a throwaway key, accepted by patching PUBLISHER
        import hashlib
        import io
        import zipfile
        from codehub import ed25519, premium
        seed = bytes(range(32))
        premium.PUBLISHER = ed25519.public_key(seed)
        files = {'codehub_premium/__init__.py': b"VERSION = '9.9'\n", 'codehub_premium/web/load.json': b'["a.js"]',
                 'codehub_premium/web/a.js': b'1'}
        manifest = json.dumps({'version': '9.9', 'files': {k: hashlib.sha256(v).hexdigest() for k, v in files.items()}}).encode()
        out = io.BytesIO()
        with zipfile.ZipFile(out, 'w') as z:
            z.writestr('MANIFEST.json', manifest)
            z.writestr('MANIFEST.sig', ed25519.sign(seed, manifest).hex())
            for k, v in files.items():
                z.writestr(k, v)
        return premium, out.getvalue()

    def test_install_needs_license_and_stays_intact(self):
        from codehub import license
        premium, data = self.package()
        self.assertEqual(premium.install(data), '9.9')
        license._valid = False
        self.assertFalse(premium.active())
        self.assertEqual(premium.scripts(), [])
        license._valid = True
        premium._intact = None
        self.assertTrue(premium.active())
        self.assertEqual(premium.scripts(), ['a.js'])
        with open(os.path.join(premium.PACKAGE, 'web', 'a.js'), 'w') as f:
            f.write('patched')
        premium._intact = None
        self.assertFalse(premium.active())


if __name__ == '__main__':
    unittest.main()
