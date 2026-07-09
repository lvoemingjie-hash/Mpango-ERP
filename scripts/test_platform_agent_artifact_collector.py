#!/usr/bin/env python3
"""Tests for platform_agent_artifact_collector.py."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
COLLECTOR = SCRIPT_DIR / "platform_agent_artifact_collector.py"


def _run(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def _git(tmpdir, args):
    return _run(["git"] + args, tmpdir)


def _init_repo(tmpdir):
    _git(tmpdir, ["init"])
    _git(tmpdir, ["checkout", "-b", "codex/platform-p1i-test"])
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


def _commit_all(tmpdir, message="fixture"):
    _git(tmpdir, ["add", "-A"])
    _git(
        tmpdir,
        [
            "-c", "user.name=test",
            "-c", "user.email=test@test.com",
            "commit", "-m", message,
        ],
    )


def _collector_cmd(
    tmpdir,
    expected=None,
    output="ai-ledger/platform/p1i-manifest.json",
    extra=None,
):
    cmd = [
        sys.executable, str(COLLECTOR),
        "--repo", tmpdir,
        "--output", output,
        "--phase", "P1-I",
        "--risk", "MEDIUM",
    ]
    for path in expected or []:
        cmd.extend(["--expected-file", path])
    if extra:
        cmd.extend(extra)
    return cmd


def _load_manifest(tmpdir, rel_path="ai-ledger/platform/p1i-manifest.json"):
    return json.loads(Path(tmpdir, rel_path).read_text(encoding="utf-8"))


class TestPassingManifest(unittest.TestCase):
    def test_exact_allowlist_passes_and_writes_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir)
            Path(tmpdir, "scripts").mkdir()
            Path(tmpdir, "scripts/out.txt").write_text("ok\n", encoding="utf-8")

            result = _run(
                _collector_cmd(tmpdir, ["scripts/out.txt"]),
                tmpdir,
            )

            self.assertEqual(
                0, result.returncode,
                f"expected exit 0\nstdout: {result.stdout}\nstderr: {result.stderr}",
            )
            self.assertIn("ARTIFACT VERDICT: PASS", result.stdout)
            manifest = _load_manifest(tmpdir)
            self.assertEqual("PASS", manifest["verdict"])
            self.assertEqual(["scripts/out.txt"], manifest["actual_paths"])
            self.assertEqual(["scripts/out.txt"], manifest["expected_files"])
            self.assertEqual([], manifest["unexpected"])
            self.assertEqual([], manifest["missing"])
            self.assertEqual([], manifest["forbidden"])

    def test_markdown_output_passes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir)
            Path(tmpdir, "scripts").mkdir()
            Path(tmpdir, "scripts/out.txt").write_text("ok\n", encoding="utf-8")

            result = _run(
                _collector_cmd(
                    tmpdir,
                    ["scripts/out.txt"],
                    output="ai-ledger/platform/p1i-manifest.md",
                ),
                tmpdir,
            )

            self.assertEqual(0, result.returncode)
            content = Path(
                tmpdir, "ai-ledger/platform/p1i-manifest.md"
            ).read_text(encoding="utf-8")
            self.assertIn("Artifact Manifest", content)
            self.assertIn("scripts/out.txt", content)
            self.assertIn("PASS", content)


class TestFailures(unittest.TestCase):
    def test_unexpected_file_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir)
            Path(tmpdir, "scripts").mkdir()
            Path(tmpdir, "scripts/out.txt").write_text("ok\n", encoding="utf-8")

            result = _run(_collector_cmd(tmpdir, []), tmpdir)

            self.assertNotEqual(0, result.returncode)
            self.assertIn("Unexpected: scripts/out.txt", result.stdout)
            manifest = _load_manifest(tmpdir)
            self.assertEqual("FAIL", manifest["verdict"])
            self.assertEqual(["scripts/out.txt"], manifest["unexpected"])

    def test_missing_expected_file_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir)

            result = _run(
                _collector_cmd(tmpdir, ["scripts/missing.txt"]),
                tmpdir,
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("Missing: scripts/missing.txt", result.stdout)
            manifest = _load_manifest(tmpdir)
            self.assertEqual(["scripts/missing.txt"], manifest["missing"])

    def test_forbidden_changed_file_fails_even_if_expected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir)
            Path(tmpdir, "backend").mkdir()
            Path(tmpdir, "backend/bad.py").write_text("bad\n", encoding="utf-8")

            result = _run(
                _collector_cmd(tmpdir, ["backend/bad.py"]),
                tmpdir,
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("forbidden expected_file", result.stdout)
            self.assertFalse(
                Path(tmpdir, "ai-ledger/platform/p1i-manifest.json").exists()
            )


class TestExpectedFileList(unittest.TestCase):
    def test_expected_file_list_json_passes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir)
            Path(tmpdir, "expected.json").write_text(
                json.dumps(["scripts/out.txt"]),
                encoding="utf-8",
            )
            _commit_all(tmpdir, "expected list")
            Path(tmpdir, "scripts").mkdir()
            Path(tmpdir, "scripts/out.txt").write_text("ok\n", encoding="utf-8")

            result = _run(
                _collector_cmd(
                    tmpdir,
                    extra=["--expected-file-list", "expected.json"],
                ),
                tmpdir,
            )

            self.assertEqual(
                0, result.returncode,
                f"expected exit 0\nstdout: {result.stdout}\nstderr: {result.stderr}",
            )
            manifest = _load_manifest(tmpdir)
            self.assertEqual(["scripts/out.txt"], manifest["expected_files"])

    def test_expected_file_list_must_be_array(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir)
            Path(tmpdir, "expected.json").write_text(
                json.dumps({"bad": True}),
                encoding="utf-8",
            )

            result = _run(
                _collector_cmd(
                    tmpdir,
                    extra=["--expected-file-list", "expected.json"],
                ),
                tmpdir,
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("must be a JSON array", result.stdout)


class TestPathValidation(unittest.TestCase):
    def test_absolute_output_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir)
            result = _run(
                _collector_cmd(tmpdir, output=str(Path(tmpdir, "outside.json"))),
                tmpdir,
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("must be relative", result.stdout)

    def test_traversal_output_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir)
            result = _run(
                _collector_cmd(tmpdir, output="../outside.json"),
                tmpdir,
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("unsafe path part", result.stdout)

    def test_output_must_be_under_platform_ledger(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir)
            result = _run(
                _collector_cmd(tmpdir, output="docs/out.json"),
                tmpdir,
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("not under ai-ledger/platform", result.stdout)

    def test_output_extension_must_be_json_or_md(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir)
            result = _run(
                _collector_cmd(tmpdir, output="ai-ledger/platform/out.txt"),
                tmpdir,
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("must end in .json or .md", result.stdout)

    def test_expected_traversal_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir)
            result = _run(
                _collector_cmd(tmpdir, expected=["../outside.txt"]),
                tmpdir,
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("unsafe path part", result.stdout)


if __name__ == "__main__":
    unittest.main()
