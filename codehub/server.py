# The web view: a small HTTP server on 127.0.0.1 that serves web/ and talks
# to view.py. Messages reach the page as server-sent events, commands come
# as POST /api/cmd. Only this machine can connect, and only pages that know
# the token of this run (handed to the page it serves) can use the API -
# other websites cannot read or change the vault through the browser.
# All vault work happens in one worker thread (SQLite connections belong to
# one thread); HTTP threads only pass commands and messages.
import json
import mimetypes
import os
import queue
import secrets
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import VERSION, config, i18n, system

WEB = os.path.join(system.PACKAGE, 'web')
LOCALES = os.path.join(system.PACKAGE, 'locale')
STATE = os.path.join(system.runtime_dir(), 'codehub-web.json')
IDLE = 600              # without a page open this long, the server ends
KEEP = ('graph', 'stats', 'tokens', 'vaults', 'settings', 'tree', 'license')


class Hub:
    # the worker: owns the view, runs commands, collects messages for pages
    def __init__(self):
        self.inbox = queue.Queue()
        self.clients = set()
        self.lock = threading.Lock()
        self.latest = {}        # newest message per kind, for pages that open later
        self.history = []
        self.last_client = time.time()
        self.ready = threading.Event()

    def run(self):
        from .view import View
        view = View()
        self._publish(view.start())
        self.ready.set()
        while True:
            try:
                command, reply = self.inbox.get(timeout=0.2)
            except queue.Empty:
                pass
            else:
                answer = view.handle(command)
                reply.put(answer)
                self._publish([m for m in answer if m.get('type') in KEEP])
            self._publish(view.poll())

    def _publish(self, messages):
        with self.lock:
            for m in messages:
                kind = m.get('type')
                if kind in KEEP:
                    self.latest[kind] = m
                elif kind == 'history':
                    self.history = m['list'][-250:]
                elif kind == 'event':
                    self.history = (self.history + [m])[-250:]
                for q in self.clients:
                    q.put(m)

    def command(self, command):
        reply = queue.Queue()
        self.inbox.put((command, reply))
        return reply.get(timeout=30)

    def join(self):
        q = queue.Queue()
        with self.lock:
            for m in self.latest.values():
                q.put(m)
            q.put({'type': 'history', 'list': list(self.history)})
            self.clients.add(q)
        return q

    def leave(self, q):
        with self.lock:
            self.clients.discard(q)
            self.last_client = time.time()

    def idle(self):
        with self.lock:
            return not self.clients and time.time() - self.last_client > IDLE


