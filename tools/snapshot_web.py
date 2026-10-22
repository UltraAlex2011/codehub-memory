#!/usr/bin/env python3
# Test bench of the web view: starts its own Code Hub server and a headless
# Firefox with a throwaway profile (no window, nothing on the screen), waits
# until the page has its data and saves a screenshot. Talks to Firefox over
# Marionette with the standard library only.
#   snapshot_web.py out.png [--size 1480x900] [--wait 6] [--js "code"] [--theme light]
#   snapshot_web.py out.png --url http://127.0.0.1:8000/   any page, no Code Hub server
# --js runs in the page after loading (e.g. to open a view); --print echoes
# what the code returns. Uses the vault from CODEHUB_VAULT, like codehub.
import argparse
import base64
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


class Marionette:
    def __init__(self, port):
        for _ in range(150):
            try:
                self.sock = socket.create_connection(('127.0.0.1', port), timeout=30)
                break
            except OSError:
                time.sleep(0.2)
        else:
            raise SystemExit('Firefox did not answer')
        self.buf = b''
        self.n = 0
        self._read()                        # handshake

    def _read(self):
        while b':' not in self.buf:
            self.buf += self.sock.recv(65536)
        size, _, rest = self.buf.partition(b':')
        size = int(size)
        while len(rest) < size:
            rest += self.sock.recv(65536)
        self.buf = rest[size:]
        return json.loads(rest[:size])

    def call(self, name, params=None):
        self.n += 1
        data = json.dumps([0, self.n, name, params or {}]).encode()
        self.sock.sendall(str(len(data)).encode() + b':' + data)
        while True:
            msg = self._read()
            if msg[0] == 1 and msg[1] == self.n:
                if msg[2]:
                    raise RuntimeError(msg[2])
                return msg[3]


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out')
    ap.add_argument('--size', default='1480x900')
    ap.add_argument('--wait', type=float, default=6)
    ap.add_argument('--js', default='')
    ap.add_argument('--print', action='store_true')
    ap.add_argument('--theme', default='')
    ap.add_argument('--url', default='')
    a = ap.parse_args()
    width, height = (int(x) for x in a.size.split('x'))
    web_port, mn_port = free_port(), free_port()
    profile = tempfile.mkdtemp(prefix='codehub-ff-')
    with open(os.path.join(profile, 'user.js'), 'w') as f:
        f.write(f'user_pref("marionette.port", {mn_port});\n'
                'user_pref("browser.shell.checkDefaultBrowser", false);\n'
                'user_pref("datareporting.policy.dataSubmissionEnabled", false);\n'
                'user_pref("toolkit.telemetry.reportingpolicy.firstRun", false);\n'
                'user_pref("webgl.force-enabled", true);\n')
    server = None if a.url else subprocess.Popen([os.path.join(ROOT, 'py'), os.path.join(ROOT, 'bin', 'codehub'),
                                                  'serve', '--port', str(web_port), '--quiet'])
    firefox = subprocess.Popen(['firefox', '--headless', '--marionette', '-no-remote', '-profile', profile],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               env=dict(os.environ, MOZ_HEADLESS='1'))
    try:
        m = Marionette(mn_port)
        m.call('WebDriver:NewSession', {'capabilities': {}})
        m.call('WebDriver:SetWindowRect', {'width': width, 'height': height})
        m.call('WebDriver:Navigate', {'url': a.url or f'http://127.0.0.1:{web_port}/'})
        if a.theme:
            m.call('WebDriver:ExecuteScript', {'script': f'localStorage.setItem("codehub.prefs", JSON.stringify(Object.assign(JSON.parse(localStorage.getItem("codehub.prefs") || "{{}}"), {{theme: "{a.theme}"}}))); location.reload();', 'args': []})
        time.sleep(a.wait)
        if a.js:
            r = m.call('WebDriver:ExecuteScript', {'script': a.js, 'args': []})
            if a.print:
                print(json.dumps(r.get('value'), ensure_ascii=False, indent=1))
            time.sleep(1.5)
        shot = m.call('WebDriver:TakeScreenshot', {'full': False})
        with open(a.out, 'wb') as f:
            f.write(base64.b64decode(shot['value']))
        print(a.out)
    finally:
        firefox.terminate()
        if server:
            server.terminate()
        try:
            firefox.wait(10)
        except subprocess.TimeoutExpired:
            firefox.kill()
        shutil.rmtree(profile, ignore_errors=True)


if __name__ == '__main__':
    main()
