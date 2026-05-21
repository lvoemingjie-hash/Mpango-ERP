#!/usr/bin/env python3
"""Tests for platform_directive_gate.py using unittest and tempfile only."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
DIRECTIVE_GATE = SCRIPT_DIR / "platform_directive_gate.py"

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


def _create_report(tmpdir, rel_path="ai-ledger/platform/test.md", content=None):
    abs_path = os.path.join(tmpdir, rel_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "w") as f:
        f.write(content or VALID_REPORT_CONTENT)
    return rel_path


def _create_directive(tmpdir, overrides=None):
    directive = {
        "phase": "P1-C",
        "branch": "codex/platform-test",
        "report": "ai-ledger/platform/test.md",
        "risk": "LOW",
        "command": [sys.executable, "-c", "print('runner-ok')"],
        "gate_only": False,
        "allow_platform_dev": False,
    }
    if overrides:
        directive.update(overrides)
    dpath = os.path.join(tmpdir, "directive.json")
    with open(dpath, "w") as f:
        json.dump(directive, f)
    return dpath


def _create_directive_with_bom(tmpdir, overrides=None):
    directive = {
        "phase": "P1-C",
        "branch": "codex/platform-test",
        "report": "ai-ledger/platform/test.md",
        "risk": "LOW",
        "command": [sys.executable, "-c", "print('runner-ok')"],
        "gate_only": False,
        "allow_platform_dev": False,
    }
    if overrides:
        directive.update(overrides)
    dpath = os.path.join(tmpdir, "directive_bom.json")
    with open(dpath, "w", encoding="utf-8-sig") as f:
        json.dump(directive, f)
    return dpath


class TestDirectiveGateDryRun(unittest.TestCase):
    def test_valid_dry_run_on_codex_branch(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-test")
            _create_report(tmpdir)
            dpath = _create_directive(tmpdir)

            result = subprocess.run(
                [sys.executable, str(DIRECTIVE_GATE),
                 "--repo", tmpdir, "--directive", dpath, "--dry-run"],
                capture_output=True, text=True,
            )
            self.assertEqual(
                0, result.returncode,
                f"expected exit 0, got {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}",
            )
            self.assertIn("platform_runner_gate.py", result.stdout)
            self.assertIn("DRY-RUN PASS", result.stdout)

    def test_utf8_bom_directive_passes_dry_run(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-test")
            _create_report(tmpdir)
            dpath = _create_directive_with_bom(tmpdir)

            result = subprocess.run(
                [sys.executable, str(DIRECTIVE_GATE),
                 "--repo", tmpdir, "--directive", dpath, "--dry-run"],
                capture_output=True, text=True,
            )
            self.assertEqual(
                0, result.returncode,
                f"expected exit 0, got {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}",
            )
            self.assertIn("DRY-RUN PASS", result.stdout)

    def test_valid_execution_invokes_runner_gate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-test")
            _create_report(tmpdir)
            dpath = _create_directive(tmpdir)

            result = subprocess.run(
                [sys.executable, str(DIRECTIVE_GATE),
                 "--repo", tmpdir, "--directive", dpath],
                capture_output=True, text=True,
            )
            self.assertEqual(
                0, result.returncode,
                f"expected exit 0, got {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}",
            )
            self.assertIn("PREFLIGHT: PASS", result.stdout)
            self.assertIn("runner-ok", result.stdout)


class TestDirectiveGateValidation(unittest.TestCase):
    def test_branch_mismatch_fails_before_runner(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-abc")
            dpath = _create_directive(tmpdir, {"branch": "codex/platform-xyz"})

            result = subprocess.run(
                [sys.executable, str(DIRECTIVE_GATE),
                 "--repo", tmpdir, "--directive", dpath, "--dry-run"],
                capture_output=True, text=True,
            )
            self.assertNotEqual(
                0, result.returncode,
                f"expected nonzero exit, got {result.returncode}\nstdout: {result.stdout}",
            )
            self.assertIn("does not match", result.stdout)
            self.assertNotIn("platform_runner_gate.py", result.stdout)

    def test_missing_required_field_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-test")
            dpath = _create_directive(tmpdir, {"phase": None})
            with open(dpath, "w") as f:
                json.dump({"branch": "codex/platform-test"}, f)

            result = subprocess.run(
                [sys.executable, str(DIRECTIVE_GATE),
                 "--repo", tmpdir, "--directive", dpath, "--dry-run"],
                capture_output=True, text=True,
            )
            self.assertNotEqual(
                0, result.returncode,
                f"expected nonzero exit, got {result.returncode}\nstdout: {result.stdout}",
            )
            self.assertIn("missing required field", result.stdout)

    def test_report_outside_ledger_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-test")
            dpath = _create_directive(tmpdir, {"report": "docs/something.md"})

            result = subprocess.run(
                [sys.executable, str(DIRECTIVE_GATE),
                 "--repo", tmpdir, "--directive", dpath, "--dry-run"],
                capture_output=True, text=True,
            )
            self.assertNotEqual(
                0, result.returncode,
                f"expected nonzero exit, got {result.returncode}\nstdout: {result.stdout}",
            )
            self.assertIn("not under ai-ledger/platform", result.stdout)
            self.assertNotIn("platform_runner_gate.py", result.stdout)

    def test_report_path_traversal_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-test")
            dpath = _create_directive(
                tmpdir,
                {"report": "ai-ledger/platform/../test.md"},
            )

            result = subprocess.run(
                [sys.executable, str(DIRECTIVE_GATE),
                 "--repo", tmpdir, "--directive", dpath, "--dry-run"],
                capture_output=True, text=True,
            )
            self.assertNotEqual(
                0, result.returncode,
                f"expected nonzero exit, got {result.returncode}\nstdout: {result.stdout}",
            )
            self.assertIn("unsafe path part", result.stdout)
            self.assertNotIn("platform_runner_gate.py", result.stdout)

    def test_command_elements_must_be_strings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-test")
            dpath = _create_directive(tmpdir, {"command": [sys.executable, 7]})

            result = subprocess.run(
                [sys.executable, str(DIRECTIVE_GATE),
                 "--repo", tmpdir, "--directive", dpath, "--dry-run"],
                capture_output=True, text=True,
            )
            self.assertNotEqual(
                0, result.returncode,
                f"expected nonzero exit, got {result.returncode}\nstdout: {result.stdout}",
            )
            self.assertIn("non-empty strings", result.stdout)

    def test_forbidden_expected_files_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-test")
            dpath = _create_directive(
                tmpdir,
                {"expected_files": ["backend/foo.py"]},
            )

            result = subprocess.run(
                [sys.executable, str(DIRECTIVE_GATE),
                 "--repo", tmpdir, "--directive", dpath, "--dry-run"],
                capture_output=True, text=True,
            )
            self.assertNotEqual(
                0, result.returncode,
                f"expected nonzero exit, got {result.returncode}\nstdout: {result.stdout}",
            )
            self.assertIn("forbidden", result.stdout)
            self.assertIn("backend", result.stdout)
            self.assertNotIn("platform_runner_gate.py", result.stdout)


class TestExpectedFilesPathSafety(unittest.TestCase):
    def test_expected_file_dotdot_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-test")
            dpath = _create_directive(
                tmpdir,
                {"expected_files": ["../scripts/platform.py"]},
            )

            result = subprocess.run(
                [sys.executable, str(DIRECTIVE_GATE),
                 "--repo", tmpdir, "--directive", dpath, "--dry-run"],
                capture_output=True, text=True,
            )
            self.assertNotEqual(
                0, result.returncode,
                f"expected nonzero exit, got {result.returncode}\nstdout: {result.stdout}",
            )
            self.assertIn("unsafe path part", result.stdout)

    def test_expected_file_posix_absolute_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-test")
            dpath = _create_directive(
                tmpdir,
                {"expected_files": ["/tmp/foo.py"]},
            )

            result = subprocess.run(
                [sys.executable, str(DIRECTIVE_GATE),
                 "--repo", tmpdir, "--directive", dpath, "--dry-run"],
                capture_output=True, text=True,
            )
            self.assertNotEqual(
                0, result.returncode,
                f"expected nonzero exit, got {result.returncode}\nstdout: {result.stdout}",
            )
            self.assertIn("must be relative", result.stdout)

    def test_expected_file_windows_drive_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-test")
            dpath = _create_directive(
                tmpdir,
                {"expected_files": ["C:/tmp/foo.py"]},
            )

            result = subprocess.run(
                [sys.executable, str(DIRECTIVE_GATE),
                 "--repo", tmpdir, "--directive", dpath, "--dry-run"],
                capture_output=True, text=True,
            )
            self.assertNotEqual(
                0, result.returncode,
                f"expected nonzero exit, got {result.returncode}\nstdout: {result.stdout}",
            )
            self.assertIn("must be relative", result.stdout)

    def test_expected_file_traversal_docs_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-test")
            dpath = _create_directive(
                tmpdir,
                {"expected_files": ["docs/ai/../ai/PROJECT.md"]},
            )

            result = subprocess.run(
                [sys.executable, str(DIRECTIVE_GATE),
                 "--repo", tmpdir, "--directive", dpath, "--dry-run"],
                capture_output=True, text=True,
            )
            self.assertNotEqual(
                0, result.returncode,
                f"expected nonzero exit, got {result.returncode}\nstdout: {result.stdout}",
            )
            self.assertIn("unsafe path part", result.stdout)

    def test_legal_expected_files_scripts_pass(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-test")
            _create_report(tmpdir)
            dpath = _create_directive(
                tmpdir,
                {"expected_files": [
                    "scripts/platform_directive_gate.py",
                    "ai-ledger/platform/test.md",
                ]},
            )

            result = subprocess.run(
                [sys.executable, str(DIRECTIVE_GATE),
                 "--repo", tmpdir, "--directive", dpath, "--dry-run"],
                capture_output=True, text=True,
            )
            self.assertEqual(
                0, result.returncode,
                f"expected exit 0, got {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}",
            )
            self.assertIn("DRY-RUN PASS", result.stdout)


class TestDirectiveGatePlatformDev(unittest.TestCase):
    def test_platform_dev_no_allow_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "platform-dev")
            _create_report(tmpdir)
            dpath = _create_directive(
                tmpdir,
                {"branch": "platform-dev", "allow_platform_dev": False},
            )

            result = subprocess.run(
                [sys.executable, str(DIRECTIVE_GATE),
                 "--repo", tmpdir, "--directive", dpath, "--dry-run"],
                capture_output=True, text=True,
            )
            self.assertNotEqual(
                0, result.returncode,
                f"expected nonzero exit, got {result.returncode}\nstdout: {result.stdout}",
            )
            self.assertIn("allow_platform_dev is not true", result.stdout)

    def test_allow_platform_dev_on_codex_branch_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "codex/platform-test")
            _create_report(tmpdir)
            dpath = _create_directive(tmpdir, {"allow_platform_dev": True})

            result = subprocess.run(
                [sys.executable, str(DIRECTIVE_GATE),
                 "--repo", tmpdir, "--directive", dpath, "--dry-run"],
                capture_output=True, text=True,
            )
            self.assertNotEqual(
                0, result.returncode,
                f"expected nonzero exit, got {result.returncode}\nstdout: {result.stdout}",
            )
            self.assertIn("only valid on platform-dev", result.stdout)

    def test_platform_dev_with_allow_passes_dry_run(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir, "platform-dev")
            _create_report(tmpdir)
            dpath = _create_directive(
                tmpdir,
                {"branch": "platform-dev", "allow_platform_dev": True},
            )

            result = subprocess.run(
                [sys.executable, str(DIRECTIVE_GATE),
                 "--repo", tmpdir, "--directive", dpath, "--dry-run"],
                capture_output=True, text=True,
            )
            self.assertEqual(
                0, result.returncode,
                f"expected exit 0, got {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}",
            )
            self.assertIn("DRY-RUN PASS", result.stdout)
            self.assertIn("platform_runner_gate.py", result.stdout)
            self.assertIn("--allow-platform-dev", result.stdout)


if __name__ == "__main__":
    unittest.main()
