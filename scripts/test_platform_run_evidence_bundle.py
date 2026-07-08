#!/usr/bin/env python3
"""Tests for platform_run_evidence_bundle.py using unittest and stdlib only."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPT = SCRIPT_DIR / "platform_run_evidence_bundle.py"


def run_git(repo, args):
    return subprocess.run(
        ["git"] + args,
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=True,
    )


def write_text(repo, relpath, text):
    path = Path(repo) / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def write_json(repo, relpath, data):
    write_text(repo, relpath, json.dumps(data, indent=2))


class EvidenceRepo:
    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        run_git(self.repo, ["init"])
        self.mission = {
            "phase": "P2-C",
            "agent": "opencode",
            "mission": "scripts/mission.md",
            "expected_files": ["scripts/generated.py"],
            "result": "ai-ledger/platform/result.json",
            "events": "ai-ledger/platform/events.jsonl",
            "timeout_seconds": 600,
        }
        self.result = {
            "status": "done",
            "files_changed": [],
            "test_result": "worker tests passed",
        }
        write_text(self.repo, "scripts/mission.md", "Implement a platform task.\n")
        write_json(self.repo, "mission.json", self.mission)
        write_json(self.repo, "ai-ledger/platform/result.json", self.result)
        write_text(self.repo, "ai-ledger/platform/events.jsonl", '{"type":"done"}\n')
        run_git(self.repo, ["add", "."])
        run_git(
            self.repo,
            [
                "-c", "user.email=platform@example.test",
                "-c", "user.name=Platform Test",
                "commit", "-m", "baseline",
            ],
        )
        return self

    def __exit__(self, exc_type, exc, tb):
        self.tmp.cleanup()

    def run_bundle(self, output="ai-ledger/platform/bundle.md", extra_args=None):
        cmd = [
            sys.executable,
            str(SCRIPT),
            "--repo", str(self.repo),
            "--mission", "mission.json",
            "--result", "ai-ledger/platform/result.json",
            "--events", "ai-ledger/platform/events.jsonl",
            "--output", output,
            "--test-command", "python scripts/test_example.py",
        ]
        if extra_args:
            cmd.extend(extra_args)
        return subprocess.run(cmd, capture_output=True, text=True)

    def bundle_text(self, output="ai-ledger/platform/bundle.md"):
        return (self.repo / output).read_text(encoding="utf-8")


class TestEvidenceBundlePasses(unittest.TestCase):
    def test_valid_bundle_writes_markdown_and_passes(self):
        with EvidenceRepo() as ctx:
            result = ctx.run_bundle()
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            text = ctx.bundle_text()
            self.assertIn("FINAL VERDICT: PASS", text)
            self.assertIn("Mission JSON: `mission.json`", text)
            self.assertIn("ai-ledger/platform/bundle.md", text)

    def test_output_file_is_allowed_and_does_not_self_fail(self):
        with EvidenceRepo() as ctx:
            result = ctx.run_bundle()
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            text = ctx.bundle_text()
            self.assertIn("`ai-ledger/platform/bundle.md`", text)
            self.assertIn("Unexpected Changed Files\n\n- None", text)


class TestEvidenceBundleFailures(unittest.TestCase):
    def test_output_path_outside_platform_ledger_fails(self):
        with EvidenceRepo() as ctx:
            result = ctx.run_bundle(output="scripts/bundle.md")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("not under ai-ledger/platform", result.stdout)
            self.assertFalse((ctx.repo / "scripts/bundle.md").exists())

    def test_missing_result_json_fails_and_writes_bundle(self):
        with EvidenceRepo() as ctx:
            (ctx.repo / "ai-ledger/platform/result.json").unlink()
            result = ctx.run_bundle()
            self.assertNotEqual(result.returncode, 0)
            text = ctx.bundle_text()
            self.assertIn("could not read result JSON", text)
            self.assertIn("FINAL VERDICT: FAIL", text)

    def test_malformed_events_jsonl_is_diagnostic_fail_not_crash(self):
        with EvidenceRepo() as ctx:
            write_text(ctx.repo, "ai-ledger/platform/events.jsonl", '{"ok":true}\nnot-json\n')
            result = ctx.run_bundle()
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            text = ctx.bundle_text()
            self.assertIn("events line 2 malformed JSON", text)
            self.assertIn("FINAL VERDICT: FAIL", text)

    def test_unexpected_actual_changed_file_fails_and_is_reported(self):
        with EvidenceRepo() as ctx:
            write_text(ctx.repo, "scripts/extra.py", "print('extra')\n")
            result = ctx.run_bundle()
            self.assertNotEqual(result.returncode, 0)
            text = ctx.bundle_text()
            self.assertIn("scripts/extra.py", text)
            self.assertIn("unexpected actual changed files", text)

    def test_forbidden_actual_changed_file_fails_and_is_reported(self):
        with EvidenceRepo() as ctx:
            write_text(ctx.repo, "backend/evil.py", "print('forbidden')\n")
            result = ctx.run_bundle()
            self.assertNotEqual(result.returncode, 0)
            text = ctx.bundle_text()
            self.assertIn("backend/evil.py", text)
            self.assertIn("forbidden actual changed files", text)

    def test_mission_validation_failure_fails(self):
        with EvidenceRepo() as ctx:
            bad_mission = dict(ctx.mission)
            bad_mission["expected_files"] = []
            write_json(ctx.repo, "mission.json", bad_mission)
            result = ctx.run_bundle()
            self.assertNotEqual(result.returncode, 0)
            text = ctx.bundle_text()
            self.assertIn("'expected_files' must be a non-empty array", text)
            self.assertIn("FINAL VERDICT: FAIL", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
