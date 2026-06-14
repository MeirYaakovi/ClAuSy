"""Read/write Claude Code and Claude Desktop config files safely."""
import json
import os
from pathlib import Path


class ConfigError(Exception):
    """Raised when a config file exists but cannot be parsed."""


def auto_detect() -> dict:
    cc = Path.home() / ".claude" / "settings.json"
    appdata = os.environ.get("APPDATA", "")
    cd_candidates = [
        Path(appdata) / "Claude" / "claude_desktop_config.json",
        Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
    ]
    cd = next((p for p in cd_candidates if p.exists()), Path(""))
    return {
        "cc_settings": str(cc),
        "cd_config": str(cd) if cd.exists() else "",
    }


def _load(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise ConfigError(
            f"Invalid JSON in {p.name}: {e.msg} (line {e.lineno})"
        ) from e


def validate_path(path: str, cfg_type: str) -> tuple:
    """Returns (ok: bool, error_msg: str). cfg_type is 'cc' or 'cd'."""
    if not path:
        return False, "No path specified"
    p = Path(path)
    if not p.exists():
        return False, "File not found"
    try:
        data = _load(path)
    except ConfigError as e:
        return False, str(e)
    if not isinstance(data, dict):
        return False, "Expected a JSON object at root level"
    return True, ""


def _save(path: str, data: dict):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def read_all_dirs(cc_settings: str, cd_config: str) -> dict:
    """
    Returns {normalised_path: {"cc_allow": bool, "cc_additional": bool, "cd": bool}}.
    Collects every directory path from all three config locations.
    """
    result: dict = {}

    if cc_settings:
        data = _load(cc_settings)
        perms = data.get("permissions", {})

        for p in perms.get("allow", []):
            if os.path.isabs(p):
                key = os.path.normpath(p)
                result.setdefault(key, {"cc_allow": False, "cc_additional": False, "cd": False})
                result[key]["cc_allow"] = True

        for p in perms.get("additionalDirectories", []):
            key = os.path.normpath(p)
            result.setdefault(key, {"cc_allow": False, "cc_additional": False, "cd": False})
            result[key]["cc_additional"] = True

    if cd_config:
        data = _load(cd_config)
        args = data.get("mcpServers", {}).get("filesystem", {}).get("args", [])
        for p in args:
            if os.path.isabs(p):
                key = os.path.normpath(p)
                result.setdefault(key, {"cc_allow": False, "cc_additional": False, "cd": False})
                result[key]["cd"] = True

    return result


def apply_changes(cc_settings: str, cd_config: str, entries: list, progress_cb=None):
    """
    Writes changes to each config file without touching unrelated content.
    progress_cb(pct: int) is called at 0, 33, 66, 100.
    entries: list of {"path", "cc_allow", "cc_additional", "cd"}.
    """
    cc_allow_dirs = [e["path"] for e in entries if e.get("cc_allow")]
    cc_add_dirs   = [e["path"] for e in entries if e.get("cc_additional")]
    cd_dirs       = [e["path"] for e in entries if e.get("cd")]

    if progress_cb:
        progress_cb(0)

    if cc_settings:
        data = _load(cc_settings)
        data.setdefault("permissions", {})
        perms = data["permissions"]

        # allow: keep non-path entries, replace path entries
        non_path_allow = [e for e in perms.get("allow", []) if not os.path.isabs(e)]
        new_allow = non_path_allow + cc_allow_dirs
        if new_allow:
            perms["allow"] = new_allow
        else:
            perms.pop("allow", None)

        if progress_cb:
            progress_cb(33)

        if cc_add_dirs:
            perms["additionalDirectories"] = cc_add_dirs
        else:
            perms.pop("additionalDirectories", None)

        _save(cc_settings, data)

    if progress_cb:
        progress_cb(66)

    if cd_config:
        data = _load(cd_config)
        data.setdefault("mcpServers", {})
        if "filesystem" not in data["mcpServers"]:
            data["mcpServers"]["filesystem"] = {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem"],
            }
        fs = data["mcpServers"]["filesystem"]
        non_path_args = [a for a in fs.get("args", []) if not os.path.isabs(a)]
        fs["args"] = non_path_args + cd_dirs
        _save(cd_config, data)

    if progress_cb:
        progress_cb(100)
