"""Read/write Claude Code and Claude Desktop config files safely."""
import fnmatch
import json
import os
import re
from datetime import datetime
from pathlib import Path


class ConfigError(Exception):
    """Raised when a config file exists but cannot be parsed."""


BACKUP_KEEP_COUNT = 5


def _cd_config_candidate_paths(appdata: str, localappdata: str, home: Path) -> list:
    """Every location claude_desktop_config.json could plausibly live in,
    whether or not it actually exists there."""
    candidates = [
        # classic (non-store) Windows install
        Path(appdata) / "Claude" / "claude_desktop_config.json",
        # macOS
        home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
    ]
    # Windows Store / MSIX install: %LOCALAPPDATA%\Packages\Claude_<hash>\LocalCache\Roaming\Claude\...
    packages_dir = Path(localappdata) / "Packages"
    if packages_dir.is_dir():
        for pkg in packages_dir.glob("Claude_*"):
            candidates.append(
                pkg / "LocalCache" / "Roaming" / "Claude" / "claude_desktop_config.json"
            )
    return candidates


def find_cd_config_candidates() -> list:
    """Every claude_desktop_config.json path that actually exists on this
    machine. On Windows in particular, more than one can genuinely exist at
    once (e.g. after switching from the classic installer to the Store app)
    — Claude Desktop's own 'Edit Config' button has been documented to open
    the wrong one in that situation, so callers should surface all of them
    rather than silently picking one."""
    appdata = os.environ.get("APPDATA", "")
    localappdata = os.environ.get("LOCALAPPDATA", "")
    candidates = _cd_config_candidate_paths(appdata, localappdata, Path.home())
    return [str(p) for p in candidates if p.exists()]


