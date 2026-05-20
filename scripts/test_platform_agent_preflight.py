#!/usr/bin/env python3
"""Tests for platform_agent_preflight.py using unittest and tempfile only."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import platform_agent_preflight as preflight


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))


class TestIsForbiddenPath(unittest.TestCase):
    def test_backend_prefix(self):
        forbidden, reason = preflight.is_forbidden_path("backend/api/foo.py")
        self.assertTrue(forbidden)

    def test_frontend_prefix(self):
        forbidden, reason = preflight.is_forbidden_path("frontend/src/bar.tsx")
        self.assertTrue(forbidden)

    def test_github_workflows_prefix(self):
        forbidden, reason = preflight.is_forbidden_path(".github/workflows/ci.yml")
        self.assertTrue(forbidden)

    def test_claude_prefix(self):
        forbidden, reason = preflight.is_forbidden_path(".claude/skill.md")
        self.assertTrue(forbidden)

    def test_phase4_contract_specific(self):
        forbidden, reason = preflight.is_forbidden_path("docs/ai/PHASE4_FRONTEND_CONTRACT.md")
        self.assertTrue(forbidden)

    def test_auth_fragment(self):
        forbidden, reason = preflight.is_forbidden_path("some/path/auth/component.py")
        self.assertTrue(forbidden)

    def test_rbac_fragment(self):
        forbidden, reason = preflight.is_forbidden_path("api/rbac/roles.py")
        self.assertTrue(forbidden)

    def test_tenancy_fragment(self):
        forbidden, reason = preflight.is_forbidden_path("core/tenancy/models.py")
        self.assertTrue(forbidden)

    def test_session_fragment(self):
        forbidden, reason = preflight.is_forbidden_path("db/session.py")
        self.assertTrue(forbidden)

    def test_migration_fragment(self):
        forbidden, reason = preflight.is_forbidden_path("alembic/migration/versions/001.py")
        self.assertTrue(forbidden)

    def test_payment_fragment(self):
        forbidden, reason = preflight.is_forbidden_path("services/payment/handler.py")
        self.assertTrue(forbidden)

    def test_allowed_path(self):
        forbidden, reason = preflight.is_forbidden_path("scripts/my_script.py")
        self.assertFalse(forbidden)

    def test_allowed_doc_path(self):
        forbidden, reason = preflight.is_forbidden_path("docs/ai/PROJECT.md")
        self.assertFalse(forbidden)

    def test_allowed_ledger_path(self):
        forbidden, reason = preflight.is_forbidden_path("ai-ledger/platform/ledger.md")
        self.assertFalse(forbidden)


class TestNormalizePath(unittest.TestCase):
    def test_windows_to_unix(self):
        self.assertEqual(preflight.normalize_path("a\\b\\c"), "a/b/c")

    def test_already_unix(self):
        self.assertEqual(preflight.normalize_path("a/b/c"), "a/b/c")


class TestGitFunctions(unittest.TestCase):
    def test_get_current_branch(self):
        branch = preflight.get_current_branch(REPO_ROOT)
        self.assertIsNotNone(branch)
        self.assertIsInstance(branch, str)
        self.assertTrue(len(branch) > 0)

    def test_get_current_commit(self):
        commit = preflight.get_current_commit(REPO_ROOT)
        self.assertIsNotNone(commit)
        self.assertIsInstance(commit, str)
        self.assertEqual(len(commit), 40)

    def test_get_changed_files_returns_set(self):
        files = preflight.get_changed_files(REPO_ROOT)
        self.assertIsInstance(files, set)


class TestValidRepoPasses(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)
        subprocess.run(["git", "init"], cwd=self.tmpdir, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "codex/platform-test"], cwd=self.tmpdir, capture_output=True)

        for doc in preflight.REQUIRED_DOCS:
            doc_path = os.path.join(self.tmpdir, doc)
            os.makedirs(os.path.dirname(doc_path), exist_ok=True)
            with open(doc_path, "w") as f:
                f.write(f"# {doc}\n")

        subprocess.run(["git", "add", "-A"], cwd=self.tmpdir, capture_output=True)
        subprocess.run(
            ["git", "-c", "user.name=test", "-c", "user.email=test@test.com", "commit", "-m", "init"],
            cwd=self.tmpdir, capture_output=True,
        )

    def test_valid_repo_passes(self):
        result = preflight.PreflightResult()
        preflight.check_branch(result, self.tmpdir)
        preflight.check_required_docs(result, self.tmpdir)
        preflight.check_changed_files(result, self.tmpdir)
        self.assertTrue(result.passed, f"expected PASS but got failures: {result.failures}")


class TestMissingDocFails(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)
        subprocess.run(["git", "init"], cwd=self.tmpdir, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "codex/platform-test"], cwd=self.tmpdir, capture_output=True)

        for doc in preflight.REQUIRED_DOCS[:-1]:
            doc_path = os.path.join(self.tmpdir, doc)
            os.makedirs(os.path.dirname(doc_path), exist_ok=True)
            with open(doc_path, "w") as f:
                f.write(f"# {doc}\n")

        subprocess.run(["git", "add", "-A"], cwd=self.tmpdir, capture_output=True)
        subprocess.run(
            ["git", "-c", "user.name=test", "-c", "user.email=test@test.com", "commit", "-m", "init"],
            cwd=self.tmpdir, capture_output=True,
        )

    def test_missing_doc_fails(self):
        result = preflight.PreflightResult()
        preflight.check_required_docs(result, self.tmpdir)
        self.assertFalse(result.passed)
        self.assertTrue(
            any("is missing" in f for f in result.failures),
            f"expected failure about missing doc, got: {result.failures}",
        )


class TestForbiddenPathFails(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)
        subprocess.run(["git", "init"], cwd=self.tmpdir, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "codex/platform-test"], cwd=self.tmpdir, capture_output=True)

        for doc in preflight.REQUIRED_DOCS:
            doc_path = os.path.join(self.tmpdir, doc)
            os.makedirs(os.path.dirname(doc_path), exist_ok=True)
            with open(doc_path, "w") as f:
                f.write(f"# {doc}\n")

        back_path = os.path.join(self.tmpdir, "backend", "foo.py")
        os.makedirs(os.path.dirname(back_path), exist_ok=True)
        with open(back_path, "w") as f:
            f.write("x = 1\n")

        subprocess.run(["git", "add", "-A"], cwd=self.tmpdir, capture_output=True)
        subprocess.run(
            ["git", "-c", "user.name=test", "-c", "user.email=test@test.com", "commit", "-m", "init"],
            cwd=self.tmpdir, capture_output=True,
        )

    def test_forbidden_changed_path_fails(self):
        forbidden_path = os.path.join(self.tmpdir, "backend", "new_file.py")
        with open(forbidden_path, "w") as f:
            f.write("y = 2\n")

        result = preflight.PreflightResult()
        preflight.check_changed_files(result, self.tmpdir)
        self.assertFalse(result.passed)
        self.assertTrue(
            any("forbidden" in f for f in result.failures),
            f"expected forbidden path failure, got: {result.failures}",
        )


class TestInvalidBranchFails(unittest.TestCase):
    def test_invalid_branch_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
            readme = os.path.join(tmpdir, "README.md")
            with open(readme, "w") as f:
                f.write("# test\n")
            subprocess.run(["git", "add", "README.md"], cwd=tmpdir, capture_output=True)
            subprocess.run(
                ["git", "-c", "user.name=test", "-c", "user.email=test@test.com", "commit", "-m", "init"],
                cwd=tmpdir,
                capture_output=True,
            )
            subprocess.run(["git", "checkout", "-b", "feature/foo"], cwd=tmpdir, capture_output=True)

            result = preflight.PreflightResult()
            preflight.check_branch(result, tmpdir)
            self.assertFalse(result.passed)
            self.assertTrue(
                any("not allowed" in f for f in result.failures),
                f"expected branch failure, got: {result.failures}",
            )


class TestPlatformDevBranchPolicy(unittest.TestCase):
    def _init_repo(self, tmpdir, branch_name):
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        readme = os.path.join(tmpdir, "README.md")
        with open(readme, "w") as f:
            f.write("# test\n")
        subprocess.run(["git", "add", "README.md"], cwd=tmpdir, capture_output=True)
        subprocess.run(
            ["git", "-c", "user.name=test", "-c", "user.email=test@test.com",
             "commit", "-m", "init"],
            cwd=tmpdir, capture_output=True,
        )
        subprocess.run(
            ["git", "checkout", "-b", branch_name],
            cwd=tmpdir, capture_output=True,
        )

    def test_platform_dev_fails_by_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._init_repo(tmpdir, "platform-dev")
            result = preflight.PreflightResult()
            preflight.check_branch(result, tmpdir)
            self.assertFalse(result.passed)
            self.assertTrue(
                any("not allowed by default" in f for f in result.failures),
                f"expected platform-dev default failure, got: {result.failures}",
            )

    def test_platform_dev_passes_with_allow_flag(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._init_repo(tmpdir, "platform-dev")
            result = preflight.PreflightResult()
            preflight.check_branch(result, tmpdir, allow_platform_dev=True)
            self.assertTrue(
                result.passed,
                f"expected pass with --allow-platform-dev, got: {result.failures}",
            )

    def test_codex_platform_branch_still_passes_by_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._init_repo(tmpdir, "codex/platform-some-task")
            result = preflight.PreflightResult()
            preflight.check_branch(result, tmpdir)
            self.assertTrue(
                result.passed,
                f"expected codex/platform-* to pass, got: {result.failures}",
            )


class TestReportValidation(unittest.TestCase):
    def test_report_with_all_fields_passes(self):
        content = """# Report

