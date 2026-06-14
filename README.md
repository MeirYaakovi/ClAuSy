# ClAuSy — Claude Paths Manager

![Python](https://img.shields.io/badge/Python-3.9+-blue?logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS-lightgrey)
![Dependencies](https://img.shields.io/badge/Dependencies-none-brightgreen)

A dark-themed desktop app that manages which directories **Claude Code** and **Claude Desktop** are authorized to access — all from a single UI, without manually editing JSON files.

---

## Features

- **Unified list** — aggregates every authorized path from all Claude config sources
- **Per-source toggles** — independently enable or disable each path for:
  - 🔴 **C (red)** — Claude Code `permissions.allow`
  - 🟢 **C (green)** — Claude Code `permissions.additionalDirectories`
  - 🔵 **D (blue)** — Claude Desktop MCP filesystem server (`args`)
- **List & Thumbnail views** — choose your preferred layout
- **Sort** — by label name (A→Z / Z→A) or directory creation date
- **Multi-select + column-header toggle** — check rows, then click a column header circle to set all at once
- **Undo** — 30-level undo stack for toggle changes before committing
- **Safe JSON patching** — only touches the relevant key in each config file; never breaks surrounding content
- **Auto-detect** — finds your Claude config files automatically on first launch
- **No hardcoded paths or secrets** — all config locations are entered by you at runtime

---

## Requirements

- Python 3.9+
- `tkinter` (included with standard Python on Windows and macOS)
- No third-party packages needed

---

## Setup

```bash
git clone https://github.com/MeirYaakovi/ClAuSy.git
cd ClAuSy
python main.py
```

---

## Usage

1. **Settings tab** → click **Auto-Detect** to find your config files, then **Save & Reload**
2. **Directories tab** — all authorized paths appear in the list with their current toggle states
3. Toggle the **C / D** circles to enable or disable each path per Claude product
4. Use **↩ Undo** to step back if needed
5. Click **▶ Execute Changes** to write the changes to your config files

---

## Config files managed

| Icon | Color | Config file | JSON key |
|------|-------|-------------|----------|
| C | 🔴 Red | `~/.claude/settings.json` | `permissions.allow` |
| C | 🟢 Green | `~/.claude/settings.json` | `permissions.additionalDirectories` |
| D | 🔵 Blue | `claude_desktop_config.json` | `mcpServers.filesystem.args` |

---

## App settings

ClAuSy saves its own UI preferences (config file paths, directory labels, view/sort mode) to:

```
~/.clauSy/settings.json
```

This file lives outside the repository and is never committed. It contains no secrets — only file paths and UI preferences.

---

## Privacy

No personal paths, tokens, or secrets are ever committed to this repository. All config file locations are entered by the user at runtime.
