#!/usr/bin/env python3
"""Tests for platform_diff_auditor.py using unittest and stdlib only."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import platform_diff_auditor as auditor


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))


class TestIsForbidden(unittest.TestCase):
    def test_backend_prefix_forbidden(self):
        forbidden, reason = auditor.is_forbidden("backend/app.py")
        self.assertTrue(forbidden)
        self.assertIn("backend", reason)

    def test_frontend_prefix_forbidden(self):
        forbidden, _ = auditor.is_forbidden("frontend/index.tsx")
        self.assertTrue(forbidden)

    def test_dotgithub_prefix_forbidden(self):
        forbidden, _ = auditor.is_forbidden(".github/workflows/ci.yml")
        self.assertTrue(forbidden)

    def test_dotclaude_prefix_forbidden(self):
        forbidden, _ = auditor.is_forbidden(".claude/settings.json")
        self.assertTrue(forbidden)

    def test_docs_ai_prefix_forbidden(self):
        forbidden, _ = auditor.is_forbidden("docs/ai/PROJECT.md")
        self.assertTrue(forbidden)

    def test_product_prefix_forbidden(self):
        forbidden, _ = auditor.is_forbidden("product-dev-recovered/app.py")
        self.assertTrue(forbidden)

    def test_auth_keyword_forbidden(self):
        forbidden, reason = auditor.is_forbidden("src/auth_handler.py")
        self.assertTrue(forbidden)
        self.assertIn("auth", reason)

    def test_rbac_keyword_forbidden(self):
        forbidden, _ = auditor.is_forbidden("src/rbac_check.py")
        self.assertTrue(forbidden)

    def test_tenancy_keyword_forbidden(self):
        forbidden, _ = auditor.is_forbidden("src/tenancy_utils.py")
        self.assertTrue(forbidden)

    def test_migration_keyword_forbidden(self):
        forbidden, _ = auditor.is_forbidden("db/migration_001.sql")
        self.assertTrue(forbidden)

    def test_payment_keyword_forbidden(self):
        forbidden, _ = auditor.is_forbidden("src/payment_service.py")
        self.assertTrue(forbidden)

    def test_session_keyword_forbidden(self):
        forbidden, _ = auditor.is_forbidden("src/session_manager.py")
        self.assertTrue(forbidden)

    def test_scripts_path_allowed(self):
        forbidden, _ = auditor.is_forbidden("scripts/platform_diff_auditor.py")
        self.assertFalse(forbidden)

    def test_ledger_path_allowed(self):
        forbidden, _ = auditor.is_forbidden("ai-ledger/platform/some_ledger.md")
        self.assertFalse(forbidden)

    def test_case_insensitive(self):
        forbidden, _ = auditor.is_forbidden("src/Auth_Handler.py")
        self.assertTrue(forbidden)

    def test_no_false_positive_keyword(self):
        """Words that merely contain the keyword as substring are not flagged."""
        forbidden, _ = auditor.is_forbidden("scripts/platform_batch_mission_check.py")
        self.assertFalse(forbidden)


class TestIsAllowed(unittest.TestCase):
    def test_scripts_prefix_allowed(self):
        self.assertTrue(auditor.is_allowed("scripts/platform_foo.py"))

    def test_ledger_prefix_allowed(self):
        self.assertTrue(auditor.is_allowed("ai-ledger/platform/ledger.md"))

    def test_other_path_not_allowed(self):
        self.assertFalse(auditor.is_allowed("README.md"))

    def test_custom_prefixes(self):
        self.assertTrue(
            auditor.is_allowed("other/file.py", allowed_prefixes=["other/"])
        )


class TestAuditFiles(unittest.TestCase):
    def test_all_clean(self):
        files = [
            "scripts/platform_foo.py",
            "ai-ledger/platform/ledger.md",
        ]
        result = auditor.audit_files(files)
        self.assertTrue(result["passed"])
        self.assertEqual(result["violations"], [])
        self.assertEqual(len(result["allowed"]), 2)

    def test_forbidden_file_fails(self):
        files = ["backend/app.py", "scripts/platform_foo.py"]
        result = auditor.audit_files(files)
        self.assertFalse(result["passed"])
        self.assertEqual(len(result["violations"]), 1)
        self.assertEqual(result["violations"][0]["file"], "backend/app.py")

    def test_keyword_file_fails(self):
        files = ["src/payment_utils.py"]
        result = auditor.audit_files(files)
        self.assertFalse(result["passed"])
        self.assertEqual(len(result["violations"]), 1)

    def test_readme_outside_allowlist_fails(self):
        """README.md is outside allowed prefixes and should block."""
        files = ["README.md"]
        result = auditor.audit_files(files)
        self.assertFalse(result["passed"])
        self.assertIn("README.md", result["disallowed"])
        self.assertEqual(len(result["violations"]), 1)
        self.assertIn("outside allowed", result["violations"][0]["reason"])

    def test_random_path_outside_allowlist_fails(self):
        """random/file.py is outside allowed prefixes and should block."""
        files = ["random/file.py"]
        result = auditor.audit_files(files)
        self.assertFalse(result["passed"])
        self.assertIn("random/file.py", result["disallowed"])

    def test_mixed_allowed_and_outside_fails(self):
        """Even with some allowed files, outside-allowlist files block."""
        files = ["scripts/platform_foo.py", "docs/readme.txt"]
        result = auditor.audit_files(files)
        self.assertFalse(result["passed"])
        self.assertEqual(len(result["allowed"]), 1)
        self.assertEqual(len(result["disallowed"]), 1)

    def test_empty_list_passes(self):
        result = auditor.audit_files([])
        self.assertTrue(result["passed"])
        self.assertEqual(result["total"], 0)


class TestCompareMode(unittest.TestCase):
    def _make_git_repo(self, tmpdir):
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(
            ["git", "checkout", "-b", "codex/platform-test"],
            cwd=tmpdir, capture_output=True,
        )
        # Initial commit
        scripts_dir = os.path.join(tmpdir, "scripts")
        os.makedirs(scripts_dir)
        with open(os.path.join(scripts_dir, "platform_alpha.py"), "w") as f:
            f.write("# alpha\n")
        subprocess.run(["git", "add", "-A"], cwd=tmpdir, capture_output=True)
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t.com",
             "commit", "-m", "init"],
            cwd=tmpdir, capture_output=True,
        )
        # Add a new file on HEAD
        with open(os.path.join(scripts_dir, "platform_beta.py"), "w") as f:
            f.write("# beta\n")
        subprocess.run(["git", "add", "-A"], cwd=tmpdir, capture_output=True)
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t.com",
             "commit", "-m", "add beta"],
            cwd=tmpdir, capture_output=True,
        )

    def test_compare_detects_changes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._make_git_repo(tmpdir)
            files = auditor.get_changed_files_compare(tmpdir, "HEAD~1")
            self.assertIn("scripts/platform_beta.py", files)

    def test_compare_passes_with_allowed_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._make_git_repo(tmpdir)
            result = subprocess.run(
                [sys.executable,
                 os.path.join(SCRIPT_DIR, "platform_diff_auditor.py"),
                 "--repo", tmpdir, "--mode", "compare",
                 "--base-ref", "HEAD~1"],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PASS", result.stdout)

    def test_compare_fails_with_forbidden_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._make_git_repo(tmpdir)
            # Add a forbidden file
            os.makedirs(os.path.join(tmpdir, "backend"), exist_ok=True)
            with open(os.path.join(tmpdir, "backend", "app.py"), "w") as f:
                f.write("# app\n")
            subprocess.run(["git", "add", "-A"], cwd=tmpdir, capture_output=True)
            subprocess.run(
                ["git", "-c", "user.name=t", "-c", "user.email=t@t.com",
                 "commit", "-m", "add forbidden"],
                cwd=tmpdir, capture_output=True,
            )
            result = subprocess.run(
                [sys.executable,
                 os.path.join(SCRIPT_DIR, "platform_diff_auditor.py"),
                 "--repo", tmpdir, "--mode", "compare",
                 "--base-ref", "HEAD~2"],
                capture_output=True, text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("FAIL", result.stdout)


class TestStagedMode(unittest.TestCase):
    def _make_repo(self, tmpdir):
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(
            ["git", "checkout", "-b", "codex/platform-test"],
            cwd=tmpdir, capture_output=True,
        )
        scripts_dir = os.path.join(tmpdir, "scripts")
        os.makedirs(scripts_dir)
        with open(os.path.join(scripts_dir, "platform_alpha.py"), "w") as f:
            f.write("# alpha\n")
        subprocess.run(["git", "add", "-A"], cwd=tmpdir, capture_output=True)
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t.com",
             "commit", "-m", "init"],
            cwd=tmpdir, capture_output=True,
        )

    def test_staged_passes_with_allowed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._make_repo(tmpdir)
            with open(os.path.join(tmpdir, "scripts", "platform_beta.py"), "w") as f:
                f.write("# beta\n")
            subprocess.run(["git", "add", "scripts/platform_beta.py"],
                           cwd=tmpdir, capture_output=True)
            result = subprocess.run(
                [sys.executable,
                 os.path.join(SCRIPT_DIR, "platform_diff_auditor.py"),
                 "--repo", tmpdir, "--mode", "staged"],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_staged_fails_with_forbidden(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._make_repo(tmpdir)
            os.makedirs(os.path.join(tmpdir, "backend"))
            with open(os.path.join(tmpdir, "backend", "new_file.py"), "w") as f:
                f.write("# backend\n")
            subprocess.run(["git", "add", "backend/new_file.py"],
                           cwd=tmpdir, capture_output=True)
            result = subprocess.run(
                [sys.executable,
                 os.path.join(SCRIPT_DIR, "platform_diff_auditor.py"),
                 "--repo", tmpdir, "--mode", "staged"],
                capture_output=True, text=True,
            )
            self.assertNotEqual(result.returncode, 0)


class TestUntrackedMode(unittest.TestCase):
    def _make_repo(self, tmpdir):
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(
            ["git", "checkout", "-b", "codex/platform-test"],
            cwd=tmpdir, capture_output=True,
        )
        scripts_dir = os.path.join(tmpdir, "scripts")
        os.makedirs(scripts_dir)
        with open(os.path.join(scripts_dir, "platform_alpha.py"), "w") as f:
            f.write("# alpha\n")
        subprocess.run(["git", "add", "-A"], cwd=tmpdir, capture_output=True)
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t.com",
             "commit", "-m", "init"],
            cwd=tmpdir, capture_output=True,
        )

    def test_untracked_passes_with_allowed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._make_repo(tmpdir)
            with open(os.path.join(tmpdir, "scripts", "platform_new.py"), "w") as f:
                f.write("# new\n")
            result = subprocess.run(
                [sys.executable,
                 os.path.join(SCRIPT_DIR, "platform_diff_auditor.py"),
                 "--repo", tmpdir, "--mode", "untracked"],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0)

    def test_untracked_fails_with_forbidden(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._make_repo(tmpdir)
            os.makedirs(os.path.join(tmpdir, "backend"))
            with open(os.path.join(tmpdir, "backend", "untracked.py"), "w") as f:
                f.write("# untracked\n")
            result = subprocess.run(
                [sys.executable,
                 os.path.join(SCRIPT_DIR, "platform_diff_auditor.py"),
                 "--repo", tmpdir, "--mode", "untracked"],
                capture_output=True, text=True,
            )
            self.assertNotEqual(result.returncode, 0)


class TestNoChanges(unittest.TestCase):
    def test_empty_diff_passes(self):
        """No changed files should pass."""
        result = auditor.audit_files([])
        self.assertTrue(result["passed"])
        self.assertEqual(result["total"], 0)


class TestJsonOutput(unittest.TestCase):
    def test_json_output(self):
        files = ["scripts/platform_foo.py", "backend/bar.py"]
        result = auditor.audit_files(files)
        self.assertIn("passed", result)
        self.assertIn("violations", result)
        self.assertIn("total", result)
        self.assertFalse(result["passed"])
        self.assertEqual(result["total"], 2)

    def test_json_cli(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
            subprocess.run(
                ["git", "checkout", "-b", "codex/platform-test"],
                cwd=tmpdir, capture_output=True,
            )
            scripts_dir = os.path.join(tmpdir, "scripts")
            os.makedirs(scripts_dir)
            with open(os.path.join(scripts_dir, "platform_x.py"), "w") as f:
                f.write("# x\n")
            subprocess.run(["git", "add", "-A"], cwd=tmpdir, capture_output=True)
            subprocess.run(
                ["git", "-c", "user.name=t", "-c", "user.email=t@t.com",
                 "commit", "-m", "init"],
                cwd=tmpdir, capture_output=True,
            )
            result = subprocess.run(
                [sys.executable,
                 os.path.join(SCRIPT_DIR, "platform_diff_auditor.py"),
                 "--repo", tmpdir, "--mode", "staged", "--json"],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0)
            data = json.loads(result.stdout)
            self.assertIn("passed", data)
            self.assertIn("violations", data)


if __name__ == "__main__":
    unittest.main()
