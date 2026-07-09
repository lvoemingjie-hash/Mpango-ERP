#!/usr/bin/env python3
"""Platform Merge Readiness Reporter - Mpango ERP.

Generates a standard merge readiness report with all required fields.
Uses short SHAs in JSON artifacts to avoid evidence drift and
detect-secrets false positives.
"""

import argparse
import json
import os
import subprocess
import sys


def normalize_path(p):
    return p.replace("\\", "/")


def run_git(cmd, repo_path):
    try:
        result = subprocess.run(
            ["git"] + cmd,
            capture_output=True,
            text=True,
            cwd=str(repo_path),
            timeout=30,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return 1, "", "timeout"
    except FileNotFoundError:
        return 1, "", "git not found"


def detect_merge_commit(repo_path):
    """Return True if HEAD is a merge commit (2+ parents)."""
    rc, out, _ = run_git(["cat-file", "-p", "HEAD"], repo_path)
    if rc != 0:
        return False
    parent_count = 0
    for line in out.splitlines():
        if line.startswith("parent "):
            parent_count += 1
    return parent_count >= 2


def smart_base_ref(repo_path, provided_ref=None):
    """Determine the best base ref for diff comparison.

    If a ref is explicitly provided, use it.
    If HEAD is a merge commit, HEAD~1 is the first parent (pre-merge tip).
    Otherwise try origin/platform-dev, falling back to HEAD~1.
    """
    if provided_ref:
        return provided_ref
    if detect_merge_commit(repo_path):
        return "HEAD~1"
    rc, _, _ = run_git(
        ["rev-parse", "--verify", "origin/platform-dev"], repo_path)
    if rc == 0:
        return "origin/platform-dev"
    return "HEAD~1"


def get_branch(repo_path):
    rc, out, _ = run_git(["rev-parse", "--abbrev-ref", "HEAD"], repo_path)
    return out if rc == 0 else "unknown"


def get_commit_short(repo_path):
    rc, out, _ = run_git(["rev-parse", "--short", "HEAD"], repo_path)
    return out if rc == 0 else "unknown"


def get_commit_full(repo_path):
    rc, out, _ = run_git(["rev-parse", "HEAD"], repo_path)
    return out if rc == 0 else "unknown"


def get_modified_files(repo_path, base_ref=None):
    """Get list of files changed vs base ref."""
    if base_ref is None:
        base_ref = "HEAD~1"
    rc, out, _ = run_git(["diff", "--name-only", base_ref, "HEAD"], repo_path)
    if rc != 0:
        return []
    return [f for f in out.splitlines() if f.strip()]


def run_test_suite(repo_path):
    """Run full platform test suite and return results."""
    scripts_dir = os.path.join(repo_path, "scripts")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "unittest", "discover",
             "-s", scripts_dir, "-p", "test_platform_*.py"],
            capture_output=True,
            text=True,
            cwd=repo_path,
            timeout=300,
        )
        output = result.stderr  # unittest outputs to stderr
        # Parse "Ran X tests" and "OK"/"FAIL"
        tests_run = 0
        status = "UNKNOWN"
        for line in output.splitlines():
            if line.startswith("Ran "):
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        tests_run = int(parts[1])
                    except ValueError:
                        pass
            if line == "OK":
                status = "PASS"
            elif "FAIL" in line:
                status = "FAIL"
        return {
            "total": tests_run,
            "status": status,
            "passed": tests_run if status == "PASS" else "N/A",
        }
    except subprocess.TimeoutExpired:
        return {"total": 0, "status": "TIMEOUT", "passed": 0}
    except Exception as e:
        return {"total": 0, "status": f"ERROR: {e}", "passed": 0}


def audit_forbidden_paths(files):
    """Check file list against forbidden paths."""
    forbidden_prefixes = [
        "backend/", "frontend/", "product-dev-recovered/",
        ".github/", ".claude/", "docs/ai/",
    ]
    forbidden_keywords = [
        "auth", "rbac", "tenancy", "migration", "payment", "session",
    ]
    violations = []
    for f in files:
        normalized = normalize_path(f).lower()
        for prefix in forbidden_prefixes:
            if normalized.startswith(prefix):
                violations.append({"file": f, "reason": f"forbidden prefix '{prefix}'"})
                break
        else:
            parts = normalized.replace("/", " ").replace("-", " ").replace("_", " ").split()
            for part in parts:
                if part in forbidden_keywords:
                    violations.append({"file": f, "reason": f"forbidden keyword '{part}'"})
                    break
    return violations


def assess_risk(files, test_result):
    """Assess overall risk level."""
    if not files:
        return "NONE"
    # Check if any files are scripts (code changes = higher risk)
    has_scripts = any(normalize_path(f).startswith("scripts/") for f in files)
    has_only_ledgers = all(
        normalize_path(f).startswith("ai-ledger/platform/") for f in files
    )

    if test_result.get("status") not in ("PASS", "SKIPPED"):
        return "HIGH"
    if has_scripts and not has_only_ledgers:
        return "MEDIUM"
    if has_only_ledgers:
        return "LOW"
    return "MEDIUM"


