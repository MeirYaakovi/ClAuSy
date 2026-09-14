"""Unit tests for claude_meta — CLAUDE.md / agents / hooks discovery."""
import json
import os
import tempfile
import unittest
from pathlib import Path

import claude_meta


class TestFindClaudeMdFiles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_global_entry_always_present(self):
        result = claude_meta.find_claude_md_files([])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["scope"], "global")

    def test_project_without_claude_md_marked_not_exists(self):
        result = claude_meta.find_claude_md_files([self.tmp])
        proj = [r for r in result if r["scope"] == "project"][0]
        self.assertFalse(proj["exists"])
        self.assertEqual(proj["path"], str(Path(self.tmp) / "CLAUDE.md"))

    def test_project_with_claude_md_marked_exists(self):
        (Path(self.tmp) / "CLAUDE.md").write_text("# hi", encoding="utf-8")
        result = claude_meta.find_claude_md_files([self.tmp])
        proj = [r for r in result if r["scope"] == "project"][0]
        self.assertTrue(proj["exists"])

    def test_duplicate_dirs_deduplicated(self):
        result = claude_meta.find_claude_md_files([self.tmp, self.tmp])
        self.assertEqual(len(result), 2)  # global + one project entry

    def test_blank_dirs_skipped(self):
        result = claude_meta.find_claude_md_files(["", None, self.tmp])
        self.assertEqual(len(result), 2)


class TestFindAgents(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.agents_dir = Path(self.tmp) / ".claude" / "agents"
        self.agents_dir.mkdir(parents=True)

    def test_no_agents_dir_returns_empty_for_that_project(self):
        empty_dir = tempfile.mkdtemp()
        result = claude_meta.find_agents([empty_dir])
        self.assertEqual([a for a in result if a["scope"] == "project"], [])

    def test_parses_frontmatter_name_and_description(self):
        (self.agents_dir / "reviewer.md").write_text(
            "---\nname: reviewer\ndescription: Reviews code for bugs\n---\nBody text.",
            encoding="utf-8",
        )
        result = claude_meta.find_agents([self.tmp])
        project_agents = [a for a in result if a["scope"] == "project"]
        self.assertEqual(len(project_agents), 1)
        self.assertEqual(project_agents[0]["name"], "reviewer")
        self.assertEqual(project_agents[0]["description"], "Reviews code for bugs")

    def test_missing_frontmatter_falls_back_to_filename(self):
        (self.agents_dir / "plain.md").write_text("Just some text.", encoding="utf-8")
        result = claude_meta.find_agents([self.tmp])
        project_agents = [a for a in result if a["scope"] == "project"]
        self.assertEqual(project_agents[0]["name"], "plain")
        self.assertEqual(project_agents[0]["description"], "")

    def test_quoted_frontmatter_values_are_unquoted(self):
        (self.agents_dir / "quoted.md").write_text(
            '---\nname: "quoted-agent"\ndescription: \'Has quotes\'\n---\n',
            encoding="utf-8",
        )
        result = claude_meta.find_agents([self.tmp])
        project_agents = [a for a in result if a["scope"] == "project"]
        self.assertEqual(project_agents[0]["name"], "quoted-agent")
        self.assertEqual(project_agents[0]["description"], "Has quotes")


class TestFindHooks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.claude_dir = Path(self.tmp) / ".claude"
        self.claude_dir.mkdir(parents=True)

    def test_no_settings_file_returns_empty(self):
        result = claude_meta.find_hooks([self.tmp])
        self.assertEqual([h for h in result if h["scope"] == "project"], [])

    def test_reads_hook_events(self):
        (self.claude_dir / "settings.json").write_text(
            json.dumps({"hooks": {"PreToolUse": [], "Stop": []}}),
            encoding="utf-8",
        )
        result = claude_meta.find_hooks([self.tmp])
        project_hooks = {h["event"] for h in result if h["scope"] == "project"}
        self.assertEqual(project_hooks, {"PreToolUse", "Stop"})

    def test_corrupt_settings_file_is_skipped_not_raised(self):
        (self.claude_dir / "settings.json").write_text("{ broken", encoding="utf-8")
        result = claude_meta.find_hooks([self.tmp])  # must not raise
        self.assertEqual([h for h in result if h["scope"] == "project"], [])


class TestCheckRtlFirstLine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = Path(self.tmp) / "CLAUDE.md"

    def test_missing_file_returns_none(self):
        self.assertIsNone(claude_meta.check_rtl_first_line(str(self.path)))

    def test_no_hebrew_content_is_ok(self):
        self.path.write_text("# Just English\n\nSome notes.", encoding="utf-8")
        result = claude_meta.check_rtl_first_line(str(self.path))
        self.assertEqual(result, {"has_hebrew": False, "first_line_hebrew": False, "ok": True})

    def test_hebrew_on_first_line_is_ok(self):
        self.path.write_text("# הוראות\n\nEnglish body.", encoding="utf-8")
        result = claude_meta.check_rtl_first_line(str(self.path))
        self.assertTrue(result["has_hebrew"])
        self.assertTrue(result["first_line_hebrew"])
        self.assertTrue(result["ok"])

    def test_hebrew_only_later_is_not_ok(self):
        self.path.write_text("# English title\n\nגוף בעברית כאן.", encoding="utf-8")
        result = claude_meta.check_rtl_first_line(str(self.path))
        self.assertTrue(result["has_hebrew"])
        self.assertFalse(result["first_line_hebrew"])
        self.assertFalse(result["ok"])

    def test_blank_lines_before_first_real_line_are_skipped(self):
        self.path.write_text("\n\n   \nגוף בעברית", encoding="utf-8")
        result = claude_meta.check_rtl_first_line(str(self.path))
        self.assertTrue(result["first_line_hebrew"])
        self.assertTrue(result["ok"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
