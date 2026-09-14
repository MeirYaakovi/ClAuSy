"""Discover Claude Code / Claude Desktop metadata: CLAUDE.md files, subagents, hooks.

Pure, side-effect-free scanning functions — kept separate from config_manager
(which reads/writes the permission config files) so each module stays testable
on its own.
"""
import os
import re
from pathlib import Path

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
FIELD_RE = re.compile(r"^(\w[\w-]*):\s*(.*)$")
HEBREW_RE = re.compile(r"[֐-׿]")


def global_claude_home() -> Path:
    return Path.home() / ".claude"


def global_claude_md() -> Path:
    return global_claude_home() / "CLAUDE.md"


def global_agents_dir() -> Path:
    return global_claude_home() / "agents"


def project_claude_md(project_dir: str) -> Path:
    return Path(project_dir) / "CLAUDE.md"


def project_agents_dir(project_dir: str) -> Path:
    return Path(project_dir) / ".claude" / "agents"


def project_settings_file(project_dir: str) -> Path:
    return Path(project_dir) / ".claude" / "settings.json"


def find_claude_md_files(project_dirs: list) -> list:
    """Returns [{"scope", "label", "path", "exists"}] for the global CLAUDE.md
    plus one entry per project_dirs that has (or could have) a CLAUDE.md."""
    out = [{
        "scope": "global",
        "label": "Global",
        "path": str(global_claude_md()),
        "exists": global_claude_md().is_file(),
    }]
    seen = set()
    for d in project_dirs:
        if not d or d in seen:
            continue
        seen.add(d)
        p = project_claude_md(d)
        out.append({
            "scope": "project",
            "label": Path(d).name or d,
            "path": str(p),
            "exists": p.is_file(),
        })
    return out


def check_rtl_first_line(path: str) -> dict | None:
    """Obsidian auto-detects RTL only if the *first line* contains a Hebrew
    character. Returns None if the file doesn't exist / can't be read,
    otherwise {"has_hebrew", "first_line_hebrew", "ok"} — ok is False only
    when the file has Hebrew content somewhere but not on line 1."""
    p = Path(path)
    if not p.is_file():
        return None
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return None
    has_hebrew = bool(HEBREW_RE.search(text))
    first_line = next((ln for ln in text.splitlines() if ln.strip()), "")
    first_line_hebrew = bool(HEBREW_RE.search(first_line))
    return {
        "has_hebrew": has_hebrew,
        "first_line_hebrew": first_line_hebrew,
        "ok": (not has_hebrew) or first_line_hebrew,
    }


CLAUDE_MD_WORD_WARN_THRESHOLD = 1500  # rough context-budget guideline


def claude_md_stats(path: str) -> dict | None:
    """Word/line counts for a CLAUDE.md file, and whether it's long enough to
    be worth trimming for context budget. Returns None if unreadable."""
    p = Path(path)
    if not p.is_file():
        return None
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return None
    words = len(text.split())
    return {
        "words": words,
        "lines": len(text.splitlines()),
        "too_long": words > CLAUDE_MD_WORD_WARN_THRESHOLD,
    }


def _parse_frontmatter(text: str) -> dict:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}
    fields = {}
    for line in m.group(1).splitlines():
        fm = FIELD_RE.match(line.strip())
        if fm:
            fields[fm.group(1)] = fm.group(2).strip().strip('"').strip("'")
    return fields


def _scan_agents_dir(directory: Path, scope: str, label: str) -> list:
    agents = []
    if not directory.is_dir():
        return agents
    for f in sorted(directory.glob("*.md")):
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            continue
        fields = _parse_frontmatter(text)
        agents.append({
            "scope": scope,
            "scope_label": label,
            "name": fields.get("name", f.stem),
            "description": fields.get("description", ""),
            "path": str(f),
        })
    return agents


def find_agents(project_dirs: list) -> list:
    """Returns subagent definitions from the global agents dir plus each
    project's .claude/agents dir. [{"scope","scope_label","name","description","path"}]"""
    agents = _scan_agents_dir(global_agents_dir(), "global", "Global")
    seen_dirs = set()
    for d in project_dirs:
        if not d or d in seen_dirs:
            continue
        seen_dirs.add(d)
        agents.extend(_scan_agents_dir(project_agents_dir(d), "project", Path(d).name or d))
    return agents


def find_hooks(project_dirs: list) -> list:
    """Returns [{"scope","scope_label","event","path"}] — one row per hook
    event configured in the global or a project settings.json."""
    import json

    hooks = []

    def _collect(path: Path, scope: str, label: str):
        if not path.is_file():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for event in data.get("hooks", {}):
            hooks.append({
                "scope": scope, "scope_label": label,
                "event": event, "path": str(path),
            })

    _collect(global_claude_home() / "settings.json", "global", "Global")
    seen_dirs = set()
    for d in project_dirs:
        if not d or d in seen_dirs:
            continue
        seen_dirs.add(d)
        _collect(project_settings_file(d), "project", Path(d).name or d)
    return hooks
