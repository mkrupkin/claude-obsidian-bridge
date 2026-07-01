#!/usr/bin/env python3
"""Export Claude Code sessions (.jsonl) to an Obsidian vault as Markdown."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

VAULT_ROOT: Path = Path(".")
SESSIONS_DIR: Path = Path(".")
INDEX_PATH: Path = Path(".")
DEFAULT_PROJECTS_ROOT = Path.home() / ".claude" / "projects"

TOOL_OUTPUT_MAX_LINES = 50
TOOL_OUTPUT_MAX_CHARS = 4000
TITLE_MAX_WORDS = 10
MAX_MARKDOWN_BYTES = 1_000_000  # Obsidian's CodeMirror chokes on multi-MB files — split into parts at this size

# Claude Code encodes a project's cwd as a directory name like
# `C--Users-Alice-Code-myproj` (Windows) or `-Users-alice-code-myproj` (macOS/Linux).
# We strip a configurable prefix to get a clean folder name in the vault.
# Override via CLAUDE_OBSIDIAN_PROJECT_PREFIX if your layout differs.
PROJECT_PREFIX = os.environ.get("CLAUDE_OBSIDIAN_PROJECT_PREFIX", "")


def slugify(text: str, max_len: int = 60) -> str:
    text = re.sub(r"[^\w\s\-]+", "", text, flags=re.UNICODE)
    text = re.sub(r"\s+", "-", text.strip())
    return text[:max_len].strip("-") or "untitled"


def derive_project_name(raw: str) -> str:
    if PROJECT_PREFIX and raw.startswith(PROJECT_PREFIX):
        return raw[len(PROJECT_PREFIX):]
    # Heuristic fallback — trim the encoded leading-path noise.
    # Patterns seen in the wild:
    #   Windows:  "C--Users-<name>-Path-To-Project"
    #   macOS:    "-Users-<name>-Code-project"
    #   Linux:    "-home-<name>-code-project"
    m = re.match(r"^(?:[A-Z]-)?-+(?:Users|home)-[^-]+-(.+)$", raw)
    if m:
        return m.group(1)
    return raw


def extract_text(content) -> str:
    """Flatten a message content (str | list of blocks) into plain text for previews/titles."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if not isinstance(item, dict):
                continue
            t = item.get("type")
            if t == "text":
                parts.append(item.get("text", ""))
            elif t == "thinking":
                continue
            elif t == "tool_use":
                parts.append(f"[tool: {item.get('name')}]")
            elif t == "tool_result":
                sub = item.get("content")
                if isinstance(sub, str):
                    parts.append(sub)
                elif isinstance(sub, list):
                    for s in sub:
                        if isinstance(s, dict) and "text" in s:
                            parts.append(s["text"])
        return "\n".join(p for p in parts if p).strip()
    return ""


def truncate_block(text: str) -> tuple[str, bool]:
    lines = text.splitlines()
    truncated = False
    if len(lines) > TOOL_OUTPUT_MAX_LINES:
        lines = lines[:TOOL_OUTPUT_MAX_LINES] + [f"… [+{len(text.splitlines()) - TOOL_OUTPUT_MAX_LINES} lines]"]
        truncated = True
    joined = "\n".join(lines)
    if len(joined) > TOOL_OUTPUT_MAX_CHARS:
        joined = joined[:TOOL_OUTPUT_MAX_CHARS] + "\n… [truncated]"
        truncated = True
    return joined, truncated


def short_input(input_obj) -> str:
    try:
        s = json.dumps(input_obj, ensure_ascii=False)
    except Exception:
        s = str(input_obj)
    if len(s) > 300:
        s = s[:300] + "…"
    return s


