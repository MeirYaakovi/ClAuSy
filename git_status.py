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
     "direct_on_main","error"} — "error" is set (and other fields best-effort)
    if git isn't reachable at all. "direct_on_main" flags unpushed commits
    sitting directly on main/master, a common branch-discipline slip."""
    name = Path(path).name
    out = {
        "path": path, "name": name, "branch": "", "has_upstream": False,
        "upstream": "", "ahead": 0, "behind": 0, "dirty_count": 0,
        "remote_url": "", "unpushed_commits": [], "error": None,
        "direct_on_main": False,
    }

    r = _run_git(path, ["branch", "--show-current"])
    if r is None:
        out["error"] = "git not available"
        return out
    out["branch"] = r.stdout.strip()

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


def push_repo(path: str) -> dict:
    """Runs `git push` in `path`. Returns {"ok", "output"}."""
    r = _run_git(path, ["push"], timeout=PUSH_TIMEOUT)
    if r is None:
        return {"ok": False, "output": "git push did not complete (timeout or git not found)."}
    output = (r.stdout or "") + (r.stderr or "")
    return {"ok": r.returncode == 0, "output": output.strip()}
