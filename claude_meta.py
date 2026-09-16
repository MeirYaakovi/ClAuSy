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


CLAUDE_MD_LINE_WARN_THRESHOLD = 150  # Claude's attention on CLAUDE.md drops off
                                      # sharply past roughly this many lines —
                                      # a line-count cliff, not a word-count one.


def claude_md_stats(path: str) -> dict | None:
    """Word/line counts for a CLAUDE.md file, and whether it's long enough to
    be worth trimming. "too_long" is based on line count — Claude's practical
    attention drop-off on CLAUDE.md tracks line count, not word count, so a
    file can be short in words but still too long in lines (or vice versa).
    Returns None if unreadable."""
    p = Path(path)
    if not p.is_file():
        return None
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return None
    lines = len(text.splitlines())
    return {
        "words": len(text.split()),
        "lines": lines,
        "too_long": lines > CLAUDE_MD_LINE_WARN_THRESHOLD,
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


MIN_AGENT_DESCRIPTION_LENGTH = 20


def find_agent_description_issues(agents: list) -> dict:
    """Flags subagents (as returned by find_agents()) whose description is
    missing, too short, or identical to another subagent's — vague or
    overlapping descriptions cause inconsistent auto-delegation, since
    Claude picks a subagent based on its description. Returns
    {path: [issue_message, ...]}."""
    issues: dict = {}
    by_description: dict = {}
    for a in agents:
        desc = (a.get("description") or "").strip()
        if not desc:
            issues.setdefault(a["path"], []).append("No description set.")
        elif len(desc) < MIN_AGENT_DESCRIPTION_LENGTH:
            issues.setdefault(a["path"], []).append(
                f"Description is very short ({len(desc)} characters) — may not "
                "give Claude enough to decide when to delegate to this agent.")
        if desc:
            by_description.setdefault(desc, []).append(a["path"])
    for desc, paths in by_description.items():
        if len(paths) > 1:
            for p in paths:
                others = len(paths) - 1
                issues.setdefault(p, []).append(
                    f"Description is identical to {others} other subagent"
                    f"{'s' if others != 1 else ''} — Claude may not reliably "
                    "pick the right one.")
    return issues


def _extract_hook_commands(event_value) -> list:
    """Pulls the actual shell command strings out of one event's hook
    config, e.g. [{"matcher": "Bash", "hooks": [{"type": "command",
    "command": "..."}]}]."""
    commands = []
    if not isinstance(event_value, list):
        return commands
    for group in event_value:
        if not isinstance(group, dict):
            continue
        for h in group.get("hooks", []):
            if isinstance(h, dict) and h.get("type") == "command" and h.get("command"):
                commands.append(h["command"])
    return commands


def find_hooks(project_dirs: list) -> list:
    """Returns [{"scope","scope_label","event","path","commands"}] — one row
    per hook event configured in the global or a project settings.json.
    "commands" is the list of shell commands actually configured for that
    event (may be empty even if the event key exists)."""
    import json

    hooks = []

    def _collect(path: Path, scope: str, label: str):
        if not path.is_file():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for event, value in data.get("hooks", {}).items():
            hooks.append({
                "scope": scope, "scope_label": label,
                "event": event, "path": str(path),
                "commands": _extract_hook_commands(value),
            })

    _collect(global_claude_home() / "settings.json", "global", "Global")
    seen_dirs = set()
    for d in project_dirs:
        if not d or d in seen_dirs:
            continue
        seen_dirs.add(d)
        _collect(project_settings_file(d), "project", Path(d).name or d)
    return hooks


DANGEROUS_HOOK_PATTERNS = [
    (re.compile(r"curl[^|]*\|\s*(sh|bash)\b"), "pipes a curl download directly into a shell"),
    (re.compile(r"wget[^|]*\|\s*(sh|bash)\b"), "pipes a wget download directly into a shell"),
    (re.compile(r"base64\s+(-d|--decode)\b"), "decodes a base64 payload before executing it"),
    (re.compile(r"powershell(\.exe)?\s+.*-enc", re.IGNORECASE), "runs an encoded PowerShell command"),
    (re.compile(r"\biex\b", re.IGNORECASE), "uses PowerShell Invoke-Expression on dynamic input"),
    (re.compile(r"\brm\s+(-[a-z]*r[a-z]*f[a-z]*\b|-[a-z]*f[a-z]*r[a-z]*\b|"
                r"--recursive\s+--force\b|--force\s+--recursive\b)", re.IGNORECASE),
     "runs a recursive force-delete (rm -rf)"),
    (re.compile(r"\brd\s+/s\s+/q\b", re.IGNORECASE), "runs a recursive force-delete (rd /s /q)"),
    (re.compile(r"remove-item\b.*-recurse\b.*-force\b|remove-item\b.*-force\b.*-recurse\b",
                re.IGNORECASE), "runs a recursive force-delete (Remove-Item -Recurse -Force)"),
    (re.compile(r"\bgit\s+push\s+(--force\b|-f\b)"), "force-pushes, which can overwrite remote history"),
]


def find_dangerous_hook_commands(hooks: list) -> list:
    """Flags hook commands (from find_hooks()) matching known malicious
    patterns — the ChainDrop npm worm planted exactly this kind of
    pipe-to-shell command in a SessionStart hook. Returns
    [{"path","event","command","reason"}]."""
    flagged = []
    for h in hooks:
        for cmd in h.get("commands", []):
            for pattern, reason in DANGEROUS_HOOK_PATTERNS:
                if pattern.search(cmd):
                    flagged.append({"path": h["path"], "event": h["event"],
                                     "command": cmd, "reason": reason})
                    break
    return flagged


LOOP_RISK_EVENTS = {"Stop", "SubagentStop", "UserPromptSubmit"}
_CLAUDE_INVOCATION_RE = re.compile(r"(^|[\s;&|])claude\b")


def find_hook_loop_risks(hooks: list) -> list:
    """Flags Stop/SubagentStop/UserPromptSubmit hooks whose command invokes
    `claude` again — that invocation can itself re-trigger the same hook,
    a documented cause of runaway loops and multi-hundred-MB log explosions.
    Returns [{"path","event","command"}]."""
    flagged = []
    for h in hooks:
        if h["event"] not in LOOP_RISK_EVENTS:
            continue
        for cmd in h.get("commands", []):
            if _CLAUDE_INVOCATION_RE.search(cmd):
                flagged.append({"path": h["path"], "event": h["event"], "command": cmd})
    return flagged
