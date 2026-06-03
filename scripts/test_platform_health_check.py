#!/usr/bin/env python3
"""Tests for platform_health_check.py using unittest and stdlib only."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import platform_health_check as health


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))


class TestBatchMissionCheck(unittest.TestCase):
    def test_returns_result_dict(self):
        result = health.check_batch_missions(REPO_ROOT, os.path.join(REPO_ROOT, "scripts"))
        self.assertIn("gate", result)
        self.assertEqual(result["gate"], "batch_mission_check")
        self.assertIn("pass", result)
        self.assertIn("total", result)

    def test_real_repo_passes(self):
        result = health.check_batch_missions(REPO_ROOT, os.path.join(REPO_ROOT, "scripts"))
        self.assertTrue(result["pass"])
        self.assertGreater(result["total"], 0)


class TestHarnessIndexCheck(unittest.TestCase):
    def test_returns_result_dict(self):
        result = health.check_harness_index(REPO_ROOT, os.path.join(REPO_ROOT, "scripts"))
        self.assertIn("gate", result)
        self.assertEqual(result["gate"], "harness_index")
        self.assertIn("scripts", result)
        self.assertIn("ledgers", result)
        self.assertIn("issues", result)

    def test_real_repo_passes(self):
        result = health.check_harness_index(REPO_ROOT, os.path.join(REPO_ROOT, "scripts"))
        self.assertTrue(result["pass"])
        self.assertGreater(result["scripts"], 0)


class TestWorkerReliabilityCheck(unittest.TestCase):
    def test_returns_result_dict(self):
        result = health.check_worker_reliability(REPO_ROOT, os.path.join(REPO_ROOT, "scripts"))
        self.assertIn("gate", result)
        self.assertEqual(result["gate"], "worker_reliability")
        self.assertIn("done", result)
        self.assertIn("failed", result)

    def test_real_repo_no_failures(self):
        result = health.check_worker_reliability(REPO_ROOT, os.path.join(REPO_ROOT, "scripts"))
        self.assertEqual(result["failed"], 0)


class TestDiffAuditorCheck(unittest.TestCase):
    def test_returns_result_dict(self):
        result = health.check_diff_auditor(REPO_ROOT, os.path.join(REPO_ROOT, "scripts"))
        self.assertIn("gate", result)
        self.assertEqual(result["gate"], "diff_auditor")
        self.assertIn("pass", result)
        self.assertIn("violations", result)

    def test_compare_with_base_ref(self):
        result = health.check_diff_auditor(
            REPO_ROOT, os.path.join(REPO_ROOT, "scripts"),
            base_ref="origin/platform-dev",
        )
        self.assertIn("gate", result)
        self.assertEqual(result["gate"], "diff_auditor")
        self.assertIn("total", result)
        self.assertGreater(result["total"], 0)


class TestDetectSecretsCheck(unittest.TestCase):
    def test_returns_result_dict(self):
        result = health.check_detect_secrets(REPO_ROOT)
        self.assertIn("gate", result)
        self.assertEqual(result["gate"], "detect_secrets")
        self.assertIn("pass", result)

    def test_real_repo_no_artifact_secrets(self):
        result = health.check_detect_secrets(REPO_ROOT)
        self.assertTrue(result["pass"])

    def test_missing_dir_passes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = health.check_detect_secrets(tmpdir)
            self.assertTrue(result["pass"])
            self.assertIn("no artifact dir", result.get("note", ""))


class TestGitnexusCheck(unittest.TestCase):
    def test_returns_result_dict(self):
        result = health.check_gitnexus(REPO_ROOT)
        self.assertIn("gate", result)
        self.assertEqual(result["gate"], "gitnexus")

    def test_real_repo_has_gitnexus(self):
        result = health.check_gitnexus(REPO_ROOT)
        self.assertIsNotNone(result["pass"])


class TestRunHealthCheck(unittest.TestCase):
    def test_aggregates_all_gates(self):
        result = health.run_health_check(REPO_ROOT)
        self.assertIn("overall", result)
        self.assertIn("gates", result)
        self.assertIn("total_gates", result)
        self.assertEqual(len(result["gates"]), 6)

    def test_real_repo_passes(self):
        result = health.run_health_check(REPO_ROOT)
        self.assertEqual(result["overall"], "PASS")

    def test_with_base_ref(self):
        result = health.run_health_check(REPO_ROOT, base_ref="origin/platform-dev")
        self.assertIn("overall", result)
        self.assertEqual(len(result["gates"]), 6)


class TestHumanOutput(unittest.TestCase):
    def test_format_human(self):
        result = health.run_health_check(REPO_ROOT)
        output = health.format_human(result)
        self.assertIn("Platform Health Check", output)
        self.assertIn("PASS", output)


class TestJsonCli(unittest.TestCase):
    def test_json_output(self):
        result = subprocess.run(
            [sys.executable,
             os.path.join(SCRIPT_DIR, "platform_health_check.py"),
             "--repo", REPO_ROOT, "--json"],
            capture_output=True, text=True,
            timeout=300,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["overall"], "PASS")
        self.assertGreater(len(data["gates"]), 0)


class TestHumanCli(unittest.TestCase):
    def test_human_output(self):
        result = subprocess.run(
            [sys.executable,
             os.path.join(SCRIPT_DIR, "platform_health_check.py"),
             "--repo", REPO_ROOT],
            capture_output=True, text=True,
            timeout=300,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Platform Health Check", result.stdout)
        self.assertIn("PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
