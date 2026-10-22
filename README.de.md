# Code Hub

**Langzeitgedächtnis für Claude Code.** Code Hub weiß, welche Datei wofür zuständig ist, merkt sich
Entscheidungen, gelöste Bugs und jede Sitzung – und gibt Claude genau die Dateien, die es braucht,
statt es das ganze Projekt durchsuchen zu lassen. Weniger Suchen, weniger Tokens, Sitzungen, die
sich an gestern erinnern.

[English](README.md)

- **Projektkarten** – Thema → Dateien mit je einer Zeile Beschreibung. Entstehen aus deiner Doku und
  den Kopfkommentaren der Dateien und bleiben aktuell, während Claude arbeitet. Kostet keine Tokens.
- **`hub_lookup` vor jeder Suche** – Claude fragt zuerst die Karte und öffnet nur die genannten
  Dateien. Bei jedem Prompt ergänzt der Hook bis zu sechs passende Dateien, wenn die Karte sicher ist.
- **Ein Gedächtnis, das bleibt** – Entscheidungen, Bugs mit Ursache, Notizen und ein Protokoll jeder
  Sitzung (Aufträge, geänderte Dateien, Commits, Subagenten, Tokens) als einfaches Markdown. Dein
  Vault, deine Dateien, funktioniert mit Obsidian.
- **Live-Ansicht** – Überblick über deine Projekte und ein Live-Feed aller Agenten und Subagenten im
  Browser. Mit Premium: ein 3D-Graph, in dem aufleuchtet, was Claude anfasst, und Token-Statistik.
- **Ehrliche Zahlen** – wie oft Claude den Hub statt einer Suche gefragt hat, wie oft der Hub richtig
  lag; mit Premium misst `codehub bench` die Ersparnis an deinem eigenen Code.

Alles läuft lokal. Nichts verlässt den Rechner außer dem, was Claude Code ohnehin sendet.

## Installieren

Eine Zeile, zwei Fragen beantworten. Code Hub richtet sich für Claude Code ein und öffnet seine Ansicht.

**macOS · Linux**
```sh
curl -fsSL https://raw.githubusercontent.com/UltraAlex2011/codehub-memory/main/scripts/install.sh | sh
```

**Windows** (PowerShell)
```powershell
irm https://raw.githubusercontent.com/UltraAlex2011/codehub-memory/main/scripts/install.ps1 | iex
```

Braucht Python 3.9+ (unter Windows bringt der Installer es per winget mit, macOS bietet es an) und
[Claude Code](https://claude.com/claude-code), sonst nichts. Mit pipx:
`pipx install git+https://github.com/UltraAlex2011/codehub-memory && codehub install`.

Danach Claude Code neu starten. `codehub update` holt neue Versionen, `codehub uninstall` nimmt Hooks,
MCP-Server und Regeln wieder heraus; der Vault bleibt.

## Benutzen

Claude benutzt es von selbst. Zum Nachschauen:

```sh
codehub open                  # Ansicht im Browser
codehub lookup "login form"   # was hub_lookup antwortet
codehub search "retry"        # Volltext über Entscheidungen, Bugs, Sitzungen
codehub add ~/code/app        # beliebigen Ordner als Projekt aufnehmen
codehub stats                 # Hub-Anteil und Trefferquote der letzten 7 Tage
codehub tokens                # Tokens heute, 7 und 30 Tage, gesamt
codehub premium               # Premium: Status, mit Schlüssel freischalten
codehub doctor                # Einrichtung prüfen
codehub remote <git-url>      # Vault nach jeder Sitzung dorthin pushen
```

Die Ansicht (`codehub open`) läuft nur auf `127.0.0.1` und weist Anfragen anderer Webseiten ab.

## Der Vault

```
00_Index/          je Projekt "<Projekt> MAP.md"
01_Projects/<p>/   Projektnotiz, Entscheidungen/, Bugs/, Notizen/, Sitzungen/
02_Code_Library/   Snippets
03_Logs/           Roh-Ereignisse für den Live-Feed (nur lokal)
04_Eigenes/        gehört dir – Code Hub schreibt hier nie
.hub/              Suchindex und Zustand (SQLite, nur lokal, jederzeit neu baubar)
```

Ordnernamen und Notizköpfe folgen der Sprache, in der der Vault angelegt wurde.

## Premium

Alles, was Tokens spart, ist kostenlos. **Code Hub Premium** (einmalig 10 €, bis zu 3 Rechner, kein
Abo) bringt den 3D-Graphen deines ganzen Gedächtnisses, Token-Statistik je Tag, Monat und Projekt,
`codehub bench` und die Themes Schwarz, Hell und System. Kaufen auf der
[Website](https://ultraalex2011.github.io/codehub-memory/#pricing); die Kauf-Mail bringt Lizenzschlüssel
und Premium-Paket. `codehub premium <schlüssel>` schaltet frei (das Paket wird in den Downloads gefunden).

## Lizenz

Der Kern in diesem Repository steht unter MIT ([LICENSE](LICENSE)). Code Hub Premium wird getrennt
unter eigener Lizenz verkauft. Code Hub ist ein unabhängiges Projekt, nicht mit Anthropic verbunden.
