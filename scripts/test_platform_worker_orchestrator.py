#!/usr/bin/env python3
"""Tests for platform_worker_orchestrator.py using unittest and stdlib only."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import platform_worker_orchestrator as orch


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_repo(tmpdir, branch="codex/platform-p8-test-2026-06-04"):
    """Create a minimal git repo for testing."""
    subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
    subprocess.run(
        ["git", "checkout", "-b", branch],
        cwd=tmpdir, capture_output=True,
    )
    scripts_dir = os.path.join(tmpdir, "scripts")
    os.makedirs(scripts_dir)
    ledger_dir = os.path.join(tmpdir, "ai-ledger", "platform")
    os.makedirs(ledger_dir)
    with open(os.path.join(scripts_dir, "platform_alpha.py"), "w") as f:
        f.write("# alpha\n")
    subprocess.run(["git", "add", "-A"], cwd=tmpdir, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t.com",
         "commit", "-m", "init"],
        cwd=tmpdir, capture_output=True,
    )


def _write_mission(tmpdir, overrides=None):
    """Write a valid mission JSON and its .md mission file."""
    mission = {
        "phase": "P8-A",
        "agent": "claude",
        "mission": "ai-ledger/platform/test_mission.md",
        "expected_files": [
            "scripts/platform_new.py",
            "ai-ledger/platform/test_mission.json",
            "ai-ledger/platform/test_mission.md",
        ],
        "result": "ai-ledger/platform/test_result.json",
        "events": "ai-ledger/platform/test_events.jsonl",
        "timeout_seconds": 30,
    }
    if overrides:
        mission.update(overrides)
    ledger_dir = os.path.join(tmpdir, "ai-ledger", "platform")
    # Write the .md mission file
    mission_md = os.path.join(ledger_dir, "test_mission.md")
    if not os.path.isfile(mission_md):
        with open(mission_md, "w") as f:
            f.write("# Test Mission\n")
    # Write the mission JSON
    path = os.path.join(ledger_dir, "test_mission.json")
    with open(path, "w") as f:
        json.dump(mission, f)
    return path


VALID_MISSION = {
    "phase": "P8-A",
    "agent": "claude",
    "mission": "ai-ledger/platform/test_mission.md",
    "expected_files": ["scripts/platform_new.py"],
    "result": "ai-ledger/platform/test_result.json",
    "events": "ai-ledger/platform/test_events.jsonl",
    "timeout_seconds": 30,
}


# ---------------------------------------------------------------------------
# Unit tests: validate_output_path
# ---------------------------------------------------------------------------

class TestValidateOutputPath(unittest.TestCase):
    def test_valid_result_path(self):
        err = orch.validate_output_path(
            "ai-ledger/platform/test_result.json", "result", ".json")
        self.assertIsNone(err)

    def test_valid_events_path(self):
        err = orch.validate_output_path(
            "ai-ledger/platform/test_events.jsonl", "events", ".jsonl")
        self.assertIsNone(err)

    def test_valid_report_path(self):
        err = orch.validate_output_path(
            "ai-ledger/platform/test_report.md", "report", ".md")
        self.assertIsNone(err)

    def test_absolute_rejected(self):
        err = orch.validate_output_path("/tmp/result.json", "result", ".json")
        self.assertIsNotNone(err)
        self.assertIn("absolute", err)

    def test_drive_qualified_rejected(self):
        err = orch.validate_output_path("C:/tmp/result.json", "result", ".json")
        self.assertIsNotNone(err)
        # On Windows, C:/ paths are caught as absolute; on other OS, as drive-qualified
        self.assertTrue(
            "absolute" in err or "drive" in err,
            f"Expected 'absolute' or 'drive' in error, got: {err}"
        )

    def test_traversal_rejected(self):
        err = orch.validate_output_path(
            "ai-ledger/platform/../result.json", "result", ".json")
        self.assertIsNotNone(err)
        self.assertIn("traversal", err)

    def test_outside_prefix_rejected(self):
        err = orch.validate_output_path("scripts/result.json", "result", ".json")
        self.assertIsNotNone(err)
        self.assertIn("ai-ledger/platform/", err)

    def test_wrong_extension_rejected(self):
        err = orch.validate_output_path(
            "ai-ledger/platform/result.txt", "result", ".json")
        self.assertIsNotNone(err)
        self.assertIn(".json", err)

    def test_forbidden_keyword_rejected(self):
        err = orch.validate_output_path(
            "ai-ledger/platform/auth_result.json", "result", ".json")
        self.assertIsNotNone(err)
        self.assertIn("auth", err)

    def test_empty_rejected(self):
        err = orch.validate_output_path("", "result", ".json")
        self.assertIsNotNone(err)

    def test_unsafe_dot_segment(self):
        err = orch.validate_output_path(
            "ai-ledger/platform/./result.json", "result", ".json")
        self.assertIsNotNone(err)


# ---------------------------------------------------------------------------
# Unit tests: load_and_validate_mission
# ---------------------------------------------------------------------------

class TestLoadAndValidateMission(unittest.TestCase):
    def test_valid_mission(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_repo(tmpdir)
            path = _write_mission(tmpdir)
            mission, failures = orch.load_and_validate_mission(path, tmpdir)
            self.assertEqual(failures, [])
            self.assertEqual(mission["phase"], "P8-A")

    def test_missing_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_repo(tmpdir)
            mission, failures = orch.load_and_validate_mission(
                "nonexistent.json", tmpdir)
            self.assertTrue(len(failures) > 0)
            self.assertIn("does not exist", failures[0])

    def test_malformed_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_repo(tmpdir)
            bad = os.path.join(tmpdir, "bad.json")
            with open(bad, "w") as f:
                f.write("{invalid json!!!")
            mission, failures = orch.load_and_validate_mission(bad, tmpdir)
            self.assertTrue(len(failures) > 0)
            self.assertIn("malformed", failures[0])

    def test_invalid_phase(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_repo(tmpdir)
            path = _write_mission(tmpdir, {"phase": "P99-Z"})
            mission, failures = orch.load_and_validate_mission(path, tmpdir)
            self.assertTrue(len(failures) > 0)


# ---------------------------------------------------------------------------
# Integration: dry-run
# ---------------------------------------------------------------------------

class TestDryRun(unittest.TestCase):
    def test_dry_run_returns_dry_run_status(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_repo(tmpdir)
            path = _write_mission(tmpdir)
            status, events, result_data, blockers = orch.orchestrate(
                tmpdir, path,
                command=[sys.executable, "-c", "print('hello')"],
                dry_run=True,
            )
            self.assertEqual(status, "DRY_RUN")
            self.assertEqual(blockers, [])
            self.assertEqual(result_data["status"], "DRY_RUN")
            self.assertEqual(result_data["phase"], "P8-A")

    def test_dry_run_writes_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_repo(tmpdir)
            path = _write_mission(tmpdir)
            orch.orchestrate(
                tmpdir, path,
                command=[sys.executable, "-c", "print('hello')"],
                dry_run=True,
            )
            result_file = os.path.join(
                tmpdir, "ai-ledger", "platform", "test_result.json")
            events_file = os.path.join(
                tmpdir, "ai-ledger", "platform", "test_events.jsonl")
            self.assertTrue(os.path.isfile(result_file))
            self.assertTrue(os.path.isfile(events_file))

    def test_dry_run_cli(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_repo(tmpdir)
            path = _write_mission(tmpdir)
            result = subprocess.run(
                [sys.executable,
                 os.path.join(SCRIPT_DIR, "platform_worker_orchestrator.py"),
                 "--repo", tmpdir, "--mission", path,
                 "--dry-run", "--json",
                 "--command", sys.executable, "-c", "print('hello')"],
                capture_output=True, text=True,
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(data["status"], "DRY_RUN")


# ---------------------------------------------------------------------------
# Integration: success
# ---------------------------------------------------------------------------

class TestSuccess(unittest.TestCase):
    def test_success_with_expected_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_repo(tmpdir)
            path = _write_mission(tmpdir)
            cmd = [
                sys.executable, "-c",
                "open('scripts/platform_new.py','w').write('# new')",
            ]
            status, events, result_data, blockers = orch.orchestrate(
                tmpdir, path, command=cmd,
            )
            self.assertEqual(status, "PASS")
            self.assertEqual(blockers, [])
            self.assertIn("scripts/platform_new.py", result_data["changed_files"])

    def test_success_writes_result_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_repo(tmpdir)
            path = _write_mission(tmpdir)
            cmd = [
                sys.executable, "-c",
                "open('scripts/platform_new.py','w').write('# new')",
            ]
            orch.orchestrate(tmpdir, path, command=cmd)
            result_file = os.path.join(
                tmpdir, "ai-ledger", "platform", "test_result.json")
            self.assertTrue(os.path.isfile(result_file))
            with open(result_file) as f:
                data = json.load(f)
            self.assertEqual(data["status"], "PASS")

    def test_success_writes_events_jsonl(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_repo(tmpdir)
            path = _write_mission(tmpdir)
            cmd = [
                sys.executable, "-c",
                "open('scripts/platform_new.py','w').write('# new')",
            ]
            orch.orchestrate(tmpdir, path, command=cmd)
            events_file = os.path.join(
                tmpdir, "ai-ledger", "platform", "test_events.jsonl")
            self.assertTrue(os.path.isfile(events_file))
            with open(events_file) as f:
                lines = f.readlines()
            self.assertGreater(len(lines), 0)
            # Each line should be valid JSON
            for line in lines:
                json.loads(line.strip())

    def test_success_writes_report_md(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_repo(tmpdir)
            path = _write_mission(tmpdir)
            cmd = [
                sys.executable, "-c",
                "open('scripts/platform_new.py','w').write('# new')",
            ]
            orch.orchestrate(tmpdir, path, command=cmd)
            report_file = os.path.join(
                tmpdir, "ai-ledger", "platform", "test_orchestrator_report.md")
            self.assertTrue(os.path.isfile(report_file))
            with open(report_file) as f:
                content = f.read()
            self.assertIn("Platform Worker Orchestrator Report", content)


# ---------------------------------------------------------------------------
# Integration: unexpected file fail
# ---------------------------------------------------------------------------

class TestUnexpectedFileFail(unittest.TestCase):
    def test_unexpected_file_blocks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_repo(tmpdir)
            path = _write_mission(tmpdir)
            # Command creates expected + unexpected file
            cmd = [
                sys.executable, "-c",
                "open('scripts/platform_new.py','w').write('# new');"
                "open('scripts/extra.py','w').write('# extra')",
            ]
            status, events, result_data, blockers = orch.orchestrate(
                tmpdir, path, command=cmd,
            )
            self.assertEqual(status, "FAIL")
            self.assertTrue(any("unexpected" in b.lower() for b in blockers))
            self.assertIn(
                orch.normalize_path("scripts/extra.py"),
                result_data["unexpected_files"],
            )


# ---------------------------------------------------------------------------
# Integration: forbidden file fail
# ---------------------------------------------------------------------------

class TestForbiddenFileFail(unittest.TestCase):
    def test_forbidden_file_blocks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_repo(tmpdir)
            path = _write_mission(tmpdir)
            # Command creates a forbidden file
            cmd = [
                sys.executable, "-c",
                "import os; os.makedirs('backend', exist_ok=True);"
                "open('backend/app.py','w').write('# backend')",
            ]
            status, events, result_data, blockers = orch.orchestrate(
                tmpdir, path, command=cmd,
            )
            self.assertEqual(status, "FAIL")
            self.assertTrue(any("forbidden" in b.lower() for b in blockers))
            self.assertGreater(len(result_data["forbidden_violations"]), 0)


# ---------------------------------------------------------------------------
# Integration: nonzero exit fail
# ---------------------------------------------------------------------------

class TestNonzeroFail(unittest.TestCase):
    def test_nonzero_exit_blocks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_repo(tmpdir)
            path = _write_mission(tmpdir)
            cmd = [sys.executable, "-c", "import sys; sys.exit(1)"]
            status, events, result_data, blockers = orch.orchestrate(
                tmpdir, path, command=cmd,
            )
            self.assertEqual(status, "FAIL")
            self.assertTrue(any("exited with code" in b for b in blockers))
            self.assertEqual(result_data["exit_code"], 1)


# ---------------------------------------------------------------------------
# Integration: timeout fail
# ---------------------------------------------------------------------------

class TestTimeoutFail(unittest.TestCase):
    def test_timeout_blocks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_repo(tmpdir)
            path = _write_mission(tmpdir, {"timeout_seconds": 1})
            cmd = [sys.executable, "-c", "import time; time.sleep(60)"]
            status, events, result_data, blockers = orch.orchestrate(
                tmpdir, path, command=cmd,
            )
            self.assertEqual(status, "FAIL")
            self.assertTrue(result_data["timed_out"])
            self.assertTrue(any("timed out" in b for b in blockers))


# ---------------------------------------------------------------------------
# Integration: missing mission fail
# ---------------------------------------------------------------------------

class TestMissingMissionFail(unittest.TestCase):
    def test_missing_mission_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_repo(tmpdir)
            status, events, result_data, blockers = orch.orchestrate(
                tmpdir, "nonexistent_mission.json",
                command=[sys.executable, "-c", "print('hi')"],
            )
            self.assertEqual(status, "FAIL")
            self.assertTrue(any("does not exist" in b for b in blockers))

    def test_missing_mission_cli_nonzero(self):
        result = subprocess.run(
            [sys.executable,
             os.path.join(SCRIPT_DIR, "platform_worker_orchestrator.py"),
             "--repo", tempfile.gettempdir(),
             "--mission", "nonexistent.json",
             "--json"],
            capture_output=True, text=True,
            timeout=15,
        )
        self.assertNotEqual(result.returncode, 0)


# ---------------------------------------------------------------------------
# Integration: unsafe path fail
# ---------------------------------------------------------------------------

class TestUnsafePathFail(unittest.TestCase):
    def test_unsafe_result_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_repo(tmpdir)
            path = _write_mission(tmpdir, {
                "result": "scripts/result.json",
            })
            status, events, result_data, blockers = orch.orchestrate(
                tmpdir, path,
                command=[sys.executable, "-c", "print('hi')"],
            )
            self.assertEqual(status, "FAIL")
            self.assertTrue(any("result" in b for b in blockers))

    def test_unsafe_events_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_repo(tmpdir)
            path = _write_mission(tmpdir, {
                "events": "scripts/events.jsonl",
            })
            status, events, result_data, blockers = orch.orchestrate(
                tmpdir, path,
                command=[sys.executable, "-c", "print('hi')"],
            )
            self.assertEqual(status, "FAIL")
            self.assertTrue(any("events" in b for b in blockers))

    def test_unsafe_report_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_repo(tmpdir)
            path = _write_mission(tmpdir)
            status, events, result_data, blockers = orch.orchestrate(
                tmpdir, path,
                command=[sys.executable, "-c", "print('hi')"],
                report_path="scripts/report.md",
            )
            self.assertEqual(status, "FAIL")
            self.assertTrue(any("report" in b for b in blockers))

    def test_absolute_report_path_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_repo(tmpdir)
            path = _write_mission(tmpdir)
            status, events, result_data, blockers = orch.orchestrate(
                tmpdir, path,
                command=[sys.executable, "-c", "print('hi')"],
                report_path="/tmp/report.md",
            )
            self.assertEqual(status, "FAIL")

    def test_forbidden_keyword_report_path_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_repo(tmpdir)
            path = _write_mission(tmpdir)
            status, events, result_data, blockers = orch.orchestrate(
                tmpdir, path,
                command=[sys.executable, "-c", "print('hi')"],
                report_path="ai-ledger/platform/auth_report.md",
            )
            self.assertEqual(status, "FAIL")


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------

class TestJsonCli(unittest.TestCase):
    def test_json_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_repo(tmpdir)
            path = _write_mission(tmpdir)
            cmd = [
                sys.executable, "-c",
                "open('scripts/platform_new.py','w').write('# new')",
            ]
            cli_cmd = [
                sys.executable,
                os.path.join(SCRIPT_DIR, "platform_worker_orchestrator.py"),
                "--repo", tmpdir, "--mission", path,
                "--json",
            ] + ["--command"] + cmd
            result = subprocess.run(
                cli_cmd, capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(data["status"], "PASS")


class TestHumanCli(unittest.TestCase):
    def test_human_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_repo(tmpdir)
            path = _write_mission(tmpdir)
            cmd = [
                sys.executable, "-c",
                "open('scripts/platform_new.py','w').write('# new')",
            ]
            cli_cmd = [
                sys.executable,
                os.path.join(SCRIPT_DIR, "platform_worker_orchestrator.py"),
                "--repo", tmpdir, "--mission", path,
            ] + ["--command"] + cmd
            result = subprocess.run(
                cli_cmd, capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Platform Worker Orchestrator", result.stdout)
            self.assertIn("PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