def render_user(content) -> list[str]:
    """Render user-side content. May contain tool_results."""
    out: list[str] = []
    if isinstance(content, str):
        if content.strip():
            out.append(f"### 🧑 User\n\n{content.strip()}\n")
        return out
    if not isinstance(content, list):
        return out
    text_buf = []
    for item in content:
        if not isinstance(item, dict):
            continue
        t = item.get("type")
        if t == "text":
            text_buf.append(item.get("text", ""))
        elif t == "tool_result":
            sub = item.get("content")
            if isinstance(sub, str):
                result_text = sub
            elif isinstance(sub, list):
                pieces = []
                for s in sub:
                    if isinstance(s, dict):
                        if "text" in s:
                            pieces.append(s["text"])
                        elif s.get("type") == "image":
                            pieces.append("[image]")
                result_text = "\n".join(pieces)
            else:
                result_text = ""
            body, was_trunc = truncate_block(result_text)
            if was_trunc:
                out.append(
                    "<details><summary>🔧 tool result (truncated)</summary>\n\n"
                    f"```\n{body}\n```\n\n</details>\n"
                )
            else:
                out.append(f"<details><summary>🔧 tool result</summary>\n\n```\n{body}\n```\n\n</details>\n")
    joined = "\n".join(p for p in text_buf if p).strip()
    if joined:
        out.insert(0, f"### 🧑 User\n\n{joined}\n")
    return out


def render_assistant(content) -> list[str]:
    out: list[str] = []
    if not isinstance(content, list):
        return out
    text_buf = []
    thinking_buf = []
    tool_calls = []
    for item in content:
        if not isinstance(item, dict):
            continue
        t = item.get("type")
        if t == "text":
            text_buf.append(item.get("text", ""))
        elif t == "thinking":
            thinking_buf.append(item.get("thinking", ""))
        elif t == "tool_use":
            name = item.get("name", "?")
            inp = short_input(item.get("input"))
            tool_calls.append(f"- **`{name}`** — `{inp}`")
    if thinking_buf:
        joined = "\n\n".join(t.strip() for t in thinking_buf if t.strip())
        if joined:
            body, _ = truncate_block(joined)
            out.append(
                "<details><summary>💭 thinking</summary>\n\n"
                f"{body}\n\n</details>\n"
            )
    text_joined = "\n".join(p for p in text_buf if p).strip()
    if text_joined:
        out.append(f"### 🤖 Assistant\n\n{text_joined}\n")
    if tool_calls:
        out.append("**🔧 Tool calls:**\n" + "\n".join(tool_calls) + "\n")
    return out


def parse_session(path: Path) -> dict | None:
    user_first_text: str | None = None
    custom_title: str | None = None
    cwd: str | None = None
    git_branch: str | None = None
    session_id: str | None = None
    first_ts: str | None = None
    last_ts: str | None = None
    user_msg_count = 0
    assistant_msg_count = 0
    tool_use_counter: Counter[str] = Counter()
    blocks: list[str] = []

    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                t = obj.get("type")
                if not session_id:
                    session_id = obj.get("sessionId")
                ts = obj.get("timestamp")
                if ts:
                    if not first_ts:
                        first_ts = ts
                    last_ts = ts
                if obj.get("cwd") and not cwd:
                    cwd = obj["cwd"]
                if obj.get("gitBranch") and not git_branch:
                    git_branch = obj["gitBranch"]

                if t == "custom-title":
                    custom_title = obj.get("customTitle") or custom_title
                elif t == "user":
                    msg = obj.get("message", {})
                    content = msg.get("content")
                    rendered = render_user(content)
                    if rendered:
                        # Only count it as a real user turn if there's user text (not pure tool_result)
                        text = extract_text(content)
                        if any("🧑 User" in b for b in rendered):
                            user_msg_count += 1
                            if user_first_text is None and text:
                                user_first_text = text
                        blocks.extend(rendered)
                elif t == "assistant":
                    msg = obj.get("message", {})
                    content = msg.get("content")
                    if isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict) and item.get("type") == "tool_use":
                                tool_use_counter[item.get("name", "?")] += 1
                    rendered = render_assistant(content)
                    if rendered:
                        assistant_msg_count += 1
                        blocks.extend(rendered)
                # ignore system/mode/attachment/queue-operation/last-prompt
    except FileNotFoundError:
        return None
    except OSError as e:
        print(f"  ! Skipping {path.name}: {e}", file=sys.stderr)
        return None

    if not session_id:
        return None
    if user_msg_count == 0 and assistant_msg_count == 0:
        return None

    title_source = (custom_title or user_first_text or "untitled").strip().splitlines()[0]
    title_words = title_source.split()
    short_title = " ".join(title_words[:TITLE_MAX_WORDS])
    if len(title_words) > TITLE_MAX_WORDS:
        short_title += "…"

    return {
        "session_id": session_id,
        "custom_title": custom_title,
        "title": short_title or "untitled",
        "title_source": title_source,
        "cwd": cwd,
        "git_branch": git_branch,
        "first_ts": first_ts,
        "last_ts": last_ts,
        "user_msg_count": user_msg_count,
        "assistant_msg_count": assistant_msg_count,
        "tool_use_counter": tool_use_counter,
        "blocks": blocks,
    }


def parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def format_yaml_value(v) -> str:
    if v is None:
        return '""'
    s = str(v)
    if any(c in s for c in [':', '#', '"', "'", '\n', '[', ']', '{', '}']):
        s = s.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{s}"'
    return s


def _frontmatter(session: dict, project_name: str, date_str: str,
                 part: int | None = None, parts_total: int | None = None) -> str:
    tools_list = sorted(session["tool_use_counter"].keys())
    tags = ["claude-code", f"project/{project_name}"]
    if parts_total and parts_total > 1:
        tags.append("multi-part")
    lines = [
        "---",
        f"project: {format_yaml_value(project_name)}",
        f"date: {date_str}",
        f"session_id: {format_yaml_value(session['session_id'])}",
        f"first_ts: {format_yaml_value(session['first_ts'])}",
        f"last_ts: {format_yaml_value(session['last_ts'])}",
        f"user_messages: {session['user_msg_count']}",
        f"assistant_messages: {session['assistant_msg_count']}",
        f"cwd: {format_yaml_value(session['cwd'])}",
        f"git_branch: {format_yaml_value(session['git_branch'])}",
    ]
    if part is not None and parts_total is not None:
        lines.append(f"part: {part}")
        lines.append(f"parts_total: {parts_total}")
    lines.append("tools_used:")
    for tool in tools_list:
        lines.append(f"  - {format_yaml_value(tool)}")
    lines.append("tags:")
    for tag in tags:
        lines.append(f"  - {format_yaml_value(tag)}")
    lines.append("---")
    return "\n".join(lines)


def _split_blocks_by_size(blocks: list[str], max_body_bytes: int) -> list[list[str]]:
    """Greedy: pack blocks into chunks so each chunk's joined size <= max_body_bytes."""
    chunks: list[list[str]] = []
    current: list[str] = []
    current_size = 0
    sep_len = len("\n".encode("utf-8"))
    for b in blocks:
        b_bytes = len(b.encode("utf-8"))
        # A single block bigger than the cap goes alone (we don't split inside a block).
        if b_bytes >= max_body_bytes:
            if current:
                chunks.append(current)
                current = []
                current_size = 0
            chunks.append([b])
            continue
        projected = current_size + (sep_len if current else 0) + b_bytes
        if current and projected > max_body_bytes:
            chunks.append(current)
            current = [b]
            current_size = b_bytes
        else:
            current.append(b)
            current_size = projected
    if current:
        chunks.append(current)
    return chunks or [[]]


def safe_filename(date_str: str, title: str, session_id: str, part: int | None = None) -> str:
    base = f"{date_str}__{slugify(title, 50)}__{session_id[:8]}"
    if part is not None:
        base += f"--p{part}"
    return base + ".md"


