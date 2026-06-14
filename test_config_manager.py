"""Unit tests for config_manager — reads, writes, validation, and error handling."""
import json
import os
import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
