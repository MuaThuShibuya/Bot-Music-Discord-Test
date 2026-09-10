import os
import subprocess
import tempfile
import unittest

from services.git_service import GitUpdateService


class GitUpdateServiceTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.origin = os.path.join(self.temp_dir.name, "origin.git")
        self.source = os.path.join(self.temp_dir.name, "source")
        self.deploy = os.path.join(self.temp_dir.name, "deploy")

        self._git(["init", "--bare", self.origin])
        self._git(["init", "-b", "main", self.source])
        self._git(["config", "user.name", "Test"], cwd=self.source)
        self._git(["config", "user.email", "test@example.com"], cwd=self.source)
        self._write(self.source, "bot.txt", "version 1\n")
        self._git(["add", "bot.txt"], cwd=self.source)
        self._git(["commit", "-m", "version 1"], cwd=self.source)
        self._git(["remote", "add", "origin", self.origin], cwd=self.source)
        self._git(["push", "-u", "origin", "main"], cwd=self.source)
        self._git(["clone", "--branch", "main", self.origin, self.deploy])

    def tearDown(self):
        self.temp_dir.cleanup()

    @staticmethod
    def _git(args, cwd=None):
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    @staticmethod
    def _write(root, name, content):
        with open(os.path.join(root, name), "w", encoding="utf-8") as file:
            file.write(content)

    def test_fast_forward_update(self):
        self._write(self.source, "bot.txt", "version 2\n")
        self._git(["add", "bot.txt"], cwd=self.source)
        self._git(["commit", "-m", "version 2"], cwd=self.source)
        self._git(["push", "origin", "main"], cwd=self.source)

        result = GitUpdateService(self.deploy).pull_latest()

        self.assertTrue(result["success"])
        self.assertIn("bot.txt", result["changed_files"])
        with open(os.path.join(self.deploy, "bot.txt"), encoding="utf-8") as file:
            self.assertEqual(file.read(), "version 2\n")

    def test_force_push_creates_backup_and_updates(self):
        old_head = self._git(["rev-parse", "HEAD"], cwd=self.deploy)
        self._write(self.source, "bot.txt", "rewritten\n")
        self._git(["add", "bot.txt"], cwd=self.source)
        self._git(["commit", "--amend", "-m", "rewritten"], cwd=self.source)
        self._git(["push", "--force", "origin", "main"], cwd=self.source)

        result = GitUpdateService(self.deploy).pull_latest()

        self.assertTrue(result["success"])
        self.assertIn("Remote đã viết lại lịch sử", result["message"])
        backup_refs = self._git(
            ["for-each-ref", "--format=%(refname:short)", "refs/heads/backup/"],
            cwd=self.deploy,
        )
        self.assertTrue(backup_refs)
        self.assertEqual(
            self._git(["rev-parse", backup_refs.splitlines()[0]], cwd=self.deploy),
            old_head,
        )
        self.assertEqual(
            self._git(["rev-parse", "HEAD"], cwd=self.deploy),
            self._git(["rev-parse", "origin/main"], cwd=self.deploy),
        )

    def test_dirty_worktree_is_not_overwritten(self):
        self._write(self.deploy, "bot.txt", "local edit\n")

        result = GitUpdateService(self.deploy).pull_latest()

        self.assertFalse(result["success"])
        self.assertIn("chưa commit", result["message"])
        with open(os.path.join(self.deploy, "bot.txt"), encoding="utf-8") as file:
            self.assertEqual(file.read(), "local edit\n")

    def test_runtime_database_files_do_not_block_update(self):
        database_dir = os.path.join(self.deploy, "database")
        os.makedirs(database_dir, exist_ok=True)
        self._write(database_dir, "users.db-wal", "runtime data\n")
        self._write(self.source, "bot.txt", "version 2\n")
        self._git(["add", "bot.txt"], cwd=self.source)
        self._git(["commit", "-m", "version 2"], cwd=self.source)
        self._git(["push", "origin", "main"], cwd=self.source)

        result = GitUpdateService(self.deploy).pull_latest()

        self.assertTrue(result["success"])
        self.assertTrue(os.path.exists(os.path.join(database_dir, "users.db-wal")))
        with open(os.path.join(self.deploy, "bot.txt"), encoding="utf-8") as file:
            self.assertEqual(file.read(), "version 2\n")


if __name__ == "__main__":
    unittest.main()
