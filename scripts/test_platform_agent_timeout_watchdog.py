#!/usr/bin/env python3
"""Tests for platform_agent_timeout_watchdog.py."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
WATCHDOG = SCRIPT_DIR / "platform_agent_timeout_watchdog.py"


def _run(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def _git(tmpdir, args):
    return _run(["git"] + args, tmpdir)


def _init_repo(tmpdir):
    _git(tmpdir, ["init"])
    _git(tmpdir, ["checkout", "-b", "codex/platform-p1h-test"])
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


def _watchdog_cmd(
    tmpdir,
    command,
    report="ai-ledger/platform/p1h-watchdog.md",
    timeout="5",
    extra=None,
):
    cmd = [
        sys.executable, str(WATCHDOG),
        "--repo", tmpdir,
        "--report", report,
        "--phase", "P1-H",
        "--agent", "test-agent",
        "--timeout-seconds", timeout,
        "--risk", "MEDIUM",
    ]
    if extra:
        cmd.extend(extra)
    cmd.append("--")
    cmd.extend(command)
    return cmd


class TestWatchdogSuccess(unittest.TestCase):
    def test_successful_command_writes_report_and_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir)
            result = _run(
                _watchdog_cmd(
                    tmpdir,
                    [sys.executable, "-c", "print('ok')"],
                ),
                tmpdir,
            )

            self.assertEqual(
                0, result.returncode,
                f"expected exit 0\nstdout: {result.stdout}\nstderr: {result.stderr}",
            )
            self.assertIn("WATCHDOG OUTCOME: PASS", result.stdout)
            report = Path(tmpdir, "ai-ledger/platform/p1h-watchdog.md")
            self.assertTrue(report.exists())
            content = report.read_text(encoding="utf-8")
            self.assertIn("`PASS`", content)
            self.assertIn("ok", content)
            self.assertIn("codex/platform-p1h-test", content)


class TestWatchdogFailure(unittest.TestCase):
    def test_failing_command_preserves_exit_code(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir)
            result = _run(
                _watchdog_cmd(
                    tmpdir,
                    [sys.executable, "-c", "import sys; print('bad'); sys.exit(7)"],
                ),
                tmpdir,
            )

            self.assertEqual(7, result.returncode)
            self.assertIn("WATCHDOG OUTCOME: FAIL", result.stdout)
            content = Path(
                tmpdir, "ai-ledger/platform/p1h-watchdog.md"
            ).read_text(encoding="utf-8")
            self.assertIn("`FAIL`", content)
            self.assertIn("`7`", content)
            self.assertIn("bad", content)


class TestWatchdogTimeout(unittest.TestCase):
    def test_timeout_returns_124_and_writes_report(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir)
            result = _run(
                _watchdog_cmd(
                    tmpdir,
                    [sys.executable, "-c", "import time; print('start'); time.sleep(3)"],
                    timeout="0.2",
                ),
                tmpdir,
            )

            self.assertEqual(124, result.returncode)
            self.assertIn("WATCHDOG OUTCOME: TIMEOUT", result.stdout)
            content = Path(
                tmpdir, "ai-ledger/platform/p1h-watchdog.md"
            ).read_text(encoding="utf-8")
            self.assertIn("`TIMEOUT`", content)
            self.assertIn("`124`", content)


class TestChangedFiles(unittest.TestCase):
    def test_report_records_changed_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir)
            code = (
                "from pathlib import Path; "
                "Path('scripts').mkdir(exist_ok=True); "
                "Path('scripts/out.txt').write_text('changed')"
            )
            result = _run(
                _watchdog_cmd(tmpdir, [sys.executable, "-c", code]),
                tmpdir,
            )

            self.assertEqual(0, result.returncode)
            content = Path(
                tmpdir, "ai-ledger/platform/p1h-watchdog.md"
            ).read_text(encoding="utf-8")
            self.assertIn("scripts/out.txt", content)


class TestPathValidation(unittest.TestCase):
    def test_absolute_report_fails_before_running_command(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir)
            marker = Path(tmpdir, "marker.txt")
            result = _run(
                _watchdog_cmd(
                    tmpdir,
                    [sys.executable, "-c", "from pathlib import Path; Path('marker.txt').write_text('ran')"],
                    report=str(Path(tmpdir, "outside.md")),
                ),
                tmpdir,
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("must be relative", result.stdout)
            self.assertFalse(marker.exists())

    def test_traversal_report_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir)
            result = _run(
                _watchdog_cmd(
                    tmpdir,
                    [sys.executable, "-c", "print('should not run')"],
                    report="../outside.md",
                ),
                tmpdir,
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("unsafe path part", result.stdout)

    def test_report_outside_platform_ledger_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir)
            result = _run(
                _watchdog_cmd(
                    tmpdir,
                    [sys.executable, "-c", "print('should not run')"],
                    report="docs/out.md",
                ),
                tmpdir,
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("not under ai-ledger/platform", result.stdout)


class TestArgumentValidation(unittest.TestCase):
    def test_timeout_must_be_positive(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir)
            result = _run(
                _watchdog_cmd(
                    tmpdir,
                    [sys.executable, "-c", "print('no')"],
                    timeout="0",
                ),
                tmpdir,
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("greater than zero", result.stdout)

    def test_command_is_required(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir)
            cmd = [
                sys.executable, str(WATCHDOG),
                "--repo", tmpdir,
                "--report", "ai-ledger/platform/p1h-watchdog.md",
                "--phase", "P1-H",
                "--timeout-seconds", "1",
            ]

            result = _run(cmd, tmpdir)

            self.assertNotEqual(0, result.returncode)
            self.assertIn("command after -- is required", result.stdout)


if __name__ == "__main__":
    unittest.main()
