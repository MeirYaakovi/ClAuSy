"""Unit tests for git_status — repo discovery and push status."""
import os
import shutil
import subprocess
import tempfile
import unittest

import git_status


def _git(path, *args):
    subprocess.run(["git", *args], cwd=path, check=True,
                    capture_output=True, text=True)


def _init_repo(path, branch="master"):
    os.makedirs(path, exist_ok=True)
    _git(path, "init", "-q", "-b", branch)
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test")


def _commit(path, filename="a.txt", content="1", message="commit"):
    with open(os.path.join(path, filename), "w") as f:
        f.write(content)
    _git(path, "add", filename)
    _git(path, "commit", "-q", "-m", message)


class TestGetRepoStatus(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_upstream(self):
        repo = os.path.join(self.tmp, "solo")
        _init_repo(repo)
        _commit(repo)
        status = git_status.get_repo_status(repo)
        self.assertFalse(status["has_upstream"])
        self.assertEqual(status["ahead"], 0)
        self.assertFalse(status["direct_on_main"])
        self.assertIsNone(status["error"])

    def _make_remote_pair(self, branch="master"):
        remote = os.path.join(self.tmp, "remote.git")
        _git(self.tmp, "init", "-q", "--bare", remote)
        local = os.path.join(self.tmp, "local")
        _init_repo(local, branch=branch)
        _commit(local)
        _git(local, "remote", "add", "origin", remote)
        _git(local, "push", "-q", "-u", "origin", branch)
        return local

    def test_direct_on_main_flagged_when_ahead(self):
        local = self._make_remote_pair(branch="master")
        _commit(local, filename="b.txt", content="2", message="second")
        status = git_status.get_repo_status(local)
        self.assertTrue(status["has_upstream"])
        self.assertEqual(status["ahead"], 1)
        self.assertTrue(status["direct_on_main"])

    def test_feature_branch_not_flagged(self):
        local = self._make_remote_pair(branch="feature/x")
        _commit(local, filename="b.txt", content="2", message="second")
        status = git_status.get_repo_status(local)
        self.assertEqual(status["ahead"], 1)
        self.assertFalse(status["direct_on_main"])

    def test_clean_main_not_flagged(self):
        local = self._make_remote_pair(branch="master")
        status = git_status.get_repo_status(local)
        self.assertEqual(status["ahead"], 0)
        self.assertFalse(status["direct_on_main"])

    def test_behind_detected(self):
        remote = os.path.join(self.tmp, "remote2.git")
        _git(self.tmp, "init", "-q", "--bare", remote)
        a = os.path.join(self.tmp, "a")
        _init_repo(a)
        _commit(a)
        _git(a, "remote", "add", "origin", remote)
        _git(a, "push", "-q", "-u", "origin", "master")

        b = os.path.join(self.tmp, "b")
        _git(self.tmp, "clone", "-q", remote, b)
        _git(b, "config", "user.email", "test@example.com")
        _git(b, "config", "user.name", "Test")
        _commit(b, filename="c.txt", content="3", message="from b")
        _git(b, "push", "-q")
        _git(a, "fetch", "-q")

        status = git_status.get_repo_status(a)
        self.assertEqual(status["behind"], 1)


class TestFindGitRepos(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_finds_subfolder_repos(self):
        projects = os.path.join(self.tmp, "Projects")
        repo_a = os.path.join(projects, "RepoA")
        _init_repo(repo_a)
        _commit(repo_a)
        found = git_status.find_git_repos([projects])
        self.assertEqual(found, [repo_a])

    def test_tracked_dir_itself_is_repo(self):
        repo = os.path.join(self.tmp, "SelfRepo")
        _init_repo(repo)
        _commit(repo)
        found = git_status.find_git_repos([repo])
        self.assertEqual(found, [repo])

    def test_no_repos_found(self):
        empty = os.path.join(self.tmp, "empty")
        os.makedirs(empty)
        self.assertEqual(git_status.find_git_repos([empty]), [])


if __name__ == "__main__":
    unittest.main()
