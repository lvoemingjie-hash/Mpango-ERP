#!/usr/bin/env python3
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import platform_worktree_batch_runner as batch

LONG_RUN = re.compile(r"[0-9A-Fa-f]{40}")
Q = chr(34)


def _env():
    env = dict(os.environ)
    env["GIT_AUTHOR_NAME"] = "t"
    env["GIT_AUTHOR_EMAIL"] = "t@t"
    env["GIT_COMMITTER_NAME"] = "t"
    env["GIT_COMMITTER_EMAIL"] = "t@t"
    return env


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)


def _make_repo(tmp):
    repo = os.path.join(tmp, "repo")
    os.makedirs(os.path.join(repo, "ai-ledger", "platform"))
    with open(os.path.join(repo, "base.txt"), "w", encoding="utf-8") as fh:
        fh.write("base\n")
    subprocess.run(["git", "init", "-q", repo], check=True)
    subprocess.run(["git", "-C", repo, "add", "."], check=True)
    subprocess.run(["git", "-C", repo, "commit", "-q", "-m", "base"], check=True, env=_env())
    return repo


def _success_cmd(rel):
    code = ("import os;os.makedirs(" + Q + "scripts" + Q + ",exist_ok=True);"
            "open(" + Q + "scripts/" + rel + Q + "," + Q + "w" + Q + ").write(" + Q + "ok" + Q + ")")
    return [sys.executable, "-c", code]


def _fail_cmd():
    return [sys.executable, "-c", "import sys;sys.exit(2)"]


def _retry_cmd(repo):
    code = ("import os,sys;m=os.path.join(sys.argv[1]," + Q + "ai-ledger" + Q + ","
            + Q + "platform" + Q + "," + Q + "retry_marker.txt" + Q + ");"
            "os.makedirs(" + Q + "scripts" + Q + ",exist_ok=True);"
            "open(" + Q + "scripts/retry_out.txt" + Q + "," + Q + "w" + Q + ").write(" + Q + "ok" + Q + ");"
            "sys.exit(0) if os.path.exists(m) else (open(m," + Q + "w" + Q + ").close() or sys.exit(2))")
    return [sys.executable, "-c", code, repo]


def _mission(branch, wt, worker, expected, report):
    return {"phase": "P16-H", "branch": branch, "base_ref": "HEAD",
            "worktree_dir": wt, "worker_command": worker,
            "expected_files": expected, "report": report, "timeout_seconds": 60}


def _leftover_worktrees(tmp):
    return [d for d in os.listdir(tmp) if d.startswith("wt-")]


def _delete_branches(repo, branches):
    for b in branches:
        subprocess.run(["git", "-C", repo, "branch", "-D", b], capture_output=True, text=True)


def run_trial(out_dir):
    proofs = {}
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(tmp)
        base = os.path.join(repo, "ai-ledger", "platform")
        _write_json(os.path.join(base, "h_ok.json"), _mission("codex/h-ok", "../wt-h-ok", _success_cmd("ok_out.txt"), ["scripts/ok_out.txt"], "ai-ledger/platform/h_ok_rep.json"))
        _write_json(os.path.join(base, "h_fail.json"), _mission("codex/h-fail", "../wt-h-fail", _fail_cmd(), ["scripts/fail_out.txt"], "ai-ledger/platform/h_fail_rep.json"))
        _write_json(os.path.join(base, "h_retry.json"), _mission("codex/h-retry", "../wt-h-retry", _retry_cmd(repo), ["scripts/retry_out.txt"], "ai-ledger/platform/h_retry_rep.json"))
        manifest = {"phase": "P16-H",
                    "missions": ["ai-ledger/platform/h_ok.json", "ai-ledger/platform/h_fail.json", "ai-ledger/platform/h_retry.json"],
                    "report": "ai-ledger/platform/h_batch.json"}
        agg, payload = batch.run_batch(manifest, repo, execute=True, continue_on_failure=True, max_retries=1)
        proofs["run1_aggregate"] = agg
        proofs["run1_verdicts"] = [m["verdict"] for m in payload["missions"]]
        proofs["run1_attempts"] = [m["attempts"] for m in payload["missions"]]
        proofs["run1_counts"] = {"passed": payload["passed"], "retried": payload["retried"], "failed": payload["failed"], "skipped": payload["skipped"]}
        bad = []
        for m in payload["missions"]:
            rp = m.get("report")
            if rp and os.path.exists(os.path.join(repo, rp)):
                if LONG_RUN.search(open(os.path.join(repo, rp), encoding="utf-8").read()):
                    bad.append(rp)
        proofs["per_mission_reports_have_no_long_run"] = (len(bad) == 0)
        proofs["reports_with_long_run"] = bad
        proofs["worktrees_cleaned_up"] = (len(_leftover_worktrees(tmp)) == 0)
        proofs["leftover_worktrees"] = _leftover_worktrees(tmp)
        _delete_branches(repo, ["codex/h-ok", "codex/h-fail", "codex/h-retry"])
        marker = os.path.join(base, "retry_marker.txt")
        if os.path.exists(marker):
            os.remove(marker)
        called = []
        orig = batch.run_mission
        def fake(mp, r, ex):
            called.append(mp)
            return orig(mp, r, ex)
        batch.run_mission = fake
        try:
            agg2, payload2 = batch.run_batch(manifest, repo, execute=True, continue_on_failure=True, max_retries=1, resume_from="ai-ledger/platform/h_batch.json")
        finally:
            batch.run_mission = orig
        proofs["run2_aggregate"] = agg2
        proofs["run2_mission0_resumed"] = payload2["missions"][0].get("resumed")
        proofs["run2_missions_actually_run"] = called
        ok_path = "ai-ledger/platform/h_ok.json"
        proofs["run2_resume_carried_passed"] = (ok_path not in called)
        os.makedirs(out_dir, exist_ok=True)
        shutil.copyfile(os.path.join(base, "h_batch.json"), os.path.join(out_dir, "2026-06-21_p16h_trial_batch_report.json"))
    _write_json(os.path.join(out_dir, "2026-06-21_p16h_trial_proofs.json"), proofs)
    return proofs


def main(argv=None):
    parser = argparse.ArgumentParser(description="P16-H end to end harness trial")
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args(argv)
    proofs = run_trial(args.out_dir)
    print(json.dumps(proofs, indent=2))
    ok = (proofs["run1_verdicts"] == ["passed", "failed", "retried"]
          and proofs["per_mission_reports_have_no_long_run"]
          and proofs["worktrees_cleaned_up"]
          and proofs["run2_resume_carried_passed"])
    print("TRIAL PASS" if ok else "TRIAL FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
