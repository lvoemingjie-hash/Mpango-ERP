#!/usr/bin/env python3
"""Tests for platform_worktree_batch_runner.py using unittest and stdlib only.

Covers the P16-D required matrix:

* valid manifest dry-run passes
* manifest mission outside ai-ledger/platform/ rejected
* traversal mission path rejected
* batch report path escape rejected
* sequential missions run in order
* stop-on-first-failure stops after the first failure
* continue-on-failure runs all but the final verdict still fails
* missing mission file fails
* invalid mission fails
* batch report is written on both failure and success
* unexpected/forbidden mission outputs still fail via the executor
* no runtime/product paths are touched

Execute-mode tests run the real platform_worktree_executor against temporary
git repositories (real worktrees, real workers, real post-run audit).
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import platform_worktree_batch_runner as batch  # noqa: E402
import platform_diff_auditor as diff_auditor  # noqa: E402

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_repo(tmpdir, name="repo"):
    """Create a minimal git repo with one base commit. Returns its path."""
    repo = os.path.join(tmpdir, name)
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
    subprocess.run(
        ["git", "-C", repo, "commit", "-q", "-m", "base"],
        check=True, env=env,
    )
    return repo


def _setup_repo_with_ledger(tmpdir):
    repo = _make_repo(tmpdir)
    os.makedirs(os.path.join(repo, "ai-ledger", "platform"), exist_ok=True)
    return repo


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)


def _mission(branch, worktree_dir, worker_command, expected_files, report,
             phase="P16-D", base_ref="HEAD", timeout=60):
    return {
        "phase": phase,
        "branch": branch,
        "base_ref": base_ref,
        "worktree_dir": worktree_dir,
        "worker_command": worker_command,
        "expected_files": expected_files,
        "report": report,
        "timeout_seconds": timeout,
    }


def _manifest(missions, report, phase="P16-D", notes=None):
    data = {"phase": phase, "missions": list(missions), "report": report}
    if notes is not None:
        data["notes"] = notes
    return data


def _success_worker_cmd(relpath):
    """Worker that creates exactly one allowlisted file (no commit)."""
    dirpart = relpath.rsplit("/", 1)[0] if "/" in relpath else ""
    prefix = (
        "__import__('os').makedirs('%s',exist_ok=True);" % dirpart
        if dirpart else ""
    )
    code = "%sopen('%s','w').write('x')" % (prefix, relpath)
    return [sys.executable, "-c", code]


def _exit_worker_cmd(code=2):
    return [sys.executable, "-c", "import sys;sys.exit(%d)" % code]


def _forbidden_worker_cmd():
    return [
        sys.executable, "-c",
        "__import__('os').makedirs('backend',exist_ok=True);"
        "open('backend/evil.txt','w').write('x')",
    ]


def _repo_changed_files(repo):
    """All changed/untracked files in repo (committed base..HEAD + staged + unstaged + untracked)."""
    files = []
    for args in (
        ["diff", "--no-renames", "--name-only", "HEAD~1", "HEAD"],
        ["diff", "--no-renames", "--name-only", "--cached"],
        ["diff", "--no-renames", "--name-only"],
        ["ls-files", "--others", "--exclude-standard"],
    ):
        r = subprocess.run(["git", "-C", repo] + args,
                           capture_output=True, text=True)
        if r.returncode == 0:
            files.extend(f for f in r.stdout.splitlines() if f.strip())
    seen, unique = set(), []
    for f in files:
        if f not in seen:
            seen.add(f)
            unique.append(f)
    return unique


# ---------------------------------------------------------------------------
# Manifest parsing
# ---------------------------------------------------------------------------

class TestManifestParsing(unittest.TestCase):
    def test_parse_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "m.json")
            _write_json(path, _manifest(["ai-ledger/platform/a.json"],
                                        "ai-ledger/platform/r.json"))
            data, issues = batch.parse_manifest(path)
        self.assertEqual(issues, [])
        self.assertEqual(data["phase"], "P16-D")

    def test_parse_malformed_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "bad.json")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("{not json")
            data, issues = batch.parse_manifest(path)
        self.assertIsNone(data)
        self.assertTrue(any("malformed" in i for i in issues))

    def test_parse_missing_file(self):
        data, issues = batch.parse_manifest("/no/such/manifest.json")
        self.assertIsNone(data)
        self.assertTrue(len(issues) > 0)


# ---------------------------------------------------------------------------
# Manifest validation (path safety is the load-bearing control)
# ---------------------------------------------------------------------------

class TestValidateManifest(unittest.TestCase):
    def test_valid_manifest_passes(self):
        m = _manifest(
            ["ai-ledger/platform/a.json", "ai-ledger/platform/b.json"],
            "ai-ledger/platform/report.json",
        )
        self.assertEqual(batch.validate_manifest(m), [])

    def test_missing_required_key_fails(self):
        for key in batch.REQUIRED_MANIFEST_KEYS:
            m = _manifest(["ai-ledger/platform/a.json"],
                          "ai-ledger/platform/r.json")
            del m[key]
            self.assertTrue(
                any("missing required key" in f for f in batch.validate_manifest(m))
            )

    def test_mission_outside_ledger_rejected(self):
        # "manifest outside ai-ledger/platform rejected": a declared mission
        # path that is not under the ledger must be rejected.
        m = _manifest(["scripts/a.json"], "ai-ledger/platform/r.json")
        failures = batch.validate_manifest(m)
        self.assertTrue(any("ai-ledger/platform/" in f for f in failures))

    def test_traversal_mission_path_rejected(self):
        m = _manifest(["ai-ledger/platform/../evil.json"],
                      "ai-ledger/platform/r.json")
        failures = batch.validate_manifest(m)
        self.assertTrue(any("traversal" in f for f in failures))

    def test_batch_report_escape_rejected(self):
        for bad in ("scripts/r.json", "ai-ledger/platform/../r.json",
                    "/etc/evil.json", "ai-ledger/platform/r.txt"):
            m = _manifest(["ai-ledger/platform/a.json"], bad)
            failures = batch.validate_manifest(m)
            self.assertTrue(failures, f"expected failure for report {bad}")

    def test_duplicate_mission_rejected(self):
        m = _manifest(["ai-ledger/platform/a.json", "ai-ledger/platform/a.json"],
                      "ai-ledger/platform/r.json")
        failures = batch.validate_manifest(m)
        self.assertTrue(any("duplicate" in f for f in failures))

    def test_empty_missions_rejected(self):
        m = _manifest([], "ai-ledger/platform/r.json")
        self.assertTrue(
            any("missions" in f for f in batch.validate_manifest(m))
        )

    def test_bad_phase_rejected(self):
        m = _manifest(["ai-ledger/platform/a.json"],
                      "ai-ledger/platform/r.json", phase="Z9")
        self.assertTrue(len(batch.validate_manifest(m)) > 0)

    def test_unknown_key_rejected(self):
        m = _manifest(["ai-ledger/platform/a.json"],
                      "ai-ledger/platform/r.json")
        m["rogue"] = 1
        self.assertTrue(any("unknown key" in f for f in batch.validate_manifest(m)))

    def test_report_path_helpers(self):
        self.assertIsNone(
            batch.validate_batch_report_path("ai-ledger/platform/r.json")
        )
        self.assertIsNotNone(
            batch.validate_batch_report_path("scripts/r.json")
        )


# ---------------------------------------------------------------------------
# Path-safety primitives
# ---------------------------------------------------------------------------

class TestPathSafety(unittest.TestCase):
    def test_mission_absolute_rejected(self):
        self.assertIsNotNone(
            batch.validate_mission_path("/etc/evil.json")
        )

    def test_mission_non_json_rejected(self):
        self.assertIsNotNone(
            batch.validate_mission_path("ai-ledger/platform/a.txt")
        )

    def test_mission_forbidden_prefix_rejected(self):
        # A mission path under a forbidden prefix is also not under the ledger.
        issue = batch.validate_mission_path("backend/a.json")
        self.assertIsNotNone(issue)

    def test_report_helpers_reject_unsafe(self):
        for bad in ("/x.json", "ai-ledger/platform/../x.json",
                    "ai-ledger/platform/x.txt", "scripts/x.json"):
            self.assertIsNotNone(batch.validate_batch_report_path(bad), bad)


# ---------------------------------------------------------------------------
# Dry-run batch (no worktree, no worker)
# ---------------------------------------------------------------------------

class TestDryRunBatch(unittest.TestCase):
    def _write_mission_file(self, repo, name, **overrides):
        path = os.path.join(repo, "ai-ledger", "platform", name)
        data = _mission(
            branch="codex/wt-%s" % name,
            worktree_dir="../wt-%s" % name,
            worker_command=_success_worker_cmd("scripts/out_%s.txt" % name),
            expected_files=["scripts/out_%s.txt" % name],
            report="ai-ledger/platform/%s_report.json" % name,
        )
        data.update(overrides)
        _write_json(path, data)
        return "ai-ledger/platform/%s" % name

    def test_valid_manifest_dry_run_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _setup_repo_with_ledger(tmp)
            m0 = self._write_mission_file(repo, "a.json")
            m1 = self._write_mission_file(repo, "b.json")
            manifest = _manifest([m0, m1],
                                 "ai-ledger/platform/batch_report.json")
            aggregate, payload = batch.run_batch(manifest, repo, execute=False)
        self.assertEqual(aggregate, "passed")
        self.assertEqual(payload["passed"], 2)
        self.assertEqual(payload["failed"], 0)
        self.assertFalse(payload["stopped_early"])

    def test_dry_run_writes_batch_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _setup_repo_with_ledger(tmp)
            m0 = self._write_mission_file(repo, "a.json")
            manifest = _manifest([m0],
                                 "ai-ledger/platform/batch_report.json")
            batch.run_batch(manifest, repo, execute=False)
            report = os.path.join(repo, "ai-ledger", "platform",
                                  "batch_report.json")
            self.assertTrue(os.path.exists(report))
            with open(report, encoding="utf-8") as fh:
                data = json.load(fh)
        self.assertEqual(data["aggregate_verdict"], "passed")
        self.assertEqual(data["mode"], "dry-run")

    def test_sequential_missions_run_in_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _setup_repo_with_ledger(tmp)
            paths = [self._write_mission_file(repo, "m%d.json" % i)
                     for i in range(3)]
            manifest = _manifest(paths,
                                 "ai-ledger/platform/batch_report.json")
            aggregate, payload = batch.run_batch(manifest, repo, execute=False)
        self.assertEqual(aggregate, "passed")
        orders = [e["mission"] for e in payload["missions"]]
        self.assertEqual(orders, paths)
        self.assertEqual([e["order"] for e in payload["missions"]], [0, 1, 2])

    def test_missing_mission_file_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _setup_repo_with_ledger(tmp)
            manifest = _manifest(
                ["ai-ledger/platform/does_not_exist.json"],
                "ai-ledger/platform/batch_report.json",
            )
            aggregate, payload = batch.run_batch(manifest, repo, execute=False)
        self.assertEqual(aggregate, "failed")
        self.assertEqual(payload["failed"], 1)
        self.assertIsNotNone(payload["missions"][0]["failure"])

    def test_invalid_mission_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _setup_repo_with_ledger(tmp)
            # Valid JSON, but an invalid mission contract (report escapes ledger).
            bad = _mission(
                branch="codex/bad",
                worktree_dir="../wt-bad",
                worker_command=_success_worker_cmd("scripts/x.txt"),
                expected_files=["scripts/x.txt"],
                report="scripts/escape.json",  # outside ledger -> invalid
            )
            _write_json(os.path.join(repo, "ai-ledger", "platform", "bad.json"),
                        bad)
            manifest = _manifest(["ai-ledger/platform/bad.json"],
                                 "ai-ledger/platform/batch_report.json")
            aggregate, payload = batch.run_batch(manifest, repo, execute=False)
        self.assertEqual(aggregate, "failed")
        self.assertEqual(payload["missions"][0]["verdict"], "failed")

    def test_dry_run_report_written_on_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _setup_repo_with_ledger(tmp)
            manifest = _manifest(
                ["ai-ledger/platform/missing.json"],
                "ai-ledger/platform/batch_report.json",
            )
            batch.run_batch(manifest, repo, execute=False)
            report = os.path.join(repo, "ai-ledger", "platform",
                                  "batch_report.json")
            self.assertTrue(os.path.exists(report))
            with open(report, encoding="utf-8") as fh:
                data = json.load(fh)
        self.assertEqual(data["aggregate_verdict"], "failed")


# ---------------------------------------------------------------------------
# Execute batch (real worktrees, real workers, real audit)
# ---------------------------------------------------------------------------

class TestExecuteBatch(unittest.TestCase):
    def _missions_for_execute(self, repo, n_success, fail_indices):
        """Build n_success success missions plus failures at fail_indices.

        Returns (mission_paths, expected_verdicts_in_order).
        """
        paths = []
        verdicts = []
        idx = 0

        def add_success(i):
            name = "exec_ok_%d.json" % i
            data = _mission(
                branch="codex/exec-ok-%d" % i,
                worktree_dir="../wt-exec-ok-%d" % i,
                worker_command=_success_worker_cmd("scripts/exec_ok_%d.txt" % i),
                expected_files=["scripts/exec_ok_%d.txt" % i],
                report="ai-ledger/platform/exec_ok_%d_report.json" % i,
            )
            _write_json(os.path.join(repo, "ai-ledger", "platform", name), data)
            paths.append("ai-ledger/platform/%s" % name)
            verdicts.append("passed")

        def add_failure(i):
            name = "exec_fail_%d.json" % i
            data = _mission(
                branch="codex/exec-fail-%d" % i,
                worktree_dir="../wt-exec-fail-%d" % i,
                worker_command=_exit_worker_cmd(2),
                expected_files=["scripts/exec_fail_%d.txt" % i],
                report="ai-ledger/platform/exec_fail_%d_report.json" % i,
            )
            _write_json(os.path.join(repo, "ai-ledger", "platform", name), data)
            paths.append("ai-ledger/platform/%s" % name)
            verdicts.append("failed")

        for s in range(n_success):
            if s in fail_indices:
                add_failure(s)
            else:
                add_success(s)
            idx += 1
        return paths, verdicts

    def test_sequential_missions_run_in_order_execute(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _setup_repo_with_ledger(tmp)
            paths, _ = self._missions_for_execute(repo, 3, fail_indices=[])
            manifest = _manifest(paths,
                                 "ai-ledger/platform/batch_report.json")
            aggregate, payload = batch.run_batch(manifest, repo, execute=True)
        self.assertEqual(aggregate, "passed")
        self.assertEqual(payload["passed"], 3)
        self.assertEqual([e["mission"] for e in payload["missions"]], paths)
        self.assertEqual([e["order"] for e in payload["missions"]], [0, 1, 2])

    def test_stop_on_first_failure_skips_rest(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _setup_repo_with_ledger(tmp)
            # [ok, FAIL, ok] -> stop after index 1, index 2 skipped.
            paths, _ = self._missions_for_execute(
                repo, 3, fail_indices=[1])
            manifest = _manifest(paths,
                                 "ai-ledger/platform/batch_report.json")
            aggregate, payload = batch.run_batch(
                manifest, repo, execute=True, continue_on_failure=False)
        self.assertEqual(aggregate, "failed")
        self.assertEqual(payload["stopped_early"], True)
        verdicts = [e["verdict"] for e in payload["missions"]]
        self.assertEqual(verdicts, ["passed", "failed", "skipped"])
        self.assertEqual(payload["skipped"], 1)

    def test_continue_on_failure_runs_all_aggregate_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _setup_repo_with_ledger(tmp)
            paths, _ = self._missions_for_execute(
                repo, 3, fail_indices=[1])
            manifest = _manifest(paths,
                                 "ai-ledger/platform/batch_report.json")
            aggregate, payload = batch.run_batch(
                manifest, repo, execute=True, continue_on_failure=True)
        self.assertEqual(aggregate, "failed")
        self.assertEqual(payload["stopped_early"], False)
        verdicts = [e["verdict"] for e in payload["missions"]]
        self.assertEqual(verdicts, ["passed", "failed", "passed"])
        self.assertEqual(payload["skipped"], 0)
        self.assertEqual(payload["passed"], 2)
        self.assertEqual(payload["failed"], 1)

    def test_execute_report_written_on_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _setup_repo_with_ledger(tmp)
            paths, _ = self._missions_for_execute(repo, 1, fail_indices=[])
            manifest = _manifest(paths,
                                 "ai-ledger/platform/batch_report.json")
            batch.run_batch(manifest, repo, execute=True)
            report = os.path.join(repo, "ai-ledger", "platform",
                                  "batch_report.json")
            self.assertTrue(os.path.exists(report))
            with open(report, encoding="utf-8") as fh:
                data = json.load(fh)
        self.assertEqual(data["aggregate_verdict"], "passed")
        self.assertEqual(data["mode"], "execute")
        self.assertEqual(data["missions"][0]["changed_files"], 1)

    def test_execute_report_written_on_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _setup_repo_with_ledger(tmp)
            paths, _ = self._missions_for_execute(repo, 1, fail_indices=[0])
            manifest = _manifest(paths,
                                 "ai-ledger/platform/batch_report.json")
            batch.run_batch(manifest, repo, execute=True)
            report = os.path.join(repo, "ai-ledger", "platform",
                                  "batch_report.json")
            self.assertTrue(os.path.exists(report))
            with open(report, encoding="utf-8") as fh:
                data = json.load(fh)
        self.assertEqual(data["aggregate_verdict"], "failed")
        self.assertEqual(data["missions"][0]["verdict"], "failed")
        self.assertIsNotNone(data["missions"][0]["failure"])

    def test_worker_failure_recorded_not_swallowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _setup_repo_with_ledger(tmp)
            paths, _ = self._missions_for_execute(repo, 1, fail_indices=[0])
            manifest = _manifest(paths,
                                 "ai-ledger/platform/batch_report.json")
            aggregate, payload = batch.run_batch(manifest, repo, execute=True)
        self.assertEqual(aggregate, "failed")
        entry = payload["missions"][0]
        self.assertEqual(entry["verdict"], "failed")
        self.assertIn("worker exited", entry["failure"])

    def test_forbidden_mission_output_fails_via_executor(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _setup_repo_with_ledger(tmp)
            name = "forbidden.json"
            data = _mission(
                branch="codex/exec-forbidden",
                worktree_dir="../wt-forbidden",
                worker_command=_forbidden_worker_cmd(),
                expected_files=["scripts/expected.txt"],
                report="ai-ledger/platform/forbidden_report.json",
            )
            _write_json(os.path.join(repo, "ai-ledger", "platform", name), data)
            manifest = _manifest(["ai-ledger/platform/%s" % name],
                                 "ai-ledger/platform/batch_report.json")
            aggregate, payload = batch.run_batch(manifest, repo, execute=True)
        self.assertEqual(aggregate, "failed")
        self.assertEqual(payload["missions"][0]["verdict"], "failed")
        # The forbidden file must not be treated as success.
        self.assertNotEqual(payload["missions"][0]["verdict"], "passed")

    def test_no_product_paths_touched_after_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _setup_repo_with_ledger(tmp)
            paths, _ = self._missions_for_execute(
                repo, 2, fail_indices=[1])
            manifest = _manifest(paths,
                                 "ai-ledger/platform/batch_report.json")
            batch.run_batch(manifest, repo, execute=True,
                            continue_on_failure=True)
            changed = _repo_changed_files(repo)
        # Every file touched in the repo must be allowed (scripts/ or
        # ai-ledger/platform/) and never forbidden runtime/product paths.
        audit = diff_auditor.audit_files(changed)
        self.assertTrue(
            audit["passed"],
            "forbidden/disallowed paths touched: %s" % audit["violations"],
        )


# ---------------------------------------------------------------------------
# Report path escape (write-side enforcement)
# ---------------------------------------------------------------------------

class TestBatchReportEscape(unittest.TestCase):
    def test_write_rejects_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            target, issue = batch.write_batch_report(
                "scripts/out.json", {"v": 1}, tmp)
        self.assertIsNotNone(issue)
        self.assertIsNone(target)

    def test_write_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "ai-ledger", "platform"))
            target, issue = batch.write_batch_report(
                "ai-ledger/platform/../out.json", {"v": 1}, tmp)
        self.assertIsNotNone(issue)
        self.assertIsNone(target)

    def test_write_creates_valid_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "ai-ledger", "platform"))
            target, issue = batch.write_batch_report(
                "ai-ledger/platform/out.json", {"v": 1}, tmp)
        self.assertIsNone(issue)
        self.assertTrue(target.endswith("out.json"))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

class TestCLI(unittest.TestCase):
    def _run(self, repo, manifest_path, extra=None):
        cmd = [
            sys.executable,
            os.path.join(SCRIPT_DIR, "platform_worktree_batch_runner.py"),
            "--repo", repo,
            "--manifest", manifest_path,
        ]
        if extra:
            cmd.extend(extra)
        return subprocess.run(cmd, capture_output=True, text=True)

    def _write_valid_manifest(self, repo):
        m0 = _mission(
            branch="codex/cli-a", worktree_dir="../wt-cli-a",
            worker_command=_success_worker_cmd("scripts/cli_a.txt"),
            expected_files=["scripts/cli_a.txt"],
            report="ai-ledger/platform/cli_a_report.json",
        )
        _write_json(os.path.join(repo, "ai-ledger", "platform", "a.json"), m0)
        manifest = _manifest(["ai-ledger/platform/a.json"],
                             "ai-ledger/platform/batch_report.json")
        mpath = os.path.join(repo, "manifest.json")
        _write_json(mpath, manifest)
        return mpath

    def test_cli_dry_run_pass_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _setup_repo_with_ledger(tmp)
            mpath = self._write_valid_manifest(repo)
            result = self._run(repo, mpath, extra=["--dry-run"])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("BATCH VERDICT: PASS", result.stdout)

    def test_cli_execute_failure_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _setup_repo_with_ledger(tmp)
            bad = _mission(
                branch="codex/cli-bad", worktree_dir="../wt-cli-bad",
                worker_command=_exit_worker_cmd(3),
                expected_files=["scripts/cli_bad.txt"],
                report="ai-ledger/platform/cli_bad_report.json",
            )
            _write_json(os.path.join(repo, "ai-ledger", "platform", "bad.json"),
                        bad)
            manifest = _manifest(["ai-ledger/platform/bad.json"],
                                 "ai-ledger/platform/batch_report.json")
            mpath = os.path.join(repo, "manifest.json")
            _write_json(mpath, manifest)
            result = self._run(repo, mpath, extra=["--execute"])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("BATCH VERDICT: FAIL", result.stdout)

    def test_cli_invalid_manifest_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _setup_repo_with_ledger(tmp)
            manifest = _manifest(["scripts/outside.json"],
                                 "ai-ledger/platform/r.json")
            mpath = os.path.join(repo, "manifest.json")
            _write_json(mpath, manifest)
            result = self._run(repo, mpath)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("VERDICT: FAIL", result.stdout)

    def test_cli_continue_on_failure_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _setup_repo_with_ledger(tmp)
            ok = _mission(
                branch="codex/cli-ok", worktree_dir="../wt-cli-ok",
                worker_command=_success_worker_cmd("scripts/cli_ok.txt"),
                expected_files=["scripts/cli_ok.txt"],
                report="ai-ledger/platform/cli_ok_report.json",
            )
            bad = _mission(
                branch="codex/cli-bad2", worktree_dir="../wt-cli-bad2",
                worker_command=_exit_worker_cmd(2),
                expected_files=["scripts/cli_bad2.txt"],
                report="ai-ledger/platform/cli_bad2_report.json",
            )
            ok2 = _mission(
                branch="codex/cli-ok2", worktree_dir="../wt-cli-ok2",
                worker_command=_success_worker_cmd("scripts/cli_ok2.txt"),
                expected_files=["scripts/cli_ok2.txt"],
                report="ai-ledger/platform/cli_ok2_report.json",
            )
            _write_json(os.path.join(repo, "ai-ledger", "platform", "ok.json"),
                        ok)
            _write_json(os.path.join(repo, "ai-ledger", "platform", "bad.json"),
                        bad)
            _write_json(os.path.join(repo, "ai-ledger", "platform", "ok2.json"),
                        ok2)
            manifest = _manifest(
                ["ai-ledger/platform/ok.json",
                 "ai-ledger/platform/bad.json",
                 "ai-ledger/platform/ok2.json"],
                "ai-ledger/platform/batch_report.json",
            )
            mpath = os.path.join(repo, "manifest.json")
            _write_json(mpath, manifest)
            result = self._run(repo, mpath,
                               extra=["--execute", "--continue-on-failure"])
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("BATCH VERDICT: FAIL", result.stdout)
            # All three ran (none skipped) under continue-on-failure.
            with open(os.path.join(repo, "ai-ledger", "platform",
                                   "batch_report.json"), encoding="utf-8") as fh:
                data = json.load(fh)
            self.assertEqual(data["stopped_early"], False)
            self.assertEqual(data["skipped"], 0)
            self.assertEqual(data["passed"], 2)
            self.assertEqual(data["failed"], 1)


class TestReportSanitizationBatch(unittest.TestCase):
    def _build(self, repo):
        data = _mission(branch="codex/san-ok", worktree_dir="../wt-san-ok",
                        worker_command=_success_worker_cmd("scripts/san_ok.txt"),
                        expected_files=["scripts/san_ok.txt"],
                        report="ai-ledger/platform/san_ok_report.json")
        _write_json(os.path.join(repo, "ai-ledger", "platform", "ok.json"), data)
        return _manifest(["ai-ledger/platform/ok.json"], "ai-ledger/platform/san_batch.json")

    def test_per_mission_reports_have_no_full_sha(self):
        import re as _re
        with tempfile.TemporaryDirectory() as tmp:
            repo = _setup_repo_with_ledger(tmp)
            manifest = self._build(repo)
            aggregate, payload = batch.run_batch(manifest, repo, execute=True)
            self.assertEqual(aggregate, "passed")
            rep = os.path.join(repo, "ai-ledger", "platform", "san_ok_report.json")
            self.assertTrue(os.path.exists(rep))
            with open(rep, encoding="utf-8") as fh:
                text = fh.read()
            self.assertEqual(_re.findall(r"[0-9A-Fa-f]{40}", text), [])

    def test_remove_reports_drops_per_mission_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _setup_repo_with_ledger(tmp)
            manifest = self._build(repo)
            aggregate, payload = batch.run_batch(manifest, repo, execute=True, keep_reports=False)
            self.assertEqual(aggregate, "passed")
            rep = os.path.join(repo, "ai-ledger", "platform", "san_ok_report.json")
            self.assertFalse(os.path.exists(rep))
            self.assertEqual(payload.get("keep_reports"), False)
            self.assertIn("ai-ledger/platform/san_ok_report.json", payload.get("removed_reports", []))
            batch_rep = os.path.join(repo, "ai-ledger", "platform", "san_batch.json")
            self.assertTrue(os.path.exists(batch_rep))

class TestRetryResumeContract(unittest.TestCase):
    def _stub(self, mp, verdict, failure=None):
        return {"mission": batch.exe.normalize_path(mp), "mode": "execute",
                "verdict": verdict, "report": "ai-ledger/platform/r.json",
                "changed_files": 0 if verdict == "passed" else None,
                "failure": failure, "attempts": 1, "resumed": False}

    def test_statuses_vocabulary(self):
        self.assertEqual(set(batch.STATUSES), {"pending", "passed", "retried", "failed", "skipped"})
        self.assertEqual(set(batch.SUCCESS_STATUSES), {"passed", "retried"})

    def test_retry_eventual_pass_is_retried(self):
        calls = {"n": 0}
        def fake(mp, repo, execute):
            calls["n"] += 1
            return self._stub(mp, "failed" if calls["n"] == 1 else "passed", "boom")
        orig = batch.run_mission
        batch.run_mission = fake
        try:
            res = batch.run_mission_with_retries("ai-ledger/platform/x.json", "/tmp/r", True, 2)
        finally:
            batch.run_mission = orig
        self.assertEqual(res["verdict"], "retried")
        self.assertEqual(res["attempts"], 2)

    def test_retry_exhausts_to_failed(self):
        orig = batch.run_mission
        batch.run_mission = lambda mp, repo, execute: self._stub(mp, "failed", "boom")
        try:
            res = batch.run_mission_with_retries("ai-ledger/platform/x.json", "/tmp/r", True, 1)
        finally:
            batch.run_mission = orig
        self.assertEqual(res["verdict"], "failed")
        self.assertEqual(res["attempts"], 2)

    def test_no_retry_single_attempt(self):
        orig = batch.run_mission
        batch.run_mission = lambda mp, repo, execute: self._stub(mp, "passed")
        try:
            res = batch.run_mission_with_retries("ai-ledger/platform/x.json", "/tmp/r", True, 0)
        finally:
            batch.run_mission = orig
        self.assertEqual(res["verdict"], "passed")
        self.assertEqual(res["attempts"], 1)

    def test_load_resume_state_only_carries_successes(self):
        with tempfile.TemporaryDirectory() as tmp:
            prior = os.path.join(tmp, "prior.json")
            _write_json(prior, {"missions": [
                {"mission": "ai-ledger/platform/a.json", "verdict": "passed"},
                {"mission": "ai-ledger/platform/b.json", "verdict": "retried"},
                {"mission": "ai-ledger/platform/c.json", "verdict": "failed"},
                {"mission": "ai-ledger/platform/d.json", "verdict": "pending"},
                {"mission": "ai-ledger/platform/e.json", "verdict": "skipped"}]})
            done = batch.load_resume_state(prior, tmp)
        self.assertEqual(done, {"ai-ledger/platform/a.json": "passed", "ai-ledger/platform/b.json": "retried"})

    def test_resume_carries_forward_passed_mission(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _setup_repo_with_ledger(tmp)
            for nm in ("p.json", "q.json"):
                stem = nm.replace(".", "")
                data = _mission(branch="codex/res-" + stem, worktree_dir="../wt-res-" + stem,
                                worker_command=_success_worker_cmd("scripts/" + stem + ".txt"),
                                expected_files=["scripts/" + stem + ".txt"],
                                report="ai-ledger/platform/" + stem + "_rep.json")
                _write_json(os.path.join(repo, "ai-ledger", "platform", nm), data)
            manifest = _manifest(["ai-ledger/platform/p.json", "ai-ledger/platform/q.json"],
                                 "ai-ledger/platform/resume_batch.json")
            prior_path = os.path.join(repo, "ai-ledger", "platform", "prior.json")
            _write_json(prior_path, {"missions": [{"mission": "ai-ledger/platform/p.json", "verdict": "passed"}]})
            called = []
            orig = batch.run_mission
            def fake(mp, repo2, execute):
                called.append(mp)
                return orig(mp, repo2, execute)
            batch.run_mission = fake
            try:
                agg, payload = batch.run_batch(manifest, repo, execute=True, resume_from=prior_path)
            finally:
                batch.run_mission = orig
            self.assertEqual(agg, "passed")
            self.assertEqual(called, ["ai-ledger/platform/q.json"])
            self.assertTrue(payload["missions"][0]["resumed"])
            self.assertEqual(payload["missions"][0]["verdict"], "passed")
            self.assertTrue(payload["resumed"])

    def test_aggregate_fails_when_required_mission_fails_after_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _setup_repo_with_ledger(tmp)
            data = _mission(branch="codex/agg-fail", worktree_dir="../wt-agg-fail",
                            worker_command=_exit_worker_cmd(2),
                            expected_files=["scripts/agg_fail.txt"],
                            report="ai-ledger/platform/agg_fail_rep.json")
            _write_json(os.path.join(repo, "ai-ledger", "platform", "agg.json"), data)
            manifest = _manifest(["ai-ledger/platform/agg.json"], "ai-ledger/platform/agg_batch.json")
            agg, payload = batch.run_batch(manifest, repo, execute=True, max_retries=2, continue_on_failure=True)
        self.assertEqual(agg, "failed")
        self.assertEqual(payload["missions"][0]["verdict"], "failed")
        self.assertEqual(payload["missions"][0]["attempts"], 3)
        self.assertEqual(payload["max_retries"], 2)

if __name__ == "__main__":
    unittest.main()