class Handler(BaseHTTPRequestHandler):
    server_version = f'CodeHub/{VERSION}'

    def log_message(self, *args):
        pass

    # ---- checks ----

    def _local(self):
        # DNS rebinding: a foreign name pointing at 127.0.0.1 is refused
        host = (self.headers.get('Host') or '').rsplit(':', 1)[0]
        return host in ('127.0.0.1', 'localhost', '[::1]')

    def _token_ok(self, query):
        token = self.headers.get('X-CodeHub-Token') or (query.get('token') or [''])[0]
        return secrets.compare_digest(token, self.server.token)

    def _send(self, code, body, kind='application/json; charset=utf-8', extra=None):
        data = body if isinstance(body, bytes) else body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    # ---- routes ----

    def do_GET(self):
        if not self._local():
            return self._send(403, '{}')
        url = urlparse(self.path)
        query = parse_qs(url.query)
        if url.path in ('/', '/index.html'):
            return self._page()
        if url.path == '/api/events':
            return self._events(query) if self._token_ok(query) else self._send(403, '{}')
        if url.path == '/api/ping':
            ok = self._token_ok(query)
            return self._send(200 if ok else 403, json.dumps({'ok': ok, 'version': VERSION}))
        if url.path.startswith('/locale/'):
            return self._file(LOCALES, url.path[len('/locale/'):])
        if url.path == '/forces.js':
            return self._forces()
        if url.path.startswith('/premium/'):
            # premium files only with an active license of this computer
            from . import premium
            folder = premium.web_dir()
            return self._file(folder, url.path[len('/premium/'):]) if folder else self._send(404, '{}')
        return self._file(WEB, url.path.lstrip('/'))

    def _forces(self):
        # forces.js is shared with the Quickshell view, which imports it as a
        # plain script; in the browser it gets its own scope as "Forces"
        with open(os.path.join(WEB, 'forces.js'), encoding='utf-8') as f:
            source = f.read()
        wrapped = (f'const Forces = (() => {{\n{source}\nreturn {{ load, steps, positions, heat, strength, hold, '
                   f'release }};\n}})();\n')
        self._send(200, wrapped, 'text/javascript; charset=utf-8')

    def do_POST(self):
        url = urlparse(self.path)
        if not self._local() or url.path != '/api/cmd' or not self._token_ok({}):
            return self._send(403, '{}')
        try:
            n = int(self.headers.get('Content-Length') or 0)
            command = json.loads(self.rfile.read(min(n, 8_000_000)).decode('utf-8'))
            if not isinstance(command, dict):
                raise ValueError
        except ValueError:
            return self._send(400, '{}')
        try:
            answer = self.server.hub.command(command)
        except queue.Empty:
            return self._send(504, '{}')
        self._send(200, json.dumps(answer, ensure_ascii=False))

    def _page(self):
        with open(os.path.join(WEB, 'index.html'), encoding='utf-8') as f:
            page = f.read()
        page = page.replace('{{token}}', self.server.token).replace('{{lang}}', i18n.language())
        policy = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                  "img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'none'; "
                  "frame-ancestors 'none'")
        self._send(200, page, 'text/html; charset=utf-8', {'Content-Security-Policy': policy})

    def _file(self, base, rel):
        path = os.path.realpath(os.path.join(base, rel))
        if not system.inside(path, os.path.realpath(base)) or not os.path.isfile(path):
            return self._send(404, '{}')
        kind = mimetypes.guess_type(path)[0] or 'application/octet-stream'
        if kind.startswith('text/') or kind in ('application/javascript', 'application/json'):
            kind += '; charset=utf-8'
        with open(path, 'rb') as f:
            self._send(200, f.read(), kind)

    def _events(self, query):
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        q = self.server.hub.join()
        try:
            while True:
                try:
                    m = q.get(timeout=15)
                    data = json.dumps(m, ensure_ascii=False, separators=(',', ':'))
                    self.wfile.write(f'data: {data}\n\n'.encode('utf-8'))
                except queue.Empty:
                    self.wfile.write(b': keep-alive\n\n')
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            self.server.hub.leave(q)


class Server(ThreadingHTTPServer):
    daemon_threads = True


def address():
    return f'http://127.0.0.1:{int(config.get("port") or 7341)}'


def running():
    # -> URL of a server of ours that answers, or None. The token is checked
    # so a foreign program on the same port is never mistaken for us.
    try:
        with open(STATE, encoding='utf-8') as f:
            state = json.load(f)
        from urllib.request import urlopen
        url = f'http://127.0.0.1:{state["port"]}'
        with urlopen(f'{url}/api/ping?token={state["token"]}', timeout=2) as r:
            if json.load(r).get('ok'):
                return url + '/'
    except Exception:
        pass
    return None


def serve(port=None, quiet=False):
    port = int(port or config.get('port') or 7341)
    server = Server(('127.0.0.1', port), Handler)
    server.token = secrets.token_urlsafe(24)
    server.hub = Hub()
    threading.Thread(target=server.hub.run, daemon=True).start()
    server.hub.ready.wait(60)
    with open(STATE, 'w', encoding='utf-8') as f:
        json.dump({'port': port, 'token': server.token, 'pid': os.getpid()}, f)
    if not quiet:
        print(f'{address()}/  ({i18n.t("web.stop")})', flush=True)

    def watch():
        while not server.hub.idle():
            time.sleep(30)
        server.shutdown()
    threading.Thread(target=watch, daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            os.remove(STATE)
        except OSError:
            pass


def open_view():
    url = running()
    if not url:
        system.detach([*system.command(), 'serve', '--quiet'])
        for _ in range(100):
            time.sleep(0.1)
            url = running()
            if url:
                break
    if not url:
        print(i18n.t('web.failed'), file=sys.stderr)
        return 1
    import webbrowser
    webbrowser.open(url)
    print(url)
    return 0
