#!/usr/bin/env python3
"""Tests for platform_task_execution_bridge.py using unittest and tempfile only."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
BRIDGE = SCRIPT_DIR / "platform_task_execution_bridge.py"

REQUIRED_DOCS = [
    "docs/ai/CTO_CURRENT_OPS.md",
    "docs/ai/AI_TEAM_OPERATING_RULES.md",
    "docs/ai/PROJECT.md",
    "docs/ai/PROJECT_MEMORY.md",
    "docs/ai/README.md",
    "docs/ai/DUAL_MACHINE_DEVELOPMENT_PROTOCOL.md",
]

BRANCH = "codex/platform-p1f-test"


def _init_repo(tmpdir, branch_name=BRANCH, create_docs=True):
    subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
    subprocess.run(
        ["git", "checkout", "-b", branch_name],
        cwd=tmpdir, capture_output=True,
    )
    if create_docs:
        for doc in REQUIRED_DOCS:
            doc_path = os.path.join(tmpdir, doc)
            os.makedirs(os.path.dirname(doc_path), exist_ok=True)
            with open(doc_path, "w") as f:
                f.write(f"# {doc}\n")
    readme = os.path.join(tmpdir, "README.md")
    if not os.path.exists(readme):
        with open(readme, "w") as f:
            f.write("# test\n")
    subprocess.run(["git", "add", "-A"], cwd=tmpdir, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.name=test", "-c", "user.email=test@test.com",
         "commit", "-m", "init"],
        cwd=tmpdir, capture_output=True,
    )


def _create_report(tmpdir, rel_path="ai-ledger/platform/p1f-test.md", content=None):
    abs_path = os.path.join(tmpdir, rel_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "w") as f:
        f.write(content or (
            "- Branch: codex/platform-p1f-test\n"
            "- Commit: fixture\n"
            "- Modified files: fixture\n"
            "- Tests: fixture\n"
            "- Report path: ai-ledger/platform/p1f-test.md\n"
            "- Risk: LOW\n"
        ))
    return rel_path


def _commit_all(tmpdir, message="fixture"):
    subprocess.run(["git", "add", "-A"], cwd=tmpdir, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.name=test", "-c", "user.email=test@test.com",
         "commit", "-m", message],
        cwd=tmpdir, capture_output=True,
    )


def _create_packet(tmpdir, overrides=None):
    write_output = (
        "from pathlib import Path; "
        "Path('scripts').mkdir(exist_ok=True); "
        "Path('scripts/p1f_output.txt').write_text('ok')"
    )
    packet = {
        "phase": "P1-F",
        "branch": BRANCH,
        "agent": "opencode",
        "report": "ai-ledger/platform/p1f-test.md",
        "risk": "LOW",
        "allowed_files": [
            "scripts/platform_task_execution_bridge.py",
            "scripts/test_platform_task_execution_bridge.py",
            "ai-ledger/platform/p1f-test.md",
        ],
        "expected_files": [
            "scripts/platform_task_execution_bridge.py",
            "scripts/test_platform_task_execution_bridge.py",
            "ai-ledger/platform/p1f-test.md",
        ],
        "command": [
            sys.executable, "-c",
            write_output,
        ],
        "tests": ["python scripts/test_platform_task_execution_bridge.py"],
        "gate_only": False,
        "allow_platform_dev": False,
    }
    if overrides:
        packet.update(overrides)
    ppath = os.path.join(tmpdir, "packet.json")
    with open(ppath, "w") as f:
        json.dump(packet, f)
    return ppath


def _run_bridge(tmpdir, ppath, extra_args=None):
    cmd = [
        sys.executable, str(BRIDGE),
        "--packet", ppath,
        "--repo", tmpdir,
    ]
    if extra_args:
        cmd.extend(extra_args)
    return subprocess.run(cmd, capture_output=True, text=True)


class TestDryRun(unittest.TestCase):
    def test_dry_run_validates_both_gates_no_file_created(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir)
            _create_report(tmpdir)
            _commit_all(tmpdir)
            ppath = _create_packet(tmpdir)

            result = _run_bridge(tmpdir, ppath, [
                "--dry-run", "--skip-agent-tool-check",
            ])
            self.assertEqual(
                0, result.returncode,
                f"expected exit 0, got {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}",
            )
            self.assertIn("RUN PACKET GATE", result.stdout)
            self.assertIn("DIRECTIVE GATE", result.stdout)
            self.assertIn("EXECUTION BRIDGE VERDICT", result.stdout)
            self.assertIn("BRIDGE VERDICT: PASS", result.stdout)
            self.assertNotIn("BRIDGE VERDICT: FAIL", result.stdout)
            output_path = os.path.join(tmpdir, "scripts", "p1f_output.txt")
            self.assertFalse(
                os.path.exists(output_path),
                "dry-run should not create command output file",
            )


class TestSuccessfulExecution(unittest.TestCase):
    def test_successful_execution_creates_expected_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir)
            _create_report(tmpdir)
            _commit_all(tmpdir)
            ppath = _create_packet(tmpdir, {
                "allowed_files": [
                    "scripts/platform_task_execution_bridge.py",
                    "scripts/test_platform_task_execution_bridge.py",
                    "scripts/p1f_output.txt",
                    "ai-ledger/platform/p1f-test.md",
                ],
                "expected_files": [
                    "scripts/platform_task_execution_bridge.py",
                    "scripts/test_platform_task_execution_bridge.py",
                    "scripts/p1f_output.txt",
                    "ai-ledger/platform/p1f-test.md",
                ],
            })
            _commit_all(tmpdir, "packet fixture")

            result = _run_bridge(tmpdir, ppath, ["--skip-agent-tool-check"])
            self.assertEqual(
                0, result.returncode,
                f"expected exit 0, got {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}",
            )
            self.assertIn("BRIDGE VERDICT: PASS", result.stdout)
            output_path = os.path.join(tmpdir, "scripts", "p1f_output.txt")
            self.assertTrue(
                os.path.exists(output_path),
                "non-dry-run should create expected output file",
            )


class TestUnexpectedFileFails(unittest.TestCase):
    def test_unexpected_file_fails_via_directive_postflight(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir)
            _create_report(tmpdir)
            _commit_all(tmpdir)
            ppath = _create_packet(tmpdir, {
                "allowed_files": [
                    "scripts/platform_task_execution_bridge.py",
                    "scripts/test_platform_task_execution_bridge.py",
                    "scripts/p1f_output.txt",
                    "scripts/unexpected.txt",
                    "ai-ledger/platform/p1f-test.md",
                ],
                "expected_files": [
                    "scripts/platform_task_execution_bridge.py",
                    "scripts/test_platform_task_execution_bridge.py",
                    "scripts/p1f_output.txt",
                    "ai-ledger/platform/p1f-test.md",
                ],
                "command": [
                    sys.executable, "-c",
                    "from pathlib import Path; Path('scripts').mkdir(exist_ok=True); Path('scripts/p1f_output.txt').write_text('ok'); Path('scripts/unexpected.txt').write_text('bad')",
                ],
            })
            _commit_all(tmpdir, "packet fixture")

            result = _run_bridge(tmpdir, ppath, ["--skip-agent-tool-check"])
            self.assertNotEqual(
                0, result.returncode,
                f"expected nonzero exit, got {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}",
            )
            self.assertIn("BRIDGE VERDICT: FAIL", result.stdout)
            self.assertIn("unexpected changed file(s)", result.stdout)
            self.assertIn("unexpected.txt", result.stdout)


class TestInvalidPacketFailsBeforeDirectiveGate(unittest.TestCase):
    def test_invalid_packet_fails_before_directive_gate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir)
            _create_report(tmpdir)
            ppath = os.path.join(tmpdir, "packet.json")
            with open(ppath, "w") as f:
                json.dump({"phase": "P1-F"}, f)

            result = _run_bridge(tmpdir, ppath)
            self.assertNotEqual(
                0, result.returncode,
                f"expected nonzero exit, got {result.returncode}\nstdout: {result.stdout}",
            )
            self.assertIn("RUN PACKET GATE", result.stdout)
            self.assertIn("DIRECTIVE GATE: SKIPPED", result.stdout)
            self.assertIn("BRIDGE VERDICT: FAIL", result.stdout)

    def test_bad_json_fails_before_directive_gate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir)
            ppath = os.path.join(tmpdir, "packet.json")
            with open(ppath, "w") as f:
                f.write("not valid json {")

            result = _run_bridge(tmpdir, ppath)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("RUN PACKET GATE", result.stdout)
            self.assertIn("DIRECTIVE GATE: SKIPPED", result.stdout)


class TestSkipAgentToolCheck(unittest.TestCase):
    def test_skip_agent_tool_check_allows_testing_without_opencode(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir)
            _create_report(tmpdir)
            _commit_all(tmpdir)
            ppath = _create_packet(tmpdir, {
                "allowed_files": [
                    "scripts/platform_task_execution_bridge.py",
                    "scripts/test_platform_task_execution_bridge.py",
                    "scripts/p1f_output.txt",
                    "ai-ledger/platform/p1f-test.md",
                ],
                "expected_files": [
                    "scripts/platform_task_execution_bridge.py",
                    "scripts/test_platform_task_execution_bridge.py",
                    "scripts/p1f_output.txt",
                    "ai-ledger/platform/p1f-test.md",
                ],
            })
            _commit_all(tmpdir, "packet fixture")

            result = _run_bridge(tmpdir, ppath, ["--skip-agent-tool-check"])
            self.assertEqual(
                0, result.returncode,
                f"expected exit 0, got {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}",
            )


class TestKeepDirective(unittest.TestCase):
    def test_keep_directive_safe_path_in_dry_run(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir)
            _create_report(tmpdir)
            _commit_all(tmpdir)
            ppath = _create_packet(tmpdir)

            keep_rel = "ai-ledger/platform/p1f-emitted-directive.json"
            result = _run_bridge(tmpdir, ppath, [
                "--dry-run", "--skip-agent-tool-check",
                "--keep-directive", keep_rel,
            ])
            self.assertEqual(
                0, result.returncode,
                f"expected exit 0, got {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}",
            )
            keep_abs = os.path.join(tmpdir, keep_rel)
            self.assertTrue(
                os.path.exists(keep_abs),
                f"keep-directive file should exist at {keep_abs}",
            )
            with open(keep_abs) as f:
                directive = json.load(f)
            self.assertIn("command", directive)
            self.assertIn("phase", directive)
            self.assertIn("branch", directive)
            self.assertIn("--keep-directive", result.stdout)

    def test_keep_directive_absolute_path_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir)
            _create_report(tmpdir)
            _commit_all(tmpdir)
            ppath = _create_packet(tmpdir)

            result = _run_bridge(tmpdir, ppath, [
                "--dry-run", "--skip-agent-tool-check",
                "--keep-directive", "/tmp/absolute_out.json",
            ])
            self.assertNotEqual(0, result.returncode)
            self.assertIn("must be relative", result.stdout)

    def test_keep_directive_traversal_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir)
            _create_report(tmpdir)
            _commit_all(tmpdir)
            ppath = _create_packet(tmpdir)

            result = _run_bridge(tmpdir, ppath, [
                "--dry-run", "--skip-agent-tool-check",
                "--keep-directive", "../outside.json",
            ])
            self.assertNotEqual(0, result.returncode)
            self.assertIn("unsafe path part", result.stdout)

    def test_keep_directive_forbidden_path_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir)
            _create_report(tmpdir)
            _commit_all(tmpdir)
            ppath = _create_packet(tmpdir)

            result = _run_bridge(tmpdir, ppath, [
                "--dry-run", "--skip-agent-tool-check",
                "--keep-directive", "backend/something.json",
            ])
            self.assertNotEqual(0, result.returncode)
            self.assertIn("forbidden", result.stdout)
            self.assertIn("backend", result.stdout)


class TestUnknownAgent(unittest.TestCase):
    def test_unknown_agent_fails_by_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir)
            _create_report(tmpdir)
            _commit_all(tmpdir)
            ppath = _create_packet(tmpdir, {"agent": "custom-agent"})

            result = _run_bridge(tmpdir, ppath)
            self.assertNotEqual(
                0, result.returncode,
                f"expected nonzero exit, got {result.returncode}\nstdout: {result.stdout}",
            )
            self.assertIn("not a known agent", result.stdout)
            self.assertIn("BRIDGE VERDICT: FAIL", result.stdout)
            self.assertIn("DIRECTIVE GATE: SKIPPED", result.stdout)

    def test_unknown_agent_passes_with_allow_and_skip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir)
            _create_report(tmpdir)
            _commit_all(tmpdir)
            ppath = _create_packet(tmpdir, {
                "agent": "custom-agent",
                "allowed_files": [
                    "scripts/platform_task_execution_bridge.py",
                    "scripts/test_platform_task_execution_bridge.py",
                    "scripts/p1f_output.txt",
                    "ai-ledger/platform/p1f-test.md",
                ],
                "expected_files": [
                    "scripts/platform_task_execution_bridge.py",
                    "scripts/test_platform_task_execution_bridge.py",
                    "scripts/p1f_output.txt",
                    "ai-ledger/platform/p1f-test.md",
                ],
            })
            _commit_all(tmpdir, "packet fixture")

            result = _run_bridge(tmpdir, ppath, [
                "--allow-unknown-agent", "--skip-agent-tool-check",
            ])
            self.assertEqual(
                0, result.returncode,
                f"expected exit 0, got {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}",
            )
            self.assertIn("BRIDGE VERDICT: PASS", result.stdout)

    def test_unknown_agent_fails_with_allow_but_no_skip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir)
            _create_report(tmpdir)
            _commit_all(tmpdir)
            ppath = _create_packet(tmpdir, {"agent": "custom-agent"})

            result = _run_bridge(tmpdir, ppath, ["--allow-unknown-agent"])
            self.assertNotEqual(
                0, result.returncode,
                f"expected nonzero exit, got {result.returncode}\nstdout: {result.stdout}",
            )
            self.assertIn("BRIDGE VERDICT: FAIL", result.stdout)


if __name__ == "__main__":
    unittest.main()
