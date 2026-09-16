"""Unit tests for storage — pure helpers only (load/save touch the real
filesystem and are exercised indirectly via the app; see the smoke-test
pattern used for UI wiring)."""
import unittest

import storage


class TestNoteBranchSeen(unittest.TestCase):
    def test_first_sighting_is_not_new(self):
        known = {}
        is_new, known = storage.note_branch_seen(known, "/repo/a", "master")
        self.assertFalse(is_new)
        self.assertEqual(known["/repo/a"], ["master"])

    def test_second_scan_same_branch_not_new(self):
        known = {"/repo/a": ["master"]}
        is_new, known = storage.note_branch_seen(known, "/repo/a", "master")
        self.assertFalse(is_new)

    def test_new_branch_flagged(self):
        known = {"/repo/a": ["master"]}
        is_new, known = storage.note_branch_seen(known, "/repo/a", "feature/x")
        self.assertTrue(is_new)
        self.assertEqual(known["/repo/a"], ["feature/x", "master"])

    def test_blank_branch_ignored(self):
        known = {}
        is_new, known = storage.note_branch_seen(known, "/repo/a", "")
        self.assertFalse(is_new)
        self.assertEqual(known, {})

    def test_different_repos_tracked_independently(self):
        known = {"/repo/a": ["master"]}
        is_new, known = storage.note_branch_seen(known, "/repo/b", "master")
        self.assertFalse(is_new)  # first sighting for repo b
        self.assertIn("/repo/b", known)


class TestNoteYoloState(unittest.TestCase):
    def test_enabling_records_timestamp(self):
        yolo = {}
        yolo = storage.note_yolo_state(yolo, "/x/settings.json", True, "2026-09-16T10:00:00")
        self.assertEqual(yolo["/x/settings.json"], "2026-09-16T10:00:00")

    def test_repeated_enable_keeps_first_timestamp(self):
        yolo = {"/x/settings.json": "2026-09-14T10:00:00"}
        yolo = storage.note_yolo_state(yolo, "/x/settings.json", True, "2026-09-16T10:00:00")
        self.assertEqual(yolo["/x/settings.json"], "2026-09-14T10:00:00")

    def test_disabling_clears_record(self):
        yolo = {"/x/settings.json": "2026-09-14T10:00:00"}
        yolo = storage.note_yolo_state(yolo, "/x/settings.json", False, "2026-09-16T10:00:00")
        self.assertNotIn("/x/settings.json", yolo)

    def test_disabling_absent_record_is_noop(self):
        yolo = {}
        yolo = storage.note_yolo_state(yolo, "/x/settings.json", False, "2026-09-16T10:00:00")
        self.assertEqual(yolo, {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
