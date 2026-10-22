# The Quickshell view's link to view.py: messages as JSON lines on stdout,
# commands as JSON lines on stdin. Ends when the view closes stdin.
# (Quickshell runs on Linux; select() on stdin is not available on Windows.)
import json
import select
import sys

from .view import View


def send(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False, separators=(',', ':')) + '\n')
    sys.stdout.flush()


def main():
    view = View()
    for m in view.start():
        send(m)
    while True:
        ready, _, _ = select.select([sys.stdin], [], [], 0.15)
        if ready:
            line = sys.stdin.readline()
            if not line:
                return              # view closed
            try:
                command = json.loads(line)
            except ValueError:
                command = None
            if isinstance(command, dict):
                for m in view.handle(command):
                    send(m)
        for m in view.poll():
            send(m)


def run():
    try:
        main()
    except (BrokenPipeError, KeyboardInterrupt):
        pass
