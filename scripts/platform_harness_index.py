#!/usr/bin/env python3
"""Platform Harness Index Generator - Mpango ERP.

Scans the platform harness scripts and ledgers, then generates
a markdown index of all harness assets.
"""

import argparse
import os
import subprocess
import sys


FORBIDDEN_PREFIXES = [
    "backend/",
    "frontend/",
    ".github/",
    ".claude/",
]

FORBIDDEN_SPECIFIC = [
    "docs/ai/PHASE4_FRONTEND_CONTRACT.md",
]

FORBIDDEN_FRAGMENTS = [
    "auth", "rbac", "tenancy", "session", "migration", "payment",
]

ALLOWED_OUTPUT_PREFIX = "ai-ledger/platform/"

REPORT_FIELDS = [
    "branch", "commit", "modified files", "tests", "report path", "risk",
]


def normalize_path(p):
    return p.replace("\\", "/")


def validate_output_path(output):
    normalized = normalize_path(output)

    if len(output) >= 2 and output[1] == ":":
        return False, "drive-qualified paths are rejected"

    if os.path.isabs(output):
        return False, "absolute paths are rejected"

    if not normalized.startswith(ALLOWED_OUTPUT_PREFIX):
        return False, f"output must be under '{ALLOWED_OUTPUT_PREFIX}'"

    if not normalized.endswith(".md"):
        return False, "output must end with '.md'"

    parts = normalized.split("/")
    for part in parts:
        if part == "" or part == "." or part == "..":
            return False, "path contains empty, '.', or '..' segments"

    for fragment in FORBIDDEN_FRAGMENTS:
        if fragment in normalized.lower():
            return False, f"output contains forbidden fragment '{fragment}'"

    for prefix in FORBIDDEN_PREFIXES:
        if normalized.startswith(prefix):
            return False, f"output matches forbidden prefix '{prefix}'"

    for specific in FORBIDDEN_SPECIFIC:
        if normalized == specific:
            return False, f"output matches forbidden specific path '{specific}'"

    return True, None


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


def get_current_branch(repo_path):
    rc, out, _ = run_git(["rev-parse", "--abbrev-ref", "HEAD"], repo_path)
    return out if rc == 0 else "unknown"


def get_current_commit(repo_path):
    rc, out, _ = run_git(["rev-parse", "--short", "HEAD"], repo_path)
    return out if rc == 0 else "unknown"


def scan_harness_scripts(scripts_dir):
    scripts = []
    if not os.path.isdir(scripts_dir):
        return scripts
    for name in sorted(os.listdir(scripts_dir)):
        if name.startswith("platform_") and name.endswith(".py"):
            script_path = normalize_path(os.path.join("scripts", name))
            test_name = "test_" + name
            test_path = normalize_path(os.path.join("scripts", test_name))
            if os.path.isfile(os.path.join(scripts_dir, test_name)):
                scripts.append((script_path, test_path))
            else:
                scripts.append((script_path, "MISSING"))
    return scripts


def scan_platform_ledgers(ledger_dir):
    ledgers = []
    if not os.path.isdir(ledger_dir):
        return ledgers
    for name in sorted(os.listdir(ledger_dir)):
        if name.endswith(".md") and name != ".gitkeep":
            ledgers.append(normalize_path(os.path.join("ai-ledger", "platform", name)))
    return ledgers


def generate_index(branch, commit, output_path, scripts, ledgers):
    lines = []
    lines.append("# Platform Harness Index")
    lines.append("")
    lines.append(f"- **Branch:** {branch}")
    lines.append(f"- **Commit:** {commit}")
    lines.append(f"- **Generated output path:** {output_path}")
    lines.append("")

    lines.append("## Harness Scripts")
    lines.append("")
    lines.append("| # | Script | Test |")
    lines.append("|---|--------|------|")
    for i, (script, test) in enumerate(scripts, 1):
        lines.append(f"| {i} | `{script}` | `{test}` |")
    lines.append("")

    lines.append("## Platform Ledgers")
    lines.append("")
    for ledger in ledgers:
        lines.append(f"- `{ledger}`")
    if not ledgers:
        lines.append("- (none)")
    lines.append("")

    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Harness scripts:** {len(scripts)}")
    lines.append(f"- **Ledgers:** {len(ledgers)}")
    missing = sum(1 for _, t in scripts if t == "MISSING")
    lines.append(f"- **Missing tests:** {missing}")
    lines.append("")

    lines.append("## Report Fields")
    lines.append("")
    lines.append(f"- **Branch:** {branch}")
    lines.append(f"- **Commit:** {commit}")
    lines.append(f"- **Modified files:** scripts/platform_harness_index.py, scripts/test_platform_harness_index.py, ai-ledger/platform/2026-05-28_p3a_platform_harness_index.md")
    lines.append(f"- **Tests:** {len(scripts) - missing} / {len(scripts)} paired")
    lines.append(f"- **Report path:** {output_path}")
    lines.append(f"- **Risk:** MEDIUM")
    lines.append("")

    return "\n".join(lines)


