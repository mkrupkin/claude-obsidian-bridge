---
description: One-time setup — point obsidian-bridge at your Obsidian vault and register auto-export hooks
allowed-tools: Bash, Read, Write, Edit
---

Task — set up obsidian-bridge for this user.

Argument hint: $ARGUMENTS may contain a vault path. If empty, ask the user where their vault is (or where they want it created).

Steps:

1. **Resolve vault path.** Trim quotes from $ARGUMENTS. If empty, ask: "Where is your Obsidian vault? (absolute path — I'll create the folder if it doesn't exist)". Wait for the user's answer.

2. **Create vault structure if needed.** If the path doesn't exist, `mkdir -p` it. Create subfolders: `Sessions/`, `Knowledge/Technologies/`, `Knowledge/Patterns/`, `Knowledge/Gotchas/`, `Knowledge/Decisions/`, `Knowledge/By-Project/`. Create a minimal `Knowledge/README.md` if missing (see `${CLAUDE_PLUGIN_ROOT}/templates/knowledge-readme.md` if available; otherwise inline a one-paragraph stub).

3. **Persist the vault path.** Read `~/.claude/settings.json`. Under top-level `env`, set `CLAUDE_OBSIDIAN_VAULT` to the resolved path (forward slashes on all platforms). Pretty-print, preserve existing keys, write back.

4. **Register hooks.** In the same `settings.json`, ensure `hooks.PreCompact` and `hooks.SessionEnd` each contain an entry whose command is:
   `python "${CLAUDE_PLUGIN_ROOT}/scripts/export_sessions.py"`
   (Don't duplicate if already present — check by command substring.)

5. **Do a first backfill.** Run `python "${CLAUDE_PLUGIN_ROOT}/scripts/export_sessions.py"` and report how many sessions were exported.

6. **Confirm and tell the user what's next:**
   - Vault path saved.
   - Auto-export armed (PreCompact + SessionEnd).
   - Use `/obsidian-save` for manual re-runs, `/obsidian-search <query>` to look back, `/obsidian-distill` to extract knowledge.

If anything fails (path not writable, settings.json malformed, Python missing), stop and report the specific error — don't try to "fix it for them" by editing broader config.
