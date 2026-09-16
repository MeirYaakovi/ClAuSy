"""Unit tests for config_manager — reads, writes, validation, and error handling."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import config_manager


class TestReadAllDirs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cc_path = os.path.join(self.tmp, "settings.json")
        self.cd_path = os.path.join(self.tmp, "claude_desktop_config.json")
        self.tracked = self.tmp  # use the temp dir itself as a tracked directory

    def _write(self, path, data):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def test_empty_paths_returns_empty(self):
        result = config_manager.read_all_dirs("", "")
        self.assertEqual(result, {})

    def test_nonexistent_files_return_empty(self):
        result = config_manager.read_all_dirs(
            os.path.join(self.tmp, "no_such.json"),
            os.path.join(self.tmp, "no_such2.json"),
        )
        self.assertEqual(result, {})

    def test_reads_additional_directories(self):
        self._write(self.cc_path, {
            "permissions": {"additionalDirectories": [self.tracked]}
        })
        result = config_manager.read_all_dirs(self.cc_path, "")
        key = os.path.normpath(self.tracked)
        self.assertIn(key, result)
        self.assertTrue(result[key]["cc_additional"])
        self.assertFalse(result[key]["cc_allow"])
        self.assertFalse(result[key]["cd"])

    def test_reads_allow_directories(self):
        self._write(self.cc_path, {
            "permissions": {"allow": [self.tracked, "Bash(rm:*)"]}
        })
        result = config_manager.read_all_dirs(self.cc_path, "")
        key = os.path.normpath(self.tracked)
        self.assertIn(key, result)
        self.assertTrue(result[key]["cc_allow"])
        # non-path allow entries must not appear as directory rows
        self.assertNotIn("Bash(rm:*)", result)

    def test_reads_desktop_mcp_args(self):
        self._write(self.cd_path, {
            "mcpServers": {
                "filesystem": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-filesystem", self.tracked],
                }
            }
        })
        result = config_manager.read_all_dirs("", self.cd_path)
        key = os.path.normpath(self.tracked)
        self.assertIn(key, result)
        self.assertTrue(result[key]["cd"])
        # non-path args must not appear
        self.assertNotIn("-y", result)

    def test_path_in_multiple_sources_merges_flags(self):
        self._write(self.cc_path, {
            "permissions": {
                "allow": [self.tracked],
                "additionalDirectories": [self.tracked],
            }
        })
        result = config_manager.read_all_dirs(self.cc_path, "")
        key = os.path.normpath(self.tracked)
        self.assertTrue(result[key]["cc_allow"])
        self.assertTrue(result[key]["cc_additional"])

    def test_empty_permissions_block_returns_empty(self):
        self._write(self.cc_path, {"theme": "dark"})
        result = config_manager.read_all_dirs(self.cc_path, "")
        self.assertEqual(result, {})

    def test_blank_additional_directory_entry_is_ignored(self):
        # Regression: an empty string in additionalDirectories used to
        # normalize to "." and appear as a bogus phantom directory row.
        self._write(self.cc_path, {
            "permissions": {"additionalDirectories": [self.tracked, ""]}
        })
        result = config_manager.read_all_dirs(self.cc_path, "")
        self.assertNotIn(".", result)
        self.assertEqual(len(result), 1)

    def test_corrupt_cc_json_raises_config_error(self):
        with open(self.cc_path, "w") as f:
            f.write("{ not valid json }")
        with self.assertRaises(config_manager.ConfigError):
            config_manager.read_all_dirs(self.cc_path, "")

    def test_corrupt_cd_json_raises_config_error(self):
        with open(self.cd_path, "w") as f:
            f.write("[1, 2, 3")  # truncated array
        with self.assertRaises(config_manager.ConfigError):
            config_manager.read_all_dirs("", self.cd_path)


class TestApplyChanges(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cc_path = os.path.join(self.tmp, "settings.json")
        self.cd_path = os.path.join(self.tmp, "claude_desktop_config.json")
        self.tracked = self.tmp

    def _load(self, path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _write(self, path, data):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def _entry(self, path=None, cc_allow=False, cc_additional=False, cd=False):
        return {"path": path or self.tracked,
                "cc_allow": cc_allow, "cc_additional": cc_additional, "cd": cd}

    def test_creates_cc_file_when_missing(self):
        entries = [self._entry(cc_additional=True)]
        config_manager.apply_changes(self.cc_path, "", entries)
        self.assertTrue(Path(self.cc_path).exists())
        data = self._load(self.cc_path)
        self.assertIn(self.tracked,
                      data.get("permissions", {}).get("additionalDirectories", []))

    def test_writes_cc_allow(self):
        entries = [self._entry(cc_allow=True)]
        config_manager.apply_changes(self.cc_path, "", entries)
        data = self._load(self.cc_path)
        self.assertIn(self.tracked, data["permissions"]["allow"])

    def test_writes_cc_additional(self):
        entries = [self._entry(cc_additional=True)]
        config_manager.apply_changes(self.cc_path, "", entries)
        data = self._load(self.cc_path)
        self.assertIn(self.tracked, data["permissions"]["additionalDirectories"])

    def test_preserves_existing_non_path_settings(self):
        self._write(self.cc_path, {"theme": "dark", "syntaxHighlightingDisabled": False})
        entries = [self._entry(cc_additional=True)]
        config_manager.apply_changes(self.cc_path, "", entries)
        data = self._load(self.cc_path)
        self.assertEqual(data["theme"], "dark")
        self.assertFalse(data["syntaxHighlightingDisabled"])

    def test_preserves_non_path_allow_entries(self):
        self._write(self.cc_path, {
            "permissions": {"allow": ["Bash(rm:*)", "Bash(git:*)"]}
        })
        entries = [self._entry(cc_allow=True)]
        config_manager.apply_changes(self.cc_path, "", entries)
        data = self._load(self.cc_path)
        allow = data["permissions"]["allow"]
        self.assertIn("Bash(rm:*)", allow)
        self.assertIn("Bash(git:*)", allow)
        self.assertIn(self.tracked, allow)

    def test_removes_path_when_all_toggles_off(self):
        other = os.path.join(self.tmp, "other")
        self._write(self.cc_path, {
            "permissions": {"additionalDirectories": [self.tracked, other]}
        })
        entries = [
            self._entry(self.tracked, cc_additional=False),  # toggled off
            self._entry(other, cc_additional=True),           # still on
        ]
        config_manager.apply_changes(self.cc_path, "", entries)
        data = self._load(self.cc_path)
        dirs = data.get("permissions", {}).get("additionalDirectories", [])
        self.assertNotIn(self.tracked, dirs)
        self.assertIn(other, dirs)

    def test_absent_additionalDirectories_key_when_no_entries(self):
        entries = [self._entry(cc_allow=False, cc_additional=False, cd=False)]
        config_manager.apply_changes(self.cc_path, "", entries)
        data = self._load(self.cc_path)
        self.assertNotIn("additionalDirectories",
                          data.get("permissions", {}))

    def test_desktop_preserves_non_path_args(self):
        old_path = os.path.join(self.tmp, "old_subdir")  # absolute path on this platform
        self._write(self.cd_path, {
            "mcpServers": {
                "filesystem": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-filesystem", old_path],
                }
            }
        })
        entries = [self._entry(cd=True)]
        config_manager.apply_changes("", self.cd_path, entries)
        data = self._load(self.cd_path)
        args = data["mcpServers"]["filesystem"]["args"]
        self.assertIn("-y", args)
        self.assertIn("@modelcontextprotocol/server-filesystem", args)
        self.assertIn(self.tracked, args)
        self.assertNotIn(old_path, args)

    def test_corrupt_cc_raises_config_error(self):
        with open(self.cc_path, "w") as f:
            f.write("{ bad }")
        with self.assertRaises(config_manager.ConfigError):
            config_manager.apply_changes(self.cc_path, "", [self._entry(cc_additional=True)])

    def test_corrupt_cd_raises_config_error(self):
        with open(self.cd_path, "w") as f:
            f.write("not json at all")
        with self.assertRaises(config_manager.ConfigError):
            config_manager.apply_changes("", self.cd_path, [self._entry(cd=True)])

    def test_invalid_path_entry_never_written(self):
        # Regression: a phantom "." entry (or any non-absolute path) that
        # somehow reaches apply_changes must never be persisted — it would
        # silently overwrite/corrupt a real entry's position in the array.
        self._write(self.cc_path, {
            "permissions": {"additionalDirectories": [self.tracked]}
        })
        entries = [
            self._entry(self.tracked, cc_additional=True),
            {"path": ".", "cc_allow": False, "cc_additional": True, "cd": False},
            {"path": "",  "cc_allow": False, "cc_additional": True, "cd": False},
        ]
        config_manager.apply_changes(self.cc_path, "", entries)
        data = self._load(self.cc_path)
        dirs = data["permissions"]["additionalDirectories"]
        self.assertNotIn(".", dirs)
        self.assertEqual(dirs, [self.tracked])

    def test_progress_callback_called(self):
        calls = []
        config_manager.apply_changes(self.cc_path, "", [], progress_cb=calls.append)
        self.assertIn(0,   calls)
        self.assertIn(100, calls)


class TestValidatePath(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def _write(self, name, data):
        p = os.path.join(self.tmp, name)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return p

    def test_empty_path_is_not_ok(self):
        ok, _ = config_manager.validate_path("", "cc")
        self.assertFalse(ok)

    def test_nonexistent_file_is_not_ok(self):
        ok, msg = config_manager.validate_path(
            os.path.join(self.tmp, "missing.json"), "cc")
        self.assertFalse(ok)
        self.assertIn("not found", msg.lower())

    def test_corrupt_json_is_not_ok(self):
        p = os.path.join(self.tmp, "bad.json")
        with open(p, "w") as f:
            f.write("{broken")
        ok, msg = config_manager.validate_path(p, "cc")
        self.assertFalse(ok)
        self.assertTrue(len(msg) > 0)

    def test_valid_cc_file_is_ok(self):
        p = self._write("settings.json", {"permissions": {}})
        ok, msg = config_manager.validate_path(p, "cc")
        self.assertTrue(ok)
        self.assertEqual(msg, "")

    def test_valid_cd_file_is_ok(self):
        p = self._write("cd.json", {"mcpServers": {}})
        ok, msg = config_manager.validate_path(p, "cd")
        self.assertTrue(ok)
        self.assertEqual(msg, "")

    def test_empty_json_object_is_ok(self):
        p = self._write("empty.json", {})
        ok, _ = config_manager.validate_path(p, "cc")
        self.assertTrue(ok)


class TestBackupRotation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "settings.json")

    def test_no_backups_for_a_file_that_never_existed(self):
        config_manager._save(self.path, {"a": 1})
        self.assertEqual(config_manager.list_backups(self.path), [])

    def test_first_overwrite_creates_one_backup(self):
        config_manager._save(self.path, {"a": 1})
        config_manager._save(self.path, {"a": 2})
        backups = config_manager.list_backups(self.path)
        self.assertEqual(len(backups), 1)
        with open(backups[0], encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"a": 1})

    def test_keeps_only_last_N_backups(self):
        config_manager._save(self.path, {"n": 0})
        for i in range(1, config_manager.BACKUP_KEEP_COUNT + 3):
            config_manager._save(self.path, {"n": i})
        backups = config_manager.list_backups(self.path)
        self.assertEqual(len(backups), config_manager.BACKUP_KEEP_COUNT)

    def test_list_backups_oldest_first(self):
        config_manager._save(self.path, {"n": 0})
        config_manager._save(self.path, {"n": 1})
        config_manager._save(self.path, {"n": 2})
        backups = config_manager.list_backups(self.path)
        contents = []
        for b in backups:
            with open(b, encoding="utf-8") as f:
                contents.append(json.load(f)["n"])
        self.assertEqual(contents, sorted(contents))

    def test_no_backup_dir_returns_empty(self):
        missing = os.path.join(self.tmp, "nosuchdir", "settings.json")
        self.assertEqual(config_manager.list_backups(missing), [])

    def test_restore_with_no_backups_returns_false(self):
        self.assertFalse(config_manager.restore_last_backup(self.path))

    def test_restore_brings_back_previous_content(self):
        config_manager._save(self.path, {"n": 0})
        config_manager._save(self.path, {"n": 1})
        ok = config_manager.restore_last_backup(self.path)
        self.assertTrue(ok)
        with open(self.path, encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"n": 0})

    def test_restore_is_itself_reversible(self):
        config_manager._save(self.path, {"n": 0})
        config_manager._save(self.path, {"n": 1})
        config_manager.restore_last_backup(self.path)  # back to n=0
        config_manager.restore_last_backup(self.path)  # back to n=1
        with open(self.path, encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"n": 1})


class TestAddDenyPatterns(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "settings.json")

    def _write(self, data):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return self.path

    def test_blank_path_is_noop(self):
        self.assertEqual(config_manager.add_deny_patterns("", ["Read(**/.env)"]), 0)

    def test_adds_new_patterns_to_missing_deny_key(self):
        p = self._write({"permissions": {"allow": ["C:\\a"]}})
        added = config_manager.add_deny_patterns(p, ["Read(**/.env)", "Read(**/*.pem)"])
        self.assertEqual(added, 2)
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["permissions"]["deny"], ["Read(**/.env)", "Read(**/*.pem)"])
        self.assertEqual(data["permissions"]["allow"], ["C:\\a"])  # untouched

    def test_does_not_duplicate_existing_patterns(self):
        p = self._write({"permissions": {"deny": ["Read(**/.env)"]}})
        added = config_manager.add_deny_patterns(p, ["Read(**/.env)", "Read(**/*.pem)"])
        self.assertEqual(added, 1)
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["permissions"]["deny"], ["Read(**/.env)", "Read(**/*.pem)"])

    def test_all_already_present_writes_nothing_new(self):
        p = self._write({"permissions": {"deny": ["Read(**/.env)"]}})
        added = config_manager.add_deny_patterns(p, ["Read(**/.env)"])
        self.assertEqual(added, 0)

    def test_creates_file_if_missing(self):
        p = os.path.join(self.tmp, "new_settings.json")
        added = config_manager.add_deny_patterns(p, ["Read(**/.env)"])
        self.assertEqual(added, 1)
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["permissions"]["deny"], ["Read(**/.env)"])

    def test_corrupt_file_raises_config_error(self):
        with open(self.path, "w") as f:
            f.write("{broken")
        with self.assertRaises(config_manager.ConfigError):
            config_manager.add_deny_patterns(self.path, ["Read(**/.env)"])


class TestFindCdConfigCandidates(unittest.TestCase):
    def test_candidate_paths_include_classic_and_macos_locations(self):
        paths = config_manager._cd_config_candidate_paths(
            "C:\\AppData", "C:\\Local", Path("C:\\Users\\x"))
        strs = [str(p) for p in paths]
        self.assertIn(str(Path("C:\\AppData") / "Claude" / "claude_desktop_config.json"), strs)
        self.assertIn(
            str(Path("C:\\Users\\x") / "Library" / "Application Support" /
                "Claude" / "claude_desktop_config.json"),
            strs)

    def test_includes_store_package_installs(self):
        tmp = tempfile.mkdtemp()
        (Path(tmp) / "Packages" / "Claude_abc123").mkdir(parents=True)
        paths = config_manager._cd_config_candidate_paths("C:\\AppData", tmp, Path("C:\\Users\\x"))
        self.assertTrue(any("Claude_abc123" in str(p) for p in paths))

    def test_only_existing_paths_are_returned(self):
        tmp = tempfile.mkdtemp()
        appdata = os.path.join(tmp, "AppData")
        classic_file = Path(appdata) / "Claude" / "claude_desktop_config.json"
        classic_file.parent.mkdir(parents=True)
        classic_file.write_text("{}")
        localappdata = os.path.join(tmp, "Local")  # no Packages dir here
        with mock.patch.dict(os.environ, {"APPDATA": appdata, "LOCALAPPDATA": localappdata}):
            with mock.patch.object(config_manager.Path, "home",
                                   return_value=Path(tmp) / "home"):
                result = config_manager.find_cd_config_candidates()
        self.assertEqual(result, [str(classic_file)])

    def test_multiple_installs_all_returned(self):
        tmp = tempfile.mkdtemp()
        appdata = os.path.join(tmp, "AppData")
        classic_file = Path(appdata) / "Claude" / "claude_desktop_config.json"
        classic_file.parent.mkdir(parents=True)
        classic_file.write_text("{}")
        localappdata = os.path.join(tmp, "Local")
        store_file = (Path(localappdata) / "Packages" / "Claude_xyz" /
                      "LocalCache" / "Roaming" / "Claude" / "claude_desktop_config.json")
        store_file.parent.mkdir(parents=True)
        store_file.write_text("{}")
        with mock.patch.dict(os.environ, {"APPDATA": appdata, "LOCALAPPDATA": localappdata}):
            with mock.patch.object(config_manager.Path, "home",
                                   return_value=Path(tmp) / "home"):
                result = config_manager.find_cd_config_candidates()
        self.assertEqual(set(result), {str(classic_file), str(store_file)})

    def test_auto_detect_picks_first_candidate(self):
        tmp = tempfile.mkdtemp()
        appdata = os.path.join(tmp, "AppData")
        classic_file = Path(appdata) / "Claude" / "claude_desktop_config.json"
        classic_file.parent.mkdir(parents=True)
        classic_file.write_text("{}")
        localappdata = os.path.join(tmp, "Local")
        with mock.patch.dict(os.environ, {"APPDATA": appdata, "LOCALAPPDATA": localappdata}):
            with mock.patch.object(config_manager.Path, "home",
                                   return_value=Path(tmp) / "home"):
                result = config_manager.auto_detect()
        self.assertEqual(result["cd_config"], str(classic_file))


class TestFileFingerprint(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "settings.json")

    def test_missing_file_returns_none(self):
        self.assertIsNone(config_manager.file_fingerprint(self.path))

    def test_existing_file_returns_tuple(self):
        with open(self.path, "w") as f:
            f.write("{}")
        fp = config_manager.file_fingerprint(self.path)
        self.assertIsInstance(fp, tuple)
        self.assertEqual(len(fp), 2)

    def test_changed_content_changes_fingerprint(self):
        with open(self.path, "w") as f:
            f.write("{}")
        fp1 = config_manager.file_fingerprint(self.path)
        with open(self.path, "w") as f:
            f.write("{\"a\": 1}")
        fp2 = config_manager.file_fingerprint(self.path)
        self.assertNotEqual(fp1, fp2)

    def test_unchanged_file_has_stable_fingerprint(self):
        with open(self.path, "w") as f:
            f.write("{}")
        fp1 = config_manager.file_fingerprint(self.path)
        fp2 = config_manager.file_fingerprint(self.path)
        self.assertEqual(fp1, fp2)


class TestGetPermissionMode(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def _write(self, data):
        p = os.path.join(self.tmp, "settings.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return p

    def test_blank_path_returns_none(self):
        self.assertIsNone(config_manager.get_permission_mode(""))

    def test_missing_file_returns_none(self):
        self.assertIsNone(config_manager.get_permission_mode(
            os.path.join(self.tmp, "missing.json")))

    def test_no_default_mode_returns_none(self):
        p = self._write({"permissions": {}})
        self.assertIsNone(config_manager.get_permission_mode(p))

    def test_reads_default_mode(self):
        p = self._write({"permissions": {"defaultMode": "bypassPermissions"}})
        self.assertEqual(config_manager.get_permission_mode(p), "bypassPermissions")

    def test_corrupt_file_returns_none(self):
        p = os.path.join(self.tmp, "bad.json")
        with open(p, "w") as f:
            f.write("{broken")
        self.assertIsNone(config_manager.get_permission_mode(p))


class TestIsZeroDenyBypassCombo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def _write(self, data):
        p = os.path.join(self.tmp, "settings.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return p

    def test_blank_path_is_false(self):
        self.assertFalse(config_manager.is_zero_deny_bypass_combo(""))

    def test_bypass_with_no_deny_key_is_true(self):
        p = self._write({"permissions": {"defaultMode": "bypassPermissions"}})
        self.assertTrue(config_manager.is_zero_deny_bypass_combo(p))

    def test_bypass_with_empty_deny_list_is_true(self):
        p = self._write({"permissions": {"defaultMode": "bypassPermissions", "deny": []}})
        self.assertTrue(config_manager.is_zero_deny_bypass_combo(p))

    def test_bypass_with_nonempty_deny_is_false(self):
        p = self._write({"permissions": {"defaultMode": "bypassPermissions",
                                          "deny": ["Read(**/.env)"]}})
        self.assertFalse(config_manager.is_zero_deny_bypass_combo(p))

    def test_non_bypass_mode_is_false(self):
        p = self._write({"permissions": {"defaultMode": "acceptEdits"}})
        self.assertFalse(config_manager.is_zero_deny_bypass_combo(p))

    def test_missing_file_is_false(self):
        self.assertFalse(config_manager.is_zero_deny_bypass_combo(
            os.path.join(self.tmp, "missing.json")))

    def test_corrupt_file_is_false(self):
        p = os.path.join(self.tmp, "bad.json")
        with open(p, "w") as f:
            f.write("{broken")
        self.assertFalse(config_manager.is_zero_deny_bypass_combo(p))


class TestFindAllowDenyConflicts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "settings.json")

    def _write(self, permissions):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"permissions": permissions}, f)
        return self.path

    def test_blank_path_returns_empty(self):
        self.assertEqual(config_manager.find_allow_deny_conflicts(""), set())

    def test_no_conflict_returns_empty(self):
        p = self._write({"allow": [r"C:\a"], "deny": [r"C:\b"]})
        self.assertEqual(config_manager.find_allow_deny_conflicts(p), set())

    def test_allow_and_deny_same_path_flagged(self):
        p = self._write({"allow": [r"C:\a"], "deny": [r"C:\a"]})
        self.assertEqual(config_manager.find_allow_deny_conflicts(p),
                         {os.path.normpath(r"C:\a")})

    def test_additional_directories_and_deny_same_path_flagged(self):
        p = self._write({"additionalDirectories": [r"C:\a"], "deny": [r"C:\a"]})
        self.assertEqual(config_manager.find_allow_deny_conflicts(p),
                         {os.path.normpath(r"C:\a")})

    def test_relative_deny_patterns_ignored(self):
        p = self._write({"allow": [r"C:\a"], "deny": ["Bash(rm:*)"]})
        self.assertEqual(config_manager.find_allow_deny_conflicts(p), set())

    def test_corrupt_file_returns_empty(self):
        with open(self.path, "w") as f:
            f.write("{broken")
        self.assertEqual(config_manager.find_allow_deny_conflicts(self.path), set())


class TestSummarizeChanges(unittest.TestCase):
    def test_no_changes(self):
        entries = [{"path": r"C:\a", "cc_allow": True}]
        result = config_manager.summarize_changes(entries, entries)
        self.assertEqual(result, {"added": [], "removed": [], "changed": {}})

    def test_added_directory(self):
        old = [{"path": r"C:\a"}]
        new = [{"path": r"C:\a"}, {"path": r"C:\b"}]
        result = config_manager.summarize_changes(old, new)
        self.assertEqual(result["added"], [r"C:\b"])
        self.assertEqual(result["removed"], [])

    def test_removed_directory(self):
        old = [{"path": r"C:\a"}, {"path": r"C:\b"}]
        new = [{"path": r"C:\a"}]
        result = config_manager.summarize_changes(old, new)
        self.assertEqual(result["removed"], [r"C:\b"])

    def test_permission_flip_detected(self):
        old = [{"path": r"C:\a", "cc_allow": False, "cc_additional": False, "cd": False}]
        new = [{"path": r"C:\a", "cc_allow": True, "cc_additional": False, "cd": False}]
        result = config_manager.summarize_changes(old, new)
        self.assertEqual(result["changed"], {r"C:\a": {"cc_allow": (False, True)}})

    def test_multiple_flips_on_same_path(self):
        old = [{"path": r"C:\a", "cc_allow": False, "cc_additional": True, "cd": False}]
        new = [{"path": r"C:\a", "cc_allow": True, "cc_additional": False, "cd": False}]
        result = config_manager.summarize_changes(old, new)
        self.assertEqual(result["changed"][r"C:\a"],
                         {"cc_allow": (False, True), "cc_additional": (True, False)})

    def test_unset_keys_default_to_false(self):
        old = [{"path": r"C:\a"}]
        new = [{"path": r"C:\a", "cc_allow": True}]
        result = config_manager.summarize_changes(old, new)
        self.assertEqual(result["changed"], {r"C:\a": {"cc_allow": (False, True)}})


class TestFindOverlappingPaths(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.parent = os.path.join(self.tmp, "proj")
        self.child = os.path.join(self.tmp, "proj", "sub")
        self.sibling = os.path.join(self.tmp, "other")

    def test_no_overlap_returns_empty(self):
        result = config_manager.find_overlapping_paths([self.parent, self.sibling])
        self.assertEqual(result, set())

    def test_parent_and_child_flagged(self):
        result = config_manager.find_overlapping_paths([self.parent, self.child])
        self.assertEqual(result, {os.path.normpath(self.parent), os.path.normpath(self.child)})

    def test_unrelated_sibling_not_flagged(self):
        result = config_manager.find_overlapping_paths([self.parent, self.child, self.sibling])
        self.assertNotIn(os.path.normpath(self.sibling), result)

    def test_similar_prefix_not_treated_as_overlap(self):
        # "proj" is not an ancestor of "proj2" just because it's a string prefix
        proj2 = os.path.join(self.tmp, "proj2")
        result = config_manager.find_overlapping_paths([self.parent, proj2])
        self.assertEqual(result, set())

    def test_blank_paths_ignored(self):
        result = config_manager.find_overlapping_paths([self.parent, "", None])
        self.assertEqual(result, set())

    def test_single_path_has_no_overlap(self):
        result = config_manager.find_overlapping_paths([self.parent])
        self.assertEqual(result, set())


class TestFindUnknownKeys(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def _write(self, data):
        p = os.path.join(self.tmp, "settings.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return p

    def test_blank_path_returns_empty(self):
        self.assertEqual(config_manager.find_unknown_keys(""), [])

    def test_all_known_keys_returns_empty(self):
        p = self._write({"permissions": {}, "hooks": {}, "model": "opus"})
        self.assertEqual(config_manager.find_unknown_keys(p), [])

    def test_flags_unknown_key(self):
        p = self._write({"permissions": {}, "totallyMadeUpKey": True})
        self.assertEqual(config_manager.find_unknown_keys(p), ["totallyMadeUpKey"])

    def test_missing_file_returns_empty(self):
        p = os.path.join(self.tmp, "missing.json")
        self.assertEqual(config_manager.find_unknown_keys(p), [])


class TestFindGitignoredSecrets(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def _gitignore(self, lines):
        with open(os.path.join(self.tmp, ".gitignore"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    def test_no_gitignore_returns_empty(self):
        self.assertEqual(config_manager.find_gitignored_secrets(self.tmp), [])

    def test_finds_ignored_env_file(self):
        self._gitignore([".env"])
        with open(os.path.join(self.tmp, ".env"), "w") as f:
            f.write("SECRET=1")
        result = config_manager.find_gitignored_secrets(self.tmp)
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0].endswith(".env"))

    def test_secret_file_not_ignored_is_skipped(self):
        self._gitignore(["node_modules/"])
        with open(os.path.join(self.tmp, ".env"), "w") as f:
            f.write("SECRET=1")
        self.assertEqual(config_manager.find_gitignored_secrets(self.tmp), [])

    def test_finds_pem_via_glob_pattern(self):
        self._gitignore(["*.pem"])
        with open(os.path.join(self.tmp, "server.pem"), "w") as f:
            f.write("---KEY---")
        result = config_manager.find_gitignored_secrets(self.tmp)
        self.assertEqual(len(result), 1)

    def test_missing_directory_returns_empty(self):
        self.assertEqual(
            config_manager.find_gitignored_secrets(os.path.join(self.tmp, "nope")), [])


class TestFindMcpExposedSecrets(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def _write(self, data):
        p = os.path.join(self.tmp, "mcp.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return p

    def test_blank_path_returns_empty(self):
        self.assertEqual(config_manager.find_mcp_exposed_secrets(""), [])

    def test_hardcoded_api_key_flagged(self):
        p = self._write({"mcpServers": {"github": {"env": {"API_KEY": "ghp_abc123realvalue"}}}})
        result = config_manager.find_mcp_exposed_secrets(p)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["server"], "github")
        self.assertEqual(result[0]["env_key"], "API_KEY")

    def test_var_reference_form_not_flagged(self):
        p = self._write({"mcpServers": {"github": {"env": {"API_KEY": "${GITHUB_TOKEN}"}}}})
        self.assertEqual(config_manager.find_mcp_exposed_secrets(p), [])

    def test_bare_var_reference_not_flagged(self):
        p = self._write({"mcpServers": {"github": {"env": {"API_KEY": "$GITHUB_TOKEN"}}}})
        self.assertEqual(config_manager.find_mcp_exposed_secrets(p), [])

    def test_non_secret_key_name_not_flagged(self):
        p = self._write({"mcpServers": {"fs": {"env": {"LOG_LEVEL": "debug"}}}})
        self.assertEqual(config_manager.find_mcp_exposed_secrets(p), [])

    def test_empty_value_not_flagged(self):
        p = self._write({"mcpServers": {"github": {"env": {"API_KEY": ""}}}})
        self.assertEqual(config_manager.find_mcp_exposed_secrets(p), [])

    def test_no_env_block_not_flagged(self):
        p = self._write({"mcpServers": {"github": {"command": "npx"}}})
        self.assertEqual(config_manager.find_mcp_exposed_secrets(p), [])

    def test_corrupt_file_returns_empty(self):
        p = os.path.join(self.tmp, "bad.json")
        with open(p, "w") as f:
            f.write("{broken")
        self.assertEqual(config_manager.find_mcp_exposed_secrets(p), [])


class TestGetPermissionRules(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def _write(self, data):
        p = os.path.join(self.tmp, "settings.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return p

    def test_blank_path_returns_empty_lists(self):
        self.assertEqual(config_manager.get_permission_rules(""), ([], []))

    def test_reads_allow_and_deny(self):
        p = self._write({"permissions": {"allow": ["Bash(npm:*)"], "deny": ["Read(**/.env)"]}})
        self.assertEqual(config_manager.get_permission_rules(p),
                          (["Bash(npm:*)"], ["Read(**/.env)"]))

    def test_corrupt_file_returns_empty_lists(self):
        p = os.path.join(self.tmp, "bad.json")
        with open(p, "w") as f:
            f.write("{broken")
        self.assertEqual(config_manager.get_permission_rules(p), ([], []))


class TestSimulatePermission(unittest.TestCase):
    def test_deny_wins_over_allow(self):
        result = config_manager.simulate_permission(
            ["Bash(npm:*)"], ["Bash(npm:*)"], "Bash(npm install)")
        self.assertEqual(result["verdict"], "deny")

    def test_allow_matches_wildcard_rule(self):
        result = config_manager.simulate_permission(
            ["Bash(npm:*)"], [], "Bash(npm install)")
        self.assertEqual(result["verdict"], "allow")
        self.assertEqual(result["allow_match"], "Bash(npm:*)")

    def test_no_match_falls_back_to_ask(self):
        result = config_manager.simulate_permission(
            ["Bash(npm:*)"], [], "Bash(rm -rf /)")
        self.assertEqual(result["verdict"], "ask")

    def test_double_star_matches_any_depth(self):
        result = config_manager.simulate_permission(
            [], ["Read(**/.env)"], "Read(a/b/c/.env)")
        self.assertEqual(result["verdict"], "deny")

    def test_single_star_does_not_cross_path_separator(self):
        result = config_manager.simulate_permission(
            [], ["Read(*/.env)"], "Read(a/b/.env)")
        self.assertEqual(result["verdict"], "ask")

    def test_bare_absolute_path_rule(self):
        result = config_manager.simulate_permission(
            ["/home/user/project"], [], "/home/user/project")
        self.assertEqual(result["verdict"], "allow")

    def test_different_tool_does_not_match(self):
        result = config_manager.simulate_permission(
            ["Read(**/.env)"], [], "Bash(cat .env)")
        self.assertEqual(result["verdict"], "ask")

    def test_bash_colon_star_prefix_syntax(self):
        result = config_manager.simulate_permission(
            ["Bash(npm run build:*)"], [], "Bash(npm run build --watch)")
        self.assertEqual(result["verdict"], "allow")

    def test_bash_colon_star_does_not_match_unrelated_command(self):
        result = config_manager.simulate_permission(
            ["Bash(npm run build:*)"], [], "Bash(npm run test)")
        self.assertEqual(result["verdict"], "ask")


class TestIsSensitiveSystemPath(unittest.TestCase):
    def test_blank_path_not_sensitive(self):
        self.assertFalse(config_manager.is_sensitive_system_path(""))

    def test_windows_system32_flagged(self):
        self.assertTrue(config_manager.is_sensitive_system_path(r"C:\Windows\System32"))

    def test_etc_flagged(self):
        self.assertTrue(config_manager.is_sensitive_system_path("/etc"))

    def test_ssh_dir_flagged(self):
        self.assertTrue(config_manager.is_sensitive_system_path("/home/user/.ssh"))

    def test_aws_dir_flagged(self):
        self.assertTrue(config_manager.is_sensitive_system_path(r"C:\Users\me\.aws"))

    def test_ordinary_project_path_not_flagged(self):
        self.assertFalse(config_manager.is_sensitive_system_path(r"C:\meir\Projects\ClAuSy"))

    def test_folder_named_myroot_not_falsely_flagged(self):
        self.assertFalse(config_manager.is_sensitive_system_path("/home/user/myroot"))

    def test_folder_literally_named_root_flagged(self):
        self.assertTrue(config_manager.is_sensitive_system_path("/root"))


class TestCountNonPathRules(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def _write(self, data):
        p = os.path.join(self.tmp, "settings.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return p

    def test_blank_path_returns_zeros(self):
        self.assertEqual(config_manager.count_non_path_rules(""), {"allow": 0, "deny": 0})

    def test_counts_tool_rules_excluding_bare_paths(self):
        abs_path = os.path.join(self.tmp, "project")
        p = self._write({"permissions": {
            "allow": ["Bash(npm:*)", "Read(**/.env)", abs_path],
            "deny": ["Read(**/*.pem)"],
        }})
        self.assertEqual(config_manager.count_non_path_rules(p), {"allow": 2, "deny": 1})

    def test_corrupt_file_returns_zeros(self):
        p = os.path.join(self.tmp, "bad.json")
        with open(p, "w") as f:
            f.write("{broken")
        self.assertEqual(config_manager.count_non_path_rules(p), {"allow": 0, "deny": 0})


class TestFindUnsafeBashWildcards(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def _write(self, allow):
        p = os.path.join(self.tmp, "settings.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"permissions": {"allow": allow}}, f)
        return p

    def test_bare_star_flagged(self):
        p = self._write(["Bash(git *)"])
        self.assertEqual(config_manager.find_unsafe_bash_wildcards(p), ["Bash(git *)"])

    def test_colon_star_not_flagged(self):
        p = self._write(["Bash(git status:*)"])
        self.assertEqual(config_manager.find_unsafe_bash_wildcards(p), [])

    def test_non_bash_rule_not_flagged(self):
        p = self._write(["Read(**/*.env)"])
        self.assertEqual(config_manager.find_unsafe_bash_wildcards(p), [])

    def test_no_wildcard_not_flagged(self):
        p = self._write(["Bash(npm install)"])
        self.assertEqual(config_manager.find_unsafe_bash_wildcards(p), [])

    def test_blank_path_returns_empty(self):
        self.assertEqual(config_manager.find_unsafe_bash_wildcards(""), [])


class TestGetEffectivePermissions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.target = os.path.join(self.tmp, "project")
        os.makedirs(self.target)

    def _write_cc(self, perms):
        p = os.path.join(self.tmp, "cc_settings.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"permissions": perms}, f)
        return p

    def test_no_signals_anywhere_is_ask(self):
        result = config_manager.get_effective_permissions(self.target, "", "")
        self.assertEqual(result["verdict"], "ask")

    def test_global_allow_gives_allow_verdict(self):
        cc = self._write_cc({"allow": [self.target]})
        result = config_manager.get_effective_permissions(self.target, cc, "")
        self.assertTrue(result["global_allow"])
        self.assertEqual(result["verdict"], "allow")

    def test_global_deny_wins_over_global_allow(self):
        cc = self._write_cc({"allow": [self.target], "deny": [self.target]})
        result = config_manager.get_effective_permissions(self.target, cc, "")
        self.assertEqual(result["verdict"], "deny")

    def test_project_level_allow_detected(self):
        claude_dir = os.path.join(self.target, ".claude")
        os.makedirs(claude_dir)
        with open(os.path.join(claude_dir, "settings.json"), "w", encoding="utf-8") as f:
            json.dump({"permissions": {"additionalDirectories": [self.target]}}, f)
        result = config_manager.get_effective_permissions(self.target, "", "")
        self.assertTrue(result["project_allow"])
        self.assertEqual(result["verdict"], "allow")

    def test_project_deny_wins_over_global_allow(self):
        cc = self._write_cc({"allow": [self.target]})
        claude_dir = os.path.join(self.target, ".claude")
        os.makedirs(claude_dir)
        with open(os.path.join(claude_dir, "settings.json"), "w", encoding="utf-8") as f:
            json.dump({"permissions": {"deny": [self.target]}}, f)
        result = config_manager.get_effective_permissions(self.target, cc, "")
        self.assertEqual(result["verdict"], "deny")

    def test_cd_allow_detected(self):
        cd = os.path.join(self.tmp, "cd_config.json")
        with open(cd, "w", encoding="utf-8") as f:
            json.dump({"mcpServers": {"filesystem": {"args": [self.target]}}}, f)
        result = config_manager.get_effective_permissions(self.target, "", cd)
        self.assertTrue(result["cd_allow"])
        self.assertEqual(result["verdict"], "allow")

    def test_unrelated_directory_not_allowed(self):
        cc = self._write_cc({"allow": [self.target]})
        other = os.path.join(self.tmp, "other")
        result = config_manager.get_effective_permissions(other, cc, "")
        self.assertEqual(result["verdict"], "ask")


if __name__ == "__main__":
    unittest.main(verbosity=2)
