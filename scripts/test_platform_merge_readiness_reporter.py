#!/usr/bin/env python3
"""Tests for platform_merge_readiness_reporter.py using unittest and stdlib only."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import platform_merge_readiness_reporter as reporter


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))


class TestGetBranch(unittest.TestCase):
    def test_returns_branch_name(self):
        branch = reporter.get_branch(REPO_ROOT)
        self.assertNotEqual(branch, "unknown")
        self.assertTrue(len(branch) > 0)


class TestGetCommit(unittest.TestCase):
    def test_short_commit(self):
        commit = reporter.get_commit_short(REPO_ROOT)
        self.assertNotEqual(commit, "unknown")
        self.assertTrue(len(commit) >= 7)

    def test_full_commit(self):
        commit = reporter.get_commit_full(REPO_ROOT)
        self.assertNotEqual(commit, "unknown")
        self.assertEqual(len(commit), 40)


class TestGetModifiedFiles(unittest.TestCase):
    def test_returns_list(self):
        files = reporter.get_modified_files(REPO_ROOT, "HEAD~1")
        self.assertIsInstance(files, list)


class TestAuditForbiddenPaths(unittest.TestCase):
    def test_clean_files_pass(self):
        files = [
            "scripts/platform_foo.py",
            "ai-ledger/platform/ledger.md",
        ]
        violations = reporter.audit_forbidden_paths(files)
        self.assertEqual(violations, [])

    def test_backend_fails(self):
        violations = reporter.audit_forbidden_paths(["backend/app.py"])
        self.assertEqual(len(violations), 1)
        self.assertIn("backend", violations[0]["reason"])

    def test_keyword_fails(self):
        violations = reporter.audit_forbidden_paths(["src/auth_handler.py"])
        self.assertEqual(len(violations), 1)
        self.assertIn("auth", violations[0]["reason"])

    def test_empty_passes(self):
        violations = reporter.audit_forbidden_paths([])
        self.assertEqual(violations, [])


class TestAssessRisk(unittest.TestCase):
    def test_no_files_is_none(self):
        risk = reporter.assess_risk([], {"status": "PASS"})
        self.assertEqual(risk, "NONE")

    def test_only_ledgers_is_low(self):
        risk = reporter.assess_risk(
            ["ai-ledger/platform/ledger.md"],
            {"status": "PASS"},
        )
        self.assertEqual(risk, "LOW")

    def test_scripts_is_medium(self):
        risk = reporter.assess_risk(
            ["scripts/platform_foo.py", "scripts/test_platform_foo.py"],
            {"status": "PASS"},
        )
        self.assertEqual(risk, "MEDIUM")

    def test_test_failure_is_high(self):
        risk = reporter.assess_risk(
            ["scripts/platform_foo.py"],
            {"status": "FAIL"},
        )
        self.assertEqual(risk, "HIGH")


class TestGenerateReport(unittest.TestCase):
    def test_report_has_required_fields(self):
        report = reporter.generate_report(REPO_ROOT, "HEAD~1", skip_tests=True)
        for field in ["branch", "commit", "modified_files", "tests",
                       "report_path", "risk", "forbidden_path_audit",
                       "gitnexus", "blockers"]:
            self.assertIn(field, report, f"Missing field: {field}")

    def test_report_commit_is_short(self):
        report = reporter.generate_report(REPO_ROOT, "HEAD~1", skip_tests=True)
        self.assertIn("commit", report)
        self.assertTrue(len(report["commit"]) <= 10)

    def test_skip_tests_flag(self):
        report = reporter.generate_report(REPO_ROOT, "HEAD~1", skip_tests=True)
        self.assertEqual(report["tests"]["status"], "SKIPPED")


class TestFormatHuman(unittest.TestCase):
    def test_format_human(self):
        report = reporter.generate_report(REPO_ROOT, "HEAD~1", skip_tests=True)
        output = reporter.format_human(report)
        self.assertIn("Platform Merge Readiness Report", output)
        self.assertIn("Branch:", output)
        self.assertIn("Commit:", output)
        self.assertIn("Risk:", output)


class TestJsonCli(unittest.TestCase):
    def test_json_no_full_sha(self):
        """JSON output should use short SHAs only."""
        result = subprocess.run(
            [sys.executable,
             os.path.join(SCRIPT_DIR, "platform_merge_readiness_reporter.py"),
             "--repo", REPO_ROOT, "--json", "--base-ref", "HEAD~1",
             "--skip-tests"],
            capture_output=True, text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        data = json.loads(result.stdout)
        # commit field should be short
        self.assertTrue(len(data["commit"]) <= 10)
        # commit_full should not be present in JSON output
        self.assertNotIn("commit_full", data)
        for field in ["branch", "commit", "modified_files", "tests",
                       "report_path", "risk", "forbidden_path_audit",
                       "gitnexus", "blockers"]:
            self.assertIn(field, data, f"Missing field in JSON: {field}")


class TestHumanCli(unittest.TestCase):
    def test_human_output(self):
        result = subprocess.run(
            [sys.executable,
             os.path.join(SCRIPT_DIR, "platform_merge_readiness_reporter.py"),
             "--repo", REPO_ROOT, "--base-ref", "HEAD~1",
             "--skip-tests"],
            capture_output=True, text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Platform Merge Readiness Report", result.stdout)
        self.assertIn("Blockers:", result.stdout)


class TestForbiddenPathCli(unittest.TestCase):
    def _make_repo_with_forbidden(self, tmpdir):
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
        # Add forbidden file
        os.makedirs(os.path.join(tmpdir, "backend"))
        with open(os.path.join(tmpdir, "backend", "app.py"), "w") as f:
            f.write("# backend\n")
        subprocess.run(["git", "add", "-A"], cwd=tmpdir, capture_output=True)
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t.com",
             "commit", "-m", "add forbidden"],
            cwd=tmpdir, capture_output=True,
        )

    def test_forbidden_file_causes_nonzero_exit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._make_repo_with_forbidden(tmpdir)
            result = subprocess.run(
                [sys.executable,
                 os.path.join(SCRIPT_DIR, "platform_merge_readiness_reporter.py"),
                 "--repo", tmpdir, "--base-ref", "HEAD~1", "--json",
                 "--skip-tests"],
                capture_output=True, text=True,
                timeout=30,
            )
            self.assertNotEqual(result.returncode, 0)
            data = json.loads(result.stdout)
            self.assertEqual(data["forbidden_path_audit"]["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