def validate_report_path(path):
    """Validate that a report path is safe to write.

    Must be under ai-ledger/platform/ and end with .md.
    No traversal, no absolute paths, no drive letters.
    """
    if not path:
        return False, "report path is empty"
    normalized = normalize_path(path)
    if os.path.isabs(path):
        return False, "absolute paths are rejected"
    if len(path) >= 2 and path[1] == ":":
        return False, "drive-qualified paths are rejected"
    if not normalized.endswith(".md"):
        return False, "report path must end with .md"
    if not normalized.startswith("ai-ledger/platform/"):
        return False, "report path must be under ai-ledger/platform/"
    parts = normalized.split("/")
    for part in parts:
        if part in ("", ".", ".."):
            return False, "path contains empty, '.', or '..' segments"
    forbidden_keywords = ["auth", "rbac", "tenancy", "migration", "payment", "session"]
    for kw in forbidden_keywords:
        if kw in normalized.lower():
            return False, f"report path contains forbidden keyword '{kw}'"
    return True, None


def generate_report(repo_path, base_ref=None, skip_tests=False):
    """Generate a complete merge readiness report."""
    branch = get_branch(repo_path)
    commit_short = get_commit_short(repo_path)
    commit_full = get_commit_full(repo_path)
    merge_context = detect_merge_commit(repo_path)
    resolved_ref = smart_base_ref(repo_path, base_ref)
    files = get_modified_files(repo_path, resolved_ref)
    forbidden = audit_forbidden_paths(files)
    if skip_tests:
        test_result = {"total": 0, "status": "SKIPPED", "passed": 0}
    else:
        test_result = run_test_suite(repo_path)
    risk = assess_risk(files, test_result)

    blockers = []
    if test_result.get("status") not in ("PASS", "SKIPPED"):
        blockers.append("test suite failure")
    if forbidden:
        blockers.append(f"{len(forbidden)} forbidden path violation(s)")

    # Build default report path from branch name
    # Extract date from branch like codex/platform-p7-safety-automation-layer-2026-06-03
    date_part = ""
    if branch.startswith("codex/platform-"):
        import re
        match = re.search(r"(\d{4}-\d{2}-\d{2})$", branch)
        if match:
            date_part = match.group(1)
    report_file = f"ai-ledger/platform/{date_part}_merge_readiness_report.md" if date_part else "ai-ledger/platform/merge_readiness_report.md"

    return {
        "branch": branch,
        "commit": commit_short,
        "commit_full": commit_full,
        "merge_context": merge_context,
        "resolved_base_ref": resolved_ref,
        "modified_files": [normalize_path(f) for f in files],
        "file_count": len(files),
        "tests": test_result,
        "report_path": report_file,
        "risk": risk,
        "forbidden_path_audit": {
            "status": "PASS" if not forbidden else "FAIL",
            "violations": forbidden,
            "files_checked": len(files),
        },
        "gitnexus": {
            "note": "run npx gitnexus analyze separately for index status",
        },
        "blockers": blockers,
    }


def format_human(report):
    lines = ["Platform Merge Readiness Report", "=" * 40]
    lines.append(f"Branch: {report['branch']}")
    lines.append(f"Commit: {report['commit']} ({report['commit_full']})")
    if report.get("merge_context"):
        lines.append("Merge Context: HEAD is a merge commit")
    lines.append(f"Base Ref: {report.get('resolved_base_ref', 'HEAD~1')}")
    lines.append(f"Risk: {report['risk']}")
    lines.append("")

    lines.append(f"Modified files ({report['file_count']}):")
    for f in report["modified_files"]:
        lines.append(f"  {f}")
    lines.append("")

    lines.append(f"Tests: {report['tests']['total']} ({report['tests']['status']})")
    lines.append("")

    audit = report["forbidden_path_audit"]
    lines.append(f"Forbidden path audit: {audit['status']}"
                 f" ({audit['files_checked']} files checked)")
    if audit["violations"]:
        for v in audit["violations"]:
            lines.append(f"  VIOLATION: {v['file']} ({v['reason']})")
    lines.append("")

    if report["blockers"]:
        lines.append(f"Blockers: {', '.join(report['blockers'])}")
    else:
        lines.append("Blockers: none")
    lines.append("")

    lines.append(f"Report path: {report['report_path']}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Mpango ERP Platform Merge Readiness Reporter"
    )
    parser.add_argument(
        "--repo", default=".",
        help="Path to the git repository root (default: current directory)",
    )
    parser.add_argument(
        "--base-ref",
        help="Base ref for comparison (e.g. origin/platform-dev)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output in JSON format",
    )
    parser.add_argument(
        "--skip-tests", action="store_true",
        help="Skip running the full test suite (report only)",
    )
    parser.add_argument(
        "--report",
        help="Write human-readable markdown report to this path (must be under ai-ledger/platform/ and end with .md)",
    )
    args = parser.parse_args()

    repo_path = os.path.abspath(args.repo)
    report = generate_report(repo_path, args.base_ref, skip_tests=args.skip_tests)

    # Override report_path if --report is given
    if args.report:
        valid, reason = validate_report_path(args.report)
        if not valid:
            print(f"ERROR: invalid --report path '{args.report}': {reason}", file=sys.stderr)
            sys.exit(1)
        report["report_path"] = normalize_path(args.report)

    if args.json:
        # JSON output uses short SHAs only
        if "commit_full" in report:
            del report["commit_full"]
        print(json.dumps(report, indent=2))
    else:
        human = format_human(report)
        print(human)

    # Write report file if --report is specified
    if args.report:
        human_output = format_human(report)
        report_abs = os.path.join(repo_path, normalize_path(args.report))
        os.makedirs(os.path.dirname(report_abs), exist_ok=True)
        with open(report_abs, "w", encoding="utf-8") as f:
            f.write(human_output)
            f.write("\n")
        print(f"Report written to: {normalize_path(args.report)}")

    has_blockers = len(report["blockers"]) > 0
    sys.exit(1 if has_blockers else 0)


if __name__ == "__main__":
    main()
