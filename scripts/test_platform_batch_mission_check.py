#!/usr/bin/env python3
"""Tests for platform_batch_mission_check.py using unittest and stdlib only."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import platform_batch_mission_check as batch_check

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LEDGER_DIR = "ai-ledger/platform"

VALID_MISSION = {
    "phase": "P3-A",
    "agent": "opencode",
    "mission": "ai-ledger/platform/2026-05-31_p5b_test_mission.md",
    "expected_files": ["scripts/output.py"],
    "result": "ai-ledger/platform/2026-05-31_p5b_test_result.json",
    "events": "ai-ledger/platform/2026-05-31_p5b_test_events.jsonl",
    "timeout_seconds": 600,
}


def _make_ledger_dir(tmpdir):
    ld = os.path.join(tmpdir, LEDGER_DIR)
    os.makedirs(ld, exist_ok=True)
    return ld


def _write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def _run_cli(repo, extra_args=None):
    cmd = [
        sys.executable,
        os.path.join(SCRIPT_DIR, "platform_batch_mission_check.py"),
        "--repo", repo,
    ]
    if extra_args:
        cmd.extend(extra_args)
    return subprocess.run(cmd, capture_output=True, text=True)


class TestAllValidBatch(unittest.TestCase):
    def test_all_valid_passes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ld = _make_ledger_dir(tmpdir)
            _write_json(os.path.join(ld, "2026-05-31_p5b_m1_mission.json"), VALID_MISSION)
            m2 = dict(VALID_MISSION, phase="P2-A", mission="ai-ledger/platform/2026-05-31_p5b_m2.md",
                      result="ai-ledger/platform/2026-05-31_p5b_m2_result.json",
                      events="ai-ledger/platform/2026-05-31_p5b_m2_events.jsonl")
            _write_json(os.path.join(ld, "2026-05-31_p5b_m2_mission.json"), m2)
            results, all_pass = batch_check.batch_check(tmpdir)
            self.assertTrue(all_pass)
            self.assertEqual(len(results), 2)
            self.assertTrue(all(r["valid"] for r in results))

    def test_all_valid_cli_zero(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ld = _make_ledger_dir(tmpdir)
            _write_json(os.path.join(ld, "2026-05-31_p5b_m1_mission.json"), VALID_MISSION)
            result = _run_cli(tmpdir)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class TestAllInvalidBatch(unittest.TestCase):
    def test_all_invalid_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ld = _make_ledger_dir(tmpdir)
            bad = {"phase": "bad"}
            _write_json(os.path.join(ld, "2026-05-31_p5b_b1_mission.json"), bad)
            _write_json(os.path.join(ld, "2026-05-31_p5b_b2_mission.json"), bad)
            results, all_pass = batch_check.batch_check(tmpdir)
            self.assertFalse(all_pass)
            self.assertEqual(len(results), 2)
            self.assertTrue(all(not r["valid"] for r in results))

    def test_all_invalid_cli_nonzero(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ld = _make_ledger_dir(tmpdir)
            _write_json(os.path.join(ld, "2026-05-31_p5b_b1_mission.json"), {"phase": "X"})
            result = _run_cli(tmpdir)
            self.assertNotEqual(result.returncode, 0)


class TestMixedBatch(unittest.TestCase):
    def test_mixed_reports_correctly(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ld = _make_ledger_dir(tmpdir)
            _write_json(os.path.join(ld, "2026-05-31_p5b_good_mission.json"), VALID_MISSION)
            _write_json(os.path.join(ld, "2026-05-31_p5b_bad_mission.json"), {"phase": "X"})
            results, all_pass = batch_check.batch_check(tmpdir)
            self.assertFalse(all_pass)
            self.assertEqual(len(results), 2)
            valid_count = sum(1 for r in results if r["valid"])
            self.assertEqual(valid_count, 1)


class TestEmptyMissionSet(unittest.TestCase):
    def test_empty_dir_passes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_ledger_dir(tmpdir)
            results, all_pass = batch_check.batch_check(tmpdir)
            self.assertTrue(all_pass)
            self.assertEqual(len(results), 0)

    def test_empty_cli_zero(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_ledger_dir(tmpdir)
            result = _run_cli(tmpdir)
            self.assertEqual(result.returncode, 0)


class TestMalformedJson(unittest.TestCase):
    def test_malformed_detected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ld = _make_ledger_dir(tmpdir)
            with open(os.path.join(ld, "2026-05-31_p5b_bad_mission.json"), "w") as f:
                f.write("{broken!!!")
            results, all_pass = batch_check.batch_check(tmpdir)
            self.assertFalse(all_pass)
            self.assertIn("malformed JSON", results[0]["failures"][0])

    def test_malformed_cli_nonzero(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ld = _make_ledger_dir(tmpdir)
            with open(os.path.join(ld, "2026-05-31_p5b_bad_mission.json"), "w") as f:
                f.write("not json")
            result = _run_cli(tmpdir)
            self.assertNotEqual(result.returncode, 0)


class TestMissingRequiredFields(unittest.TestCase):
    def test_missing_fields_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ld = _make_ledger_dir(tmpdir)
            incomplete = {"phase": "P3-A", "agent": "opencode"}
            _write_json(os.path.join(ld, "2026-05-31_p5b_inc_mission.json"), incomplete)
            results, all_pass = batch_check.batch_check(tmpdir)
            self.assertFalse(all_pass)
            failures = results[0]["failures"]
            self.assertTrue(any("missing required key" in f for f in failures))


class TestUnsafePathReference(unittest.TestCase):
    def test_unsafe_path_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ld = _make_ledger_dir(tmpdir)
            bad_mission = dict(VALID_MISSION)
            bad_mission["result"] = "../etc/passwd"
            _write_json(os.path.join(ld, "2026-05-31_p5b_unsafe_mission.json"), bad_mission)
            results, all_pass = batch_check.batch_check(tmpdir)
            self.assertFalse(all_pass)
            failures = results[0]["failures"]
            self.assertTrue(
                any("traversal" in f.lower() or "forbidden" in f.lower() for f in failures)
            )


class TestStableJsonOutput(unittest.TestCase):
    def test_json_output_structure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ld = _make_ledger_dir(tmpdir)
            _write_json(os.path.join(ld, "2026-05-31_p5b_m1_mission.json"), VALID_MISSION)
            result = _run_cli(tmpdir, ["--json"])
            self.assertEqual(result.returncode, 0)
            data = json.loads(result.stdout)
            self.assertIn("missions", data)
            self.assertIn("total", data)
            self.assertIn("passed", data)
            self.assertIn("failed", data)
            self.assertIn("all_pass", data)
            self.assertEqual(data["total"], 1)
            self.assertEqual(data["passed"], 1)
            self.assertTrue(data["all_pass"])


if __name__ == "__main__":
    unittest.main()