def check_consistency(repo_root):
    """Check harness index consistency. Returns list of issues."""
    scripts_dir = os.path.join(repo_root, "scripts")
    ledger_dir = os.path.join(repo_root, "ai-ledger", "platform")
    issues = []

    scripts = scan_harness_scripts(scripts_dir)
    ledgers = scan_platform_ledgers(ledger_dir)

    for script_path, test_path in scripts:
        script_abs = os.path.join(repo_root, normalize_path(script_path))
        if not os.path.isfile(script_abs):
            issues.append({"type": "missing_script", "path": script_path})

        if test_path == "MISSING":
            issues.append({"type": "missing_test", "script": script_path})
        else:
            test_abs = os.path.join(repo_root, normalize_path(test_path))
            if not os.path.isfile(test_abs):
                issues.append({"type": "missing_test", "path": test_path})

    for ledger_path in ledgers:
        ledger_abs = os.path.join(repo_root, normalize_path(ledger_path))
        if not os.path.isfile(ledger_abs):
            issues.append({"type": "missing_ledger", "path": ledger_path})

    return issues, scripts, ledgers


def format_check_human(issues, scripts, ledgers):
    if not issues:
        lines = ["Harness index consistency: PASS"]
        lines.append(f"  Scripts: {len(scripts)}")
        lines.append(f"  Ledgers: {len(ledgers)}")
        lines.append(f"  Issues:  0")
        return "\n".join(lines)

    lines = [f"Harness index consistency: FAIL ({len(issues)} issue(s))"]
    for issue in issues:
        detail = issue.get("path") or issue.get("script") or ""
        lines.append(f"  [{issue['type']}] {detail}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Mpango ERP Platform Harness Index Generator"
    )
    parser.add_argument(
        "--repo",
        default=".",
        help="Path to the git repository root (default: current directory)",
    )
    parser.add_argument(
        "--output",
        required=False,
        help="Output path for the generated index (must be under ai-ledger/platform/)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check consistency only; do not write files",
    )
    args = parser.parse_args()

    repo_path = os.path.abspath(args.repo)

    if args.check:
        issues, scripts, ledgers = check_consistency(repo_path)
        if hasattr(args, 'json') and args.json:
            print(json.dumps({"issues": issues, "count": len(issues)}, indent=2))
        else:
            print(format_check_human(issues, scripts, ledgers))
        sys.exit(0 if not issues else 1)

    if not args.output:
        print("Error: --output is required when not using --check", file=sys.stderr)
        sys.exit(1)

    valid, reason = validate_output_path(args.output)
    if not valid:
        print(f"ERROR: invalid output path '{args.output}': {reason}")
        sys.exit(1)

    scripts_dir = os.path.join(repo_path, "scripts")
    ledger_dir = os.path.join(repo_path, "ai-ledger", "platform")

    branch = get_current_branch(repo_path)
    commit = get_current_commit(repo_path)

    scripts = scan_harness_scripts(scripts_dir)
    ledgers = scan_platform_ledgers(ledger_dir)

    index_content = generate_index(branch, commit, args.output, scripts, ledgers)

    output_abs = os.path.join(repo_path, normalize_path(args.output))
    os.makedirs(os.path.dirname(output_abs), exist_ok=True)

    with open(output_abs, "w", encoding="utf-8") as f:
        f.write(index_content)

    print(f"Wrote harness index to {output_abs}")
    print(f"  Branch:  {branch}")
    print(f"  Commit:  {commit}")
    print(f"  Scripts: {len(scripts)} ({sum(1 for _, t in scripts if t == 'MISSING')} missing tests)")
    print(f"  Ledgers: {len(ledgers)}")


if __name__ == "__main__":
    main()