def auto_detect() -> dict:
    cc = Path.home() / ".claude" / "settings.json"
    candidates = find_cd_config_candidates()
    return {
        "cc_settings": str(cc),
        "cd_config": candidates[0] if candidates else "",
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


def list_backups(path: str) -> list:
    """Returns backup files for `path`, oldest first."""
    p = Path(path)
    if not p.parent.is_dir():
        return []
    return sorted(p.parent.glob(p.name + ".*.bak"))


def _rotate_backup(p: Path):
    """Backs up `p`'s current content (if any) and prunes old backups
    beyond BACKUP_KEEP_COUNT. No-op if `p` doesn't exist yet."""
    if not p.exists():
        return
    try:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        (p.parent / f"{p.name}.{ts}.bak").write_bytes(p.read_bytes())
        for old in list_backups(str(p))[:-BACKUP_KEEP_COUNT]:
            old.unlink(missing_ok=True)
    except OSError:
        pass


def _save(path: str, data: dict):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    _rotate_backup(p)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def restore_last_backup(path: str) -> bool:
    """Restores `path` in-place from its most recent backup. The file's
    current content (if any) is itself backed up first, so this can be
    reversed by restoring again. Returns False if there's no backup."""
    backups = list_backups(path)
    if not backups:
        return False
    p = Path(path)
    _rotate_backup(p)
    p.write_bytes(backups[-1].read_bytes())
    return True


DEFAULT_DENY_SECRET_PATTERNS = [
    "Read(./.env)",
    "Read(./.env.*)",
    "Read(**/.env)",
    "Read(**/.env.*)",
    "Read(**/*.pem)",
    "Read(**/*.key)",
    "Read(**/id_rsa)",
    "Read(**/id_ed25519)",
    "Read(**/credentials.json)",
    "Read(**/.aws/**)",
    "Read(**/.ssh/**)",
]


def add_deny_patterns(cc_settings: str, patterns: list) -> int:
    """Merges `patterns` into permissions.deny in cc_settings.json, preserving
    everything else in the file. Returns how many patterns were newly added
    (patterns already present are left as-is, not duplicated)."""
    if not cc_settings:
        return 0
    data = _load(cc_settings)
    data.setdefault("permissions", {})
    existing = data["permissions"].get("deny", [])
    new = [p for p in patterns if p not in existing]
    if new:
        data["permissions"]["deny"] = existing + new
        _save(cc_settings, data)
    return len(new)


SECRET_FILE_GLOBS = [
    ".env", ".env.*", "*.pem", "*.key", "id_rsa", "id_ed25519", "credentials.json",
]


def _gitignore_line_covers(line: str, rel_path: str) -> bool:
    line = line.strip().rstrip("/")
    if not line or line.startswith("#") or line.startswith("!"):
        return False
    name = rel_path.rsplit("/", 1)[-1]
    return fnmatch.fnmatch(rel_path, line) or fnmatch.fnmatch(name, line) or line in (rel_path, name)


def find_gitignored_secrets(directory: str) -> list:
    """For a tracked directory, finds files matching common secret patterns
    (the same ones the 'Deny Secrets' preset protects against) that exist on
    disk AND are excluded from git via .gitignore — meaning the file was
    deliberately kept out of version control, but Claude could still read it
    if the directory is granted access."""
    d = Path(directory)
    gitignore = d / ".gitignore"
    if not d.is_dir() or not gitignore.is_file():
        return []
    try:
        lines = gitignore.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return []

    found = []
    for pattern in SECRET_FILE_GLOBS:
        try:
            matches = d.rglob(pattern)
        except OSError:
            continue
        for match in matches:
            if not match.is_file():
                continue
            rel = match.relative_to(d).as_posix()
            if any(_gitignore_line_covers(line, rel) for line in lines):
                found.append(str(match))
    return sorted(set(found))


def file_fingerprint(path: str) -> tuple | None:
    """(mtime_ns, size) for `path`, or None if it doesn't exist. Used to
    detect whether a config file changed on disk since ClAuSy last read it
    — Claude Code itself has a known bug where it silently rewrites
    settings.json mid-session, and ClAuSy shouldn't blindly clobber that."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


def count_non_path_rules(cc_settings: str) -> dict:
    """Returns {"allow": n, "deny": n} — counts of tool-scoped permission
    rules (e.g. "Bash(npm:*)") in cc_settings.json, deliberately excluding
    bare directory paths (which ClAuSy itself manages via the Directories
    tab and already tracks separately). Used to detect an external rewrite
    that silently dropped rules ClAuSy doesn't otherwise watch."""
    if not cc_settings:
        return {"allow": 0, "deny": 0}
    try:
        data = _load(cc_settings)
    except ConfigError:
        return {"allow": 0, "deny": 0}
    perms = data.get("permissions", {})
    return {
        "allow": len([p for p in perms.get("allow", []) if not os.path.isabs(p)]),
        "deny": len([p for p in perms.get("deny", []) if not os.path.isabs(p)]),
    }


def find_unsafe_bash_wildcards(cc_settings: str) -> list:
    """Flags Bash allow rules using a bare '*' wildcard instead of the
    safer, documented trailing ':*' prefix-match form. Since '*' matches
    any character — including shell operators like ';', '&&', '|' — a rule
    such as Bash(git *) can in principle be satisfied by a command that
    does something unrelated after a separator. Returns the flagged rule
    strings."""
    if not cc_settings:
        return []
    try:
        data = _load(cc_settings)
    except ConfigError:
        return []
    allow = data.get("permissions", {}).get("allow", [])
    flagged = []
    for rule in allow:
        tool, pattern = _rule_tool_and_pattern(rule)
        if tool != "Bash":
            continue
        if pattern.endswith(":*"):
            continue
        if "*" in pattern:
            flagged.append(rule)
    return flagged


KNOWN_SETTINGS_KEYS = {
    "permissions", "hooks", "model", "env", "apiKeyHelper",
    "cleanupPeriodDays", "includeCoAuthoredBy", "statusLine", "outputStyle",
    "enabledPlugins", "extraKnownMarketplaces", "forceLoginMethod",
    "spinnerTipsEnabled", "editorMode", "autoUpdates", "$schema",
    "teammateDefaultModel",
}


def find_unknown_keys(cc_settings: str) -> list:
    """Returns top-level keys in cc_settings.json that ClAuSy doesn't
    recognize — a possible typo or a renamed/deprecated setting silently
    doing nothing. Claude Code has no officially published settings.json
    schema, so unknown keys are otherwise easy to miss."""
    if not cc_settings:
        return []
    data = _load(cc_settings)
    return sorted(set(data.keys()) - KNOWN_SETTINGS_KEYS)


def get_permission_mode(cc_settings: str) -> str | None:
    """Returns permissions.defaultMode from cc_settings.json, or None if the
    file is missing/unreadable or the key isn't set."""
    if not cc_settings:
        return None
    try:
        data = _load(cc_settings)
    except ConfigError:
        return None
    return data.get("permissions", {}).get("defaultMode")


def get_permission_rules(cc_settings: str) -> tuple:
    """Returns (allow, deny) rule-string lists from permissions in
    cc_settings.json, or ([], []) if unreadable."""
    if not cc_settings:
        return [], []
    try:
        data = _load(cc_settings)
    except ConfigError:
        return [], []
    perms = data.get("permissions", {})
    return list(perms.get("allow", [])), list(perms.get("deny", []))


_RULE_RE = re.compile(r"^([A-Za-z]+)\((.*)\)$")


def _rule_tool_and_pattern(rule: str) -> tuple:
    m = _RULE_RE.match(rule)
    if m:
        return m.group(1), m.group(2)
    return None, rule


def _glob_to_regex(pattern: str):
    """Translates Claude Code's rule-glob syntax to a regex: '**' matches
    anything (including path separators), '*' matches within one path
    segment only."""
    placeholder = "\x00DOUBLESTAR\x00"
    escaped = re.escape(pattern).replace(r"\*\*", placeholder)
    escaped = escaped.replace(r"\*", r"[^/\\]*").replace(placeholder, ".*")
    return re.compile("^" + escaped + "$")


def _rule_matches(rule_pattern: str, target_val: str) -> bool:
    """A trailing ':*' is Claude Code's Bash-rule prefix-match syntax (e.g.
    'npm run build:*' matches any command starting with 'npm run build') —
    distinct from the gitignore-style '*'/'**' glob used elsewhere, and a
    frequent source of confusion (bare 'npm *' vs. correct 'npm:*')."""
    if rule_pattern.endswith(":*"):
        prefix = rule_pattern[:-2]
        return target_val == prefix or target_val.startswith(prefix + " ")
    return bool(_glob_to_regex(rule_pattern).match(target_val))


def simulate_permission(allow: list, deny: list, target: str) -> dict:
    """Tests `target` (e.g. "Bash(npm install)" or a bare absolute path)
    against allow/deny rule lists using Claude Code's matching rules, and
    returns which rule (if any) from each list matched, plus the resulting
    verdict — deny always wins over allow, and no match at all means Claude
    Code will ask. Returns {"verdict", "deny_match", "allow_match"}."""
    target_tool, target_val = _rule_tool_and_pattern(target)

    def find_match(rules):
        for rule in rules:
            rule_tool, rule_pattern = _rule_tool_and_pattern(rule)
            if rule_tool != target_tool:
                continue
            if _rule_matches(rule_pattern, target_val):
                return rule
        return None

    deny_match = find_match(deny)
    allow_match = find_match(allow)
    if deny_match:
        verdict = "deny"
    elif allow_match:
        verdict = "allow"
    else:
        verdict = "ask"
    return {"verdict": verdict, "deny_match": deny_match, "allow_match": allow_match}


def find_allow_deny_conflicts(cc_settings: str) -> set:
    """Returns normalized absolute paths that appear in permissions.deny AND
    in permissions.allow or permissions.additionalDirectories in the same
    cc_settings.json. Claude Code's deny rules always win over allow rules
    on a matching path, so these entries are silently doing nothing."""
    if not cc_settings:
        return set()
    try:
        data = _load(cc_settings)
    except ConfigError:
        return set()
    perms = data.get("permissions", {})
    allow_paths = {os.path.normpath(p) for p in perms.get("allow", []) if os.path.isabs(p)}
    add_paths = {os.path.normpath(p) for p in perms.get("additionalDirectories", [])
                 if os.path.isabs(p)}
    deny_paths = {os.path.normpath(p) for p in perms.get("deny", []) if os.path.isabs(p)}
    return (allow_paths | add_paths) & deny_paths


def _path_set(rules: list) -> set:
    return {os.path.normpath(p) for p in rules if os.path.isabs(p)}


def get_effective_permissions(directory: str, cc_settings: str, cd_config: str) -> dict:
    """Merges permission signals for one directory across every layer
    ClAuSy can see: the global cc_settings.json, that directory's own
    project-level .claude/settings.json (only meaningful if `directory` is
    itself a tracked project root — Claude Code doesn't apply a project's
    settings.json to paths outside it), and claude_desktop_config.json's
    filesystem MCP server. Returns {"global_allow","global_additional",
    "global_deny","project_allow","project_deny","cd_allow","verdict"} —
    verdict is "deny" if any layer denies (deny always wins), else "allow"
    if any layer allows, else "ask" (Claude Code's default)."""
    norm_dir = os.path.normpath(directory) if directory else ""

    global_allow = global_additional = global_deny = False
    if cc_settings:
        try:
            data = _load(cc_settings)
        except ConfigError:
            data = {}
        perms = data.get("permissions", {})
        global_allow = norm_dir in _path_set(perms.get("allow", []))
        global_additional = norm_dir in _path_set(perms.get("additionalDirectories", []))
        global_deny = norm_dir in _path_set(perms.get("deny", []))

    project_allow = project_deny = False
    if directory:
        project_settings = Path(directory) / ".claude" / "settings.json"
        if project_settings.is_file():
            try:
                pdata = _load(str(project_settings))
            except ConfigError:
                pdata = {}
            pperms = pdata.get("permissions", {})
            project_allow = (norm_dir in _path_set(pperms.get("allow", [])) or
                              norm_dir in _path_set(pperms.get("additionalDirectories", [])))
            project_deny = norm_dir in _path_set(pperms.get("deny", []))

    cd_allow = False
    if cd_config:
        try:
            cdata = _load(cd_config)
        except ConfigError:
            cdata = {}
        args = cdata.get("mcpServers", {}).get("filesystem", {}).get("args", [])
        cd_allow = norm_dir in _path_set(args)

    any_deny = global_deny or project_deny
    any_allow = global_allow or global_additional or project_allow or cd_allow
    verdict = "deny" if any_deny else ("allow" if any_allow else "ask")

    return {
        "global_allow": global_allow, "global_additional": global_additional,
        "global_deny": global_deny, "project_allow": project_allow,
        "project_deny": project_deny, "cd_allow": cd_allow, "verdict": verdict,
    }


def summarize_changes(old_entries: list, new_entries: list) -> dict:
    """Compares two entry snapshots ({"path","cc_allow","cc_additional","cd"})
    and returns {"added": [path,...], "removed": [path,...],
    "changed": {path: {key: (old_bool, new_bool)}}} — added/removed
    directories and per-directory permission flips."""
    old_by_path = {e["path"]: e for e in old_entries if e.get("path")}
    new_by_path = {e["path"]: e for e in new_entries if e.get("path")}
    added = sorted(set(new_by_path) - set(old_by_path))
    removed = sorted(set(old_by_path) - set(new_by_path))
    changed = {}
    for path in sorted(set(old_by_path) & set(new_by_path)):
        o, n = old_by_path[path], new_by_path[path]
        diffs = {}
        for key in ("cc_allow", "cc_additional", "cd"):
            old_val, new_val = bool(o.get(key)), bool(n.get(key))
            if old_val != new_val:
                diffs[key] = (old_val, new_val)
        if diffs:
            changed[path] = diffs
    return {"added": added, "removed": removed, "changed": changed}


SENSITIVE_EXACT_SEGMENTS = {"system32", "etc", "boot", "sys", "proc", "root"}
SENSITIVE_SUBSTRINGS = [".ssh", ".aws", ".gnupg", "keychains"]


def is_sensitive_system_path(path: str) -> bool:
    """True if `path` looks like a sensitive OS/credential directory
    (System32, /etc, ~/.ssh, ~/.aws, ...) rather than an ordinary project
    folder — granting broad tool access there is materially higher risk.
    Matches whole path segments for ambiguous short names (so a folder
    named "myroot" isn't flagged) and substrings for distinctive ones."""
    if not path:
        return False
    normalized = path.replace("\\", "/").lower()
    segments = [s for s in normalized.split("/") if s]
    if any(seg in SENSITIVE_EXACT_SEGMENTS for seg in segments):
        return True
    return any(marker in normalized for marker in SENSITIVE_SUBSTRINGS)


def find_overlapping_paths(paths: list) -> set:
    """Returns the subset of `paths` that is an ancestor (or descendant) of
    another path in the same list — e.g. tracking both C:\\proj and
    C:\\proj\\sub is redundant, since permissions on the parent already
    cover the child."""
    norm = [os.path.normpath(p) for p in paths if p]
    overlapping = set()
    for a in norm:
        for b in norm:
            if a == b:
                continue
            try:
                ancestor = os.path.commonpath([a, b]) == a
            except ValueError:
                ancestor = False  # different drives, or a mix of abs/relative
            if ancestor:
                overlapping.add(a)
                overlapping.add(b)
    return overlapping


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
            if os.path.isabs(p):
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
    Entries whose "path" is not an absolute filesystem path are dropped —
    they can never legitimately reach here, but silently writing one out
    (e.g. "." from a stray empty string) would corrupt the config file.
    """
    valid_entries = [e for e in entries if e.get("path") and os.path.isabs(e["path"])]
    cc_allow_dirs = [e["path"] for e in valid_entries if e.get("cc_allow")]
    cc_add_dirs   = [e["path"] for e in valid_entries if e.get("cc_additional")]
    cd_dirs       = [e["path"] for e in valid_entries if e.get("cd")]

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
