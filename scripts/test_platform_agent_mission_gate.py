#!/usr/bin/env python3
"""Tests for platform_agent_mission_gate.py using unittest and stdlib only."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import platform_agent_mission_gate as gate

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

VALID_MISSION = {
    "phase": "P2-A",
    "agent": "opencode",
    "mission": "scripts/mission.md",
    "expected_files": ["scripts/output.py"],
    "result": "ai-ledger/platform/result.json",
    "events": "ai-ledger/platform/events.jsonl",
    "timeout_seconds": 600,
}


def _write_mission(tmpdir, data):
    path = os.path.join(tmpdir, "mission.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return path


def _run_cli(mission_path, extra_args=None, repo=None):
    cmd = [
        sys.executable,
        os.path.join(SCRIPT_DIR, "platform_agent_mission_gate.py"),
        "--repo", repo or tempfile.gettempdir(),
        "--mission", mission_path,
    ]
    if extra_args:
        cmd.extend(extra_args)
    return subprocess.run(cmd, capture_output=True, text=True)


class TestValidMissionPasses(unittest.TestCase):
    def test_valid_mission_passes(self):
        failures = gate.validate_mission(VALID_MISSION)
        self.assertEqual(failures, [], f"expected no failures, got: {failures}")

    def test_valid_mission_cli_passes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _write_mission(tmpdir, VALID_MISSION)
            result = _run_cli(path, repo=tmpdir)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("VERDICT: PASS", result.stdout)


class TestMissingRequiredKeyFails(unittest.TestCase):
    def test_missing_key_fails(self):
        for key in gate.REQUIRED_KEYS:
            data = dict(VALID_MISSION)
            del data[key]
            failures = gate.validate_mission(data)
            self.assertTrue(
                any(f"missing required key '{key}'" in f for f in failures),
                f"expected failure for missing '{key}', got: {failures}",
            )

    def test_missing_key_cli_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data = dict(VALID_MISSION)
            del data["phase"]
            path = _write_mission(tmpdir, data)
            result = _run_cli(path, repo=tmpdir)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("FAIL", result.stdout)


class TestMalformedJsonFails(unittest.TestCase):
    def test_malformed_json_cli_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "bad.json")
            with open(path, "w") as f:
                f.write("{not valid json!!!")
            result = _run_cli(path, repo=tmpdir)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("malformed JSON", result.stdout)


class TestUnsafeMissionPathFails(unittest.TestCase):
    def test_absolute_mission(self):
        data = dict(VALID_MISSION, mission="/etc/passwd")
        failures = gate.validate_mission(data)
        self.assertTrue(len(failures) > 0)

    def test_traversal_mission(self):
        data = dict(VALID_MISSION, mission="../etc/passwd")
        failures = gate.validate_mission(data)
        self.assertTrue(len(failures) > 0)

    def test_drive_qualified_mission(self):
        data = dict(VALID_MISSION, mission="C:/tmp/mission.md")
        failures = gate.validate_mission(data)
        self.assertTrue(len(failures) > 0)

    def test_dot_mission_path_part(self):
        data = dict(VALID_MISSION, mission="scripts/./mission.md")
        failures = gate.validate_mission(data)
        self.assertTrue(len(failures) > 0)

    def test_empty_mission_path_part(self):
        data = dict(VALID_MISSION, mission="scripts//mission.md")
        failures = gate.validate_mission(data)
        self.assertTrue(len(failures) > 0)

    def test_non_md_mission(self):
        data = dict(VALID_MISSION, mission="scripts/mission.txt")
        failures = gate.validate_mission(data)
        self.assertTrue(
            any(".md" in f for f in failures),
            f"expected .md extension failure, got: {failures}",
        )

    def test_forbidden_mission(self):
        data = dict(VALID_MISSION, mission="backend/evil.md")
        failures = gate.validate_mission(data)
        self.assertTrue(len(failures) > 0)


class TestForbiddenExpectedFileFails(unittest.TestCase):
    def test_forbidden_expected_file(self):
        data = dict(VALID_MISSION, expected_files=["backend/evil.py"])
        failures = gate.validate_mission(data)
        self.assertTrue(
            any("forbidden" in f.lower() for f in failures),
            f"expected forbidden failure, got: {failures}",
        )

    def test_absolute_expected_file(self):
        data = dict(VALID_MISSION, expected_files=["/tmp/evil.py"])
        failures = gate.validate_mission(data)
        self.assertTrue(len(failures) > 0)

    def test_traversal_expected_file(self):
        data = dict(VALID_MISSION, expected_files=["../../etc/passwd"])
        failures = gate.validate_mission(data)
        self.assertTrue(len(failures) > 0)

    def test_drive_qualified_expected_file(self):
        data = dict(VALID_MISSION, expected_files=["C:/tmp/out.py"])
        failures = gate.validate_mission(data)
        self.assertTrue(len(failures) > 0)

    def test_dot_expected_file_path_part(self):
        data = dict(VALID_MISSION, expected_files=["scripts/./out.py"])
        failures = gate.validate_mission(data)
        self.assertTrue(len(failures) > 0)

    def test_empty_expected_file_path_part(self):
        data = dict(VALID_MISSION, expected_files=["scripts//out.py"])
        failures = gate.validate_mission(data)
        self.assertTrue(len(failures) > 0)


class TestEmptyExpectedFilesFails(unittest.TestCase):
    def test_empty_array(self):
        data = dict(VALID_MISSION, expected_files=[])
        failures = gate.validate_mission(data)
        self.assertTrue(
            any("non-empty array" in f for f in failures),
            f"expected non-empty array failure, got: {failures}",
        )

    def test_not_array(self):
        data = dict(VALID_MISSION, expected_files="not-a-list")
        failures = gate.validate_mission(data)
        self.assertTrue(len(failures) > 0)


class TestInvalidResultEventsPathsFail(unittest.TestCase):
    def test_result_not_under_ledger(self):
        data = dict(VALID_MISSION, result="scripts/result.json")
        failures = gate.validate_mission(data)
        self.assertTrue(
            any("ai-ledger/platform/" in f for f in failures),
            f"expected ai-ledger/platform failure, got: {failures}",
        )

    def test_result_wrong_extension(self):
        data = dict(VALID_MISSION, result="ai-ledger/platform/result.txt")
        failures = gate.validate_mission(data)
        self.assertTrue(len(failures) > 0)

    def test_result_drive_qualified_fails(self):
        data = dict(VALID_MISSION, result="C:/tmp/result.json")
        failures = gate.validate_mission(data)
        self.assertTrue(len(failures) > 0)

    def test_events_wrong_extension(self):
        data = dict(VALID_MISSION, events="ai-ledger/platform/events.json")
        failures = gate.validate_mission(data)
        self.assertTrue(
            any(".jsonl" in f for f in failures),
            f"expected .jsonl extension failure, got: {failures}",
        )

    def test_events_not_under_ledger(self):
        data = dict(VALID_MISSION, events="scripts/events.jsonl")
        failures = gate.validate_mission(data)
        self.assertTrue(len(failures) > 0)

    def test_events_empty_path_part_fails(self):
        data = dict(VALID_MISSION, events="ai-ledger/platform//events.jsonl")
        failures = gate.validate_mission(data)
        self.assertTrue(len(failures) > 0)


class TestTimeoutOutOfRangeFails(unittest.TestCase):
    def test_zero_timeout(self):
        data = dict(VALID_MISSION, timeout_seconds=0)
        failures = gate.validate_mission(data)
        self.assertTrue(len(failures) > 0)

    def test_negative_timeout(self):
        data = dict(VALID_MISSION, timeout_seconds=-1)
        failures = gate.validate_mission(data)
        self.assertTrue(len(failures) > 0)

    def test_too_large_timeout(self):
        data = dict(VALID_MISSION, timeout_seconds=43201)
        failures = gate.validate_mission(data)
        self.assertTrue(len(failures) > 0)

    def test_float_timeout(self):
        data = dict(VALID_MISSION, timeout_seconds=60.5)
        failures = gate.validate_mission(data)
        self.assertTrue(len(failures) > 0)

    def test_max_valid_timeout(self):
        data = dict(VALID_MISSION, timeout_seconds=43200)
        failures = gate.validate_mission(data)
        self.assertEqual(failures, [], f"43200 should be valid, got: {failures}")

    def test_min_valid_timeout(self):
        data = dict(VALID_MISSION, timeout_seconds=1)
        failures = gate.validate_mission(data)
        self.assertEqual(failures, [], f"1 should be valid, got: {failures}")


class TestPrintRunnerCommandOpencode(unittest.TestCase):
    def test_print_runner_includes_worker_gate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _write_mission(tmpdir, VALID_MISSION)
            result = _run_cli(path, extra_args=["--print-runner-command"], repo=tmpdir)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("platform_opencode_worker_gate.py", result.stdout)
            self.assertIn("scripts/output.py", result.stdout)

    def test_print_runner_includes_expected_files(self):
        data = dict(VALID_MISSION, expected_files=[
            "scripts/a.py", "scripts/b.py",
        ])
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _write_mission(tmpdir, data)
            result = _run_cli(path, extra_args=["--print-runner-command"], repo=tmpdir)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("scripts/a.py", result.stdout)
            self.assertIn("scripts/b.py", result.stdout)


class TestPrintRunnerCommandClaudeFails(unittest.TestCase):
    def test_claude_unsupported(self):
        data = dict(VALID_MISSION, agent="claude")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _write_mission(tmpdir, data)
            result = _run_cli(path, extra_args=["--print-runner-command"], repo=tmpdir)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unsupported", result.stdout.lower())


class TestOptionalFields(unittest.TestCase):
    def test_allow_edits_true(self):
        data = dict(VALID_MISSION, allow_edits=True)
        failures = gate.validate_mission(data)
        self.assertEqual(failures, [])

    def test_allow_edits_false(self):
        data = dict(VALID_MISSION, allow_edits=False)
        failures = gate.validate_mission(data)
        self.assertEqual(failures, [])

    def test_allow_edits_invalid(self):
        data = dict(VALID_MISSION, allow_edits="yes")
        failures = gate.validate_mission(data)
        self.assertTrue(len(failures) > 0)

    def test_notes_valid(self):
        data = dict(VALID_MISSION, notes="test run")
        failures = gate.validate_mission(data)
        self.assertEqual(failures, [])

    def test_notes_invalid(self):
        data = dict(VALID_MISSION, notes=123)
        failures = gate.validate_mission(data)
        self.assertTrue(len(failures) > 0)


class TestPhaseValidation(unittest.TestCase):
    def test_p2_phase(self):
        data = dict(VALID_MISSION, phase="P2-Z")
        failures = gate.validate_mission(data)
        self.assertEqual(failures, [])

    def test_p1_phase(self):
        data = dict(VALID_MISSION, phase="P1-A")
        failures = gate.validate_mission(data)
        self.assertEqual(failures, [])

    def test_p3_phase(self):
        data = dict(VALID_MISSION, phase="P3-A")
        failures = gate.validate_mission(data)
        self.assertEqual(failures, [])

    def test_p4_phase(self):
        data = dict(VALID_MISSION, phase="P4-A")
        failures = gate.validate_mission(data)
        self.assertEqual(failures, [])

    def test_invalid_phase_prefix(self):
        data = dict(VALID_MISSION, phase="P5-A")
        failures = gate.validate_mission(data)
        self.assertTrue(len(failures) > 0)

    def test_empty_phase(self):
        data = dict(VALID_MISSION, phase="")
        failures = gate.validate_mission(data)
        self.assertTrue(len(failures) > 0)


class TestAgentValidation(unittest.TestCase):
    def test_opencode_agent(self):
        data = dict(VALID_MISSION, agent="opencode")
        failures = gate.validate_mission(data)
        self.assertEqual(failures, [])

    def test_claude_agent(self):
        data = dict(VALID_MISSION, agent="claude")
        failures = gate.validate_mission(data)
        self.assertEqual(failures, [])

    def test_goose_agent(self):
        data = dict(VALID_MISSION, agent="goose")
        failures = gate.validate_mission(data)
        self.assertEqual(failures, [])

    def test_invalid_agent(self):
        data = dict(VALID_MISSION, agent="gpt4")
        failures = gate.validate_mission(data)
        self.assertTrue(len(failures) > 0)


class TestBuildRunnerCommand(unittest.TestCase):
    def test_basic_command(self):
        cmd = gate.build_runner_command(VALID_MISSION)
        joined = " ".join(cmd)
        self.assertIn("platform_opencode_worker_gate.py", joined)
        self.assertIn("--mission", joined)
        self.assertIn("scripts/mission.md", joined)
        self.assertIn("--timeout-seconds", joined)
        self.assertIn("600", joined)

    def test_with_allow_edits(self):
        data = dict(VALID_MISSION, allow_edits=True)
        cmd = gate.build_runner_command(data)
        self.assertIn("--allow-edits", cmd)

    def test_without_allow_edits(self):
        cmd = gate.build_runner_command(VALID_MISSION)
        self.assertNotIn("--allow-edits", cmd)


class TestNonObjectJsonFails(unittest.TestCase):
    def test_array_json(self):
        failures = gate.validate_mission([1, 2, 3])
        self.assertTrue(len(failures) > 0)
        self.assertTrue(any("object" in f for f in failures))


class TestNonexistentMissionFileFails(unittest.TestCase):
    def test_nonexistent_file(self):
        result = _run_cli("/nonexistent/mission.json")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not exist", result.stdout)


if __name__ == "__main__":
    unittest.main()
