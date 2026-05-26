#!/usr/bin/env python3
"""Tests for platform_opencode_worker_gate.py."""

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
GATE = SCRIPT_DIR / "platform_opencode_worker_gate.py"


def run(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def git(tmpdir, args):
    return run(["git"] + args, tmpdir)


def init_repo(tmpdir):
    git(tmpdir, ["init"])
    git(tmpdir, ["checkout", "-b", "codex/platform-p1k-test"])
    Path(tmpdir, "README.md").write_text("# test\n", encoding="utf-8")
    git(tmpdir, ["add", "-A"])
    git(
        tmpdir,
        [
            "-c", "user.name=test",
            "-c", "user.email=test@test.com",
            "commit", "-m", "init",
        ],
    )


def commit_all(tmpdir, message="fixture"):
    git(tmpdir, ["add", "-A"])
    git(
        tmpdir,
        [
            "-c", "user.name=test",
            "-c", "user.email=test@test.com",
            "commit", "-m", message,
        ],
    )


def make_fake_opencode(tmpdir, script):
    tool_dir = Path(tempfile.mkdtemp(prefix="fake-opencode-"))
    script_path = tool_dir / "fake_opencode.py"
    script_path.write_text(script, encoding="utf-8")
    if sys.platform.startswith("win"):
        shim = tool_dir / "fake_opencode.cmd"
        shim.write_text(f'@echo off\r\n"{sys.executable}" "{script_path}" %*\r\n', encoding="utf-8")
    else:
        shim = tool_dir / "fake_opencode"
        shim.write_text(f'#!/bin/sh\n"{sys.executable}" "{script_path}" "$@"\n', encoding="utf-8")
        os.chmod(shim, 0o755)
    return str(shim)


def mission(tmpdir):
    Path(tmpdir, "scripts").mkdir(exist_ok=True)
    path = Path(tmpdir, "scripts/mission.md")
    path.write_text("do the thing\n", encoding="utf-8")
    commit_all(tmpdir, "mission")
    return "scripts/mission.md"


def gate_cmd(tmpdir, opencode, extra=None):
    cmd = [
        sys.executable, str(GATE),
        "--repo", tmpdir,
        "--mission", "scripts/mission.md",
        "--result", "ai-ledger/platform/result.json",
        "--events", "ai-ledger/platform/events.jsonl",
        "--expected-file", "scripts/out.txt",
        "--opencode", opencode,
        "--allow-edits",
        "--timeout-seconds", "5",
    ]
    if extra:
        cmd.extend(extra)
    return cmd


def fake_script(status="done", exit_code=0, write_result=True, extra_change=False):
    body = f"""
import json
import sys
from pathlib import Path

root = Path.cwd()
(root / 'scripts').mkdir(exist_ok=True)
(root / 'scripts/out.txt').write_text('ok', encoding='utf-8')
if {str(extra_change)}:
    (root / 'scripts/extra.txt').write_text('extra', encoding='utf-8')
if {str(write_result)}:
    out = {{
        'status': {status!r},
        'files_changed': ['scripts/out.txt'],
        'test_result': 'fake tests passed',
    }}
    p = root / 'ai-ledger/platform/result.json'
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out), encoding='utf-8')
print('{{"type":"text","part":{{"text":"fake"}}}}')
sys.exit({exit_code})
"""
    return textwrap.dedent(body)


class TestWorkerGate(unittest.TestCase):
    def test_dry_run_creates_no_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            init_repo(tmpdir)
            mission(tmpdir)
            fake = make_fake_opencode(tmpdir, fake_script())
            result = run(gate_cmd(tmpdir, fake, ["--dry-run"]), tmpdir)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIn("DRY-RUN PASS", result.stdout)
            self.assertFalse(Path(tmpdir, "ai-ledger/platform/result.json").exists())

    def test_successful_worker_passes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            init_repo(tmpdir)
            mission(tmpdir)
            fake = make_fake_opencode(tmpdir, fake_script())
            result = run(gate_cmd(tmpdir, fake), tmpdir)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIn("WORKER VERDICT: PASS", result.stdout)
            self.assertTrue(Path(tmpdir, "ai-ledger/platform/events.jsonl").exists())

    def test_nonzero_worker_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            init_repo(tmpdir)
            mission(tmpdir)
            fake = make_fake_opencode(tmpdir, fake_script(status="failed", exit_code=7))
            result = run(gate_cmd(tmpdir, fake), tmpdir)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("WORKER VERDICT: FAIL", result.stdout)

    def test_timeout_returns_124(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            init_repo(tmpdir)
            mission(tmpdir)
            fake = make_fake_opencode(tmpdir, "import time\ntime.sleep(3)\n")
            result = run(
                gate_cmd(tmpdir, fake, ["--timeout-seconds", "0.2"]),
                tmpdir,
            )
            self.assertEqual(124, result.returncode)

    def test_missing_result_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            init_repo(tmpdir)
            mission(tmpdir)
            fake = make_fake_opencode(tmpdir, fake_script(write_result=False))
            result = run(gate_cmd(tmpdir, fake), tmpdir)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("could not load result JSON", result.stdout)

    def test_partial_status_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            init_repo(tmpdir)
            mission(tmpdir)
            fake = make_fake_opencode(tmpdir, fake_script(status="partial"))
            result = run(gate_cmd(tmpdir, fake), tmpdir)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("WORKER VERDICT: FAIL", result.stdout)

    def test_extra_actual_file_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            init_repo(tmpdir)
            mission(tmpdir)
            fake = make_fake_opencode(tmpdir, fake_script(extra_change=True))
            result = run(gate_cmd(tmpdir, fake), tmpdir)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("unexpected actual changed files", result.stdout)

    def test_unsafe_paths_fail(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            init_repo(tmpdir)
            mission(tmpdir)
            fake = make_fake_opencode(tmpdir, fake_script())
            result = run(
                gate_cmd(
                    tmpdir,
                    fake,
                    ["--expected-file", "../outside.txt"],
                ),
                tmpdir,
            )
            self.assertNotEqual(0, result.returncode)
            self.assertIn("unsafe path part", result.stdout)


if __name__ == "__main__":
    unittest.main()
