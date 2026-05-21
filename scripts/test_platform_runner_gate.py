#!/usr/bin/env python3
"""Tests for platform_runner_gate.py using unittest and tempfile only."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
RUNNER_GATE = SCRIPT_DIR / "platform_runner_gate.py"

REQUIRED_DOCS = [
    "docs/ai/CTO_CURRENT_OPS.md",
    "docs/ai/AI_TEAM_OPERATING_RULES.md",
    "docs/ai/PROJECT.md",
    "docs/ai/PROJECT_MEMORY.md",
    "docs/ai/README.md",
    "docs/ai/DUAL_MACHINE_DEVELOPMENT_PROTOCOL.md",
]

VALID_REPORT_CONTENT = (
    "- Branch: codex/platform-test\n"
    "- Commit: abc123\n"
    "- Modified files: none\n"
    "- Tests: self-check\n"
    "- Report path: report.md\n"
    "- Risk: LOW\n"
)


def _init_repo(tmpdir, branch_name):
    subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
    subprocess.run(["git", "checkout", "-b", branch_name], cwd=tmpdir, capture_output=True)

    for doc in REQUIRED_DOCS:
        doc_path = os.path.join(tmpdir, doc)
        os.makedirs(os.path.dirname(doc_path), exist_ok=True)
        with open(doc_path, "w") as f:
            f.write(f"# {doc}\n")

    readme = os.path.join(tmpdir, "README.md")
    with open(readme, "w") as f:
        f.write("# test\n")

    subprocess.run(["git", "add", "-A"], cwd=tmpdir, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.name=test", "-c", "user.email=test@test.com",
         "commit", "-m", "init"],
        cwd=tmpdir, capture_output=True,
    )


def _create_report(tmpdir, content=None):
    report_path = os.path.join(tmpdir, "report.md")
    with open(report_path, "w") as f:
        f.write(content or VALID_REPORT_CONTENT)
    return report_path


class TestRunnerGate(unittest.TestCase):
    def test_gate_only_success_on_codex_branch(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-test")
            report_path = _create_report(tmpdir)

            result = subprocess.run(
                [sys.executable, str(RUNNER_GATE),
                 "--repo", tmpdir,
                 "--report", report_path],
                capture_output=True, text=True,
            )
            self.assertEqual(
                0, result.returncode,
                f"expected exit 0, got {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}",
            )
            self.assertIn("PREFLIGHT: PASS", result.stdout)
            self.assertIn("gate-only", result.stdout)

    def test_command_executes_after_preflight_passes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-test")
            report_path = _create_report(tmpdir)

            result = subprocess.run(
                [sys.executable, str(RUNNER_GATE),
                 "--repo", tmpdir,
                 "--report", report_path,
                 "--", sys.executable, "-c", "print('runner-ok')"],
                capture_output=True, text=True,
            )
            self.assertEqual(
                0, result.returncode,
                f"expected exit 0, got {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}",
            )
            self.assertIn("PREFLIGHT: PASS", result.stdout)
            self.assertIn("runner-ok", result.stdout)

    def test_command_runs_from_repo_root(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-test")
            report_path = _create_report(tmpdir)

            result = subprocess.run(
                [sys.executable, str(RUNNER_GATE),
                 "--repo", tmpdir,
                 "--report", report_path,
                 "--", sys.executable, "-c",
                 "import os; print(os.path.basename(os.getcwd()))"],
                capture_output=True, text=True,
                cwd=os.path.dirname(tmpdir),
            )
            self.assertEqual(
                0, result.returncode,
                f"expected exit 0, got {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}",
            )
            self.assertIn(os.path.basename(tmpdir), result.stdout)

    def test_command_blocked_when_preflight_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "platform-dev")
            report_path = _create_report(tmpdir)

            result = subprocess.run(
                [sys.executable, str(RUNNER_GATE),
                 "--repo", tmpdir,
                 "--report", report_path,
                 "--", sys.executable, "-c", "print('should-not-run')"],
                capture_output=True, text=True,
            )
            self.assertNotEqual(
                0, result.returncode,
                f"expected nonzero exit, got {result.returncode}\nstdout: {result.stdout}",
            )
            self.assertIn("PREFLIGHT: FAIL", result.stdout)
            self.assertNotIn("should-not-run", result.stdout)

    def test_platform_dev_passes_with_allow_flag(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "platform-dev")
            report_path = _create_report(tmpdir)

            result = subprocess.run(
                [sys.executable, str(RUNNER_GATE),
                 "--repo", tmpdir,
                 "--report", report_path,
                 "--allow-platform-dev",
                 "--", sys.executable, "-c", "print('platform-dev-ok')"],
                capture_output=True, text=True,
            )
            self.assertEqual(
                0, result.returncode,
                f"expected exit 0, got {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}",
            )
            self.assertIn("PREFLIGHT: PASS", result.stdout)
            self.assertIn("platform-dev-ok", result.stdout)

    def test_missing_report_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-test")

            result = subprocess.run(
                [sys.executable, str(RUNNER_GATE),
                 "--repo", tmpdir,
                 "--report", os.path.join(tmpdir, "nonexistent.md"),
                 "--", sys.executable, "-c", "print('should-not-run')"],
                capture_output=True, text=True,
            )
            self.assertNotEqual(
                0, result.returncode,
                f"expected nonzero exit, got {result.returncode}\nstdout: {result.stdout}",
            )
            self.assertIn("PREFLIGHT: FAIL", result.stdout)
            self.assertNotIn("should-not-run", result.stdout)


if __name__ == "__main__":
    unittest.main()
