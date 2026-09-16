"""Persist ClAuSy's own settings: config paths and user-defined labels."""
import json
from pathlib import Path

_STORE = Path.home() / ".clauSy" / "settings.json"

_DEFAULTS = {
    "cc_settings": "",
    "cd_config": "",
    "labels": {},       # {normalised_path: label_string}
    "view_mode": "list",
    "sort_mode": "name_asc",
    "window_maximized": True,
    "window_geometry": "",   # e.g. "1100x720+100+80" — used only when not maximized
    "legend_collapsed": False,
    "git_known_branches": {},  # {repo_path: [branch_name, ...]} — Git Push tab
    "yolo_since": {},          # {cc_settings_path: iso_timestamp} — YOLO-mode duration
    "git_last_head": {},       # {repo_path: head_sha} — Git Push tab, rewrite detection
}


def load() -> dict:
    if not _STORE.exists():
        return dict(_DEFAULTS)
    with open(_STORE, "r", encoding="utf-8") as f:
        data = json.load(f)
    for k, v in _DEFAULTS.items():
        data.setdefault(k, v)
    return data


def save(data: dict):
    _STORE.parent.mkdir(parents=True, exist_ok=True)
    with open(_STORE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def note_branch_seen(known_branches: dict, repo_path: str, branch: str) -> tuple:
    """Records `branch` as seen for `repo_path` in `known_branches` (mutated
    in place, and also returned for chaining). Returns (is_new, updated).
    is_new is always False the very first time a repo is seen — that scan
    establishes the baseline, not a surprise — and True only if `branch`
    wasn't in a previously recorded set for that repo."""
    if not branch:
        return False, known_branches
    seen_before = repo_path in known_branches
    branches = set(known_branches.get(repo_path, []))
    is_new = seen_before and branch not in branches
    branches.add(branch)
    known_branches[repo_path] = sorted(branches)
    return is_new, known_branches


def note_head_seen(last_heads: dict, repo_path: str, head_sha: str) -> str | None:
    """Returns the previously recorded HEAD sha for `repo_path` (None the
    first time it's seen), then records `head_sha` as the new baseline
    (mutates `last_heads` in place)."""
    previous = last_heads.get(repo_path)
    if head_sha:
        last_heads[repo_path] = head_sha
    return previous


def note_yolo_state(yolo_since: dict, cc_settings_path: str, is_yolo: bool, now_iso: str) -> dict:
    """Tracks when bypassPermissions mode was first observed for a given
    settings.json path (mutated in place, and also returned for chaining).
    Clears the record once the mode is no longer bypassPermissions, so a
    later re-enable starts a fresh count instead of showing a stale one."""
    if is_yolo:
        yolo_since.setdefault(cc_settings_path, now_iso)
    else:
        yolo_since.pop(cc_settings_path, None)
    return yolo_since
