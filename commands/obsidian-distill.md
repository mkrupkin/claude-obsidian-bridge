---
description: Scan recent exported sessions and distill knowledge (tech, patterns, gotchas, decisions) into the Knowledge/ folder
allowed-tools: Read, Glob, Grep, Write, Edit, Bash
---

Vault root: `$CLAUDE_OBSIDIAN_VAULT` (read from env). If unset, tell the user to run `/obsidian-init` first and stop.

Task — distill knowledge from session notes into the Knowledge base.

**Pick which sessions to process.** If $ARGUMENTS is given, use it as a filter (project name, date range, "last N"). Otherwise: list `$CLAUDE_OBSIDIAN_VAULT/Sessions/**/*.md` modified in the last 7 days OR not yet referenced from anywhere under `$CLAUDE_OBSIDIAN_VAULT/Knowledge/` (grep Knowledge for the session filename to check).

**For each session file:**

1. Read the session markdown (skip `<details>` blocks unless load-bearing).
2. Identify these signals (only when actually present — don't fabricate):
   - **Technology** — concrete tools/libs/services used non-trivially (not just `bash`/`cat`)
   - **Pattern** — a repeatable solution worth reusing on another project
   - **Gotcha** — something that broke, why, and how it was fixed
   - **Decision** — an architectural call with reasoning worth remembering
3. For each signal worth keeping (use judgment — skip trivia):
   - Check if a matching note already exists in the relevant subfolder (`Knowledge/Technologies/`, `Knowledge/Patterns/`, etc.). Use Glob and Grep.
   - **If exists:** append a new `## Update from <date> — <session-link>` section. Add the session to `source_sessions` in frontmatter. Don't rewrite old content.
   - **If new:** create a fresh note. Filename: kebab-case topic (e.g. `cloudflare-pages-deploy.md`).
4. Always link back: every Knowledge note must reference its source session via wiki-link `[[Sessions/<project>/<file>]]`.

**Quality bar — be strict.** A Knowledge note should be worth re-reading 6 months from now. If a session has nothing distillable beyond "I ran some commands", skip it. Don't create stub notes.

**Optionally update By-Project/** — if a session covered a project that has no `By-Project/<name>.md` yet, create a brief TL;DR (what the project is, stack, current state) using the session as source.

**At the end** report:
- N sessions scanned
- N Knowledge notes created
- N existing notes updated
- N sessions skipped as "nothing distillable" (count only, no list)

Be honest about uncertainty. If a session is ambiguous (e.g., abandoned mid-task), skip rather than guess.
