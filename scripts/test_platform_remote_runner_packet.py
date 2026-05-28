#!/usr/bin/env python3
"""Tests for platform_remote_runner_packet.py."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = str(
    Path(__file__).resolve().parent / "platform_remote_runner_packet.py"
)
REPO_ROOT = str(Path(__file__).resolve().parent.parent)


def run_script(*extra_args, cwd=None):
    cmd = [sys.executable, SCRIPT] + list(extra_args)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=30,
        cwd=cwd or REPO_ROOT,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


class TestRemoteRunnerPacket(unittest.TestCase):

    def _base_args(self, **overrides):
        args = [
            "--repo", REPO_ROOT,
            "--base-ref", "origin/platform-dev",
            "--output", "ai-ledger/platform/packet_test.md",
            "--report", "ai-ledger/platform/report_test.md",
            "--risk", "MEDIUM",
            "--test-command", "python scripts/test_x.py",
            "--allow-platform-dev",
        ]
        for k, v in overrides.items():
            flag = "--" + k.replace("_", "-")
            args.append(flag)
            args.append(v)
        return args

    def test_valid_repo_writes_packet_and_pass(self):
        rc, out, err = run_script(*self._base_args())
        self.assertEqual(rc, 0, f"stdout={out}\nstderr={err}")
        packet = Path(REPO_ROOT) / "ai-ledger" / "platform" / "packet_test.md"
        report = Path(REPO_ROOT) / "ai-ledger" / "platform" / "report_test.md"
        self.assertTrue(packet.exists())
        self.assertTrue(report.exists())
        content = packet.read_text(encoding="utf-8")
        self.assertIn("P2-D", content)
        self.assertIn("MEDIUM", content)
        report_text = report.read_text(encoding="utf-8")
        self.assertIn("PENDING", report_text)
        packet.unlink(missing_ok=True)
        report.unlink(missing_ok=True)

    def test_non_codex_platform_branch_fails_by_default(self):
        with tempfile.TemporaryDirectory() as td:
            subprocess.run(
                ["git", "init"], cwd=td, capture_output=True, timeout=10,
            )
            subprocess.run(
                ["git", "config", "user.email", "t@t.com"],
                cwd=td, capture_output=True, timeout=10,
            )
            subprocess.run(
                ["git", "config", "user.name", "T"],
                cwd=td, capture_output=True, timeout=10,
            )
            dummy = Path(td) / "f.txt"
            dummy.write_text("x", encoding="utf-8")
            subprocess.run(
                ["git", "add", "."], cwd=td, capture_output=True, timeout=10,
            )
            subprocess.run(
                ["git", "commit", "-m", "init"],
                cwd=td, capture_output=True, timeout=10,
            )
            base = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=td, capture_output=True, text=True, timeout=10,
            ).stdout.strip()
            subprocess.run(
                ["git", "checkout", "-b", "feature/other"],
                cwd=td, capture_output=True, timeout=10,
            )
            f2 = Path(td) / "g.txt"
            f2.write_text("y", encoding="utf-8")
            subprocess.run(
                ["git", "add", "."], cwd=td, capture_output=True, timeout=10,
            )
            subprocess.run(
                ["git", "commit", "-m", "second"],
                cwd=td, capture_output=True, timeout=10,
            )
            rc, out, err = run_script(
                "--repo", td,
                "--base-ref", base,
                "--output", "ai-ledger/platform/p.md",
                "--report", "ai-ledger/platform/r.md",
                "--risk", "MEDIUM",
                "--test-command", "echo hi",
                cwd=td,
            )
            self.assertNotEqual(rc, 0)
            self.assertIn("codex/platform-", out + err)

    def test_allow_platform_dev_does_not_allow_other_branch(self):
        with tempfile.TemporaryDirectory() as td:
            subprocess.run(
                ["git", "init"], cwd=td, capture_output=True, timeout=10,
            )
            subprocess.run(
                ["git", "config", "user.email", "t@t.com"],
                cwd=td, capture_output=True, timeout=10,
            )
            subprocess.run(
                ["git", "config", "user.name", "T"],
                cwd=td, capture_output=True, timeout=10,
            )
            subprocess.run(
                ["git", "commit", "--allow-empty", "-m", "base"],
                cwd=td, capture_output=True, timeout=10,
            )
            base = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=td, capture_output=True, text=True, timeout=10,
            ).stdout.strip()
            subprocess.run(
                ["git", "checkout", "-b", "feature/other"],
                cwd=td, capture_output=True, timeout=10,
            )
            rc, out, err = run_script(
                "--repo", td,
                "--base-ref", base,
                "--output", "ai-ledger/platform/p.md",
                "--report", "ai-ledger/platform/r.md",
                "--risk", "MEDIUM",
                "--test-command", "echo hi",
                "--allow-platform-dev",
                cwd=td,
            )
            self.assertNotEqual(rc, 0)
            self.assertIn("platform-dev", out + err)

    def test_platform_dev_passes_with_allow_flag(self):
        with tempfile.TemporaryDirectory() as td:
            subprocess.run(
                ["git", "init"], cwd=td, capture_output=True, timeout=10,
            )
            subprocess.run(
                ["git", "config", "user.email", "t@t.com"],
                cwd=td, capture_output=True, timeout=10,
            )
            subprocess.run(
                ["git", "config", "user.name", "T"],
                cwd=td, capture_output=True, timeout=10,
            )
            dummy = Path(td) / "f.txt"
            dummy.write_text("x", encoding="utf-8")
            subprocess.run(
                ["git", "add", "."], cwd=td, capture_output=True, timeout=10,
            )
            subprocess.run(
                ["git", "commit", "-m", "init"],
                cwd=td, capture_output=True, timeout=10,
            )
            base = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=td, capture_output=True, text=True, timeout=10,
            ).stdout.strip()
            subprocess.run(
                ["git", "checkout", "-b", "platform-dev"],
                cwd=td, capture_output=True, timeout=10,
            )
            f2 = Path(td) / "g.txt"
            f2.write_text("y", encoding="utf-8")
            subprocess.run(
                ["git", "add", "."], cwd=td, capture_output=True, timeout=10,
            )
            subprocess.run(
                ["git", "commit", "-m", "second"],
                cwd=td, capture_output=True, timeout=10,
            )
            rc, out, err = run_script(
                "--repo", td,
                "--base-ref", base,
                "--output", "ai-ledger/platform/p.md",
                "--report", "ai-ledger/platform/r.md",
                "--risk", "LOW",
                "--test-command", "echo hi",
                "--allow-platform-dev",
                cwd=td,
            )
            self.assertEqual(rc, 0, f"stdout={out}\nstderr={err}")
            self.assertTrue((Path(td) / "ai-ledger" / "platform" / "p.md").exists())

    def test_output_outside_ai_ledger_platform_fails(self):
        rc, out, err = run_script(
            "--repo", REPO_ROOT,
            "--base-ref", "origin/platform-dev",
            "--output", "scripts/bad.md",
            "--report", "ai-ledger/platform/r.md",
            "--risk", "MEDIUM",
            "--test-command", "echo hi",
        )
        self.assertNotEqual(rc, 0)
        self.assertIn("ai-ledger/platform/", out + err)

    def test_forbidden_changed_path_fails(self):
        with tempfile.TemporaryDirectory() as td:
            subprocess.run(
                ["git", "init"], cwd=td, capture_output=True, timeout=10,
            )
            subprocess.run(
                ["git", "config", "user.email", "t@t.com"],
                cwd=td, capture_output=True, timeout=10,
            )
            subprocess.run(
                ["git", "config", "user.name", "T"],
                cwd=td, capture_output=True, timeout=10,
            )
            subprocess.run(
                ["git", "commit", "--allow-empty", "-m", "base"],
                cwd=td, capture_output=True, timeout=10,
            )
            base = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=td, capture_output=True, text=True, timeout=10,
            ).stdout.strip()
            subprocess.run(
                ["git", "checkout", "-b", "codex/platform-test"],
                cwd=td, capture_output=True, timeout=10,
            )
            forbidden_dir = Path(td) / "backend"
            forbidden_dir.mkdir()
            bad_file = forbidden_dir / "app.py"
            bad_file.write_text("x", encoding="utf-8")
            subprocess.run(
                ["git", "add", "."], cwd=td, capture_output=True, timeout=10,
            )
            subprocess.run(
                ["git", "commit", "-m", "bad"],
                cwd=td, capture_output=True, timeout=10,
            )
            rc, out, err = run_script(
                "--repo", td,
                "--base-ref", base,
                "--output", "ai-ledger/platform/p.md",
                "--report", "ai-ledger/platform/r.md",
                "--risk", "HIGH",
                "--test-command", "echo hi",
                cwd=td,
            )
            self.assertNotEqual(rc, 0)
            self.assertIn("forbidden", (out + err).lower())

    def test_require_clean_fails_with_uncommitted(self):
        with tempfile.TemporaryDirectory() as td:
            subprocess.run(
                ["git", "init"], cwd=td, capture_output=True, timeout=10,
            )
            subprocess.run(
                ["git", "config", "user.email", "t@t.com"],
                cwd=td, capture_output=True, timeout=10,
            )
            subprocess.run(
                ["git", "config", "user.name", "T"],
                cwd=td, capture_output=True, timeout=10,
            )
            subprocess.run(
                ["git", "commit", "--allow-empty", "-m", "base"],
                cwd=td, capture_output=True, timeout=10,
            )
            subprocess.run(
                ["git", "checkout", "-b", "codex/platform-test"],
                cwd=td, capture_output=True, timeout=10,
            )
            dirty = Path(td) / "dirty.txt"
            dirty.write_text("uncommitted", encoding="utf-8")
            rc, out, err = run_script(
                "--repo", td,
                "--base-ref", "HEAD",
                "--output", "ai-ledger/platform/p.md",
                "--report", "ai-ledger/platform/r.md",
                "--risk", "LOW",
                "--test-command", "echo hi",
                "--require-clean",
                cwd=td,
            )
            self.assertNotEqual(rc, 0)
            self.assertIn("require-clean", (out + err).lower())

    def test_missing_test_command_fails(self):
        rc, out, err = run_script(
            "--repo", REPO_ROOT,
            "--base-ref", "origin/platform-dev",
            "--output", "ai-ledger/platform/p.md",
            "--report", "ai-ledger/platform/r.md",
            "--risk", "MEDIUM",
        )
        self.assertNotEqual(rc, 0)

    def test_expected_file_traversal_drive_path_fails(self):
        rc, out, err = run_script(
            "--repo", REPO_ROOT,
            "--base-ref", "origin/platform-dev",
            "--output", "ai-ledger/platform/p.md",
            "--report", "ai-ledger/platform/r.md",
            "--risk", "MEDIUM",
            "--test-command", "echo hi",
            "--expected-file", "../etc/passwd",
        )
        self.assertNotEqual(rc, 0)

        rc2, out2, err2 = run_script(
            "--repo", REPO_ROOT,
            "--base-ref", "origin/platform-dev",
            "--output", "ai-ledger/platform/p.md",
            "--report", "ai-ledger/platform/r.md",
            "--risk", "MEDIUM",
            "--test-command", "echo hi",
            "--expected-file", "C:\\Windows\\System32\\config",
        )
        self.assertNotEqual(rc2, 0)


if __name__ == "__main__":
    unittest.main()
