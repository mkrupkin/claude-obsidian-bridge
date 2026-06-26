---
description: Export Claude Code sessions to the configured Obsidian vault (manual / on-demand)
allowed-tools: Bash, Read
---

Run the bundled exporter and report the result.

1. Run via Bash:
   `python "${CLAUDE_PLUGIN_ROOT}/scripts/export_sessions.py" $ARGUMENTS`

2. The script reads `CLAUDE_OBSIDIAN_VAULT` from env. If it's not set, the script will exit with a clear message — surface it and tell the user to run `/obsidian-init` first.

3. On success, report counters: projects scanned, JSONL files seen, exported, skipped (already present), failed.

4. If `$ARGUMENTS` contains `--verbose`, also relay any warning lines from stderr.

Notes:
- Script is idempotent — re-runs skip already-exported sessions by `session_id`.
- `--force` rewrites every note (useful after format changes).
- Auto-export hooks (`PreCompact`, `SessionEnd`) normally cover this — manual use is for backfill or sanity checks.
