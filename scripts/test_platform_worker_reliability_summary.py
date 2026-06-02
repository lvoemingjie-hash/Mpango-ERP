#!/usr/bin/env python3
"""Tests for platform_worker_reliability_summary.py using unittest and stdlib only."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import platform_worker_reliability_summary as wrs

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LEDGER_DIR = "ai-ledger/platform"

VALID_MISSION = {
    "phase": "P3-A",
    "agent": "opencode",
    "mission": "ai-ledger/platform/2026-05-31_test_mission.md",
    "expected_files": ["scripts/output.py"],
    "result": "ai-ledger/platform/2026-05-31_test_result.json",
    "events": "ai-ledger/platform/2026-05-31_test_events.jsonl",
    "timeout_seconds": 600,
}


def _make_ledger_dir(tmpdir):
    ld = os.path.join(tmpdir, LEDGER_DIR)
    os.makedirs(ld, exist_ok=True)
    return ld


def _write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def _write_file(path, content=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _setup_success(tmpdir):
    ld = _make_ledger_dir(tmpdir)
    _write_json(os.path.join(ld, "2026-05-31_s1_mission.json"), VALID_MISSION)
    _write_json(os.path.join(ld, "2026-05-31_test_result.json"), {"status": "done"})
    _write_file(os.path.join(ld, "2026-05-31_test_events.jsonl"),
                '{"elapsed_seconds": 42.5, "exit_code": 0, "redacted": true}\n')


def _run_cli(repo, extra_args=None):
    cmd = [
        sys.executable,
        os.path.join(SCRIPT_DIR, "platform_worker_reliability_summary.py"),
        "--repo", repo,
    ]
    if extra_args:
        cmd.extend(extra_args)
    return subprocess.run(cmd, capture_output=True, text=True)


class TestAllSuccessDataset(unittest.TestCase):
    def test_done_counted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _setup_success(tmpdir)
            s = wrs.summarize_results(tmpdir)
            self.assertEqual(s["results"]["done"], 1)
            self.assertEqual(s["results"]["failed"], 0)
            self.assertEqual(s["total_missions"], 1)

    def test_elapsed_recorded(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _setup_success(tmpdir)
            s = wrs.summarize_results(tmpdir)
            self.assertEqual(len(s["elapsed"]), 1)
            self.assertAlmostEqual(s["elapsed"][0], 42.5)


class TestAllFailureDataset(unittest.TestCase):
    def test_failed_counted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ld = _make_ledger_dir(tmpdir)
            _write_json(os.path.join(ld, "2026-05-31_f1_mission.json"), VALID_MISSION)
            _write_json(os.path.join(ld, "2026-05-31_test_result.json"), {"status": "failed"})
            _write_file(os.path.join(ld, "2026-05-31_test_events.jsonl"),
                        '{"exit_code": 1, "redacted": true}\n')
            s = wrs.summarize_results(tmpdir)
            self.assertEqual(s["results"]["failed"], 1)
            self.assertEqual(s["nonzero_exit"], 1)


class TestMixedOutcomes(unittest.TestCase):
    def test_mixed_counts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ld = _make_ledger_dir(tmpdir)
            # Success
            m1 = dict(VALID_MISSION,
                      result="ai-ledger/platform/2026-05-31_r1.json",
                      events="ai-ledger/platform/2026-05-31_e1.jsonl")
            _write_json(os.path.join(ld, "2026-05-31_m1_mission.json"), m1)
            _write_json(os.path.join(ld, "2026-05-31_r1.json"), {"status": "done"})
            _write_file(os.path.join(ld, "2026-05-31_e1.jsonl"),
                        '{"elapsed_seconds": 10, "exit_code": 0, "redacted": true}\n')
            # Partial
            m2 = dict(VALID_MISSION,
                      result="ai-ledger/platform/2026-05-31_r2.json",
                      events="ai-ledger/platform/2026-05-31_e2.jsonl")
            _write_json(os.path.join(ld, "2026-05-31_m2_mission.json"), m2)
            _write_json(os.path.join(ld, "2026-05-31_r2.json"),
                        {"status": "partial", "blocker": "timeout at 900 seconds"})
            _write_file(os.path.join(ld, "2026-05-31_e2.jsonl"),
                        '{"timed_out": true, "elapsed_seconds": 900, "exit_code": 124, "redacted": true}\n')
            s = wrs.summarize_results(tmpdir)
            self.assertEqual(s["results"]["done"], 1)
            self.assertEqual(s["results"]["partial"], 1)
            self.assertEqual(s["timeouts"], 1)


class TestTimeoutOnly(unittest.TestCase):
    def test_timeout_detected_from_blocker(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ld = _make_ledger_dir(tmpdir)
            _write_json(os.path.join(ld, "2026-05-31_t1_mission.json"), VALID_MISSION)
            _write_json(os.path.join(ld, "2026-05-31_test_result.json"),
                        {"status": "partial", "blocker": "opencode timed out"})
            _write_file(os.path.join(ld, "2026-05-31_test_events.jsonl"), '')
            s = wrs.summarize_results(tmpdir)
            self.assertEqual(s["timeouts"], 1)


class TestMissingEvents(unittest.TestCase):
    def test_missing_events_counted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ld = _make_ledger_dir(tmpdir)
            _write_json(os.path.join(ld, "2026-05-31_me_mission.json"), VALID_MISSION)
            _write_json(os.path.join(ld, "2026-05-31_test_result.json"), {"status": "done"})
            s = wrs.summarize_results(tmpdir)
            self.assertEqual(s["missing_artifacts"], 1)


class TestMalformedEventsJsonl(unittest.TestCase):
    def test_malformed_events_counted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ld = _make_ledger_dir(tmpdir)
            _write_json(os.path.join(ld, "2026-05-31_mf_mission.json"), VALID_MISSION)
            _write_json(os.path.join(ld, "2026-05-31_test_result.json"), {"status": "done"})
            _write_file(os.path.join(ld, "2026-05-31_test_events.jsonl"),
                        '{"valid": true}\n{broken!!!\n')
            s = wrs.summarize_results(tmpdir)
            self.assertEqual(s["malformed_artifacts"], 1)


class TestEmptyDirectory(unittest.TestCase):
    def test_empty_dir_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_ledger_dir(tmpdir)
            s = wrs.summarize_results(tmpdir)
            self.assertEqual(s["total_missions"], 0)
            self.assertEqual(s["results"]["done"], 0)

    def test_empty_cli_zero(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_ledger_dir(tmpdir)
            result = _run_cli(tmpdir)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class TestStableJsonOutput(unittest.TestCase):
    def test_json_structure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _setup_success(tmpdir)
            result = _run_cli(tmpdir, ["--json"])
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertIn("total_missions", data)
            self.assertIn("results", data)
            self.assertIn("elapsed_stats", data)
            self.assertNotIn("elapsed", data)
            stats = data["elapsed_stats"]
            self.assertEqual(stats["min"], 42.5)
            self.assertEqual(stats["max"], 42.5)
            self.assertEqual(stats["count"], 1)

    def test_sanitized_events_counted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _setup_success(tmpdir)
            s = wrs.summarize_results(tmpdir)
            self.assertEqual(s["sanitized_events"], 1)
            self.assertEqual(s["unsanitized_events"], 0)


if __name__ == "__main__":
    unittest.main()
