# Code Hub

**Long-term memory for Claude Code.** Code Hub knows which file is responsible for what, remembers
decisions, solved bugs and every session – and hands Claude exactly the files it needs instead of
letting it search the whole project. Fewer searches, fewer tokens, sessions that remember yesterday.

[Deutsch](README.de.md)

- **Project maps** – topic → files, each with one line of description. Built from your docs and the
  header comments of your files, kept up to date while Claude works. No tokens spent on it.
- **`hub_lookup` before every search** – Claude asks the map first and opens only the files named.
  With every prompt the hook also adds up to six matching files when the map is sure.
- **A memory that lasts** – decisions, bugs with their root cause, notes and a log of every session
  (prompts, changed files, commits, subagents, tokens) as plain Markdown. Your vault, your files,
  works with Obsidian.
- **Live view** – overview of your projects and a live feed of every agent and subagent in the
  browser. With Premium: a 3D graph where whatever Claude touches lights up, and token statistics.
- **Honest numbers** – how often Claude asked the hub instead of searching, how often the hub was
  right; with Premium, `codehub bench` measures the savings on your own code.

Everything runs locally. Nothing leaves your machine except what Claude Code sends anyway.

## Install

One line, then answer two questions. Code Hub sets itself up for Claude Code and opens its view.

**macOS · Linux**
```sh
curl -fsSL https://raw.githubusercontent.com/UltraAlex2011/codehub-memory/main/scripts/install.sh | sh
```

**Windows** (PowerShell)
```powershell
irm https://raw.githubusercontent.com/UltraAlex2011/codehub-memory/main/scripts/install.ps1 | iex
```

Needs Python 3.9+ (the Windows installer brings it with winget, macOS offers it) and
[Claude Code](https://claude.com/claude-code). No other dependencies. With pipx:
`pipx install git+https://github.com/UltraAlex2011/codehub-memory && codehub install`.

Restart Claude Code afterwards. `codehub update` brings new versions, `codehub uninstall` removes
hooks, MCP server and rules again; the vault stays.

## Use

Claude uses it by itself. You can look:

```sh
codehub open                  # the view in your browser
codehub lookup "login form"   # what hub_lookup answers
codehub search "retry"        # full text over decisions, bugs, sessions
codehub add ~/code/app        # map any folder as a project
codehub stats                 # hub share and hit rate of the last 7 days
codehub tokens                # token use today, 7 and 30 days, total
codehub premium               # premium: status, unlock with a key
codehub doctor                # check the setup
codehub remote <git-url>      # push the vault there after every session
```

The view (`codehub open`) runs on `127.0.0.1` only and refuses requests from other websites.

| Tool for Claude | Purpose |
|---|---|
| `hub_lookup(query, project?)` | files responsible for a topic |
| `hub_search(query)` | full text over notes, decisions, bugs, sessions, docs |
| `hub_note(project, title, content, kind?)` | save a decision, bug, note, snippet, architecture or open point |
| `hub_map_update(file, description, topic?)` | correct or add a map entry |
| `hub_log(action, detail?)` | a milestone in the live feed |

## The vault

```
00_Index/          one "<project> MAP.md" per project
01_Projects/<p>/   project note, Decisions/, Bugs/, Notes/, Sessions/
02_Code_Library/   snippets
03_Logs/           raw events for the live feed (local only)
04_Own/            yours – Code Hub never writes here
.hub/              search index and state (SQLite, local only, rebuildable)
```

The Markdown files are the truth; the index is rebuilt from them at any time
(`codehub index --rebuild`). The vault is a git repository – with `codehub remote` it is backed up
after every session.

## Settings

`codehub config` shows them, `codehub config <name> <value>` changes them; the view has the same
switches. `autoLookup` (files with every prompt), `startContext` (overview at session start),
`push`, `logDays`, `language` (`en`/`de`), `port`.

## Development

```sh
python -m unittest discover tests     # tests, standard library only
tools/snapshot_web.py out.png         # screenshot of the web view (headless Firefox)
```

## Premium

Everything that saves tokens is free. **Code Hub Premium** (10 € once, up to 3 computers, no
subscription) adds the 3D graph of your whole memory, token statistics per day, month and project,
`codehub bench` and the black, light and system themes. Buy it on the
[website](https://ultraalex2011.github.io/codehub-memory/#pricing); the purchase email brings a license
key and the premium package. `codehub premium <key>` unlocks it (the package is found in Downloads).

## License

The core in this repository is MIT ([LICENSE](LICENSE)). Code Hub Premium is sold separately under
its own license. Code Hub is an independent project, not affiliated with Anthropic.
