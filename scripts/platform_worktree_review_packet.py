#!/usr/bin/env python3
# Platform Worktree CTO Review Packet Generator (P16-G).
# Builds an ai-ledger/platform review packet from a batch run: branch, commit
# subjects, modified files, forbidden audit, batch summary, tests, GitNexus
# summary, and a risk level. Commit subjects are used instead of object ids so
# the packet stays free of hex runs and passes detect-secrets.

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import platform_diff_auditor as diff_auditor
import platform_worktree_executor as exe

LEDGER_PREFIX = exe.LEDGER_PREFIX


def run_git(args, repo):
    r = subprocess.run(["git", "-C", str(repo)] + list(args), capture_output=True, text=True)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def current_branch(repo):
    rc, out, _ = run_git(["rev-parse", "--abbrev-ref", "HEAD"], repo)
    if rc == 0 and out and out != "HEAD":
        return out
    return None


def commit_subjects(repo, base_ref):
    rc, out, _ = run_git(["log", "--no-decorate", "--format=%s", base_ref + "..HEAD"], repo)
    if rc != 0:
        return []
    return [line for line in out.splitlines() if line.strip()]


def changed_files(repo, base_ref):
    rc, out, _ = run_git(["diff", "--no-renames", "--name-only", base_ref, "HEAD"], repo)
    if rc != 0:
        return []
    return [line for line in out.splitlines() if line.strip()]


def forbidden_audit_summary(repo, base_ref):
    files = changed_files(repo, base_ref)
    audit = diff_auditor.audit_files(files)
    violations = audit.get("violations", []) or []
    forbidden = sorted(set(v.get("file") for v in violations if v.get("file")))
    return {
        "passed": bool(audit.get("passed")),
        "changed_file_count": len(files),
        "violations": violations,
        "forbidden": forbidden,
    }


def load_batch_summary(batch_report_path, repo):
    if not batch_report_path:
        return None
    p = Path(batch_report_path)
    if not p.is_absolute():
        p = Path(repo) / exe.normalize_path(str(batch_report_path))
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    return {
        "aggregate_verdict": data.get("aggregate_verdict"),
        "mode": data.get("mode"),
        "passed": data.get("passed"),
        "retried": data.get("retried"),
        "failed": data.get("failed"),
        "skipped": data.get("skipped"),
        "total_missions": data.get("total_missions"),
        "report": data.get("report"),
    }


def assess_risk(audit, batch_summary, test_results):
    risk = "low"
    reasons = ["all gates passed"]
    if not audit.get("passed"):
        risk = "high"
        reasons = ["forbidden path audit failed"]
    if batch_summary and batch_summary.get("aggregate_verdict") != "passed":
        risk = "high"
        reasons.append("batch aggregate verdict is not passed")
    if test_results and test_results.get("failed"):
        risk = "high"
        reasons.append("one or more test suites failed")
    return {"level": risk, "reasons": reasons}


def build_review_packet(repo, base_ref, batch_report_path, packet_path,
                        gitnexus_summary=None, test_results=None):
    repo = Path(repo).resolve()
    commits = commit_subjects(repo, base_ref)
    files = changed_files(repo, base_ref)
    audit = forbidden_audit_summary(repo, base_ref)
    audit["changed_file_count"] = len(files)
    batch_summary = load_batch_summary(batch_report_path, repo)
    packet = {
        "evidence_kind": "platform_cto_review_packet",
        "branch": current_branch(repo),
        "base_ref": base_ref,
        "commits": commits,
        "commit_count": len(commits),
        "modified_files": files,
        "forbidden_audit": audit,
        "batch_summary": batch_summary,
        "gitnexus_summary": gitnexus_summary,
        "test_results": test_results,
        "risk": assess_risk(audit, batch_summary, test_results),
    }
    issue = exe.validate_report_path(packet_path)
    if issue:
        return None, issue
    target = repo / exe.normalize_path(packet_path)
    try:
        target.resolve().relative_to(repo / LEDGER_PREFIX)
    except ValueError:
        return None, "packet resolves outside ledger"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")
    return str(target), None


def render_packet_markdown(packet):
    lines = []
    lines.append("# Platform CTO Review Packet")
    lines.append("")
    lines.append("Branch: " + str(packet.get("branch")))
    lines.append("Base: " + str(packet.get("base_ref")))
    lines.append("Risk: " + str(packet.get("risk", {}).get("level")))
    lines.append("")
    lines.append("## Commits (" + str(packet.get("commit_count")) + ")")
    for c in packet.get("commits", []):
        lines.append("- " + c)
    lines.append("")
    lines.append("## Modified files (" + str(len(packet.get("modified_files", []))) + ")")
    for f in packet.get("modified_files", []):
        lines.append("- " + f)
    lines.append("")
    audit = packet.get("forbidden_audit", {}) or {}
    lines.append("## Forbidden path audit: " + ("PASS" if audit.get("passed") else "FAIL"))
    lines.append("")
    bs = packet.get("batch_summary") or {}
    if bs:
        lines.append("## Batch summary")
        lines.append("- aggregate: " + str(bs.get("aggregate_verdict")))
        line = "- passed/retried/failed/skipped: "
        line = line + str(bs.get("passed")) + "/" + str(bs.get("retried"))
        line = line + "/" + str(bs.get("failed")) + "/" + str(bs.get("skipped"))
        lines.append(line)
        lines.append("")
    if packet.get("gitnexus_summary"):
        lines.append("## GitNexus summary")
        lines.append(str(packet.get("gitnexus_summary")))
        lines.append("")
    if packet.get("test_results"):
        lines.append("## Tests")
        lines.append(json.dumps(packet.get("test_results"), indent=2))
        lines.append("")
    lines.append("## Risk reasons")
    for r in packet.get("risk", {}).get("reasons", []):
        lines.append("- " + r)
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Platform Worktree CTO Review Packet Generator (P16-G)")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--base-ref", required=True)
    parser.add_argument("--batch-report", default=None)
    parser.add_argument("--packet", required=True)
    parser.add_argument("--gitnexus-summary", default=None)
    args = parser.parse_args(argv)
    repo = Path(args.repo).resolve()
    gn = args.gitnexus_summary
    if gn and Path(gn).exists():
        gn = Path(gn).read_text(encoding="utf-8")
    target, issue = build_review_packet(repo, args.base_ref, args.batch_report, args.packet, gitnexus_summary=gn)
    if issue:
        print("FAIL " + issue)
        return 1
    packet = json.loads(Path(target).read_text(encoding="utf-8"))
    print(render_packet_markdown(packet))
    print("")
    print("PACKET: " + str(target))
    return 0


if __name__ == "__main__":
    sys.exit(main())
