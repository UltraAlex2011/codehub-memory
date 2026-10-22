<!-- codehub:start -->
## Code Hub (MCP "codehub", vault {vault})
- Locate code with `hub_lookup` (topic words) BEFORE Grep/Glob/find or opening files. A prompt may already carry a "Code Hub (…)" list of files — start there.
- Open only the files the hub names. Search yourself only if they are not enough, then record the right file with `hub_map_update` (path + 1-line description).
- Subagents follow the same rule: pass them the hub hits instead of letting them search broadly.
- Record lasting decisions (`hub_note` kind=decision) and solved bugs with root cause (kind=bug) — short, no commit/diff duplicates.
- Earlier work: `hub_search` (decisions, bugs, session logs). Tool calls are logged automatically; `hub_log` only for milestones.
<!-- codehub:end -->
