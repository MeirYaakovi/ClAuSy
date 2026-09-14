# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased] - 2026-09-14

### Added
- Remember window size and maximized state between launches
- Warn when a CLAUDE.md file's Hebrew content isn't on the first line, so Obsidian can auto-detect RTL
- Word/line count and a "too long" warning on CLAUDE.md files (over 1500 words)
- Warn when a tracked directory with active permissions no longer exists on disk
- Warn when two tracked directories overlap (one is a parent of another)
- Collapsible legend panel on the Directories tab
- Right-click context menu on directory rows: Open, Copy path, Remove
- Search box to filter the Directories list by label or path
- Keyboard shortcuts: Ctrl+Z (undo), Delete (remove selected rows), Ctrl+F (focus search)
- "Report Confusing Config" button that opens a pre-filled GitHub issue

### Changed
- Migrated the UI from plain Tkinter to CustomTkinter
- Added a "CLAUDE.md Map" tab showing every CLAUDE.md/settings/subagent/hook location across tracked projects
- Added an "Agents & Routines" tab listing subagents and hooks found in tracked projects

## [1.0.0]

Initial release. See the [GitHub Release notes](https://github.com/MeirYaakovi/ClAuSy/releases/tag/v1.0.0).
