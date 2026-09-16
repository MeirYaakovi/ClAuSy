"""Discover local git repos and their push status.

Scanning/status reads are side-effect-free; push_repo() is the one function
here that touches the outside world (runs `git push`). Kept separate from
claude_meta / config_manager since this has nothing to do with Claude's own
config files — it's about the project folders ClAuSy already tracks.
"""
import os
import subprocess
from pathlib import Path

STATUS_TIMEOUT = 15
PUSH_TIMEOUT = 90
UNPUSHED_LOG_LIMIT = 8


def _run_git(path: str, args: list, timeout: int = STATUS_TIMEOUT):
    """Runs a git command in `path`. Returns CompletedProcess, or None if git
    isn't available / the call couldn't complete at all."""
    try:
        return subprocess.run(
            ["git", *args], cwd=path, capture_output=True, text=True,
            timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return None


def is_git_repo(path: str) -> bool:
    return os.path.isdir(os.path.join(path, ".git"))


def is_path_tracked(repo_path: str, rel_path: str) -> bool:
    """True if `rel_path` (relative to `repo_path`, forward or back slashes
    both fine) is tracked by git in that repo."""
    r = _run_git(repo_path, ["ls-files", "--error-unmatch", rel_path.replace("\\", "/")])
    return r is not None and r.returncode == 0


def find_tracked_settings_local(project_dirs: list) -> list:
    """Flags tracked directories whose .claude/settings.local.json is
    accidentally committed to git instead of gitignored — that file is
    meant to hold personal/local-only overrides, so committing it can leak
    per-developer settings or just cause noisy merge conflicts. Returns the
    settings.local.json paths that are tracked."""
    flagged = []
    for d in project_dirs:
        if not d or not is_git_repo(d):
            continue
        rel = os.path.join(".claude", "settings.local.json")
        full = os.path.join(d, rel)
        if os.path.isfile(full) and is_path_tracked(d, rel):
            flagged.append(full)
    return flagged


def find_git_repos(project_dirs: list) -> list:
    """Returns absolute paths of git repos found among the tracked project
    directories: a tracked dir that's itself a repo is included directly;
    otherwise its immediate subdirectories are checked (matches how a
    "Projects" folder holds one repo per subfolder)."""
    found = []
    seen = set()
    for d in project_dirs:
        if not d or not os.path.isdir(d):
            continue
        if is_git_repo(d):
            if d not in seen:
                seen.add(d)
                found.append(d)
            continue
        try:
            children = sorted(os.scandir(d), key=lambda e: e.name.lower())
        except OSError:
            continue
        for entry in children:
            if entry.is_dir() and is_git_repo(entry.path) and entry.path not in seen:
                seen.add(entry.path)
                found.append(entry.path)
    return found


def get_repo_status(path: str) -> dict:
    """Returns status for one repo:
    {"path","name","branch","has_upstream","upstream","ahead","behind",
     "dirty_count","remote_url","unpushed_commits":[{"hash","subject","date"}],
     "direct_on_main","head_sha","error"} — "error" is set (and other fields
    best-effort) if git isn't reachable at all. "direct_on_main" flags
    unpushed commits sitting directly on main/master, a common
    branch-discipline slip."""
    name = Path(path).name
    out = {
        "path": path, "name": name, "branch": "", "has_upstream": False,
        "upstream": "", "ahead": 0, "behind": 0, "dirty_count": 0,
        "remote_url": "", "unpushed_commits": [], "error": None,
        "direct_on_main": False, "head_sha": "",
    }

    r = _run_git(path, ["branch", "--show-current"])
    if r is None:
        out["error"] = "git not available"
        return out
    out["branch"] = r.stdout.strip()

    r = _run_git(path, ["rev-parse", "HEAD"])
    if r is not None and r.returncode == 0:
        out["head_sha"] = r.stdout.strip()

    r = _run_git(path, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    if r is not None and r.returncode == 0 and r.stdout.strip():
        out["has_upstream"] = True
        out["upstream"] = r.stdout.strip()

        r = _run_git(path, ["rev-list", "--count", "@{u}..HEAD"])
        if r is not None and r.returncode == 0:
            out["ahead"] = int(r.stdout.strip() or 0)

        r = _run_git(path, ["rev-list", "--count", "HEAD..@{u}"])
        if r is not None and r.returncode == 0:
            out["behind"] = int(r.stdout.strip() or 0)

        if out["ahead"]:
            r = _run_git(path, [
                "log", "@{u}..HEAD", f"-{UNPUSHED_LOG_LIMIT}",
                "--format=%h\x1f%s\x1f%ad", "--date=short",
            ])
            if r is not None and r.returncode == 0:
                for line in r.stdout.splitlines():
                    parts = line.split("\x1f")
                    if len(parts) == 3:
                        out["unpushed_commits"].append(
                            {"hash": parts[0], "subject": parts[1], "date": parts[2]})

    out["direct_on_main"] = out["branch"] in ("main", "master") and out["ahead"] > 0

    r = _run_git(path, ["status", "--porcelain"])
    if r is not None and r.returncode == 0:
        out["dirty_count"] = len([ln for ln in r.stdout.splitlines() if ln.strip()])

    r = _run_git(path, ["remote", "get-url", "origin"])
    if r is not None and r.returncode == 0:
        out["remote_url"] = r.stdout.strip()

    return out


def scan(project_dirs: list) -> list:
    """find_git_repos() + get_repo_status() for each, sorted with repos that
    have unpushed commits first, then by name."""
    repos = [get_repo_status(p) for p in find_git_repos(project_dirs)]
    repos.sort(key=lambda r: (r["ahead"] == 0, r["name"].lower()))
    return repos


def is_ancestor(path: str, ancestor_sha: str, descendant_ref: str = "HEAD") -> bool | None:
    """True if `ancestor_sha` is an ancestor of (or equal to) `descendant_ref`
    in `path`'s repo. Returns None if either commit can't be resolved (e.g.
    the recorded sha was pruned by a gc, or this isn't a git repo) — the
    caller should treat that as "can't tell", not as a rewrite."""
    r = _run_git(path, ["merge-base", "--is-ancestor", ancestor_sha, descendant_ref])
    if r is None or r.returncode not in (0, 1):
        return None
    return r.returncode == 0


def _hook_commands_at_ref(path: str, ref: str) -> set | None:
    """Hook shell commands configured in .claude/settings.json as it existed
    at `ref`, or None if the file didn't exist there / couldn't be parsed."""
    import json
    r = _run_git(path, ["show", f"{ref}:.claude/settings.json"])
    if r is None or r.returncode != 0:
        return None
    try:
        data = json.loads(r.stdout)
    except ValueError:
        return None
    commands = set()
    for event_value in data.get("hooks", {}).values():
        if not isinstance(event_value, list):
            continue
        for group in event_value:
            if not isinstance(group, dict):
                continue
            for h in group.get("hooks", []):
                if isinstance(h, dict) and h.get("type") == "command" and h.get("command"):
                    commands.add(h["command"])
    return commands


def find_hooks_changed_since(path: str, old_sha: str) -> dict | None:
    """Compares .claude/settings.json hooks between `old_sha` (typically the
    last HEAD ClAuSy saw for this repo) and the current HEAD. A same-repo
    hook injected via a pulled commit — the CVE-2025-59536 pattern — runs at
    session start before any trust prompt, so surfacing exactly what changed
    is more actionable than the generic 'file changed externally' warning.
    Returns None if there's nothing to compare (no prior sha, or the file
    didn't exist at one end and doesn't at the other). Otherwise
    {"added": [...], "removed": [...]} — both empty means hooks are
    unchanged."""
    if not old_sha:
        return None
    old_commands = _hook_commands_at_ref(path, old_sha)
    new_commands = _hook_commands_at_ref(path, "HEAD")
    if old_commands is None and new_commands is None:
        return None
    old_commands = old_commands or set()
    new_commands = new_commands or set()
    added = sorted(new_commands - old_commands)
    removed = sorted(old_commands - new_commands)
    if not added and not removed:
        return None
    return {"added": added, "removed": removed}


def push_repo(path: str) -> dict:
    """Runs `git push` in `path`. Returns {"ok", "output"}."""
    r = _run_git(path, ["push"], timeout=PUSH_TIMEOUT)
    if r is None:
        return {"ok": False, "output": "git push did not complete (timeout or git not found)."}
    output = (r.stdout or "") + (r.stderr or "")
    return {"ok": r.returncode == 0, "output": output.strip()}
