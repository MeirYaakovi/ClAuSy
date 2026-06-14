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
