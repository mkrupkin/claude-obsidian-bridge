---
description: Search past Claude Code sessions and the Knowledge base in the user's Obsidian vault
allowed-tools: Grep, Glob, Read, Bash
---

Vault root: `$CLAUDE_OBSIDIAN_VAULT` (read from env). If unset, tell the user to run `/obsidian-init` first and stop.

Search targets: `<vault>/Sessions/` (all past conversations) and `<vault>/Knowledge/` (distilled notes).

Query: $ARGUMENTS

Steps:

1. **Interpret the query.** If $ARGUMENTS is a single keyword (e.g. `kwinside`, `Higgsfield`, `Cloudflare Pages`) — use as a literal grep pattern. If it's a question ("how did I deploy to pages.dev?") — extract 2-3 likely keywords and search each, then merge results.

2. **Grep.** Run `Grep` against `$CLAUDE_OBSIDIAN_VAULT/Sessions/` and `$CLAUDE_OBSIDIAN_VAULT/Knowledge/` (case-insensitive, `output_mode: files_with_matches` first). If a project name is mentioned in the query, scope to `Sessions/<project>/` first to avoid noise.

3. **For each hit file** read enough to extract project (from frontmatter or path), date, and a few lines around the match. Don't dump entire files.

4. **Report concisely.** Group by project. Use markdown links so the user can click into Obsidian:
   `[2026-06-16 — Backlinks Catalog](Sessions/agnts-agnt-backlink/2026-06-16__Backlinks-Catalog__a8b731a3.md)`
   Include a 1-line excerpt of the match for each hit.

5. **If nothing relevant found:** say so clearly — don't pad with weak matches. Suggest the user broaden the query or check `Index.md`.

6. **Limit:** at most ~10 strongest matches. If there are more, mention the count and offer to narrow down.

Be honest: if matches are tangential, say so. Don't pretend a fuzzy hit is a real answer.
