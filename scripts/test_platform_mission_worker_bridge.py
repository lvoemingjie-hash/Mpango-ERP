#!/usr/bin/env python3
"""Tests for platform_mission_worker_bridge.py."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
BRIDGE = SCRIPT_DIR / "platform_mission_worker_bridge.py"


VALID_MISSION = {
    "phase": "P2-B",
    "agent": "opencode",
    "mission": "scripts/mission.md",
    "expected_files": ["scripts/output.py"],
    "result": "ai-ledger/platform/result.json",
    "events": "ai-ledger/platform/events.jsonl",
    "timeout_seconds": 60,
}


def run(cmd, cwd):
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)


def git(repo, *args):
    return run(["git", *args], repo)


def init_repo(repo):
    git(repo, "init")
    git(repo, "checkout", "-b", "codex/platform-p2b-test")
    (repo / "scripts").mkdir()
    (repo / "ai-ledger" / "platform").mkdir(parents=True)
    (repo / "scripts" / "mission.md").write_text("do work\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(
        repo,
        "-c",
        "user.name=test",
        "-c",
        "user.email=test@test.com",
        "commit",
        "-m",
        "init",
    )


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def write_fake_worker(path, body):
    path.write_text(
        "\n".join(
            [
                "import pathlib, sys",
                "repo = pathlib.Path(sys.argv[sys.argv.index('--repo') + 1])",
                body,
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    git(path.parent, "add", path.name)
    git(
        path.parent,
        "-c",
        "user.name=test",
        "-c",
        "user.email=test@test.com",
        "commit",
        "-m",
        "fake worker",
    )


def bridge_cmd(repo, mission, worker, *extra):
    return [
        sys.executable,
        str(BRIDGE),
        "--repo",
        str(repo),
        "--mission",
        str(mission),
        "--worker-script",
        str(worker),
        *extra,
    ]


class TestBridgeValidation(unittest.TestCase):
    def test_dry_run_prints_worker_command_and_does_not_execute(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            init_repo(repo)
            mission = repo / "ai-ledger" / "platform" / "mission.json"
            write_json(mission, VALID_MISSION)
            git(repo, "add", "-A")
            git(repo, "-c", "user.name=test", "-c", "user.email=test@test.com", "commit", "-m", "mission")
            worker = repo / "fake_worker.py"
            write_fake_worker(worker, "(repo / 'scripts/output.py').write_text('bad', encoding='utf-8')")

            result = run(bridge_cmd(repo, mission, worker, "--dry-run"), repo)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("platform", result.stdout)
            self.assertFalse((repo / "scripts" / "output.py").exists())

    def test_invalid_mission_contract_fails_before_worker(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            init_repo(repo)
            mission = repo / "ai-ledger" / "platform" / "mission.json"
            write_json(mission, dict(VALID_MISSION, expected_files=[]))
            worker = repo / "fake_worker.py"
            write_fake_worker(worker, "(repo / 'scripts/output.py').write_text('bad', encoding='utf-8')")

            result = run(bridge_cmd(repo, mission, worker), repo)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("expected_files", result.stdout)
            self.assertFalse((repo / "scripts" / "output.py").exists())

    def test_non_opencode_agent_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            init_repo(repo)
            mission = repo / "ai-ledger" / "platform" / "mission.json"
            write_json(mission, dict(VALID_MISSION, agent="claude"))
            worker = repo / "fake_worker.py"
            write_fake_worker(worker, "sys.exit(0)")

            result = run(bridge_cmd(repo, mission, worker), repo)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("opencode only", result.stdout)


class TestBridgePostCommandAudit(unittest.TestCase):
    def test_expected_file_result_and_events_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            init_repo(repo)
            mission = repo / "ai-ledger" / "platform" / "mission.json"
            write_json(mission, VALID_MISSION)
            git(repo, "add", "-A")
            git(repo, "-c", "user.name=test", "-c", "user.email=test@test.com", "commit", "-m", "mission")
            worker = repo / "fake_worker.py"
            write_fake_worker(
                worker,
                "\n".join(
                    [
                        "(repo / 'scripts/output.py').write_text('ok', encoding='utf-8')",
                        "(repo / 'ai-ledger/platform/result.json').write_text('{}', encoding='utf-8')",
                        "(repo / 'ai-ledger/platform/events.jsonl').write_text('', encoding='utf-8')",
                    ]
                ),
            )

            result = run(bridge_cmd(repo, mission, worker), repo)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("BRIDGE VERDICT: PASS", result.stdout)

    def test_extra_file_fails_even_when_worker_exit_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            init_repo(repo)
            mission = repo / "ai-ledger" / "platform" / "mission.json"
            write_json(mission, VALID_MISSION)
            git(repo, "add", "-A")
            git(repo, "-c", "user.name=test", "-c", "user.email=test@test.com", "commit", "-m", "mission")
            worker = repo / "fake_worker.py"
            write_fake_worker(
                worker,
                "\n".join(
                    [
                        "(repo / 'scripts/output.py').write_text('ok', encoding='utf-8')",
                        "(repo / 'scripts/extra.py').write_text('nope', encoding='utf-8')",
                        "(repo / 'ai-ledger/platform/result.json').write_text('{}', encoding='utf-8')",
                        "(repo / 'ai-ledger/platform/events.jsonl').write_text('', encoding='utf-8')",
                    ]
                ),
            )

            result = run(bridge_cmd(repo, mission, worker), repo)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unexpected", result.stdout.lower())
            self.assertIn("scripts/extra.py", result.stdout)

    def test_forbidden_actual_file_fails_even_if_expected_were_impossible(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            init_repo(repo)
            mission = repo / "ai-ledger" / "platform" / "mission.json"
            write_json(mission, VALID_MISSION)
            git(repo, "add", "-A")
            git(repo, "-c", "user.name=test", "-c", "user.email=test@test.com", "commit", "-m", "mission")
            worker = repo / "fake_worker.py"
            write_fake_worker(
                worker,
                "\n".join(
                    [
                        "(repo / 'backend').mkdir(exist_ok=True)",
                        "(repo / 'backend/bad.py').write_text('bad', encoding='utf-8')",
                        "(repo / 'ai-ledger/platform/result.json').write_text('{}', encoding='utf-8')",
                        "(repo / 'ai-ledger/platform/events.jsonl').write_text('', encoding='utf-8')",
                    ]
                ),
            )

            result = run(bridge_cmd(repo, mission, worker), repo)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("backend/bad.py", result.stdout)
            self.assertIn("forbidden", result.stdout.lower())

    def test_worker_nonzero_still_prints_changed_file_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            init_repo(repo)
            mission = repo / "ai-ledger" / "platform" / "mission.json"
            write_json(mission, VALID_MISSION)
            git(repo, "add", "-A")
            git(repo, "-c", "user.name=test", "-c", "user.email=test@test.com", "commit", "-m", "mission")
            worker = repo / "fake_worker.py"
            write_fake_worker(
                worker,
                "\n".join(
                    [
                        "(repo / 'scripts/output.py').write_text('partial', encoding='utf-8')",
                        "sys.exit(7)",
                    ]
                ),
            )

            result = run(bridge_cmd(repo, mission, worker), repo)

            self.assertEqual(result.returncode, 7, result.stdout + result.stderr)
            self.assertIn("Actual changed files", result.stdout)
            self.assertIn("scripts/output.py", result.stdout)
            self.assertIn("worker command failed", result.stdout)


if __name__ == "__main__":
    unittest.main()
