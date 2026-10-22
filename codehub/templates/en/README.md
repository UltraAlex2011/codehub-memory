# Code Hub

Memory for Claude Code: this vault knows **which file is responsible for what**, what was
decided, how bugs were solved and what happened in every session. Claude looks here first
(`hub_lookup`) and then opens only the files named, instead of searching the whole project.
That saves tokens.

## Layout

| Folder | Contents |
|---|---|
| `00_Index/` | one `<project> MAP.md` per project: topic → files with a one-line description; `Projects.md` as overview |
| `01_Projects/<project>/` | project note, `Decisions/`, `Bugs/`, `Notes/`, `Sessions/`, `<project> Architecture.md`, `<project> Open.md` |
| `02_Code_Library/` | proven snippets with tags |
| `03_Logs/` | raw events per day (JSONL) for the live feed – stays local |
| `04_Own/` | yours – Code Hub never writes here by itself |
| `.hub/` | search index and state (SQLite) – stays local, `codehub index --rebuild` rebuilds the index |

The Markdown files are the truth. Read and edit everything in Obsidian; the hub picks up
changes on its next access.

## How it fills up

- **Maps:** from the project's docs (topics) and each file's header comment (descriptions).
  A hook adds new files as soon as Claude creates them; Claude improves entries with
  `hub_map_update`. A git repo in your home folder becomes a project as soon as Claude changes
  something there; any other folder with `codehub add <folder>`.
- **Sessions:** hooks record every session (prompts, changed files, commits, subagents,
  tokens). Costs no extra tokens.
- **Decisions, bugs, notes:** Claude writes them with `hub_note`.

## Commands

```sh
codehub open                 # view in the browser
codehub lookup "login form"  # like hub_lookup
codehub search "settings"    # like hub_search
codehub add ~/code/app       # map a folder as a project
codehub stats                # how often Claude asked the hub instead of searching
codehub doctor               # checks the setup
codehub remote <git-url>     # push the vault there after every session
```