## Summary
- **Branch:** codex/platform-test
- **Commit:** abc123
- **Modified files:** file1.py, file2.py
- **Tests:** all passed
- **Report path:** path/to/report
- **Risk:** LOW
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(content)
            f.flush()
            report_path = f.name

        try:
            result = preflight.PreflightResult()
            preflight.validate_report(result, report_path)
            self.assertTrue(result.passed)
        finally:
            os.unlink(report_path)

    def test_report_missing_fields_fails(self):
        content = """# Report
- **Branch:** codex/platform-test
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(content)
            f.flush()
            report_path = f.name

        try:
            result = preflight.PreflightResult()
            preflight.validate_report(result, report_path)
            self.assertFalse(result.passed)
            self.assertTrue(
                any("missing" in f for f in result.failures),
                f"expected missing field failure, got: {result.failures}",
            )
        finally:
            os.unlink(report_path)

    def test_nonexistent_report_fails(self):
        result = preflight.PreflightResult()
        preflight.validate_report(result, "/nonexistent/report.md")
        self.assertFalse(result.passed)
        self.assertTrue(
            any("does not exist" in f for f in result.failures),
            f"expected nonexistent file failure, got: {result.failures}",
        )


class TestCliReportBehavior(unittest.TestCase):
    def test_require_report_without_report_fails(self):
        result = subprocess.run(
            [sys.executable, os.path.join(SCRIPT_DIR, "platform_agent_preflight.py"), "--require-report"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--require-report requires --report PATH", result.stdout)

    def test_relative_report_resolves_from_repo(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
            subprocess.run(["git", "checkout", "-b", "codex/platform-test"], cwd=tmpdir, capture_output=True)

            for doc in preflight.REQUIRED_DOCS:
                doc_path = os.path.join(tmpdir, doc)
                os.makedirs(os.path.dirname(doc_path), exist_ok=True)
                with open(doc_path, "w") as f:
                    f.write(f"# {doc}\n")

            report_path = os.path.join(tmpdir, "report.md")
            with open(report_path, "w") as f:
                f.write(
                    "- Branch: codex/platform-test\n"
                    "- Commit: abc123\n"
                    "- Modified files: none\n"
                    "- Tests: self-check\n"
                    "- Report path: report.md\n"
                    "- Risk: LOW\n"
                )

            subprocess.run(["git", "add", "-A"], cwd=tmpdir, capture_output=True)
            subprocess.run(
                ["git", "-c", "user.name=test", "-c", "user.email=test@test.com", "commit", "-m", "init"],
                cwd=tmpdir,
                capture_output=True,
            )

            result = subprocess.run(
                [
                    sys.executable,
                    os.path.join(SCRIPT_DIR, "platform_agent_preflight.py"),
                    "--repo",
                    tmpdir,
                    "--report",
                    "report.md",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


    def test_platform_dev_without_flag_fails_cli(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
            readme = os.path.join(tmpdir, "README.md")
            with open(readme, "w") as f:
                f.write("# test\n")
            subprocess.run(["git", "add", "README.md"], cwd=tmpdir, capture_output=True)
            subprocess.run(
                ["git", "-c", "user.name=test", "-c", "user.email=test@test.com",
                 "commit", "-m", "init"],
                cwd=tmpdir, capture_output=True,
            )
            subprocess.run(
                ["git", "checkout", "-b", "platform-dev"],
                cwd=tmpdir, capture_output=True,
            )

            for doc in preflight.REQUIRED_DOCS:
                doc_path = os.path.join(tmpdir, doc)
                os.makedirs(os.path.dirname(doc_path), exist_ok=True)
                with open(doc_path, "w") as f:
                    f.write(f"# {doc}\n")

            subprocess.run(["git", "add", "-A"], cwd=tmpdir, capture_output=True)
            subprocess.run(
                ["git", "-c", "user.name=test", "-c", "user.email=test@test.com", "commit", "-m", "init"],
                cwd=tmpdir, capture_output=True,
            )

            result = subprocess.run(
                [sys.executable, os.path.join(SCRIPT_DIR, "platform_agent_preflight.py"),
                 "--repo", tmpdir],
                capture_output=True, text=True,
            )
            self.assertNotEqual(result.returncode, 0, result.stdout)

    def test_platform_dev_with_flag_passes_cli(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
            readme = os.path.join(tmpdir, "README.md")
            with open(readme, "w") as f:
                f.write("# test\n")
            subprocess.run(["git", "add", "README.md"], cwd=tmpdir, capture_output=True)
            subprocess.run(
                ["git", "-c", "user.name=test", "-c", "user.email=test@test.com",
                 "commit", "-m", "init"],
                cwd=tmpdir, capture_output=True,
            )
            subprocess.run(
                ["git", "checkout", "-b", "platform-dev"],
                cwd=tmpdir, capture_output=True,
            )

            for doc in preflight.REQUIRED_DOCS:
                doc_path = os.path.join(tmpdir, doc)
                os.makedirs(os.path.dirname(doc_path), exist_ok=True)
                with open(doc_path, "w") as f:
                    f.write(f"# {doc}\n")

            report_path = os.path.join(tmpdir, "report.md")
            with open(report_path, "w") as f:
                f.write(
                    "- Branch: platform-dev\n"
                    "- Commit: abc123\n"
                    "- Modified files: none\n"
                    "- Tests: self-check\n"
                    "- Report path: report.md\n"
                    "- Risk: LOW\n"
                )

            subprocess.run(["git", "add", "-A"], cwd=tmpdir, capture_output=True)
            subprocess.run(
                ["git", "-c", "user.name=test", "-c", "user.email=test@test.com", "commit", "-m", "init"],
                cwd=tmpdir, capture_output=True,
            )

            result = subprocess.run(
                [sys.executable, os.path.join(SCRIPT_DIR, "platform_agent_preflight.py"),
                 "--repo", tmpdir, "--report", "report.md", "--allow-platform-dev"],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class TestPreflightResult(unittest.TestCase):
    def test_passed_when_no_failures(self):
        r = preflight.PreflightResult()
        r.add_pass("ok")
        self.assertTrue(r.passed)

    def test_failed_when_any_failure(self):
        r = preflight.PreflightResult()
        r.add_fail("not ok")
        self.assertFalse(r.passed)

    def test_mixed_checks(self):
        r = preflight.PreflightResult()
        r.add_pass("ok")
        r.add_fail("not ok")
        self.assertFalse(r.passed)
        self.assertEqual(len(r.checks), 2)



if __name__ == "__main__":
    unittest.main()
