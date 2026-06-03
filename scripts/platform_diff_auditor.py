#!/usr/bin/env python3
"""Platform Diff Auditor - Mpango ERP.

Checks changed files against allowed and forbidden path lists.
Supports compare, staged, unstaged, and untracked modes.
"""

import argparse
import json
import os
import subprocess
import sys


FORBIDDEN_PREFIXES = [
    "backend/",
    "frontend/",
    "product-dev-recovered/",
    ".github/",
    ".claude/",
    "docs/ai/",
]

FORBIDDEN_KEYWORDS = [
    "auth", "rbac", "tenancy", "migration", "payment", "session",
]

DEFAULT_ALLOWED_PREFIXES = [
    "scripts/",
    "ai-ledger/platform/",
]


def normalize_path(p):
    return p.replace("\\", "/")


def is_forbidden(file_path):
    """Check if a file path is forbidden by prefix or keyword.

    Returns (is_forbidden: bool, reason: str or None).
    """
    normalized = normalize_path(file_path).lower()
    for prefix in FORBIDDEN_PREFIXES:
        if normalized.startswith(prefix):
            return True, f"forbidden prefix '{prefix}'"
    for keyword in FORBIDDEN_KEYWORDS:
        # Check keyword as a path segment or in filename
        parts = normalized.replace("/", " ").replace("-", " ").replace("_", " ").split()
        for part in parts:
            if part == keyword:
                return True, f"forbidden keyword '{keyword}'"
    return False, None


def is_allowed(file_path, allowed_prefixes=None):
    """Check if a file path starts with one of the allowed prefixes."""
    if allowed_prefixes is None:
        allowed_prefixes = DEFAULT_ALLOWED_PREFIXES
    normalized = normalize_path(file_path)
    for prefix in allowed_prefixes:
        if normalized.startswith(prefix):
            return True
    return False


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


def get_changed_files_compare(repo_path, base_ref):
    """Get files changed between base_ref and HEAD."""
    rc, out, _ = run_git(["diff", "--name-only", base_ref, "HEAD"], repo_path)
    if rc != 0:
        return []
    return [f for f in out.splitlines() if f.strip()]


def get_staged_files(repo_path):
    """Get staged (cached) files."""
    rc, out, _ = run_git(["diff", "--cached", "--name-only"], repo_path)
    if rc != 0:
        return []
    return [f for f in out.splitlines() if f.strip()]


def get_unstaged_files(repo_path):
    """Get unstaged modified files."""
    rc, out, _ = run_git(["diff", "--name-only"], repo_path)
    if rc != 0:
        return []
    return [f for f in out.splitlines() if f.strip()]


def get_untracked_files(repo_path):
    """Get untracked files."""
    rc, out, _ = run_git(
        ["ls-files", "--others", "--exclude-standard"], repo_path
    )
    if rc != 0:
        return []
    return [f for f in out.splitlines() if f.strip()]


def audit_files(files):
    """Audit a list of file paths against forbidden and allowlist rules.

    A file passes only if it is NOT forbidden AND IS within an allowed prefix.
    Files outside allowed prefixes are blocking disallowed files.

    Returns dict with: passed, violations, allowed, disallowed.
    """
    violations = []
    allowed = []
    disallowed = []

    for f in files:
        forbidden, reason = is_forbidden(f)
        if forbidden:
            violations.append({"file": f, "reason": reason})
            disallowed.append(f)
        elif is_allowed(f):
            allowed.append(f)
        else:
            disallowed.append(f)
            violations.append({"file": f, "reason": "outside allowed prefixes"})

    return {
        "passed": len(violations) == 0,
        "violations": violations,
        "allowed": allowed,
        "disallowed": disallowed,
        "total": len(files),
    }


def format_human(result, source):
    lines = [f"Platform Diff Auditor ({source})"]
    lines.append(f"Files checked: {result['total']}")
    lines.append(f"Allowed: {len(result['allowed'])}")
    lines.append(f"Disallowed: {len(result['disallowed'])}")

    if result["violations"]:
        lines.append(f"Violations: {len(result['violations'])}")
        for v in result["violations"]:
            lines.append(f"  BLOCKED: {v['file']} ({v['reason']})")
        lines.append("")
        lines.append("VERDICT: FAIL")
    else:
        lines.append("Violations: 0")
        lines.append("")
        lines.append("VERDICT: PASS")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Mpango ERP Platform Diff Auditor"
    )
    parser.add_argument(
        "--repo", default=".",
        help="Path to the git repository root (default: current directory)",
    )
    parser.add_argument(
        "--base-ref",
        help="Base ref for compare mode (e.g. origin/platform-dev)",
    )
    parser.add_argument(
        "--mode",
        choices=["compare", "staged", "unstaged", "untracked", "all"],
        default="compare",
        help="Source of file list (default: compare)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output in JSON format",
    )
    args = parser.parse_args()

    repo_path = os.path.abspath(args.repo)

    files = []
    source = args.mode

    if args.mode == "compare":
        base_ref = args.base_ref or "HEAD~1"
        files = get_changed_files_compare(repo_path, base_ref)
        source = f"compare ({base_ref}..HEAD)"
    elif args.mode == "staged":
        files = get_staged_files(repo_path)
    elif args.mode == "unstaged":
        files = get_unstaged_files(repo_path)
    elif args.mode == "untracked":
        files = get_untracked_files(repo_path)
    elif args.mode == "all":
        files = (
            get_changed_files_compare(repo_path, args.base_ref or "HEAD~1")
            + get_staged_files(repo_path)
            + get_unstaged_files(repo_path)
            + get_untracked_files(repo_path)
        )
        # Deduplicate while preserving order
        seen = set()
        unique = []
        for f in files:
            if f not in seen:
                seen.add(f)
                unique.append(f)
        files = unique
        source = "all"

    result = audit_files(files)

    if args.json:
        output = {**result, "source": source}
        print(json.dumps(output, indent=2))
    else:
        print(format_human(result, source))

    sys.exit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
