# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased] - 2026-09-14

### Added
- Remember window size and maximized state between launches
- Warn when a CLAUDE.md file's Hebrew content isn't on the first line, so Obsidian can auto-detect RTL
- Word/line count and a "too long" warning on CLAUDE.md files (based on line count, ~150 lines — matches Claude's actual attention drop-off, not a word count)
- Warn when a tracked directory with active permissions no longer exists on disk
- Warn when two tracked directories overlap (one is a parent of another)
- Collapsible legend panel on the Directories tab
- Right-click context menu on directory rows: Open, Copy path, Remove
- Search box to filter the Directories list by label or path
- Keyboard shortcuts: Ctrl+Z (undo), Delete (remove selected rows), Ctrl+F (focus search)
- "Report Confusing Config" button that opens a pre-filled GitHub issue
- Warn prominently if Claude Code's default permission mode is `bypassPermissions` ("YOLO mode")
- Warn when a path is in both an allow rule and a deny rule (deny always wins, silently)
- One-click "Deny Secrets" preset — adds deny rules for .env, *.pem, *.key, id_rsa, credentials.json, .aws/, .ssh/
- Rotating config backups (last 5 kept) instead of a single overwritten .bak file
- "Restore" button to roll back a config file from its most recent backup
- Detect and surface multiple `claude_desktop_config.json` candidates (Windows Store vs. classic install)
- Flag subagents with vague, missing, or duplicated descriptions
- Warn before Execute if a config file changed on disk externally since ClAuSy last read it
- "What changed" review dialog before Execute writes anything (added/removed directories, permission flips)

### Changed
- Migrated the UI from plain Tkinter to CustomTkinter
- Added a "CLAUDE.md Map" tab showing every CLAUDE.md/settings/subagent/hook location across tracked projects
- Added an "Agents & Routines" tab listing subagents and hooks found in tracked projects

## [1.0.0]

Initial release. See the [GitHub Release notes](https://github.com/MeirYaakovi/ClAuSy/releases/tag/v1.0.0).
