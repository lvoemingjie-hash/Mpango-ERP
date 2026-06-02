#!/usr/bin/env python3
"""Tests for platform_harness_index.py using unittest and stdlib only."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import platform_harness_index as harness


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))


class TestValidateOutputPath(unittest.TestCase):
    def test_valid_path(self):
        valid, reason = harness.validate_output_path(
            "ai-ledger/platform/harness_index.md"
        )
        self.assertTrue(valid)

    def test_absolute_path_rejected(self):
        valid, reason = harness.validate_output_path(
            "/tmp/ai-ledger/platform/harness_index.md"
        )
        self.assertFalse(valid)
        self.assertIn("absolute", reason)

    def test_drive_qualified_rejected(self):
        valid, reason = harness.validate_output_path(
            "C:/ai-ledger/platform/harness_index.md"
        )
        self.assertFalse(valid)
        self.assertIn("drive", reason)

    def test_output_outside_prefix_rejected(self):
        valid, reason = harness.validate_output_path("scripts/harness_index.md")
        self.assertFalse(valid)
        self.assertIn("must be under", reason)

    def test_non_md_extension_rejected(self):
        valid, reason = harness.validate_output_path(
            "ai-ledger/platform/harness_index.txt"
        )
        self.assertFalse(valid)
        self.assertIn(".md", reason)

    def test_dot_segment_rejected(self):
        valid, reason = harness.validate_output_path(
            "ai-ledger/platform/./harness_index.md"
        )
        self.assertFalse(valid)

    def test_dotdot_segment_rejected(self):
        valid, reason = harness.validate_output_path(
            "ai-ledger/platform/../harness_index.md"
        )
        self.assertFalse(valid)

    def test_empty_segment_rejected(self):
        valid, reason = harness.validate_output_path(
            "ai-ledger/platform//harness_index.md"
        )
        self.assertFalse(valid)

    def test_backend_prefix_rejected(self):
        valid, reason = harness.validate_output_path(
            "backend/ai-ledger/platform/harness_index.md"
        )
        self.assertFalse(valid)

    def test_frontend_prefix_rejected(self):
        valid, reason = harness.validate_output_path(
            "frontend/ai-ledger/platform/harness_index.md"
        )
        self.assertFalse(valid)

    def test_github_prefix_rejected(self):
        valid, reason = harness.validate_output_path(
            ".github/ai-ledger/platform/harness_index.md"
        )
        self.assertFalse(valid)

    def test_claude_prefix_rejected(self):
        valid, reason = harness.validate_output_path(
            ".claude/ai-ledger/platform/harness_index.md"
        )
        self.assertFalse(valid)

    def test_auth_fragment_rejected(self):
        valid, reason = harness.validate_output_path(
            "ai-ledger/platform/auth_harness_index.md"
        )
        self.assertFalse(valid)
        self.assertIn("auth", reason)

    def test_rbac_fragment_rejected(self):
        valid, reason = harness.validate_output_path(
            "ai-ledger/platform/rbac_harness_index.md"
        )
        self.assertFalse(valid)

    def test_tenancy_fragment_rejected(self):
        valid, reason = harness.validate_output_path(
            "ai-ledger/platform/tenancy_harness_index.md"
        )
        self.assertFalse(valid)

    def test_session_fragment_rejected(self):
        valid, reason = harness.validate_output_path(
            "ai-ledger/platform/session_harness_index.md"
        )
        self.assertFalse(valid)

    def test_migration_fragment_rejected(self):
        valid, reason = harness.validate_output_path(
            "ai-ledger/platform/migration_harness_index.md"
        )
        self.assertFalse(valid)

    def test_payment_fragment_rejected(self):
        valid, reason = harness.validate_output_path(
            "ai-ledger/platform/payment_harness_index.md"
        )
        self.assertFalse(valid)

    def test_phase4_specific_rejected(self):
        valid, reason = harness.validate_output_path(
            "docs/ai/PHASE4_FRONTEND_CONTRACT.md"
        )
        self.assertFalse(valid)


class TestScanHarnessScripts(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.scripts_dir = os.path.join(self.tmpdir, "scripts")
        os.makedirs(self.scripts_dir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_finds_platform_scripts(self):
        with open(os.path.join(self.scripts_dir, "platform_alpha.py"), "w") as f:
            f.write("# alpha\n")
        with open(os.path.join(self.scripts_dir, "platform_beta.py"), "w") as f:
            f.write("# beta\n")

        scripts = harness.scan_harness_scripts(self.scripts_dir)
        self.assertEqual(len(scripts), 2)

    def test_ignores_non_platform_scripts(self):
        with open(os.path.join(self.scripts_dir, "helper.py"), "w") as f:
            f.write("# helper\n")
        scripts = harness.scan_harness_scripts(self.scripts_dir)
        self.assertEqual(len(scripts), 0)

    def test_pairs_with_existing_test(self):
        with open(os.path.join(self.scripts_dir, "platform_alpha.py"), "w") as f:
            f.write("# alpha\n")
        with open(
            os.path.join(self.scripts_dir, "test_platform_alpha.py"), "w"
        ) as f:
            f.write("# test alpha\n")

        scripts = harness.scan_harness_scripts(self.scripts_dir)
        self.assertEqual(len(scripts), 1)
        self.assertIn("test_platform_alpha.py", scripts[0][1])
        self.assertEqual(scripts[0][0], "scripts/platform_alpha.py")
        self.assertEqual(scripts[0][1], "scripts/test_platform_alpha.py")

    def test_missing_test_rendered_as_missing(self):
        with open(os.path.join(self.scripts_dir, "platform_solo.py"), "w") as f:
            f.write("# solo\n")

        scripts = harness.scan_harness_scripts(self.scripts_dir)
        self.assertEqual(len(scripts), 1)
        self.assertEqual(scripts[0][1], "MISSING")

    def test_missing_dir_returns_empty(self):
        scripts = harness.scan_harness_scripts(
            os.path.join(self.tmpdir, "nonexistent")
        )
        self.assertEqual(scripts, [])


class TestScanPlatformLedgers(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.ledger_dir = os.path.join(self.tmpdir, "platform")
        os.makedirs(self.ledger_dir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_finds_md_ledgers(self):
        with open(os.path.join(self.ledger_dir, "ledger_a.md"), "w") as f:
            f.write("# A\n")
        with open(os.path.join(self.ledger_dir, "ledger_b.md"), "w") as f:
            f.write("# B\n")

        ledgers = harness.scan_platform_ledgers(self.ledger_dir)
        self.assertEqual(len(ledgers), 2)
        self.assertEqual(ledgers[0], "ai-ledger/platform/ledger_a.md")

    def test_ignores_non_md(self):
        with open(os.path.join(self.ledger_dir, "ledger.json"), "w") as f:
            f.write("{}")
        ledgers = harness.scan_platform_ledgers(self.ledger_dir)
        self.assertEqual(len(ledgers), 0)

    def test_ignores_gitkeep(self):
        with open(os.path.join(self.ledger_dir, ".gitkeep"), "w") as f:
            f.write("")
        with open(os.path.join(self.ledger_dir, "real.md"), "w") as f:
            f.write("# real\n")

        ledgers = harness.scan_platform_ledgers(self.ledger_dir)
        self.assertEqual(len(ledgers), 1)


class TestGenerateIndex(unittest.TestCase):
    def test_contains_required_fields(self):
        scripts = [("scripts/platform_foo.py", "scripts/test_platform_foo.py")]
        ledgers = ["ai-ledger/platform/some_ledger.md"]

        content = harness.generate_index(
            "main", "abc123", "ai-ledger/platform/harness_index.md",
            scripts, ledgers,
        )

        for field in harness.REPORT_FIELDS:
            self.assertIn(field, content.lower())

    def test_missing_test_in_table(self):
        scripts = [("scripts/platform_solo.py", "MISSING")]
        content = harness.generate_index(
            "main", "abc123", "ai-ledger/platform/harness_index.md",
            scripts, [],
        )
        self.assertIn("MISSING", content)


class TestValidCliWritesIndex(unittest.TestCase):
    def test_cli_writes_index_and_exits_0(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
            subprocess.run(
                ["git", "checkout", "-b", "codex/platform-test"],
                cwd=tmpdir, capture_output=True,
            )

            scripts_dir = os.path.join(tmpdir, "scripts")
            os.makedirs(scripts_dir)
            with open(os.path.join(scripts_dir, "platform_alpha.py"), "w") as f:
                f.write("# alpha\n")
            with open(os.path.join(scripts_dir, "test_platform_alpha.py"), "w") as f:
                f.write("# test alpha\n")
            with open(os.path.join(scripts_dir, "platform_solo.py"), "w") as f:
                f.write("# solo\n")

            ledger_dir = os.path.join(tmpdir, "ai-ledger", "platform")
            os.makedirs(ledger_dir)
            with open(os.path.join(ledger_dir, "some_ledger.md"), "w") as f:
                f.write("# ledger\n")

            subprocess.run(["git", "add", "-A"], cwd=tmpdir, capture_output=True)
            subprocess.run(
                ["git", "-c", "user.name=test", "-c", "user.email=test@test.com",
                 "commit", "-m", "init"],
                cwd=tmpdir, capture_output=True,
            )

            result = subprocess.run(
                [
                    sys.executable,
                    os.path.join(SCRIPT_DIR, "platform_harness_index.py"),
                    "--repo", tmpdir,
                    "--output", "ai-ledger/platform/harness_index.md",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            output_file = os.path.join(
                tmpdir, "ai-ledger", "platform", "harness_index.md"
            )
            self.assertTrue(os.path.isfile(output_file))

            with open(output_file, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("platform_alpha.py", content)
            self.assertIn("test_platform_alpha.py", content)
            self.assertIn("platform_solo.py", content)
            self.assertIn("MISSING", content)
            self.assertIn("some_ledger.md", content)


class TestInvalidCliPaths(unittest.TestCase):
    def test_output_outside_prefix_fails(self):
        result = subprocess.run(
            [
                sys.executable,
                os.path.join(SCRIPT_DIR, "platform_harness_index.py"),
                "--repo", REPO_ROOT,
                "--output", "scripts/harness_index.md",
            ],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must be under", result.stdout)

    def test_absolute_output_fails(self):
        result = subprocess.run(
            [
                sys.executable,
                os.path.join(SCRIPT_DIR, "platform_harness_index.py"),
                "--repo", REPO_ROOT,
                "--output", "/tmp/harness_index.md",
            ],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("absolute", result.stdout)

    def test_forbidden_fragment_fails(self):
        result = subprocess.run(
            [
                sys.executable,
                os.path.join(SCRIPT_DIR, "platform_harness_index.py"),
                "--repo", REPO_ROOT,
                "--output", "ai-ledger/platform/auth_index.md",
            ],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("auth", result.stdout)

    def test_traversal_fails(self):
        result = subprocess.run(
            [
                sys.executable,
                os.path.join(SCRIPT_DIR, "platform_harness_index.py"),
                "--repo", REPO_ROOT,
                "--output", "ai-ledger/platform/../harness_index.md",
            ],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)


class TestCheckModePassesWithConsistentIndex(unittest.TestCase):
    def _make_repo(self, tmpdir):
        scripts_dir = os.path.join(tmpdir, "scripts")
        os.makedirs(scripts_dir, exist_ok=True)
        with open(os.path.join(scripts_dir, "platform_alpha.py"), "w") as f:
            f.write("# alpha\n")
        with open(os.path.join(scripts_dir, "test_platform_alpha.py"), "w") as f:
            f.write("# test\n")
        ledger_dir = os.path.join(tmpdir, "ai-ledger", "platform")
        os.makedirs(ledger_dir, exist_ok=True)
        with open(os.path.join(ledger_dir, "alpha_ledger.md"), "w") as f:
            f.write("# ledger\n")

    def test_check_passes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._make_repo(tmpdir)
            issues, _, _ = harness.check_consistency(tmpdir)
            self.assertEqual(issues, [])

    def test_check_cli_zero(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._make_repo(tmpdir)
            result = subprocess.run(
                [sys.executable,
                 os.path.join(SCRIPT_DIR, "platform_harness_index.py"),
                 "--repo", tmpdir, "--check"],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PASS", result.stdout)


class TestCheckModeFailsWithMissingTest(unittest.TestCase):
    def test_check_detects_missing_test(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            scripts_dir = os.path.join(tmpdir, "scripts")
            os.makedirs(scripts_dir)
            with open(os.path.join(scripts_dir, "platform_solo.py"), "w") as f:
                f.write("# solo\n")
            issues, _, _ = harness.check_consistency(tmpdir)
            types = [i["type"] for i in issues]
            self.assertIn("missing_test", types)


class TestCheckModeIgnoresOrphanedLedgers(unittest.TestCase):
    """Verify that a ledger with no matching script does not trigger a
    pairing/existence issue.  Orphaned ledgers are outside the scope of
    the consistency check (the check validates script/test pairing and
    file existence, not ledger-to-script mapping)."""

    def test_orphaned_ledger_not_flagged(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_dir = os.path.join(tmpdir, "ai-ledger", "platform")
            os.makedirs(ledger_dir, exist_ok=True)
            with open(os.path.join(ledger_dir, "stale_ledger.md"), "w") as f:
                f.write("# stale\n")
            issues, _, _ = harness.check_consistency(tmpdir)
            self.assertEqual(issues, [])


class TestCheckModeDoesNotWriteFiles(unittest.TestCase):
    def test_check_no_file_written(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            scripts_dir = os.path.join(tmpdir, "scripts")
            os.makedirs(scripts_dir)
            with open(os.path.join(scripts_dir, "platform_x.py"), "w") as f:
                f.write("# x\n")
            with open(os.path.join(scripts_dir, "test_platform_x.py"), "w") as f:
                f.write("# test\n")
            result = subprocess.run(
                [sys.executable,
                 os.path.join(SCRIPT_DIR, "platform_harness_index.py"),
                 "--repo", tmpdir, "--check"],
                capture_output=True, text=True,
            )
            output_file = os.path.join(tmpdir, "ai-ledger", "platform", "index.md")
            self.assertFalse(os.path.isfile(output_file))


class TestExistingGenerateStillWorks(unittest.TestCase):
    def test_generate_backward_compat(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
            subprocess.run(
                ["git", "checkout", "-b", "test-branch"],
                cwd=tmpdir, capture_output=True,
            )
            scripts_dir = os.path.join(tmpdir, "scripts")
            os.makedirs(scripts_dir)
            with open(os.path.join(scripts_dir, "platform_compat.py"), "w") as f:
                f.write("# compat\n")
            with open(os.path.join(scripts_dir, "test_platform_compat.py"), "w") as f:
                f.write("# test\n")
            ledger_dir = os.path.join(tmpdir, "ai-ledger", "platform")
            os.makedirs(ledger_dir)
            subprocess.run(["git", "add", "-A"], cwd=tmpdir, capture_output=True)
            subprocess.run(
                ["git", "-c", "user.name=t", "-c", "user.email=t@t.com",
                 "commit", "-m", "init"],
                cwd=tmpdir, capture_output=True,
            )
            result = subprocess.run(
                [sys.executable,
                 os.path.join(SCRIPT_DIR, "platform_harness_index.py"),
                 "--repo", tmpdir,
                 "--output", "ai-ledger/platform/index.md"],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(
                os.path.isfile(os.path.join(tmpdir, "ai-ledger", "platform", "index.md"))
            )


class TestStaleIndexDetection(unittest.TestCase):
    """Tests for stale index detection via --check-index option.

    Default --check is pairing/existence only.  Stale detection requires an
    explicit index artifact path via --check-index (or the index_artifact
    parameter to check_consistency).
    """

    def _make_repo_with_index(self, tmpdir):
        """Create a repo with scripts, ledgers, and a generated index."""
        scripts_dir = os.path.join(tmpdir, "scripts")
        os.makedirs(scripts_dir, exist_ok=True)
        with open(os.path.join(scripts_dir, "platform_alpha.py"), "w") as f:
            f.write("# alpha\n")
        with open(os.path.join(scripts_dir, "test_platform_alpha.py"), "w") as f:
            f.write("# test\n")
        ledger_dir = os.path.join(tmpdir, "ai-ledger", "platform")
        os.makedirs(ledger_dir, exist_ok=True)
        with open(os.path.join(ledger_dir, "alpha_ledger.md"), "w") as f:
            f.write("# ledger\n")
        # Generate the index
        scripts = harness.scan_harness_scripts(scripts_dir)
        ledgers = harness.scan_platform_ledgers(ledger_dir)
        index_content = harness.generate_index(
            "test-branch", "abc1234",
            "ai-ledger/platform/harness_index.md",
            scripts, ledgers,
        )
        index_path = os.path.join(ledger_dir, "harness_index.md")
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(index_content)
        return scripts_dir, ledger_dir

    def test_default_check_ignores_index_files(self):
        """Default --check is pairing/existence only; does NOT scan for
        *harness_index*.md files in the ledger directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scripts_dir, _ = self._make_repo_with_index(tmpdir)
            # Add a new script not in the index
            with open(os.path.join(scripts_dir, "platform_beta.py"), "w") as f:
                f.write("# beta\n")
            with open(os.path.join(scripts_dir, "test_platform_beta.py"), "w") as f:
                f.write("# test beta\n")
            # Without --check-index, no stale issues reported
            issues, _, _ = harness.check_consistency(tmpdir)
            stale = [i for i in issues if "stale_index" in i["type"]]
            self.assertEqual(stale, [])

    def test_check_index_detects_new_script(self):
        """With explicit index_artifact, new scripts are detected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scripts_dir, _ = self._make_repo_with_index(tmpdir)
            with open(os.path.join(scripts_dir, "platform_beta.py"), "w") as f:
                f.write("# beta\n")
            with open(os.path.join(scripts_dir, "test_platform_beta.py"), "w") as f:
                f.write("# test beta\n")
            issues, _, _ = harness.check_consistency(
                tmpdir, index_artifact="ai-ledger/platform/harness_index.md",
            )
            stale = [i for i in issues if "stale_index" in i["type"]]
            self.assertTrue(len(stale) > 0)
            paths = [i["path"] for i in stale]
            self.assertIn("scripts/platform_beta.py", paths)

    def test_check_index_detects_new_ledger(self):
        """With explicit index_artifact, new ledgers are detected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _, ledger_dir = self._make_repo_with_index(tmpdir)
            with open(os.path.join(ledger_dir, "beta_ledger.md"), "w") as f:
                f.write("# beta ledger\n")
            issues, _, _ = harness.check_consistency(
                tmpdir, index_artifact="ai-ledger/platform/harness_index.md",
            )
            stale = [i for i in issues if "stale_index" in i["type"]]
            self.assertTrue(len(stale) > 0)
            paths = [i["path"] for i in stale]
            self.assertIn("ai-ledger/platform/beta_ledger.md", paths)

    def test_fresh_index_no_stale_issues(self):
        """Fresh index matches current state: no stale issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._make_repo_with_index(tmpdir)
            issues, _, _ = harness.check_consistency(
                tmpdir, index_artifact="ai-ledger/platform/harness_index.md",
            )
            stale = [i for i in issues if "stale_index" in i["type"]]
            self.assertEqual(stale, [])

    def test_missing_index_artifact_reported(self):
        """Nonexistent --check-index path yields a missing_index issue."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scripts_dir = os.path.join(tmpdir, "scripts")
            os.makedirs(scripts_dir)
            with open(os.path.join(scripts_dir, "platform_x.py"), "w") as f:
                f.write("# x\n")
            with open(os.path.join(scripts_dir, "test_platform_x.py"), "w") as f:
                f.write("# test\n")
            issues, _, _ = harness.check_consistency(
                tmpdir, index_artifact="ai-ledger/platform/nonexistent.md",
            )
            types = [i["type"] for i in issues]
            self.assertIn("missing_index", types)

    def test_cli_check_index_flag(self):
        """CLI --check --check-index detects stale index."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scripts_dir, _ = self._make_repo_with_index(tmpdir)
            with open(os.path.join(scripts_dir, "platform_gamma.py"), "w") as f:
                f.write("# gamma\n")
            result = subprocess.run(
                [sys.executable,
                 os.path.join(SCRIPT_DIR, "platform_harness_index.py"),
                 "--repo", tmpdir, "--check",
                 "--check-index", "ai-ledger/platform/harness_index.md"],
                capture_output=True, text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("stale_index", result.stdout)

    def test_cli_check_without_index_passes(self):
        """CLI --check alone (no --check-index) passes even with stale
        index files present in the ledger directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scripts_dir, _ = self._make_repo_with_index(tmpdir)
            with open(os.path.join(scripts_dir, "platform_gamma.py"), "w") as f:
                f.write("# gamma\n")
            with open(os.path.join(scripts_dir, "test_platform_gamma.py"), "w") as f:
                f.write("# test gamma\n")
            result = subprocess.run(
                [sys.executable,
                 os.path.join(SCRIPT_DIR, "platform_harness_index.py"),
                 "--repo", tmpdir, "--check"],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PASS", result.stdout)

    def test_multiple_harness_index_files_not_treated_as_stale(self):
        """Multiple *harness_index*.md files in ledger dir are NOT treated
        as canonical indices by default --check."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scripts_dir = os.path.join(tmpdir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            with open(os.path.join(scripts_dir, "platform_alpha.py"), "w") as f:
                f.write("# alpha\n")
            with open(os.path.join(scripts_dir, "test_platform_alpha.py"), "w") as f:
                f.write("# test\n")
            ledger_dir = os.path.join(tmpdir, "ai-ledger", "platform")
            os.makedirs(ledger_dir, exist_ok=True)
            # Create multiple harness_index*.md files (not canonical indices)
            with open(os.path.join(ledger_dir, "2026-05-28_harness_index_mission.md"), "w") as f:
                f.write("# Mission doc, not an index\n")
            with open(os.path.join(ledger_dir, "2026-05-28_harness_index.md"), "w") as f:
                f.write("# Old generated index with stale content\n")
            with open(os.path.join(ledger_dir, "alpha_ledger.md"), "w") as f:
                f.write("# ledger\n")
            # Default --check should PASS: only pairing/existence checked
            issues, _, _ = harness.check_consistency(tmpdir)
            self.assertEqual(issues, [])

    def test_explicit_index_checks_only_that_file(self):
        """--check-index targets one specific file, not all *harness_index*.md."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scripts_dir = os.path.join(tmpdir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            with open(os.path.join(scripts_dir, "platform_alpha.py"), "w") as f:
                f.write("# alpha\n")
            with open(os.path.join(scripts_dir, "test_platform_alpha.py"), "w") as f:
                f.write("# test\n")
            with open(os.path.join(scripts_dir, "platform_beta.py"), "w") as f:
                f.write("# beta\n")
            with open(os.path.join(scripts_dir, "test_platform_beta.py"), "w") as f:
                f.write("# test beta\n")
            ledger_dir = os.path.join(tmpdir, "ai-ledger", "platform")
            os.makedirs(ledger_dir, exist_ok=True)
            # Old index only mentions alpha
            with open(os.path.join(ledger_dir, "harness_index.md"), "w") as f:
                f.write("# Index\nscripts/platform_alpha.py\n")
            # Other harness_index file mentions beta (not checked)
            with open(os.path.join(ledger_dir, "2026-05-28_harness_index.md"), "w") as f:
                f.write("# Other\nscripts/platform_beta.py\n")
            # Only harness_index.md is checked when explicitly specified
            issues, _, _ = harness.check_consistency(
                tmpdir, index_artifact="ai-ledger/platform/harness_index.md",
            )
            stale = [i for i in issues if "stale_index" in i["type"]]
            paths = [i["path"] for i in stale]
            # beta is stale because harness_index.md doesn't mention it
            self.assertIn("scripts/platform_beta.py", paths)
            # alpha is NOT stale because harness_index.md mentions it
            self.assertNotIn("scripts/platform_alpha.py", paths)

    def test_check_index_staleness_function_directly(self):
        """Unit test for the check_index_staleness helper."""
        with tempfile.TemporaryDirectory() as tmpdir:
            index_path = os.path.join(tmpdir, "harness_index.md")
            with open(index_path, "w", encoding="utf-8") as f:
                f.write("# Old Index\nscripts/platform_old.py\n")
            scripts = [("scripts/platform_new.py", "scripts/test_platform_new.py")]
            ledgers = ["ai-ledger/platform/new_ledger.md"]
            issues = harness.check_index_staleness(index_path, scripts, ledgers)
            self.assertEqual(len(issues), 3)  # new script + new test + new ledger
            types = [i["type"] for i in issues]
            self.assertIn("stale_index_new_script", types)
            self.assertIn("stale_index_new_ledger", types)


if __name__ == "__main__":
    unittest.main()
