# Everything that differs between Linux, macOS and Windows: directories,
# file locks, detached processes and opening files. The rest of the package
# talks to the operating system only through this module.
import os
import subprocess
import sys
import tempfile
from contextlib import contextmanager

WINDOWS = os.name == 'nt'
MAC = sys.platform == 'darwin'
HOME = os.path.expanduser('~')
PACKAGE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(PACKAGE)


def _app_data():
    if WINDOWS:
        return os.environ.get('APPDATA') or os.path.join(HOME, 'AppData', 'Roaming')
    if MAC:
        return os.path.join(HOME, 'Library', 'Application Support')
    return os.environ.get('XDG_CONFIG_HOME') or os.path.join(HOME, '.config')


def config_dir():
    return os.path.join(_app_data(), 'codehub')


def data_dir():
    # program data that is no setting: license, premium package
    if WINDOWS:
        base = os.environ.get('LOCALAPPDATA') or os.path.join(HOME, 'AppData', 'Local')
    elif MAC:
        base = os.path.join(HOME, 'Library', 'Application Support')
    else:
        base = os.environ.get('XDG_DATA_HOME') or os.path.join(HOME, '.local', 'share')
    return os.path.join(base, 'codehub')


def machine_id():
    # stable id of this computer (not secret, not personal): binds an
    # activation to the machine it was made on
    found = ''
    try:
        if WINDOWS:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Cryptography') as k:
                found = winreg.QueryValueEx(k, 'MachineGuid')[0]
        elif MAC:
            out = subprocess.run(['ioreg', '-rd1', '-c', 'IOPlatformExpertDevice'], capture_output=True,
                                 text=True, timeout=5).stdout
            found = next((line.split('"')[-2] for line in out.splitlines() if 'IOPlatformUUID' in line), '')
        else:
            for path in ('/etc/machine-id', '/var/lib/dbus/machine-id'):
                if os.path.exists(path):
                    with open(path) as f:
                        found = f.read().strip()
                    break
    except (OSError, ValueError, subprocess.SubprocessError, IndexError):
        pass
    import hashlib
    import socket
    return hashlib.sha256(f'codehub:{found or socket.gethostname()}:{HOME}'.encode()).hexdigest()[:32]


def obsidian_config():
    return os.path.join(_app_data(), 'obsidian', 'obsidian.json')


def runtime_dir():
    # Short-lived files (live status). XDG_RUNTIME_DIR lives in RAM on Linux.
    d = os.environ.get('XDG_RUNTIME_DIR')
    if d and os.path.isdir(d) and not WINDOWS:
        return d
    return tempfile.gettempdir()


def claude_dir():
    return os.environ.get('CLAUDE_CONFIG_DIR') or os.path.join(HOME, '.claude')


def python():
    # Interpreter for hooks and background work. A frozen runtime next to the
    # program (the A-Shell's "py" wrapper) survives distro Python updates.
    wrapper = os.path.join(ROOT, 'py')
    if not WINDOWS and os.access(wrapper, os.X_OK):
        return wrapper
    return sys.executable or 'python3'


def command():
    # How to start Code Hub from a hook, the MCP config or a background job
    launcher = os.path.join(ROOT, 'bin', 'codehub')
    if os.path.isfile(launcher):
        return [python(), launcher]
    return [python(), '-m', 'codehub']


@contextmanager
def file_lock(path):
    # Exclusive lock across processes; released when the block ends
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'a+b') as f:
        if WINDOWS:
            import msvcrt
            f.seek(0)
            while True:
                try:
                    msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
                    break
                except OSError:
                    continue        # LK_LOCK gives up after 10 s; keep waiting
            try:
                yield
            finally:
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX)
            yield


def detach(cmd):
    # Start a process that outlives the caller (hooks must return at once)
    kwargs = {'stdin': subprocess.DEVNULL, 'stdout': subprocess.DEVNULL, 'stderr': subprocess.DEVNULL,
              'close_fds': True}
    if WINDOWS:
        kwargs['creationflags'] = 0x00000008 | 0x00000200 | 0x08000000   # detached, new group, no window
    else:
        kwargs['start_new_session'] = True
    try:
        subprocess.Popen(cmd, **kwargs)
    except OSError:
        pass


def open_external(target):
    # File, folder or URL in the program the system picks
    if WINDOWS:
        os.startfile(target)
    else:
        detach(['open' if MAC else 'xdg-open', target])


def resolve(path):
    return os.path.realpath(os.path.expanduser(str(path)))


def inside(path, root):
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def posix(rel):
    # Paths inside a project are stored with "/" on every system
    return rel.replace(os.sep, '/') if os.sep != '/' else rel


def tilde(path):
    return '~' + path[len(HOME):] if inside(path, HOME) else path
