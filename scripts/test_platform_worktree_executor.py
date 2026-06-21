#!/usr/bin/env python3
"""Tests for platform_worktree_executor.py using unittest and stdlib only."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import platform_worktree_executor as exe

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

VALID_MISSION = {
    "phase": "P16-A",
    "branch": "codex/platform-p16-test",
    "base_ref": "HEAD",
    "worktree_dir": "../wt-test",
    "worker_command": [sys.executable, "--version"],
    "expected_files": ["scripts/foo.py"],
    "report": "ai-ledger/platform/report.json",
    "timeout_seconds": 60,
}


def _write_mission(tmpdir, data, name="mission.json"):
    path = os.path.join(tmpdir, name)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    return path


def _run_cli(mission_path, extra=None, repo=None):
    cmd = [
        sys.executable,
        os.path.join(SCRIPT_DIR, "platform_worktree_executor.py"),
        "--repo", repo or tempfile.gettempdir(),
        "--mission", mission_path,
    ]
    if extra:
        cmd.extend(extra)
    return subprocess.run(cmd, capture_output=True, text=True)


def _make_repo(tmpdir):
    repo = os.path.join(tmpdir, "repo")
    os.makedirs(repo)
    with open(os.path.join(repo, "base.txt"), "w", encoding="utf-8") as fh:
        fh.write("base\n")
    env = dict(os.environ)
    env["GIT_AUTHOR_NAME"] = "t"
    env["GIT_AUTHOR_EMAIL"] = "t@t"
    env["GIT_COMMITTER_NAME"] = "t"
    env["GIT_COMMITTER_EMAIL"] = "t@t"
    subprocess.run(["git", "init", "-q", repo], check=True)
    subprocess.run(["git", "-C", repo, "add", "."], check=True)
    subprocess.run(["git", "-C", repo, "commit", "-q", "-m", "base"], check=True, env=env)
    return repo


class TestMissionParsing(unittest.TestCase):
    def test_parse_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_mission(tmp, VALID_MISSION)
            data, issues = exe.parse_mission(path)
        self.assertEqual(issues, [])
        self.assertEqual(data["phase"], "P16-A")

    def test_parse_malformed_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "bad.json")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("{not json")
            data, issues = exe.parse_mission(path)
        self.assertIsNone(data)
        self.assertTrue(any("malformed" in i for i in issues))

    def test_parse_missing_file(self):
        data, issues = exe.parse_mission("/no/such/file.json")
        self.assertIsNone(data)
        self.assertTrue(len(issues) > 0)


class TestValidateMission(unittest.TestCase):
    def test_valid_passes(self):
        self.assertEqual(exe.validate_mission(VALID_MISSION), [])

    def test_missing_required_key_fails(self):
        for key in exe.REQUIRED_KEYS:
            data = dict(VALID_MISSION)
            del data[key]
            failures = exe.validate_mission(data)
            self.assertTrue(any("missing required key" in f for f in failures))

    def test_bad_phase_fails(self):
        data = dict(VALID_MISSION, phase="Z9-A")
        self.assertTrue(len(exe.validate_mission(data)) > 0)

    def test_report_outside_ledger_fails(self):
        data = dict(VALID_MISSION, report="scripts/x.json")
        self.assertTrue(any("ai-ledger/platform/" in f for f in exe.validate_mission(data)))

    def test_bad_timeout_fails(self):
        data = dict(VALID_MISSION, timeout_seconds=0)
        self.assertTrue(len(exe.validate_mission(data)) > 0)


class TestBuildWorktreeCommand(unittest.TestCase):
    def test_command_shape(self):
        cmd = exe.build_worktree_command(VALID_MISSION)
        self.assertEqual(cmd[0], "git")
        self.assertEqual(cmd[1], "worktree")
        self.assertEqual(cmd[2], "add")
        self.assertIn("-B", cmd)
        self.assertIn(VALID_MISSION["branch"], cmd)
        self.assertIn(VALID_MISSION["worktree_dir"], cmd)
        self.assertIn(VALID_MISSION["base_ref"], cmd)

    def test_command_does_not_execute(self):
        cmd = exe.build_worktree_command(VALID_MISSION)
        self.assertIsInstance(cmd, list)


class TestBuildWorkerCommand(unittest.TestCase):
    def test_worker_verbatim(self):
        cmd = exe.build_worker_command(VALID_MISSION)
        self.assertEqual(cmd, VALID_MISSION["worker_command"])


class TestAuditAgainstExpected(unittest.TestCase):
    def test_only_expected_passes(self):
        result = exe.audit_against_expected(["scripts/foo.py"], ["scripts/foo.py"])
        self.assertTrue(result["passed"])

    def test_unexpected_file_fails(self):
        result = exe.audit_against_expected(
            ["scripts/foo.py", "scripts/other.py"], ["scripts/foo.py"]
        )
        self.assertFalse(result["passed"])
        self.assertIn("scripts/other.py", result["unexpected"])

    def test_forbidden_file_fails(self):
        result = exe.audit_against_expected(["backend/evil.py"], ["backend/evil.py"])
        self.assertFalse(result["passed"])
        self.assertIn("backend/evil.py", result["forbidden"])

    def test_missing_expected_detected(self):
        result = exe.audit_against_expected([], ["scripts/foo.py"])
        self.assertFalse(result["passed"])
        self.assertIn("scripts/foo.py", result["missing"])


class TestForbiddenPathBlocking(unittest.TestCase):
    def test_backend_forbidden(self):
        forb, _ = exe.is_forbidden("backend/app.py")
        self.assertTrue(forb)

    def test_frontend_forbidden(self):
        forb, _ = exe.is_forbidden("frontend/ui.ts")
        self.assertTrue(forb)

    def test_product_dev_recovered_forbidden(self):
        forb, _ = exe.is_forbidden("product-dev-recovered/x.py")
        self.assertTrue(forb)

    def test_auth_keyword_forbidden(self):
        forb, _ = exe.is_forbidden("scripts/auth_helper.py")
        self.assertTrue(forb)

    def test_scripts_allowed(self):
        forb, _ = exe.is_forbidden("scripts/platform_worktree_executor.py")
        self.assertFalse(forb)

    def test_expected_file_validation_rejects_backend(self):
        data = dict(VALID_MISSION, expected_files=["backend/x.py"])
        self.assertTrue(any("forbidden" in f for f in exe.validate_mission(data)))


class TestReportPathEscape(unittest.TestCase):
    def test_report_must_be_under_ledger(self):
        data = dict(VALID_MISSION, report="scripts/out.json")
        self.assertTrue(any("ai-ledger/platform/" in f for f in exe.validate_mission(data)))

    def test_report_traversal_rejected(self):
        issue = exe.validate_report_path("ai-ledger/platform/../out.json")
        self.assertIsNotNone(issue)

    def test_report_absolute_rejected(self):
        issue = exe.validate_report_path("/etc/evil.json")
        self.assertIsNotNone(issue)

    def test_report_non_json_rejected(self):
        issue = exe.validate_report_path("ai-ledger/platform/out.txt")
        self.assertIsNotNone(issue)

    def test_report_valid_ok(self):
        issue = exe.validate_report_path("ai-ledger/platform/out.json")
        self.assertIsNone(issue)


class TestDryRunCLI(unittest.TestCase):
    def test_dry_run_passes_and_prints_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_mission(tmp, VALID_MISSION)
            result = _run_cli(path, repo=tmp)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("DRY-RUN PASS", result.stdout)
        self.assertIn("git worktree add", result.stdout)
        self.assertIn("WORKER COMMAND", result.stdout)

    def test_dry_run_does_not_create_worktree(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_mission(tmp, VALID_MISSION)
            result = _run_cli(path, repo=tmp)
            wt = os.path.normpath(os.path.join(tmp, "..", "wt-test"))
            self.assertFalse(os.path.exists(wt))
        self.assertEqual(result.returncode, 0)

    def test_invalid_mission_cli_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = dict(VALID_MISSION)
            del data["phase"]
            path = _write_mission(tmp, data)
            result = _run_cli(path, repo=tmp)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("VERDICT: FAIL", result.stdout)


class TestReportWriting(unittest.TestCase):
    def test_write_report_creates_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "ai-ledger", "platform"))
            target, issue = exe.write_report(
                "ai-ledger/platform/out.json", {"verdict": "passed"}, tmp
            )
            self.assertIsNone(issue)
            self.assertTrue(target.endswith("out.json"))
            with open(target, "r", encoding="utf-8") as fh:
                loaded = json.load(fh)
        self.assertEqual(loaded["verdict"], "passed")

    def test_write_report_rejects_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            target, issue = exe.write_report("scripts/out.json", {"v": 1}, tmp)
        self.assertIsNotNone(issue)
        self.assertIsNone(target)


class TestExecuteSuccess(unittest.TestCase):
    def test_worker_creates_expected_file_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(tmp)
            worker = os.path.join(tmp, "worker.py")
            with open(worker, "w", encoding="utf-8") as fh:
                fh.write("open(" + chr(34) + "output.txt" + chr(34) + ", " + chr(34) + "w" + chr(34) + ").write(" + chr(34) + "x" + chr(34) + ")" + chr(10))
            mission = dict(VALID_MISSION)
            mission["worker_command"] = [sys.executable, worker]
            mission["expected_files"] = ["output.txt"]
            verdict, payload = exe.execute(mission, repo, write_completion=False)
            self.assertEqual(verdict, "passed", payload)


class TestFailureReporting(unittest.TestCase):
    def test_worker_failure_not_swallowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(tmp)
            mission = dict(VALID_MISSION)
            mission["worker_command"] = [sys.executable, "-c", "raise SystemExit(2)"]
            verdict, payload = exe.execute(mission, repo, write_completion=False)
            self.assertEqual(verdict, "failed")
            self.assertIn("failure", payload["details"])

    def test_worker_failure_writes_failed_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(tmp)
            mission = dict(VALID_MISSION)
            mission["worker_command"] = [sys.executable, "-c", "raise SystemExit(7)"]
            mission["report"] = "ai-ledger/platform/fail.json"
            verdict, payload = exe.execute(mission, repo, write_completion=True)
            self.assertEqual(verdict, "failed")
            with open(os.path.join(repo, mission["report"]), encoding="utf-8") as fh:
                report = json.load(fh)
            self.assertEqual(report["verdict"], "failed")


class TestImmutableBaseShaAudit(unittest.TestCase):
    def setUp(self):
        os.environ["GIT_AUTHOR_NAME"] = "t"
        os.environ["GIT_AUTHOR_EMAIL"] = "t@t"
        os.environ["GIT_COMMITTER_NAME"] = "t"
        os.environ["GIT_COMMITTER_EMAIL"] = "t@t"

    def _write_worker(self, tmp, name, lines):
        worker = os.path.join(tmp, name)
        with open(worker, "w", encoding="utf-8") as fh:
            fh.write(chr(10).join(lines) + chr(10))
        return worker

    def _clean_lines(self, path):
        q = chr(34)
        return [
            "import os, subprocess",
            "os.makedirs(" + q + "scripts" + q + ", exist_ok=True)",
            "open(" + q + path + q + ", " + q + "w" + q + ").write(" + q + "x" + q + ")",
            "subprocess.run([" + q + "git" + q + ", " + q + "add" + q + ", " + q + path + q + "])",
            "subprocess.run([" + q + "git" + q + ", " + q + "commit" + q + ", " + q + "-q" + q + ", " + q + "-m" + q + ", " + q + "w" + q + "])",
        ]

    def test_committed_forbidden_file_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(tmp)
            q = chr(34)
            lines = [
                "import os, subprocess",
                "os.makedirs(" + q + "backend" + q + ", exist_ok=True)",
                "open(" + q + "backend/evil.txt" + q + ", " + q + "w" + q + ").write(" + q + "x" + q + ")",
                "open(" + q + "allowed.txt" + q + ", " + q + "w" + q + ").write(" + q + "x" + q + ")",
                "subprocess.run([" + q + "git" + q + ", " + q + "add" + q + ", " + q + "backend/evil.txt" + q + "])",
                "subprocess.run([" + q + "git" + q + ", " + q + "commit" + q + ", " + q + "-q" + q + ", " + q + "-m" + q + ", " + q + "w" + q + "])",
            ]
            worker = self._write_worker(tmp, "evil.py", lines)
            mission = dict(VALID_MISSION)
            mission["worker_command"] = [sys.executable, worker]
            mission["expected_files"] = ["allowed.txt"]
            verdict, payload = exe.execute(mission, repo, write_completion=False)
            self.assertEqual(verdict, "failed")
            self.assertIn("backend/evil.txt", payload["details"]["audit"]["forbidden"])

    def test_committed_allowlisted_file_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(tmp)
            worker = self._write_worker(tmp, "ok.py", self._clean_lines("scripts/feature.txt"))
            mission = dict(VALID_MISSION)
            mission["worker_command"] = [sys.executable, worker]
            mission["expected_files"] = ["scripts/feature.txt"]
            verdict, payload = exe.execute(mission, repo, write_completion=False)
            self.assertEqual(verdict, "passed", payload)

    def test_unresolved_base_ref_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(tmp)
            mission = dict(VALID_MISSION)
            mission["base_ref"] = "no-such-ref-xyz"
            verdict, payload = exe.execute(mission, repo, write_completion=False)
            self.assertEqual(verdict, "failed")
            self.assertEqual(payload["details"]["failure"], "unresolved base_ref")
            self.assertIsNone(payload["base_sha"])

    def test_report_contains_base_sha(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(tmp)
            worker = self._write_worker(tmp, "ok2.py", self._clean_lines("scripts/feature.txt"))
            mission = dict(VALID_MISSION)
            mission["worker_command"] = [sys.executable, worker]
            mission["expected_files"] = ["scripts/feature.txt"]
            mission["report"] = "ai-ledger/platform/sha.json"
            verdict, payload = exe.execute(mission, repo, write_completion=True)
            self.assertEqual(verdict, "passed", payload)
            self.assertIsNotNone(payload.get("base_sha"))
            self.assertIn("audit_command", payload)
            with open(os.path.join(repo, mission["report"]), encoding="utf-8") as fh:
                report = json.load(fh)
            self.assertIsNotNone(report.get("base_sha"))
            self.assertIn("base_ref", report)


class TestReportShaSanitization(unittest.TestCase):
    def test_shorten_shas_truncates_full_hex(self):
        full = "f98e637f4563b47c0f5f0e01e2322e6cdf8bc4b4"  # pragma: allowlist secret
        out = exe.shorten_shas("base=" + full)
        self.assertNotIn(full, out)
        self.assertIn(full[:12], out)

    def test_shorten_shas_keeps_short_hex(self):
        short = "f98e637f4563"  # pragma: allowlist secret
        self.assertEqual(exe.shorten_shas("v=" + short), "v=" + short)

    def test_written_report_has_no_full_object_sha(self):
        import re as _re
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(tmp)
            worker = os.path.join(tmp, "wk.py")
            with open(worker, "w", encoding="utf-8") as fh:
                fh.write("open(" + chr(34) + "out.txt" + chr(34) + ", " + chr(34) + "w" + chr(34) + ").write(" + chr(34) + "x" + chr(34) + ")")
            mission = dict(VALID_MISSION)
            mission["worker_command"] = [sys.executable, worker]
            mission["expected_files"] = ["out.txt"]
            mission["report"] = "ai-ledger/platform/san_check.json"
            verdict, payload = exe.execute(mission, repo, write_completion=True)
            self.assertEqual(verdict, "passed", payload)
            with open(os.path.join(repo, mission["report"]), encoding="utf-8") as fh:
                text = fh.read()
        self.assertEqual(_re.findall(r"[0-9A-Fa-f]{40}", text), [])
        self.assertIsNotNone(payload.get("base_sha"))
        self.assertTrue(0 < len(payload.get("base_sha")) < 40)

class TestRerunSameBranch(unittest.TestCase):
    def test_rerun_same_branch_resets_and_succeeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(tmp)
            worker = os.path.join(tmp, "w.py")
            with open(worker, "w", encoding="utf-8") as fh:
                fh.write("open(" + chr(34) + "out.txt" + chr(34) + ", " + chr(34) + "w" + chr(34) + ").write(" + chr(34) + "x" + chr(34) + ")")
            mission = dict(VALID_MISSION)
            mission["worker_command"] = [sys.executable, worker]
            mission["expected_files"] = ["out.txt"]
            v1, p1 = exe.execute(mission, repo, write_completion=False)
            v2, p2 = exe.execute(mission, repo, write_completion=False)
        self.assertEqual(v1, "passed", p1)
        self.assertEqual(v2, "passed", p2)

if __name__ == "__main__":
    unittest.main()
