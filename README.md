# Claude Code → Obsidian Bridge

Mirror every Claude Code session into your Obsidian vault as readable Markdown — automatically, with search and knowledge distillation on top.

- 🪞 **Auto-export** sessions on `PreCompact` (before context shrinks) and `SessionEnd`
- 🔪 **Smart splitting** — files >1 MB are sliced into linked parts so Obsidian doesn't choke
- 🔎 **Search** the whole archive with `/obsidian-search`
- 🧠 **Distill** lessons (tech, patterns, gotchas, decisions) into a structured Knowledge base with `/obsidian-distill`
- 🪝 Idempotent — re-runs never duplicate

## Install

This is a Claude Code plugin distributed via a GitHub-backed marketplace.

```bash
# 1. add this repo as a marketplace
claude /plugin marketplace add MaxKrupkin/claude-obsidian-bridge

# 2. install
claude /plugin install obsidian-bridge@claude-obsidian-bridge
```

Or add to `~/.claude/settings.json` manually:

```json
{
  "enabledPlugins": {
    "obsidian-bridge@claude-obsidian-bridge": true
  },
  "extraKnownMarketplaces": {
    "claude-obsidian-bridge": {
      "source": { "source": "github", "repo": "MaxKrupkin/claude-obsidian-bridge" }
    }
  }
}
```

Requires Python 3.9+ on PATH.

## First-time setup

```
/obsidian-init <absolute-path-to-vault>
```

This will:
1. Create the vault structure if it doesn't exist (`Sessions/`, `Knowledge/{Technologies,Patterns,Gotchas,Decisions,By-Project}/`)
2. Save the vault path to `~/.claude/settings.json` under `env.CLAUDE_OBSIDIAN_VAULT`
3. Register `PreCompact` and `SessionEnd` hooks that run the exporter automatically
4. Run an initial backfill of all existing sessions

## Manual setup — automation via `settings.json`

If you'd rather wire things up yourself (or `/obsidian-init` isn't available), edit `~/.claude/settings.json` and add these blocks. Two pieces — the env var (so the exporter knows where your vault is), and the hooks (so it runs automatically).

```jsonc
{
  // existing keys above ...

  "env": {
    // Absolute path to your Obsidian vault. Forward slashes work on every OS.
    "CLAUDE_OBSIDIAN_VAULT": "C:/Users/you/Documents/MyVault"
  },

  "hooks": {
    // Run BEFORE auto-compaction so the full conversation is archived
    // before any of it gets summarized away.
    "PreCompact": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python \"${CLAUDE_PLUGIN_ROOT}/scripts/export_sessions.py\""
          }
        ]
      }
    ],
    // Belt-and-suspenders: also archive when a session closes (covers
    // short sessions that never hit compaction).
    "SessionEnd": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python \"${CLAUDE_PLUGIN_ROOT}/scripts/export_sessions.py\""
          }
        ]
      }
    ]
  }
}
```

**Important notes**

- `${CLAUDE_PLUGIN_ROOT}` resolves to this plugin's install directory at hook-run time — leave it as-is. If you cloned the plugin manually (no marketplace install), replace it with the absolute path to your local checkout, e.g. `python "C:/Users/you/code/claude-obsidian-bridge/scripts/export_sessions.py"`.
- Python 3.9+ must be on PATH from the shell Claude Code uses to run hooks. On Windows: `winget install Python.Python.3.12`; on macOS/Linux: `python3` from your package manager.
- The script writes to `${CLAUDE_OBSIDIAN_VAULT}/Sessions/` and rebuilds `${CLAUDE_OBSIDIAN_VAULT}/Index.md` on each run.
- Both hooks fire the same idempotent command — no risk of double-export. The exporter detects already-written sessions by `session_id` in frontmatter and skips them.
- If you only want one trigger, keep `PreCompact` (more important — captures content before it's summarized). `SessionEnd` is the safety net.

**Verify**: after saving `settings.json`, run `/compact` in a Claude Code session. Within a few seconds a new `.md` should appear under `<vault>/Sessions/<project>/`. If nothing happens, run `/obsidian-save --verbose` — its stderr will tell you what's wrong (missing env, Python not on PATH, vault dir not writable).

## Slash commands

| Command | What |
|---|---|
| `/obsidian-init <path>` | One-time setup (see above) |
| `/obsidian-save` | Manual export (e.g. backfill). Auto-hooks normally cover this. `--force` rewrites all notes. |
| `/obsidian-search <query>` | Grep Sessions + Knowledge, return hits with project, date, excerpt, click-through link |
| `/obsidian-distill [filter]` | Scan recent sessions and write extracted lessons into `Knowledge/`. Filter is optional (project name, "last 7 days", etc.) |

## What the vault looks like

```
<vault>/
├── Sessions/
│   └── <project>/
│       ├── 2026-06-21__topic__abc12345.md           # single-file session
│       ├── 2026-06-12__big-session__e9d3a38d--p1.md # multi-part
│       └── 2026-06-12__big-session__e9d3a38d--p2.md
├── Knowledge/
│   ├── Technologies/
│   ├── Patterns/
│   ├── Gotchas/
│   ├── Decisions/
│   ├── By-Project/
│   └── README.md
└── Index.md      # auto-generated dashboard
```

Each session note has YAML frontmatter (`project`, `date`, `session_id`, `cwd`, `git_branch`, `tools_used`, `tags`) so Obsidian's graph, tags pane, and Dataview can slice it. Tool calls are summarized; large outputs collapsed into `<details>` blocks (truncated to 50 lines / 4000 chars per block).

## Configuration

Read from environment:

| Variable | Default | Notes |
|---|---|---|
| `CLAUDE_OBSIDIAN_VAULT` | _(required)_ | Absolute path to your Obsidian vault root |
| `CLAUDE_OBSIDIAN_PROJECT_PREFIX` | auto-detect | Override if Claude Code's project-dir encoding on your machine doesn't strip cleanly |

Set them in `~/.claude/settings.json`:

```json
{
  "env": {
    "CLAUDE_OBSIDIAN_VAULT": "C:/Users/you/Documents/MyVault"
  }
}
```

`/obsidian-init` does this for you.

## How it works

Claude Code stores every session as JSONL in `~/.claude/projects/<encoded-cwd>/<session-id>.jsonl`. This plugin's exporter:

1. Walks every JSONL under `~/.claude/projects/`
2. Reconstructs the conversation (user / assistant / tool calls / results)
3. Writes Markdown with frontmatter to `<vault>/Sessions/<project>/`
4. Splits files larger than ~1 MB into linked parts at block boundaries (Obsidian's editor struggles past that)
5. Rebuilds `Index.md`

Idempotent: existing notes are detected by `session_id` in frontmatter. `--force` rewrites everything.

## Troubleshooting

**Obsidian renders a blank window.**
Some sessions can produce multi-MB notes; older versions of this plugin didn't split. If you have huge notes from a previous tool, `/obsidian-save --force` re-exports them with current splitting. Also disable hardware acceleration in Obsidian (Settings → Appearance) and/or launch with `--disable-gpu`.

**`Vault not configured.`**
Run `/obsidian-init <path>` once. Verify with `Get-Content ~/.claude/settings.json` (or `cat`) that `env.CLAUDE_OBSIDIAN_VAULT` is set.

**Hook fires but nothing exports.**
Python isn't on PATH from Claude Code's hook environment. Either install Python system-wide or set the full path in the hook command.

## License

MIT
