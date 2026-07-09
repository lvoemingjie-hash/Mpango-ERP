#!/usr/bin/env python3
"""Tests for platform_batch_review_packet.py."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
BATCH_PACKET = SCRIPT_DIR / "platform_batch_review_packet.py"


def _run(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def _git(tmpdir, args):
    return _run(["git"] + args, tmpdir)


def _init_repo(tmpdir):
    _git(tmpdir, ["init"])
    _git(tmpdir, ["checkout", "-b", "codex/platform-p1g-test"])
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
    return _git(tmpdir, ["rev-parse", "HEAD"]).stdout.strip()


def _commit_file(tmpdir, rel_path, content="data\n", message="change"):
    path = Path(tmpdir, rel_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _git(tmpdir, ["add", "-A"])
    _git(
        tmpdir,
        [
            "-c", "user.name=test",
            "-c", "user.email=test@test.com",
            "commit", "-m", message,
        ],
    )


def _packet_cmd(tmpdir, base_ref, output="ai-ledger/platform/p1g.md", extra=None):
    cmd = [
        sys.executable, str(BATCH_PACKET),
        "--repo", tmpdir,
        "--base-ref", base_ref,
        "--output", output,
        "--risk", "MEDIUM",
        "--phase", "P1-D Agent Toolchain Gate",
        "--phase", "P1-E Agent Run Packet Standardization",
    ]
    if extra:
        cmd.extend(extra)
    return cmd


class TestValidPacket(unittest.TestCase):
    def test_valid_repo_writes_packet(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = _init_repo(tmpdir)
            _commit_file(tmpdir, "scripts/platform_tool.py")

            result = _run(_packet_cmd(tmpdir, base), tmpdir)

            self.assertEqual(
                0, result.returncode,
                f"expected exit 0\nstdout: {result.stdout}\nstderr: {result.stderr}",
            )
            out = Path(tmpdir, "ai-ledger/platform/p1g.md")
            self.assertTrue(out.exists())
            content = out.read_text(encoding="utf-8")
            self.assertIn("Phase P1-G", content)
            self.assertIn("codex/platform-p1g-test", content)
            self.assertIn(base, content)
            self.assertIn("P1-D Agent Toolchain Gate", content)
            self.assertIn("scripts/platform_tool.py", content)
            self.assertIn("MEDIUM", content)


class TestRequireClean(unittest.TestCase):
    def test_require_clean_fails_with_uncommitted_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = _init_repo(tmpdir)
            Path(tmpdir, "scripts").mkdir()
            Path(tmpdir, "scripts/dirty.txt").write_text("dirty\n", encoding="utf-8")

            result = _run(
                _packet_cmd(tmpdir, base, extra=["--require-clean"]),
                tmpdir,
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("--require-clean", result.stdout)
            self.assertFalse(Path(tmpdir, "ai-ledger/platform/p1g.md").exists())


class TestForbiddenPaths(unittest.TestCase):
    def test_forbidden_changed_path_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = _init_repo(tmpdir)
            _commit_file(tmpdir, "backend/bad.py")

            result = _run(_packet_cmd(tmpdir, base), tmpdir)

            self.assertNotEqual(0, result.returncode)
            self.assertIn("forbidden changed path", result.stdout)
            self.assertIn("backend/bad.py", result.stdout)
            self.assertFalse(Path(tmpdir, "ai-ledger/platform/p1g.md").exists())


class TestInvalidOutput(unittest.TestCase):
    def test_absolute_output_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = _init_repo(tmpdir)
            output = str(Path(tmpdir, "outside.md"))

            result = _run(_packet_cmd(tmpdir, base, output=output), tmpdir)

            self.assertNotEqual(0, result.returncode)
            self.assertIn("must be relative", result.stdout)

    def test_traversal_output_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = _init_repo(tmpdir)

            result = _run(_packet_cmd(tmpdir, base, output="../outside.md"), tmpdir)

            self.assertNotEqual(0, result.returncode)
            self.assertIn("unsafe path part", result.stdout)

    def test_output_outside_ledger_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = _init_repo(tmpdir)

            result = _run(_packet_cmd(tmpdir, base, output="docs/p1g.md"), tmpdir)

            self.assertNotEqual(0, result.returncode)
            self.assertIn("not under ai-ledger/platform", result.stdout)


class TestInvalidArguments(unittest.TestCase):
    def test_invalid_risk_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = _init_repo(tmpdir)
            cmd = _packet_cmd(tmpdir, base)
            cmd[cmd.index("--risk") + 1] = "NOPE"

            result = _run(cmd, tmpdir)

            self.assertNotEqual(0, result.returncode)
            self.assertIn("invalid choice", result.stderr)

    def test_no_phase_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = _init_repo(tmpdir)
            cmd = [
                sys.executable, str(BATCH_PACKET),
                "--repo", tmpdir,
                "--base-ref", base,
                "--output", "ai-ledger/platform/p1g.md",
                "--risk", "MEDIUM",
            ]

            result = _run(cmd, tmpdir)

            self.assertNotEqual(0, result.returncode)
            self.assertIn("at least one --phase", result.stdout)


if __name__ == "__main__":
    unittest.main()
