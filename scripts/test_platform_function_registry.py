#!/usr/bin/env python3
"""Tests for platform_function_registry.py using unittest and stdlib only."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import platform_function_registry as registry


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))


class TestScanScripts(unittest.TestCase):
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
        entries = registry.scan_scripts(self.scripts_dir)
        self.assertEqual(len(entries), 2)

    def test_ignores_non_platform(self):
        with open(os.path.join(self.scripts_dir, "helper.py"), "w") as f:
            f.write("# helper\n")
        entries = registry.scan_scripts(self.scripts_dir)
        self.assertEqual(len(entries), 0)

    def test_pairs_with_test(self):
        with open(os.path.join(self.scripts_dir, "platform_alpha.py"), "w") as f:
            f.write("# alpha\n")
        with open(os.path.join(self.scripts_dir, "test_platform_alpha.py"), "w") as f:
            f.write("# test\n")
        entries = registry.scan_scripts(self.scripts_dir)
        self.assertEqual(len(entries), 1)
        self.assertTrue(entries[0]["paired"])
        self.assertIn("test_platform_alpha.py", entries[0]["test"])

    def test_missing_test_marked_unpaired(self):
        with open(os.path.join(self.scripts_dir, "platform_solo.py"), "w") as f:
            f.write("# solo\n")
        entries = registry.scan_scripts(self.scripts_dir)
        self.assertEqual(len(entries), 1)
        self.assertFalse(entries[0]["paired"])
        self.assertIsNone(entries[0]["test"])

    def test_function_name_extracted(self):
        with open(os.path.join(self.scripts_dir, "platform_health_check.py"), "w") as f:
            f.write("# health\n")
        entries = registry.scan_scripts(self.scripts_dir)
        self.assertEqual(entries[0]["function"], "health_check")

    def test_missing_dir_returns_empty(self):
        entries = registry.scan_scripts(os.path.join(self.tmpdir, "nonexistent"))
        self.assertEqual(entries, [])


class TestFindRelatedLedgers(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.ledger_dir = os.path.join(self.tmpdir, "platform")
        os.makedirs(self.ledger_dir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_exact_function_match(self):
        with open(os.path.join(self.ledger_dir, "2026-06-03_p7a_diff_auditor.md"), "w") as f:
            f.write("# ledger\n")
        related = registry.find_related_ledgers(self.ledger_dir, "diff_auditor")
        self.assertEqual(len(related), 1)
        self.assertIn("diff_auditor", related[0])

    def test_keyword_match(self):
        with open(os.path.join(self.ledger_dir, "2026-06-03_harness_index.md"), "w") as f:
            f.write("# ledger\n")
        related = registry.find_related_ledgers(self.ledger_dir, "harness_index_check")
        # "harness" and "index" are keywords, should match
        self.assertTrue(len(related) >= 1)

    def test_no_match(self):
        with open(os.path.join(self.ledger_dir, "2026-06-03_unrelated.md"), "w") as f:
            f.write("# unrelated\n")
        related = registry.find_related_ledgers(self.ledger_dir, "health_check")
        self.assertEqual(len(related), 0)

    def test_missing_dir_returns_empty(self):
        related = registry.find_related_ledgers(
            os.path.join(self.tmpdir, "nonexistent"), "health_check"
        )
        self.assertEqual(related, [])


class TestBuildRegistry(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        scripts_dir = os.path.join(self.tmpdir, "scripts")
        os.makedirs(scripts_dir)
        ledger_dir = os.path.join(self.tmpdir, "ai-ledger", "platform")
        os.makedirs(ledger_dir)

        # Create scripts
        with open(os.path.join(scripts_dir, "platform_alpha.py"), "w") as f:
            f.write("# alpha\n")
        with open(os.path.join(scripts_dir, "test_platform_alpha.py"), "w") as f:
            f.write("# test\n")
        with open(os.path.join(scripts_dir, "platform_solo.py"), "w") as f:
            f.write("# solo\n")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_registry_counts(self):
        result = registry.build_registry(self.tmpdir)
        self.assertEqual(result["total_scripts"], 2)
        self.assertEqual(result["paired"], 1)
        self.assertEqual(result["unpaired"], 1)

    def test_entries_have_required_fields(self):
        result = registry.build_registry(self.tmpdir)
        for entry in result["entries"]:
            self.assertIn("script", entry)
            self.assertIn("test", entry)
            self.assertIn("function", entry)
            self.assertIn("paired", entry)
            self.assertIn("ledgers", entry)


class TestHumanOutput(unittest.TestCase):
    def test_format_human(self):
        reg = {
            "total_scripts": 2,
            "paired": 1,
            "unpaired": 1,
            "entries": [
                {
                    "script": "scripts/platform_alpha.py",
                    "test": "scripts/test_platform_alpha.py",
                    "function": "alpha",
                    "paired": True,
                    "ledgers": [],
                },
                {
                    "script": "scripts/platform_solo.py",
                    "test": None,
                    "function": "solo",
                    "paired": False,
                    "ledgers": [],
                },
            ],
        }
        output = registry.format_human(reg)
        self.assertIn("Platform Function Registry", output)
        self.assertIn("alpha", output)
        self.assertIn("solo", output)
        self.assertIn("PASS", output)
        self.assertIn("MISSING TEST", output)


class TestJsonOutput(unittest.TestCase):
    def test_json_cli(self):
        result = subprocess.run(
            [sys.executable,
             os.path.join(SCRIPT_DIR, "platform_function_registry.py"),
             "--repo", REPO_ROOT, "--json"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        data = json.loads(result.stdout)
        self.assertIn("total_scripts", data)
        self.assertIn("entries", data)
        self.assertGreater(data["total_scripts"], 0)


class TestAgainstRealRepo(unittest.TestCase):
    def test_real_repo_has_scripts(self):
        result = registry.build_registry(REPO_ROOT)
        self.assertGreater(result["total_scripts"], 0)
        # All existing scripts should be paired
        self.assertEqual(result["unpaired"], 0)

    def test_real_repo_human_output(self):
        result = subprocess.run(
            [sys.executable,
             os.path.join(SCRIPT_DIR, "platform_function_registry.py"),
             "--repo", REPO_ROOT],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Platform Function Registry", result.stdout)


if __name__ == "__main__":
    unittest.main()
