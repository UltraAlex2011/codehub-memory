#!/bin/sh
# Code Hub installer for macOS and Linux - one line in a terminal:
#   curl -fsSL https://raw.githubusercontent.com/UltraAlex2011/codehub-memory/main/scripts/install.sh | sh
# Puts the newest release into the data folder, adds the "codehub" command,
# sets Code Hub up for Claude Code and opens the view. Running it again
# updates. Needs Python 3.9 or newer, nothing else.
set -eu

REPO="UltraAlex2011/codehub-memory"
case "${LC_ALL:-${LANG:-}}" in de*) DE=1 ;; *) DE= ;; esac
say() { if [ -n "$DE" ]; then printf '%s\n' "$1"; else printf '%s\n' "$2"; fi; }
fail() { say "✗ $1" "✗ $2" >&2; exit 1; }
# questions come from the keyboard even when the script arrives through a pipe
ask() {
    printf '%s ' "$1"
    if [ -r /dev/tty ]; then read -r answer </dev/tty || answer=""; else answer=""; fi
    [ -z "$answer" ] && answer="$2"
}

say "Code Hub wird installiert …" "Installing Code Hub …"

# ---- Python 3.9+ ----
PY=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 \
        && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null; then
        PY="$(command -v "$candidate")"
        break
    fi
done
if [ -z "$PY" ]; then
    if [ "$(uname)" = Darwin ]; then
        xcode-select --install >/dev/null 2>&1 || true
        fail "Python fehlt. macOS fragt jetzt, ob es die Entwicklerwerkzeuge (mit Python) installieren soll – danach diesen Befehl noch einmal ausführen." \
             "Python is missing. macOS now offers to install the developer tools (with Python) – then run this command again."
    fi
    fail "Python 3.9 oder neuer fehlt. Installieren (z. B. „sudo apt install python3“, „sudo dnf install python3“ oder „sudo pacman -S python“), dann noch einmal." \
         "Python 3.9 or newer is missing. Install it (e.g. “sudo apt install python3”, “sudo dnf install python3” or “sudo pacman -S python”), then run this again."
fi
command -v curl >/dev/null 2>&1 || fail "curl fehlt." "curl is missing."
command -v claude >/dev/null 2>&1 || say "! Claude Code ist noch nicht installiert – Code Hub richtet sich trotzdem ein; danach https://claude.com/claude-code installieren." \
                                        "! Claude Code is not installed yet – Code Hub sets itself up anyway; install https://claude.com/claude-code afterwards."

# ---- newest release ----
if [ "$(uname)" = Darwin ]; then
    DATA="$HOME/Library/Application Support/codehub"
else
    DATA="${XDG_DATA_HOME:-$HOME/.local/share}/codehub"
fi
APP="$DATA/app"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
URL="$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" 2>/dev/null \
       | sed -n 's/.*"tarball_url": *"\([^"]*\)".*/\1/p' | head -n 1)"
[ -n "$URL" ] || URL="https://github.com/$REPO/archive/refs/heads/main.tar.gz"
curl -fsSL "$URL" | tar -xzf - -C "$TMP" || fail "Download fehlgeschlagen – Internetverbindung prüfen." "Download failed – check the internet connection."
SRC="$(find "$TMP" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
[ -f "$SRC/codehub/__init__.py" ] || fail "Der Download ist unvollständig." "The download is incomplete."
mkdir -p "$DATA"
rm -rf "$APP.old"
[ -d "$APP" ] && mv "$APP" "$APP.old"
mv "$SRC" "$APP"
rm -rf "$APP.old"
chmod +x "$APP/bin/codehub"

# ---- the "codehub" command ----
BIN="$HOME/.local/bin"
mkdir -p "$BIN"
cat > "$BIN/codehub" <<EOF
#!/bin/sh
exec "$PY" "$APP/bin/codehub" "\$@"
EOF
chmod +x "$BIN/codehub"
case ":$PATH:" in
    *":$BIN:"*) ;;
    *)
        RC="$HOME/.profile"
        case "${SHELL:-}" in */zsh) RC="$HOME/.zshrc" ;; */bash) RC="$HOME/.bashrc" ;; esac
        if [ -n "$DE" ]; then ask "„codehub“ als Befehl in $RC eintragen? [J/n]" j; else ask "Add “codehub” as a command to $RC? [Y/n]" y; fi
        case "$answer" in
            [JjYy]*) printf '\n# Code Hub\nexport PATH="$HOME/.local/bin:$PATH"\n' >> "$RC"
                     say "✓ In $RC eingetragen – gilt in neuen Terminals." "✓ Added to $RC – works in new terminals." ;;
            *) say "Ohne Eintrag: $BIN/codehub" "Without it: $BIN/codehub" ;;
        esac
        ;;
esac

# ---- set up for Claude Code, then show it ----
if [ -r /dev/tty ]; then "$BIN/codehub" install </dev/tty; else "$BIN/codehub" install; fi
"$BIN/codehub" open >/dev/null 2>&1 || true
say "✓ Fertig. Die Ansicht ist im Browser offen – später jederzeit: codehub open" \
    "✓ Done. The view is open in your browser – any time later: codehub open"
