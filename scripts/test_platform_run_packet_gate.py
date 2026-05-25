#!/usr/bin/env python3
"""Tests for platform_run_packet_gate.py using unittest and tempfile only."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PACKET_GATE = SCRIPT_DIR / "platform_run_packet_gate.py"
DIRECTIVE_GATE = SCRIPT_DIR / "platform_directive_gate.py"

REQUIRED_TEMPLATE_FIELDS = [
    "phase", "branch", "agent", "report", "risk",
    "allowed_files", "expected_files", "command", "tests", "gate_only",
]

DIRECTIVE_FIELDS = [
    "phase", "branch", "report", "risk", "command",
    "gate_only", "expected_files", "allow_platform_dev",
]

VALID_PACKET = {
    "phase": "P1-E",
    "branch": "codex/platform-p1e-test",
    "agent": "opencode",
    "report": "ai-ledger/platform/p1e-test.md",
    "risk": "LOW",
    "allowed_files": [
        "scripts/platform_run_packet_gate.py",
        "scripts/test_platform_run_packet_gate.py",
        "ai-ledger/platform/p1e-test.md",
    ],
    "expected_files": [
        "scripts/platform_run_packet_gate.py",
        "scripts/test_platform_run_packet_gate.py",
        "ai-ledger/platform/p1e-test.md",
    ],
    "command": ["python", "scripts/platform_run_packet_gate.py", "--print-template"],
    "tests": ["python scripts/test_platform_run_packet_gate.py"],
    "gate_only": False,
    "allow_platform_dev": False,
}

REQUIRED_DOCS = [
    "docs/ai/CTO_CURRENT_OPS.md",
    "docs/ai/AI_TEAM_OPERATING_RULES.md",
    "docs/ai/PROJECT.md",
    "docs/ai/PROJECT_MEMORY.md",
    "docs/ai/README.md",
    "docs/ai/DUAL_MACHINE_DEVELOPMENT_PROTOCOL.md",
]


def _init_repo(tmpdir, branch_name, create_docs=True):
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


def _create_report(tmpdir, rel_path="ai-ledger/platform/p1e-test.md", content=None):
    abs_path = os.path.join(tmpdir, rel_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "w") as f:
        f.write(content or "- Branch: codex/platform-p1e-test\n- Risk: LOW\n")
    return rel_path


def _create_packet(tmpdir, overrides=None):
    packet = dict(VALID_PACKET)
    if overrides:
        packet.update(overrides)
    ppath = os.path.join(tmpdir, "packet.json")
    with open(ppath, "w") as f:
        json.dump(packet, f)
    return ppath


def _commit_all(tmpdir, message="fixture"):
    subprocess.run(["git", "add", "-A"], cwd=tmpdir, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.name=test", "-c", "user.email=test@test.com",
         "commit", "-m", message],
        cwd=tmpdir, capture_output=True,
    )


def _run_gate(tmpdir, ppath, extra_args=None):
    cmd = [sys.executable, str(PACKET_GATE), "--packet", ppath, "--repo", tmpdir]
    if extra_args:
        cmd.extend(extra_args)
    return subprocess.run(cmd, capture_output=True, text=True)


class TestPrintTemplate(unittest.TestCase):
    def test_print_template_outputs_valid_json(self):
        result = subprocess.run(
            [sys.executable, str(PACKET_GATE), "--print-template"],
            capture_output=True, text=True,
        )
        self.assertEqual(0, result.returncode)
        try:
            template = json.loads(result.stdout)
        except json.JSONDecodeError:
            self.fail("template is not valid JSON")

        for field in REQUIRED_TEMPLATE_FIELDS:
            self.assertIn(field, template,
                          f"template missing required field '{field}'")

    def test_print_template_exits_zero(self):
        result = subprocess.run(
            [sys.executable, str(PACKET_GATE), "--print-template"],
            capture_output=True, text=True,
        )
        self.assertEqual(0, result.returncode)

    def test_print_template_has_valid_agent(self):
        result = subprocess.run(
            [sys.executable, str(PACKET_GATE), "--print-template"],
            capture_output=True, text=True,
        )
        template = json.loads(result.stdout)
        self.assertIn(template["agent"], ["opencode", "goose", "codex"])


class TestValidPacketPasses(unittest.TestCase):
    def test_valid_packet_passes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-p1e-test")
            _create_report(tmpdir)
            ppath = _create_packet(tmpdir)

            result = _run_gate(tmpdir, ppath)
            self.assertEqual(
                0, result.returncode,
                f"expected exit 0, got {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}",
            )
            self.assertIn("RUN PACKET VALIDATION", result.stdout)
            self.assertIn("NORMALIZED RUN PACKET", result.stdout)
            self.assertIn("EMITTED DIRECTIVE", result.stdout)
            self.assertIn("RUN PACKET VERDICT: PASS", result.stdout)

    def test_valid_packet_with_notes_string(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-p1e-test")
            _create_report(tmpdir)
            ppath = _create_packet(tmpdir, {"notes": "A single note string"})

            result = _run_gate(tmpdir, ppath)
            self.assertEqual(
                0, result.returncode,
                f"expected exit 0, got {result.returncode}\nstdout: {result.stdout}",
            )

    def test_valid_packet_with_notes_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-p1e-test")
            _create_report(tmpdir)
            ppath = _create_packet(tmpdir, {"notes": ["note1", "note2"]})

            result = _run_gate(tmpdir, ppath)
            self.assertEqual(
                0, result.returncode,
                f"expected exit 0, got {result.returncode}\nstdout: {result.stdout}",
            )

    def test_valid_packet_gate_only_true(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-p1e-test")
            _create_report(tmpdir)
            ppath = _create_packet(tmpdir, {"gate_only": True, "command": []})

            result = _run_gate(tmpdir, ppath)
            self.assertEqual(
                0, result.returncode,
                f"expected exit 0, got {result.returncode}\nstdout: {result.stdout}",
            )


class TestEmitDirective(unittest.TestCase):
    def test_emit_directive_writes_correct_subset(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-p1e-test")
            _create_report(tmpdir)
            ppath = _create_packet(tmpdir)
            dpath = os.path.join(tmpdir, "out_directive.json")

            result = _run_gate(tmpdir, ppath, ["--emit-directive", dpath])
            self.assertEqual(
                0, result.returncode,
                f"expected exit 0, got {result.returncode}\nstdout: {result.stdout}",
            )
            self.assertTrue(os.path.exists(dpath))

            with open(dpath) as f:
                directive = json.load(f)

            self.assertIn("Directive written to", result.stdout)

            for field in DIRECTIVE_FIELDS:
                self.assertIn(field, directive,
                              f"emitted directive missing field '{field}'")

            self.assertNotIn("allowed_files", directive,
                             "emitted directive must not include allowed_files")
            self.assertNotIn("tests", directive,
                             "emitted directive must not include tests")
            self.assertNotIn("agent", directive,
                             "emitted directive must not include agent")

    def test_emitted_directive_has_correct_values(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-p1e-test")
            _create_report(tmpdir)
            ppath = _create_packet(tmpdir)
            dpath = os.path.join(tmpdir, "out_directive.json")

            _run_gate(tmpdir, ppath, ["--emit-directive", dpath])

            with open(dpath) as f:
                directive = json.load(f)

            self.assertEqual(directive["phase"], "P1-E")
            self.assertEqual(directive["branch"], "codex/platform-p1e-test")
            self.assertEqual(directive["report"], "ai-ledger/platform/p1e-test.md")
            self.assertEqual(directive["risk"], "LOW")
            self.assertEqual(directive["command"], VALID_PACKET["command"])
            self.assertEqual(directive["gate_only"], False)
            self.assertEqual(directive["expected_files"], VALID_PACKET["expected_files"])
            self.assertEqual(directive["allow_platform_dev"], False)

    def test_emit_directive_normalizes_paths(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-p1e-test")
            _create_report(tmpdir)
            ppath = _create_packet(tmpdir, {
                "report": "ai-ledger\\platform\\p1e-test.md",
                "allowed_files": [
                    "scripts\\platform_run_packet_gate.py",
                    "scripts\\test_platform_run_packet_gate.py",
                    "ai-ledger\\platform\\p1e-test.md",
                ],
                "expected_files": [
                    "scripts\\platform_run_packet_gate.py",
                    "scripts\\test_platform_run_packet_gate.py",
                    "ai-ledger\\platform\\p1e-test.md",
                ],
            })
            dpath = os.path.join(tmpdir, "out_directive.json")

            result = _run_gate(tmpdir, ppath, ["--emit-directive", dpath])
            self.assertEqual(
                0, result.returncode,
                f"expected exit 0, got {result.returncode}\nstdout: {result.stdout}",
            )

            with open(dpath) as f:
                directive = json.load(f)

            self.assertEqual(directive["report"], "ai-ledger/platform/p1e-test.md")
            self.assertIn(
                "scripts/platform_run_packet_gate.py",
                directive["expected_files"],
            )


class TestEmittedDirectiveAcceptedByDirectiveGate(unittest.TestCase):
    def test_emitted_directive_passes_directive_gate_dry_run(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-p1e-test")
            _create_report(tmpdir)
            ppath = _create_packet(tmpdir)
            dpath = os.path.join(tmpdir, "emitted.json")

            result = _run_gate(tmpdir, ppath, ["--emit-directive", dpath])
            self.assertEqual(0, result.returncode)

            dg_result = subprocess.run(
                [sys.executable, str(DIRECTIVE_GATE),
                 "--repo", tmpdir, "--directive", dpath, "--dry-run"],
                capture_output=True, text=True,
            )
            self.assertEqual(
                0, dg_result.returncode,
                f"directive gate rejected emitted directive\nstdout: {dg_result.stdout}\nstderr: {dg_result.stderr}",
            )
            self.assertIn("DRY-RUN PASS", dg_result.stdout)


class TestValidationExpectedFilesSubset(unittest.TestCase):
    def test_expected_files_not_subset_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-p1e-test")
            _create_report(tmpdir)
            ppath = _create_packet(tmpdir, {
                "expected_files": [
                    "scripts/platform_run_packet_gate.py",
                    "scripts/test_platform_run_packet_gate.py",
                    "ai-ledger/platform/p1e-test.md",
                    "scripts/extra_unlisted.py",
                ],
            })

            result = _run_gate(tmpdir, ppath)
            self.assertNotEqual(
                0, result.returncode,
                f"expected nonzero exit, got {result.returncode}\nstdout: {result.stdout}",
            )
            self.assertIn("not in 'allowed_files'", result.stdout)

    def test_expected_files_exactly_allowed_files_passes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-p1e-test")
            _create_report(tmpdir)
            allowed = [
                "scripts/a.py",
                "scripts/b.py",
                "ai-ledger/platform/p1e-test.md",
            ]
            ppath = _create_packet(tmpdir, {
                "allowed_files": allowed,
                "expected_files": allowed,
            })

            result = _run_gate(tmpdir, ppath)
            self.assertEqual(
                0, result.returncode,
                f"expected exit 0, got {result.returncode}\nstdout: {result.stdout}",
            )


class TestValidationReportInLists(unittest.TestCase):
    def test_report_missing_from_allowed_files_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-p1e-test")
            _create_report(tmpdir)
            ppath = _create_packet(tmpdir, {
                "allowed_files": [
                    "scripts/platform_run_packet_gate.py",
                ],
            })

            result = _run_gate(tmpdir, ppath)
            self.assertNotEqual(
                0, result.returncode,
                f"expected nonzero exit, got {result.returncode}\nstdout: {result.stdout}",
            )
            self.assertIn("must be in 'allowed_files'", result.stdout)

    def test_report_missing_from_expected_files_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-p1e-test")
            _create_report(tmpdir)
            ppath = _create_packet(tmpdir, {
                "expected_files": [
                    "scripts/platform_run_packet_gate.py",
                ],
            })

            result = _run_gate(tmpdir, ppath)
            self.assertNotEqual(
                0, result.returncode,
                f"expected nonzero exit, got {result.returncode}\nstdout: {result.stdout}",
            )
            self.assertIn("must be in 'expected_files'", result.stdout)

    def test_report_in_both_lists_passes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-p1e-test")
            _create_report(tmpdir)
            ppath = _create_packet(tmpdir, {
                "expected_files": [
                    "ai-ledger/platform/p1e-test.md",
                ],
                "allowed_files": [
                    "ai-ledger/platform/p1e-test.md",
                ],
            })

            result = _run_gate(tmpdir, ppath)
            self.assertEqual(
                0, result.returncode,
                f"expected exit 0, got {result.returncode}\nstdout: {result.stdout}",
            )


class TestValidationForbiddenPaths(unittest.TestCase):
    def test_forbidden_allowed_file_prefix_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-p1e-test")
            _create_report(tmpdir)
            ppath = _create_packet(tmpdir, {
                "allowed_files": [
                    "scripts/platform_run_packet_gate.py",
                    "scripts/test_platform_run_packet_gate.py",
                    "ai-ledger/platform/p1e-test.md",
                    "backend/foo.py",
                ],
            })

            result = _run_gate(tmpdir, ppath)
            self.assertNotEqual(
                0, result.returncode,
                f"expected nonzero exit, got {result.returncode}\nstdout: {result.stdout}",
            )
            self.assertIn("forbidden allowed_file", result.stdout)
            self.assertIn("backend", result.stdout)

    def test_forbidden_allowed_file_fragment_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-p1e-test")
            _create_report(tmpdir)
            ppath = _create_packet(tmpdir, {
                "allowed_files": [
                    "scripts/platform_run_packet_gate.py",
                    "scripts/auth_handler.py",
                    "ai-ledger/platform/p1e-test.md",
                ],
            })

            result = _run_gate(tmpdir, ppath)
            self.assertNotEqual(
                0, result.returncode,
                f"expected nonzero exit, got {result.returncode}\nstdout: {result.stdout}",
            )
            self.assertIn("forbidden allowed_file", result.stdout)
            self.assertIn("auth", result.stdout)

    def test_forbidden_expected_file_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-p1e-test")
            _create_report(tmpdir)
            ppath = _create_packet(tmpdir, {
                "expected_files": [
                    "frontend/app.js",
                    "ai-ledger/platform/p1e-test.md",
                ],
                "allowed_files": [
                    "frontend/app.js",
                    "ai-ledger/platform/p1e-test.md",
                ],
            })

            result = _run_gate(tmpdir, ppath)
            self.assertNotEqual(
                0, result.returncode,
                f"expected nonzero exit, got {result.returncode}\nstdout: {result.stdout}",
            )
            self.assertIn("forbidden expected_file", result.stdout)
            self.assertIn("frontend", result.stdout)


class TestValidationPathSafety(unittest.TestCase):
    def test_absolute_allowed_file_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-p1e-test")
            _create_report(tmpdir)
            ppath = _create_packet(tmpdir, {
                "allowed_files": [
                    "/tmp/foo.py",
                    "scripts/test_platform_run_packet_gate.py",
                    "ai-ledger/platform/p1e-test.md",
                ],
            })

            result = _run_gate(tmpdir, ppath)
            self.assertNotEqual(
                0, result.returncode,
                f"expected nonzero exit, got {result.returncode}\nstdout: {result.stdout}",
            )
            self.assertIn("must be relative", result.stdout)

    def test_windows_drive_allowed_file_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-p1e-test")
            _create_report(tmpdir)
            ppath = _create_packet(tmpdir, {
                "allowed_files": [
                    "C:/tmp/foo.py",
                    "scripts/test_platform_run_packet_gate.py",
                    "ai-ledger/platform/p1e-test.md",
                ],
            })

            result = _run_gate(tmpdir, ppath)
            self.assertNotEqual(
                0, result.returncode,
                f"expected nonzero exit, got {result.returncode}\nstdout: {result.stdout}",
            )
            self.assertIn("must be relative", result.stdout)

    def test_traversal_allowed_file_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-p1e-test")
            _create_report(tmpdir)
            ppath = _create_packet(tmpdir, {
                "allowed_files": [
                    "../scripts/foo.py",
                    "scripts/test_platform_run_packet_gate.py",
                    "ai-ledger/platform/p1e-test.md",
                ],
            })

            result = _run_gate(tmpdir, ppath)
            self.assertNotEqual(
                0, result.returncode,
                f"expected nonzero exit, got {result.returncode}\nstdout: {result.stdout}",
            )
            self.assertIn("unsafe path part", result.stdout)

    def test_absolute_report_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-p1e-test")
            _create_report(tmpdir)
            ppath = _create_packet(tmpdir, {"report": "/tmp/outside.md"})

            result = _run_gate(tmpdir, ppath)
            self.assertNotEqual(
                0, result.returncode,
                f"expected nonzero exit, got {result.returncode}\nstdout: {result.stdout}",
            )
            self.assertIn("must be relative", result.stdout)


class TestValidationPlatformDev(unittest.TestCase):
    def test_platform_dev_without_allow_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "platform-dev")
            _create_report(tmpdir)
            ppath = _create_packet(tmpdir, {
                "branch": "platform-dev",
                "allow_platform_dev": False,
            })

            result = _run_gate(tmpdir, ppath)
            self.assertNotEqual(
                0, result.returncode,
                f"expected nonzero exit, got {result.returncode}\nstdout: {result.stdout}",
            )
            self.assertIn("allow_platform_dev is not true", result.stdout)

    def test_platform_dev_with_allow_passes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "platform-dev")
            _create_report(tmpdir)
            ppath = _create_packet(tmpdir, {
                "branch": "platform-dev",
                "allow_platform_dev": True,
            })

            result = _run_gate(tmpdir, ppath)
            self.assertEqual(
                0, result.returncode,
                f"expected exit 0, got {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}",
            )

    def test_allow_platform_dev_on_non_platform_dev_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-p1e-test")
            _create_report(tmpdir)
            ppath = _create_packet(tmpdir, {"allow_platform_dev": True})

            result = _run_gate(tmpdir, ppath)
            self.assertNotEqual(
                0, result.returncode,
                f"expected nonzero exit, got {result.returncode}\nstdout: {result.stdout}",
            )
            self.assertIn("only valid on platform-dev", result.stdout)


class TestValidationUnknownAgent(unittest.TestCase):
    def test_unknown_agent_fails_by_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-p1e-test")
            _create_report(tmpdir)
            ppath = _create_packet(tmpdir, {"agent": "custom-agent"})

            result = _run_gate(tmpdir, ppath)
            self.assertNotEqual(
                0, result.returncode,
                f"expected nonzero exit, got {result.returncode}\nstdout: {result.stdout}",
            )
            self.assertIn("not a known agent", result.stdout)
            self.assertIn("--allow-unknown-agent", result.stdout)

    def test_unknown_agent_passes_with_flag(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-p1e-test")
            _create_report(tmpdir)
            ppath = _create_packet(tmpdir, {"agent": "custom-agent"})

            result = _run_gate(tmpdir, ppath, ["--allow-unknown-agent"])
            self.assertEqual(
                0, result.returncode,
                f"expected exit 0, got {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}",
            )

    def test_known_agents_all_pass(self):
        for agent in ["opencode", "goose", "codex"]:
            with tempfile.TemporaryDirectory() as tmpdir:
                _init_repo(tmpdir, "codex/platform-p1e-test")
                _create_report(tmpdir)
                ppath = _create_packet(tmpdir, {"agent": agent})

                result = _run_gate(tmpdir, ppath)
                self.assertEqual(
                    0, result.returncode,
                    f"agent '{agent}' should pass, got exit {result.returncode}\nstdout: {result.stdout}",
                )


class TestValidationTests(unittest.TestCase):
    def test_empty_tests_list_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-p1e-test")
            _create_report(tmpdir)
            ppath = _create_packet(tmpdir, {"tests": []})

            result = _run_gate(tmpdir, ppath)
            self.assertNotEqual(
                0, result.returncode,
                f"expected nonzero exit, got {result.returncode}\nstdout: {result.stdout}",
            )
            self.assertIn("non-empty list", result.stdout)

    def test_tests_with_empty_string_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-p1e-test")
            _create_report(tmpdir)
            ppath = _create_packet(tmpdir, {"tests": [""]})

            result = _run_gate(tmpdir, ppath)
            self.assertNotEqual(
                0, result.returncode,
                f"expected nonzero exit, got {result.returncode}\nstdout: {result.stdout}",
            )
            self.assertIn("non-empty string", result.stdout)

    def test_tests_not_a_list_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-p1e-test")
            _create_report(tmpdir)
            ppath = _create_packet(tmpdir, {"tests": "just a string"})

            result = _run_gate(tmpdir, ppath)
            self.assertNotEqual(
                0, result.returncode,
                f"expected nonzero exit, got {result.returncode}\nstdout: {result.stdout}",
            )
            self.assertIn("must be a list", result.stdout)


class TestValidationCommand(unittest.TestCase):
    def test_empty_command_without_gate_only_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-p1e-test")
            _create_report(tmpdir)
            ppath = _create_packet(tmpdir, {"command": [], "gate_only": False})

            result = _run_gate(tmpdir, ppath)
            self.assertNotEqual(
                0, result.returncode,
                f"expected nonzero exit, got {result.returncode}\nstdout: {result.stdout}",
            )
            self.assertIn("command is empty", result.stdout)


class TestValidationNotes(unittest.TestCase):
    def test_notes_must_be_string_or_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-p1e-test")
            _create_report(tmpdir)
            ppath = _create_packet(tmpdir, {"notes": {"bad": "shape"}})

            result = _run_gate(tmpdir, ppath)
            self.assertNotEqual(
                0, result.returncode,
                f"expected nonzero exit, got {result.returncode}\nstdout: {result.stdout}",
            )
            self.assertIn("notes", result.stdout)


class TestValidationMissingRequired(unittest.TestCase):
    def test_missing_required_field_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-p1e-test")
            _create_report(tmpdir)
            ppath = os.path.join(tmpdir, "packet.json")
            with open(ppath, "w") as f:
                json.dump({"phase": "P1-E"}, f)

            result = _run_gate(tmpdir, ppath)
            self.assertNotEqual(
                0, result.returncode,
                f"expected nonzero exit, got {result.returncode}\nstdout: {result.stdout}",
            )
            self.assertIn("missing required packet field", result.stdout)

    def test_all_errors_collected_before_failing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-p1e-test")
            ppath = _create_packet(tmpdir, {
                "report": "bad/report.txt",
                "risk": "INVALID",
                "tests": [],
            })

            result = _run_gate(tmpdir, ppath)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("not under ai-ledger/platform", result.stdout)
            self.assertIn("must be one of", result.stdout)
            self.assertIn("non-empty list", result.stdout)


class TestValidationReportPath(unittest.TestCase):
    def test_report_not_md_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-p1e-test")
            ppath = _create_packet(tmpdir, {"report": "ai-ledger/platform/test.txt"})

            result = _run_gate(tmpdir, ppath)
            self.assertNotEqual(
                0, result.returncode,
                f"expected nonzero exit, got {result.returncode}\nstdout: {result.stdout}",
            )
            self.assertIn("must end in .md", result.stdout)

    def test_report_not_under_ledger_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-p1e-test")
            ppath = _create_packet(tmpdir, {"report": "docs/something.md"})

            result = _run_gate(tmpdir, ppath)
            self.assertNotEqual(
                0, result.returncode,
                f"expected nonzero exit, got {result.returncode}\nstdout: {result.stdout}",
            )
            self.assertIn("not under ai-ledger/platform", result.stdout)


class TestValidationTypes(unittest.TestCase):
    def test_command_not_list_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-p1e-test")
            _create_report(tmpdir)
            ppath = _create_packet(tmpdir, {"command": "not-a-list"})

            result = _run_gate(tmpdir, ppath)
            self.assertNotEqual(
                0, result.returncode,
                f"expected nonzero exit, got {result.returncode}\nstdout: {result.stdout}",
            )
            self.assertIn("must be a list", result.stdout)

    def test_gate_only_not_bool_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-p1e-test")
            _create_report(tmpdir)
            ppath = _create_packet(tmpdir, {"gate_only": "yes"})

            result = _run_gate(tmpdir, ppath)
            self.assertNotEqual(
                0, result.returncode,
                f"expected nonzero exit, got {result.returncode}\nstdout: {result.stdout}",
            )
            self.assertIn("must be a boolean", result.stdout)

    def test_allowed_files_not_list_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-p1e-test")
            _create_report(tmpdir)
            ppath = _create_packet(tmpdir, {"allowed_files": "not-a-list"})

            result = _run_gate(tmpdir, ppath)
            self.assertNotEqual(
                0, result.returncode,
                f"expected nonzero exit, got {result.returncode}\nstdout: {result.stdout}",
            )
            self.assertIn("must be a list", result.stdout)


class TestAgentToolCheck(unittest.TestCase):
    def _create_fake_tool(self, tmpdir, name):
        if sys.platform.startswith("win"):
            ext = ".bat"
            content = f"@echo off\r\necho {name} version 1.0\r\nexit /b 0\r\n"
        else:
            ext = ""
            content = f"#!/bin/sh\necho {name} version 1.0\nexit 0\n"
        path = os.path.join(tmpdir, name + ext)
        with open(path, "w") as f:
            f.write(content)
        if not sys.platform.startswith("win"):
            os.chmod(path, 0o755)
        return path

    def test_agent_tool_check_with_fake_agent_on_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-p1e-test")
            _create_report(tmpdir)
            ppath = _create_packet(tmpdir, {"agent": "fakecoder"})

            self._create_fake_tool(tmpdir, "fakecoder")
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = tmpdir + os.pathsep + old_path
            try:
                result = _run_gate(
                    tmpdir, ppath,
                    ["--agent-tool-check", "--allow-unknown-agent"],
                )
                self.assertEqual(
                    0, result.returncode,
                    f"expected exit 0, got {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}",
                )
                self.assertIn("TOOLCHAIN CHECK", result.stdout)
                self.assertIn("toolchain check for 'fakecoder'", result.stdout)
                self.assertIn("RUN PACKET VERDICT: PASS", result.stdout)
            finally:
                os.environ["PATH"] = old_path

    def test_agent_tool_check_missing_tool_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-p1e-test")
            _create_report(tmpdir)
            ppath = _create_packet(tmpdir, {"agent": "doesnotexist_xyz"})

            result = _run_gate(
                tmpdir, ppath,
                ["--agent-tool-check", "--allow-unknown-agent"],
            )
            self.assertNotEqual(
                0, result.returncode,
                f"expected nonzero exit, got {result.returncode}\nstdout: {result.stdout}",
            )
            self.assertIn("TOOLCHAIN CHECK", result.stdout)
            self.assertIn("FAIL", result.stdout)
            self.assertIn("RUN PACKET VERDICT: FAIL", result.stdout)


class TestPacketNotProvided(unittest.TestCase):
    def test_no_packet_no_template_fails(self):
        result = subprocess.run(
            [sys.executable, str(PACKET_GATE)],
            capture_output=True, text=True,
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("--packet PATH is required", result.stdout)

    def test_bad_json_file_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bpath = os.path.join(tmpdir, "bad.json")
            with open(bpath, "w") as f:
                f.write("not valid json {")
            result = _run_gate(tmpdir, bpath)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("could not load packet", result.stdout)


class TestBranchMismatch(unittest.TestCase):
    def test_branch_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-abc")
            _create_report(tmpdir)
            ppath = _create_packet(tmpdir, {"branch": "codex/platform-xyz"})

            result = _run_gate(tmpdir, ppath)
            self.assertNotEqual(
                0, result.returncode,
                f"expected nonzero exit, got {result.returncode}\nstdout: {result.stdout}",
            )
            self.assertIn("does not match", result.stdout)


if __name__ == "__main__":
    unittest.main()
