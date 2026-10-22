# Code Hub

Gedächtnis für Claude Code: Hier steht, **welche Datei wofür zuständig ist**, was entschieden
wurde, welche Bugs wie gelöst wurden und was in jeder Sitzung passiert ist. Claude schaut zuerst
hier nach (`hub_lookup`) und öffnet dann nur die genannten Dateien, statt das ganze Projekt zu
durchsuchen. Das spart Tokens.

## Aufbau

| Ordner | Inhalt |
|---|---|
| `00_Index/` | je Projekt `<Projekt> MAP.md`: Thema → Dateien mit einer Zeile Beschreibung; `Projekte.md` als Übersicht |
| `01_Projects/<Projekt>/` | Projektnotiz, `Entscheidungen/`, `Bugs/`, `Notizen/`, `Sitzungen/`, `<Projekt> Architektur.md`, `<Projekt> Offen.md` |
| `02_Code_Library/` | geprüfte Snippets mit Tags |
| `03_Logs/` | Roh-Ereignisse je Tag (JSONL) für den Live-Feed – bleibt lokal |
| `04_Eigenes/` | gehört dir – der Code Hub schreibt hier nie von selbst |
| `.hub/` | Suchindex und Zustand (SQLite) – bleibt lokal, `codehub index --rebuild` baut den Index neu |

Die Markdown-Dateien sind die Wahrheit. Alles lässt sich in Obsidian lesen und von Hand ändern;
der Hub liest Änderungen beim nächsten Zugriff neu ein.

## Wie es sich füllt

- **Karten:** aus der Projekt-Doku (Themen) und den Kopfkommentaren der Dateien (Beschreibungen).
  Neue Dateien trägt ein Hook ein, sobald Claude sie anlegt; Claude verbessert Einträge mit
  `hub_map_update`. Ein Git-Repo im Home-Ordner wird zum Projekt, sobald Claude dort etwas ändert,
  andere Ordner mit `codehub add <ordner>`.
- **Sitzungen:** Hooks schreiben jede Sitzung mit (Aufträge, geänderte Dateien, Commits,
  Subagenten, Tokens). Kostet keine zusätzlichen Tokens.
- **Entscheidungen, Bugs, Notizen:** schreibt Claude mit `hub_note`.

## Befehle

```sh
codehub open                 # Ansicht im Browser
codehub lookup "login form"  # wie hub_lookup
codehub search "settings"    # wie hub_search
codehub add ~/projekte/app   # Ordner als Projekt aufnehmen
codehub stats                # wie oft der Hub statt freier Suche gefragt wurde
codehub doctor               # prüft die Einrichtung
codehub remote <git-url>     # Vault nach jeder Sitzung dorthin pushen
```
