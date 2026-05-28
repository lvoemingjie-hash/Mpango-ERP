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


if __name__ == "__main__":
    unittest.main()
