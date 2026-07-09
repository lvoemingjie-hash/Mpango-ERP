#!/usr/bin/env python3
"""Tests for platform_worktree_smoke_worker.py (P16-C) using unittest + stdlib."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import platform_worktree_smoke_worker as worker

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def _make_repo(tmpdir):
    repo = os.path.join(tmpdir, "repo")
    os.makedirs(repo)
    with open(os.path.join(repo, "base.txt"), "w", encoding="utf-8") as fh:
        fh.write("base\n")
    env = dict(os.environ)
    env["GIT_AUTHOR_NAME"] = "t"
    env["GIT_AUTHOR_EMAIL"] = "t@t"
    env["GIT_COMMITTER_NAME"] = "t"
    env["GIT_COMMITTER_EMAIL"] = "t@t"
    subprocess.run(["git", "init", "-q", repo], check=True)
    subprocess.run(["git", "-C", repo, "add", "."], check=True)
    subprocess.run(
        ["git", "-C", repo, "commit", "-q", "-m", "base"], check=True, env=env
    )
    return repo


class TestValidateOutputPath(unittest.TestCase):
    def test_valid_scripts_path_ok(self):
        self.assertIsNone(worker.validate_output_path("scripts/out.json"))

    def test_valid_ledger_path_ok(self):
        self.assertIsNone(
            worker.validate_output_path("ai-ledger/platform/out.json")
        )

    def test_absolute_posix_rejected(self):
        self.assertIsNotNone(worker.validate_output_path("/etc/evil.json"))

    def test_absolute_windows_drive_rejected(self):
        self.assertIsNotNone(worker.validate_output_path("C:/evil.json"))

    def test_traversal_rejected(self):
        self.assertIsNotNone(
            worker.validate_output_path("scripts/../evil.json")
        )

    def test_unsafe_empty_part_rejected(self):
        self.assertIsNotNone(worker.validate_output_path("scripts//out.json"))

    def test_dot_part_rejected(self):
        self.assertIsNotNone(worker.validate_output_path("scripts/./out.json"))

    def test_empty_rejected(self):
        self.assertIsNotNone(worker.validate_output_path(""))

    def test_backend_prefix_forbidden(self):
        issue = worker.validate_output_path("backend/app.py")
        self.assertIsNotNone(issue)
        self.assertIn("forbidden", issue)

    def test_frontend_prefix_forbidden(self):
        self.assertIsNotNone(worker.validate_output_path("frontend/ui.ts"))

    def test_product_dev_recovered_forbidden(self):
        self.assertIsNotNone(
            worker.validate_output_path("product-dev-recovered/x.py")
        )

    def test_auth_keyword_forbidden(self):
        self.assertIsNotNone(worker.validate_output_path("scripts/auth_x.py"))

    def test_payment_keyword_forbidden(self):
        self.assertIsNotNone(
            worker.validate_output_path("scripts/payment_x.py")
        )

    def test_outside_allowlist_rejected(self):
        issue = worker.validate_output_path("README.md")
        self.assertIsNotNone(issue)
        self.assertIn("allowlisted", issue)


class TestRunWritesOutput(unittest.TestCase):
    def test_writes_allowlisted_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(tmp)
            rc = worker.run("scripts/out.json", do_commit=False, repo_dir=repo)
            self.assertEqual(rc, 0)
            with open(os.path.join(repo, "scripts", "out.json"), encoding="utf-8") as fh:
                data = json.load(fh)
            self.assertTrue(data["p16c_smoke"])
            self.assertEqual(data["source"], "platform_worktree_smoke_worker")

    def test_writes_nested_ledger_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(tmp)
            rc = worker.run(
                "ai-ledger/platform/nested/out.json",
                do_commit=False, repo_dir=repo,
            )
            self.assertEqual(rc, 0)
            self.assertTrue(
                os.path.exists(os.path.join(repo, "ai-ledger", "platform", "nested", "out.json"))
            )


class TestRunRejectsUnsafe(unittest.TestCase):
    def test_rejects_absolute_no_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(tmp)
            rc = worker.run("/etc/evil.json", do_commit=False, repo_dir=repo)
            self.assertEqual(rc, 2)
            self.assertFalse(os.path.exists("/etc/evil.json"))

    def test_rejects_forbidden_no_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(tmp)
            rc = worker.run("backend/evil.py", do_commit=False, repo_dir=repo)
            self.assertEqual(rc, 2)
            self.assertFalse(os.path.exists(os.path.join(repo, "backend")))

    def test_rejects_outside_allowlist_no_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(tmp)
            rc = worker.run("evil.txt", do_commit=False, repo_dir=repo)
            self.assertEqual(rc, 2)
            self.assertFalse(os.path.exists(os.path.join(repo, "evil.txt")))


class TestCommitOption(unittest.TestCase):
    def test_commit_creates_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(tmp)
            rc = worker.run("scripts/out.json", do_commit=True, repo_dir=repo)
            self.assertEqual(rc, 0)
            # File is tracked.
            tracked = subprocess.run(
                ["git", "-C", repo, "ls-files", "scripts/out.json"],
                capture_output=True, text=True,
            )
            self.assertIn("scripts/out.json", tracked.stdout)
            # A new commit beyond 'base' exists.
            log = subprocess.run(
                ["git", "-C", repo, "log", "--oneline"],
                capture_output=True, text=True,
            )
            self.assertIn("P16-C smoke worker output", log.stdout)
            # Working tree clean after commit.
            status = subprocess.run(
                ["git", "-C", repo, "status", "--porcelain"],
                capture_output=True, text=True,
            )
            self.assertEqual(status.stdout.strip(), "")

    def test_commit_message_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(tmp)
            worker.run("scripts/a.json", do_commit=True, repo_dir=repo)
            worker.run("scripts/b.json", do_commit=True, repo_dir=repo)
            log = subprocess.run(
                ["git", "-C", repo, "log", "--oneline"],
                capture_output=True, text=True,
            )
            # base + two smoke commits
            self.assertEqual(len(log.stdout.strip().splitlines()), 3)


class TestMainCLI(unittest.TestCase):
    def _run_cli(self, args, cwd):
        cmd = [sys.executable, os.path.join(SCRIPT_DIR, "platform_worktree_smoke_worker.py")] + args
        return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)

    def test_missing_output_arg_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(tmp)
            result = self._run_cli([], cwd=repo)
        self.assertNotEqual(result.returncode, 0)

    def test_cli_writes_and_commits(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(tmp)
            result = self._run_cli(
                ["--output", "scripts/cli_out.json", "--commit"], cwd=repo
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(
                os.path.exists(os.path.join(repo, "scripts", "cli_out.json"))
            )

    def test_cli_rejects_forbidden(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(tmp)
            result = self._run_cli(["--output", "backend/x.py"], cwd=repo)
            self.assertEqual(result.returncode, 2)
            self.assertIn("forbidden", result.stderr)


if __name__ == "__main__":
    unittest.main()
