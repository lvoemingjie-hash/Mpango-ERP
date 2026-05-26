#!/usr/bin/env python3
"""Tests for platform_agent_run_bundle_gate.py."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
BUNDLE_GATE = SCRIPT_DIR / "platform_agent_run_bundle_gate.py"


def _run(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def _git(tmpdir, args):
    return _run(["git"] + args, tmpdir)


def _init_repo(tmpdir):
    _git(tmpdir, ["init"])
    _git(tmpdir, ["checkout", "-b", "codex/platform-p1j-test"])
    Path(tmpdir, "README.md").write_text("# test\n", encoding="utf-8")
    _git(tmpdir, ["add", "-A"])
    _git(
        tmpdir,
        [
            "-c", "user.name=test",
            "-c", "user.email=test@test.com",
            "commit", "-m", "init",
        ],
    )


def _commit_all(tmpdir, message="fixture"):
    _git(tmpdir, ["add", "-A"])
    _git(
        tmpdir,
        [
            "-c", "user.name=test",
            "-c", "user.email=test@test.com",
            "commit", "-m", message,
        ],
    )


def _write_bundle(tmpdir, overrides=None, commit=True):
    command = (
        "from pathlib import Path; "
        "Path('scripts').mkdir(exist_ok=True); "
        "Path('scripts/out.txt').write_text('ok')"
    )
    bundle = {
        "phase": "P1-J",
        "agent": "test-agent",
        "timeout_seconds": 5,
        "risk": "MEDIUM",
        "command": [sys.executable, "-c", command],
        "expected_files": ["scripts/out.txt"],
        "watchdog_report": "ai-ledger/platform/p1j-watchdog.md",
        "artifact_manifest": "ai-ledger/platform/p1j-artifacts.json",
    }
    if overrides:
        bundle.update(overrides)
    path = Path(tmpdir, "bundle.json")
    path.write_text(json.dumps(bundle), encoding="utf-8")
    if commit:
        _commit_all(tmpdir, "bundle fixture")
    return str(path)


def _bundle_cmd(tmpdir, bundle_path, extra=None):
    cmd = [
        sys.executable, str(BUNDLE_GATE),
        "--repo", tmpdir,
        "--bundle", bundle_path,
    ]
    if extra:
        cmd.extend(extra)
    return cmd


class TestDryRun(unittest.TestCase):
    def test_dry_run_prints_plans_and_creates_no_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir)
            bundle_path = _write_bundle(tmpdir)

            result = _run(_bundle_cmd(tmpdir, bundle_path, ["--dry-run"]), tmpdir)

            self.assertEqual(
                0, result.returncode,
                f"expected exit 0\nstdout: {result.stdout}\nstderr: {result.stderr}",
            )
            self.assertIn("BUNDLE VALIDATION", result.stdout)
            self.assertIn("WATCHDOG INVOCATION", result.stdout)
            self.assertIn("ARTIFACT COLLECTION", result.stdout)
            self.assertIn("DRY-RUN PASS", result.stdout)
            self.assertFalse(Path(tmpdir, "scripts/out.txt").exists())
            self.assertFalse(Path(tmpdir, "ai-ledger/platform/p1j-watchdog.md").exists())
            self.assertFalse(Path(tmpdir, "ai-ledger/platform/p1j-artifacts.json").exists())


class TestExecution(unittest.TestCase):
    def test_successful_command_and_collector_exit_zero(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir)
            bundle_path = _write_bundle(tmpdir)

            result = _run(_bundle_cmd(tmpdir, bundle_path), tmpdir)

            self.assertEqual(
                0, result.returncode,
                f"expected exit 0\nstdout: {result.stdout}\nstderr: {result.stderr}",
            )
            self.assertIn("BUNDLE VERDICT: PASS", result.stdout)
            self.assertTrue(Path(tmpdir, "scripts/out.txt").exists())
            self.assertTrue(Path(tmpdir, "ai-ledger/platform/p1j-watchdog.md").exists())
            manifest = json.loads(
                Path(tmpdir, "ai-ledger/platform/p1j-artifacts.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual("PASS", manifest["verdict"])

    def test_nonzero_command_still_runs_collector_and_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir)
            command = (
                "from pathlib import Path; import sys; "
                "Path('scripts').mkdir(exist_ok=True); "
                "Path('scripts/out.txt').write_text('bad'); sys.exit(7)"
            )
            bundle_path = _write_bundle(
                tmpdir,
                {"command": [sys.executable, "-c", command]},
            )

            result = _run(_bundle_cmd(tmpdir, bundle_path), tmpdir)

            self.assertEqual(7, result.returncode)
            self.assertIn("WATCHDOG: 7", result.stdout)
            self.assertIn("COLLECTOR: 0", result.stdout)
            self.assertTrue(Path(tmpdir, "ai-ledger/platform/p1j-artifacts.json").exists())

    def test_timeout_preserves_124_when_collector_passes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir)
            bundle_path = _write_bundle(
                tmpdir,
                {
                    "timeout_seconds": 0.2,
                    "command": [
                        sys.executable,
                        "-c",
                        "import time; time.sleep(3)",
                    ],
                    "expected_files": [],
                },
            )

            result = _run(_bundle_cmd(tmpdir, bundle_path), tmpdir)

            self.assertEqual(124, result.returncode)
            self.assertIn("WATCHDOG: 124", result.stdout)
            self.assertIn("COLLECTOR: 0", result.stdout)

    def test_unexpected_artifact_causes_collector_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir)
            command = (
                "from pathlib import Path; "
                "Path('scripts').mkdir(exist_ok=True); "
                "Path('scripts/out.txt').write_text('ok'); "
                "Path('scripts/extra.txt').write_text('extra')"
            )
            bundle_path = _write_bundle(
                tmpdir,
                {"command": [sys.executable, "-c", command]},
            )

            result = _run(_bundle_cmd(tmpdir, bundle_path), tmpdir)

            self.assertNotEqual(0, result.returncode)
            self.assertIn("COLLECTOR:", result.stdout)
            manifest = json.loads(
                Path(tmpdir, "ai-ledger/platform/p1j-artifacts.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertIn("scripts/extra.txt", manifest["unexpected"])


class TestValidation(unittest.TestCase):
    def test_invalid_bundle_missing_field_fails_before_execution(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir)
            bundle_path = Path(tmpdir, "bundle.json")
            bundle_path.write_text(json.dumps({"phase": "P1-J"}), encoding="utf-8")

            result = _run(_bundle_cmd(tmpdir, str(bundle_path)), tmpdir)

            self.assertNotEqual(0, result.returncode)
            self.assertIn("missing required field", result.stdout)
            self.assertFalse(Path(tmpdir, "ai-ledger/platform/p1j-watchdog.md").exists())

    def test_unsafe_expected_path_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir)
            bundle_path = _write_bundle(
                tmpdir,
                {"expected_files": ["../outside.txt"]},
                commit=False,
            )

            result = _run(_bundle_cmd(tmpdir, bundle_path), tmpdir)

            self.assertNotEqual(0, result.returncode)
            self.assertIn("unsafe path part", result.stdout)

    def test_unsafe_report_path_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir)
            bundle_path = _write_bundle(
                tmpdir,
                {"watchdog_report": "../outside.md"},
                commit=False,
            )

            result = _run(_bundle_cmd(tmpdir, bundle_path), tmpdir)

            self.assertNotEqual(0, result.returncode)
            self.assertIn("unsafe path part", result.stdout)


if __name__ == "__main__":
    unittest.main()
