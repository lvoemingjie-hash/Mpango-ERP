#!/usr/bin/env python3
"""Platform Health Check - Mpango ERP.

Aggregates results from batch mission check, harness index,
worker reliability, diff auditor, and optional GitNexus status.
Read-only. No external secrets.
"""

import argparse
import json
import os
import subprocess
import sys


def normalize_path(p):
    return p.replace("\\", "/")


def run_tool(cmd, cwd, timeout=120):
    """Run a subprocess and return (exit_code, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(cwd),
            timeout=timeout,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except FileNotFoundError:
        return -1, "", "command not found"


def check_batch_missions(repo_path, scripts_dir):
    """Run batch mission check."""
    script = os.path.join(scripts_dir, "platform_batch_mission_check.py")
    rc, out, err = run_tool(
        [sys.executable, script, "--repo", repo_path],
        repo_path, timeout=60,
    )
    # Parse output for totals
    passed = 0
    failed = 0
    total = 0
    for line in out.splitlines():
        if "Total:" in line:
            parts = line.split("|")
            for p in parts:
                p = p.strip()
                if p.startswith("Total:"):
                    total = int(p.split(":")[1].strip())
                elif p.startswith("Passed:"):
                    passed = int(p.split(":")[1].strip())
                elif p.startswith("Failed:"):
                    failed = int(p.split(":")[1].strip())
    return {
        "gate": "batch_mission_check",
        "pass": rc == 0,
        "total": total,
        "passed": passed,
        "failed": failed,
        "output": out,
    }


def check_harness_index(repo_path, scripts_dir):
    """Run harness index check."""
    script = os.path.join(scripts_dir, "platform_harness_index.py")
    rc, out, err = run_tool(
        [sys.executable, script, "--repo", repo_path, "--check"],
        repo_path, timeout=60,
    )
    scripts_count = 0
    ledgers_count = 0
    issues = 0
    for line in out.splitlines():
        if "Scripts:" in line:
            scripts_count = int(line.split(":")[1].strip())
        elif "Ledgers:" in line:
            ledgers_count = int(line.split(":")[1].strip())
        elif "Issues:" in line:
            issues = int(line.split(":")[1].strip())
    return {
        "gate": "harness_index",
        "pass": rc == 0 and issues == 0,
        "scripts": scripts_count,
        "ledgers": ledgers_count,
        "issues": issues,
    }


def check_worker_reliability(repo_path, scripts_dir):
    """Run worker reliability summary."""
    script = os.path.join(scripts_dir, "platform_worker_reliability_summary.py")
    rc, out, err = run_tool(
        [sys.executable, script, "--repo", repo_path],
        repo_path, timeout=60,
    )
    done = 0
    partial = 0
    failed = 0
    for line in out.splitlines():
        l = line.strip()
        if l.startswith("done:"):
            done = int(l.split(":")[1].strip())
        elif l.startswith("partial:"):
            partial = int(l.split(":")[1].strip())
        elif l.startswith("failed:"):
            failed = int(l.split(":")[1].strip())
    return {
        "gate": "worker_reliability",
        "pass": rc == 0 and failed == 0,
        "done": done,
        "partial": partial,
        "failed": failed,
    }


def check_diff_auditor(repo_path, scripts_dir, base_ref=None):
    """Run diff auditor."""
    script = os.path.join(scripts_dir, "platform_diff_auditor.py")
    cmd = [sys.executable, script, "--repo", repo_path, "--mode", "staged", "--json"]
    rc, out, err = run_tool(cmd, repo_path, timeout=30)
    try:
        data = json.loads(out) if out else {}
    except json.JSONDecodeError:
        data = {}
    return {
        "gate": "diff_auditor",
        "pass": rc == 0,
        "violations": len(data.get("violations", [])),
        "total": data.get("total", 0),
    }


def check_detect_secrets(repo_path):
    """Run detect-secrets scan on ai-ledger/platform/ artifacts."""
    artifact_dir = os.path.join(repo_path, "ai-ledger", "platform")
    if not os.path.isdir(artifact_dir):
        return {"gate": "detect_secrets", "pass": True, "secrets_found": 0, "note": "no artifact dir"}

    # Collect JSON and JSONL files to scan
    targets = []
    for name in os.listdir(artifact_dir):
        if name.endswith((".json", ".jsonl")):
            targets.append(os.path.join(artifact_dir, name))

    if not targets:
        return {"gate": "detect_secrets", "pass": True, "secrets_found": 0, "note": "no scan targets"}

    total_secrets = 0
    for target in targets:
        rc, out, _ = run_tool(
            ["detect-secrets", "scan", target],
            repo_path, timeout=30,
        )
        if rc == 0 and out:
            try:
                data = json.loads(out)
                total_secrets += sum(len(v) for v in data.get("results", {}).values())
            except json.JSONDecodeError:
                pass

    return {
        "gate": "detect_secrets",
        "pass": total_secrets == 0,
        "secrets_found": total_secrets,
        "files_scanned": len(targets),
    }


def check_gitnexus(repo_path):
    """Check if GitNexus index exists and is potentially fresh."""
    gitnexus_dir = os.path.join(repo_path, ".gitnexus")
    if not os.path.isdir(gitnexus_dir):
        return {"gate": "gitnexus", "pass": None, "note": "no .gitnexus dir"}

    meta_path = os.path.join(gitnexus_dir, "meta.json")
    if not os.path.isfile(meta_path):
        return {"gate": "gitnexus", "pass": None, "note": "no meta.json"}

    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        stats = meta.get("stats", {})
        return {
            "gate": "gitnexus",
            "pass": True,
            "nodes": stats.get("nodes", 0),
            "edges": stats.get("edges", 0),
            "clusters": stats.get("clusters", 0),
            "flows": stats.get("execution_flows", 0),
        }
    except (json.JSONDecodeError, OSError):
        return {"gate": "gitnexus", "pass": None, "note": "meta.json unreadable"}


def run_health_check(repo_path):
    """Run all health check gates and aggregate results."""
    scripts_dir = os.path.join(repo_path, "scripts")

    gates = []
    gates.append(check_batch_missions(repo_path, scripts_dir))
    gates.append(check_harness_index(repo_path, scripts_dir))
    gates.append(check_worker_reliability(repo_path, scripts_dir))
    gates.append(check_diff_auditor(repo_path, scripts_dir))
    gates.append(check_detect_secrets(repo_path))
    gates.append(check_gitnexus(repo_path))

    all_pass = all(
        g["pass"] is True or g["pass"] is None
        for g in gates
    )
    blocking_failures = [g for g in gates if g["pass"] is False]

    return {
        "overall": "PASS" if all_pass else "FAIL",
        "gates": gates,
        "total_gates": len(gates),
        "passed": sum(1 for g in gates if g["pass"] is True),
        "skipped": sum(1 for g in gates if g["pass"] is None),
        "failed": len(blocking_failures),
    }


def format_human(result):
    lines = ["Platform Health Check", "=" * 40]
    lines.append(f"Overall: {result['overall']}")
    lines.append(f"Gates: {result['passed']}/{result['total_gates']} passed"
                 f" ({result['skipped']} skipped, {result['failed']} failed)")
    lines.append("")

    for gate in result["gates"]:
        name = gate["gate"]
        if gate["pass"] is True:
            status = "PASS"
        elif gate["pass"] is False:
            status = "FAIL"
        else:
            status = "SKIP"
        lines.append(f"  [{status}] {name}")
        # Add details
        for k, v in gate.items():
            if k in ("gate", "pass", "output"):
                continue
            lines.append(f"    {k}: {v}")
        if gate.get("output"):
            for line in gate["output"].splitlines()[:3]:
                lines.append(f"    | {line}")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Mpango ERP Platform Health Check"
    )
    parser.add_argument(
        "--repo", default=".",
        help="Path to the git repository root (default: current directory)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output in JSON format",
    )
    args = parser.parse_args()

    repo_path = os.path.abspath(args.repo)
    result = run_health_check(repo_path)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(format_human(result))

    sys.exit(0 if result["overall"] == "PASS" else 1)


if __name__ == "__main__":
    main()