def build_markdown_parts(session: dict, project_name: str) -> list[tuple[int | None, int, str]]:
    """Return list of (part_index_or_None, parts_total, markdown). Single-part files use (None, 1, md)."""
    dt = parse_iso(session["first_ts"]) or datetime.now(timezone.utc)
    date_str = dt.strftime("%Y-%m-%d")
    title = session["title"]
    title_source = session["title_source"]

    def header_block(part: int | None, parts_total: int) -> str:
        suffix = f"  ·  Part {part}/{parts_total}" if part and parts_total > 1 else ""
        lines = [
            f"# {title}{suffix}",
            "",
            f"> Project: **{project_name}**  ·  Date: **{date_str}**  ·  Messages: **{session['user_msg_count']}** ↔ **{session['assistant_msg_count']}**",
            "",
        ]
        if title_source and title_source != title:
            lines += [
                "<details><summary>Full first prompt</summary>",
                "",
                title_source,
                "",
                "</details>",
                "",
            ]
        return "\n".join(lines)

    full_header = header_block(None, 1)
    full_fm = _frontmatter(session, project_name, date_str)
    full_body = "\n".join(session["blocks"])
    single = full_fm + "\n\n" + full_header + full_body + "\n"
    if len(single.encode("utf-8")) <= MAX_MARKDOWN_BYTES:
        return [(None, 1, single)]

    # Need to split. Reserve ~12 KB per chunk for frontmatter+header+nav links.
    overhead = 12_000
    max_body = max(MAX_MARKDOWN_BYTES - overhead, MAX_MARKDOWN_BYTES // 2)
    chunks = _split_blocks_by_size(session["blocks"], max_body)
    parts_total = len(chunks)

    def nav(part: int) -> str:
        fname_no_ext = lambda p: safe_filename(date_str, title, session["session_id"], p).removesuffix(".md")
        links = []
        if part > 1:
            links.append(f"← [[{fname_no_ext(part - 1)}|Part {part - 1}]]")
        if part < parts_total:
            links.append(f"[[{fname_no_ext(part + 1)}|Part {part + 1}]] →")
        return "  ·  ".join(links)

    out: list[tuple[int | None, int, str]] = []
    for idx, block_group in enumerate(chunks, start=1):
        fm = _frontmatter(session, project_name, date_str, part=idx, parts_total=parts_total)
        hdr = header_block(idx, parts_total)
        nav_line = nav(idx)
        nav_block = f"\n_{nav_line}_\n\n" if nav_line else "\n"
        body = "\n".join(block_group)
        md = fm + "\n\n" + hdr + nav_block + body + "\n\n---\n" + (f"_{nav_line}_\n" if nav_line else "")
        out.append((idx, parts_total, md))
    return out


def export_all(projects_root: Path, force: bool = False, verbose: bool = False) -> dict:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    stats = {"projects": 0, "jsonl_total": 0, "exported": 0, "skipped": 0, "failed": 0}
    project_index: dict[str, list[dict]] = defaultdict(list)

    # session_id -> latest mtime among md files already written for that session.
    # We compare this against the source jsonl's mtime: if the jsonl was updated
    # after the md was written, the session is still in progress and needs re-export.
    existing_mtimes: dict[str, float] = {}
    if not force:
        for md in SESSIONS_DIR.rglob("*.md"):
            try:
                with md.open("r", encoding="utf-8") as f:
                    head = f.read(2000)
                m = re.search(r"^session_id:\s*\"?([0-9a-f-]{8,})\"?\s*$", head, re.MULTILINE)
                if not m:
                    continue
                sid = m.group(1)
                md_mtime = md.stat().st_mtime
                if md_mtime > existing_mtimes.get(sid, 0.0):
                    existing_mtimes[sid] = md_mtime
            except OSError:
                pass

    for project_dir in sorted(projects_root.iterdir()):
        if not project_dir.is_dir():
            continue
        dir_project_name = derive_project_name(project_dir.name)
        stats["projects"] += 1
        for jsonl in sorted(project_dir.glob("*.jsonl")):
            stats["jsonl_total"] += 1
            try:
                session = parse_session(jsonl)
            except Exception as e:
                print(f"  ! parse failed: {jsonl}: {e}", file=sys.stderr)
                stats["failed"] += 1
                continue
            if not session:
                stats["skipped"] += 1
                continue
            # Prefer the session's own cwd (authoritative) over the encoded dir name.
            cwd = session.get("cwd")
            if cwd:
                project_name = Path(cwd).name or dir_project_name
            else:
                project_name = dir_project_name
            if verbose:
                print(f"  · {project_name}/{jsonl.name}")
            if not force and session["session_id"] in existing_mtimes:
                # Skip only if the exported markdown is at least as fresh as the jsonl.
                # If the jsonl has been touched since (session still growing), fall through
                # to re-export so new messages get captured.
                try:
                    jsonl_mtime = jsonl.stat().st_mtime
                except OSError:
                    jsonl_mtime = 0.0
                if jsonl_mtime <= existing_mtimes[session["session_id"]]:
                    stats["skipped"] += 1
                    project_index[project_name].append(session)
                    continue
                if verbose:
                    print(f"    (jsonl newer than md — re-exporting)")
            parts = build_markdown_parts(session, project_name)
            dt = parse_iso(session["first_ts"]) or datetime.now(timezone.utc)
            date_str = dt.strftime("%Y-%m-%d")
            out_dir = SESSIONS_DIR / project_name
            out_dir.mkdir(parents=True, exist_ok=True)
            try:
                # Remove any stale single-file export for this session before writing multi-part.
                stale = out_dir / safe_filename(date_str, session["title"], session["session_id"])
                if len(parts) > 1 and stale.exists():
                    stale.unlink()
                for part_idx, _parts_total, md in parts:
                    fname = safe_filename(date_str, session["title"], session["session_id"], part_idx)
                    (out_dir / fname).write_text(md, encoding="utf-8")
                stats["exported"] += 1
                session["_parts_total"] = len(parts)
                project_index[project_name].append(session)
            except OSError as e:
                print(f"  ! write failed for {session['session_id']}: {e}", file=sys.stderr)
                stats["failed"] += 1

    write_index(project_index)
    return stats


def write_index(project_index: dict[str, list[dict]]) -> None:
    lines = [
        "---",
        "tags:",
        "  - claude-code",
        "  - index",
        "---",
        "",
        "# Claude Code Sessions — Index",
        "",
        f"_Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}_",
        "",
        f"**Projects:** {len(project_index)}  ·  **Total sessions:** {sum(len(v) for v in project_index.values())}",
        "",
        "## Projects",
        "",
    ]
    for project, sessions in sorted(project_index.items(), key=lambda kv: kv[0].lower()):
        sessions_sorted = sorted(sessions, key=lambda s: s.get("first_ts") or "", reverse=True)
        lines.append(f"### {project}  ·  {len(sessions_sorted)} sessions")
        lines.append("")
        for s in sessions_sorted[:20]:
            dt = parse_iso(s.get("first_ts"))
            date_str = dt.strftime("%Y-%m-%d") if dt else "?"
            title = s.get("title") or "untitled"
            sid = s.get("session_id", "")
            parts_total = s.get("_parts_total", 1)
            first_part = 1 if parts_total > 1 else None
            fname = safe_filename(date_str, title, sid, first_part)
            link = f"Sessions/{project}/{fname}"
            badge = f" _(split into {parts_total} parts)_" if parts_total > 1 else ""
            lines.append(f"- [[{link}|{date_str} — {title}]]{badge}")
        if len(sessions_sorted) > 20:
            lines.append(f"- _… and {len(sessions_sorted) - 20} more_")
        lines.append("")
    INDEX_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    global VAULT_ROOT, SESSIONS_DIR, INDEX_PATH
    env_vault = os.environ.get("CLAUDE_OBSIDIAN_VAULT")
    parser = argparse.ArgumentParser(description="Export Claude Code sessions to Obsidian vault.")
    parser.add_argument("--vault", type=Path, default=Path(env_vault) if env_vault else None,
                        help="Obsidian vault root (or set CLAUDE_OBSIDIAN_VAULT). Sessions written to <vault>/Sessions/.")
    parser.add_argument("--projects-root", type=Path, default=DEFAULT_PROJECTS_ROOT,
                        help=f"Root of Claude Code projects (default: {DEFAULT_PROJECTS_ROOT})")
    parser.add_argument("--force", action="store_true", help="Re-export even if session_id already exists")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    if not args.vault:
        print("Vault not configured. Pass --vault or set CLAUDE_OBSIDIAN_VAULT.", file=sys.stderr)
        print("Tip: run /obsidian-init in Claude Code to set this up interactively.", file=sys.stderr)
        return 2

    VAULT_ROOT = args.vault.expanduser().resolve()
    SESSIONS_DIR = VAULT_ROOT / "Sessions"
    INDEX_PATH = VAULT_ROOT / "Index.md"

    if not VAULT_ROOT.exists():
        try:
            VAULT_ROOT.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            print(f"Could not create vault dir {VAULT_ROOT}: {e}", file=sys.stderr)
            return 1

    if not args.projects_root.exists():
        print(f"Projects root not found: {args.projects_root}", file=sys.stderr)
        return 1

    print(f"Vault: {VAULT_ROOT}")
    print(f"Source: {args.projects_root}")
    stats = export_all(args.projects_root, force=args.force, verbose=args.verbose)
    print()
    print(f"Projects scanned: {stats['projects']}")
    print(f"JSONL files:      {stats['jsonl_total']}")
    print(f"Exported:         {stats['exported']}")
    print(f"Skipped:          {stats['skipped']}")
    print(f"Failed:           {stats['failed']}")
    print(f"Index:            {INDEX_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
