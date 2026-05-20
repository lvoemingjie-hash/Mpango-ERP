#!/usr/bin/env python3
"""Platform Agent Preflight Gate - Mpango ERP.

Validates that a platform-track agent is operating in a clean,
compliant environment before proceeding with implementation.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


REQUIRED_DOCS = [
    "docs/ai/CTO_CURRENT_OPS.md",
    "docs/ai/AI_TEAM_OPERATING_RULES.md",
    "docs/ai/PROJECT.md",
    "docs/ai/PROJECT_MEMORY.md",
    "docs/ai/README.md",
    "docs/ai/DUAL_MACHINE_DEVELOPMENT_PROTOCOL.md",
]

FORBIDDEN_PREFIXES = [
    "backend/",
    "frontend/",
    ".github/workflows/",
    ".claude/",
]

FORBIDDEN_SPECIFIC = [
    "docs/ai/PHASE4_FRONTEND_CONTRACT.md",
]

FORBIDDEN_FRAGMENTS = [
    "auth", "rbac", "tenancy", "session", "migration", "payment",
]

REPORT_FIELDS = [
    "branch", "commit", "modified files", "tests", "report path", "risk",
]


class PreflightResult:
    def __init__(self):
        self.checks = []
        self.failures = []

    def add_pass(self, msg):
        self.checks.append(("PASS", msg))
        print(f"  PASS  {msg}")

    def add_fail(self, msg):
        self.checks.append(("FAIL", msg))
        self.failures.append(msg)
        print(f"  FAIL  {msg}")

    @property
    def passed(self):
        return len(self.failures) == 0


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
    return out if rc == 0 else None


def get_current_commit(repo_path):
    rc, out, _ = run_git(["rev-parse", "HEAD"], repo_path)
    return out if rc == 0 else None


def get_changed_files(repo_path):
    rc1, staged, _ = run_git(["diff", "--cached", "--name-only"], repo_path)
    rc2, unstaged, _ = run_git(["diff", "--name-only"], repo_path)
    rc3, untracked, _ = run_git(["ls-files", "--others", "--exclude-standard"], repo_path)

    files = set()
    if rc1 == 0 and staged:
        files.update(staged.splitlines())
    if rc2 == 0 and unstaged:
        files.update(unstaged.splitlines())
    if rc3 == 0 and untracked:
        files.update(untracked.splitlines())
    return files


def normalize_path(p):
    return p.replace("\\", "/")


def is_forbidden_path(path):
    normalized = normalize_path(path)

    for prefix in FORBIDDEN_PREFIXES:
        if normalized.startswith(prefix):
            return True, f"matches forbidden prefix '{prefix}'"

    for specific in FORBIDDEN_SPECIFIC:
        if normalized == specific:
            return True, f"matches forbidden specific path '{specific}'"

    parts = normalized.split("/")
    for part in parts:
        part_lower = part.lower()
        for fragment in FORBIDDEN_FRAGMENTS:
            if fragment in part_lower:
                return True, f"contains forbidden fragment '{fragment}' in '{part}'"

    return False, None


def check_branch(result, repo_path, allow_platform_dev=False):
    branch = get_current_branch(repo_path)
    if branch is None:
        result.add_fail("could not determine current branch")
        return None

    if branch.startswith("codex/platform-"):
        result.add_pass(f"branch '{branch}' is allowed")
    elif branch == "platform-dev":
        if allow_platform_dev:
            result.add_pass(
                "branch 'platform-dev' is allowed (--allow-platform-dev)"
            )
        else:
            result.add_fail(
                "branch 'platform-dev' is not allowed by default; "
                "use --allow-platform-dev to enable"
            )
    else:
        result.add_fail(
            f"branch '{branch}' is not allowed; "
            "must start with 'codex/platform-' "
            "or use --allow-platform-dev for 'platform-dev'"
        )
    return branch


def check_required_docs(result, repo_path):
    all_exist = True
    for doc in REQUIRED_DOCS:
        doc_path = Path(repo_path) / normalize_path(doc)
        if doc_path.exists():
            result.add_pass(f"required doc '{doc}' exists")
        else:
            result.add_fail(f"required doc '{doc}' is missing")
            all_exist = False
    return all_exist


def check_changed_files(result, repo_path):
    changed = get_changed_files(repo_path)
    if not changed:
        result.add_pass("no changed files detected")
        return True

    all_clean = True
    for f in sorted(changed):
        forbidden, reason = is_forbidden_path(f)
        if forbidden:
            result.add_fail(f"forbidden changed path '{f}' ({reason})")
            all_clean = False
        else:
            result.add_pass(f"changed path '{f}' is allowed")
    return all_clean


def validate_report(result, report_path):
    if not os.path.isfile(report_path):
        result.add_fail(f"report file '{report_path}' does not exist")
        return False

    try:
        with open(report_path, "r", encoding="utf-8") as f:
            content = f.read()
    except (IOError, OSError) as e:
        result.add_fail(f"could not read report '{report_path}': {e}")
        return False

    content_lower = content.lower()
    missing = [f for f in REPORT_FIELDS if f not in content_lower]

    if missing:
        result.add_fail(f"report missing required field(s): {', '.join(missing)}")
        return False

    result.add_pass(f"report '{report_path}' contains all required fields")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Mpango ERP Platform Agent Preflight Gate"
    )
    parser.add_argument(
        "--repo",
        default=".",
        help="Path to the git repository root (default: current directory)",
    )
    parser.add_argument(
        "--report",
        default=None,
        help="Path to the report file to validate",
    )
    parser.add_argument(
        "--require-report",
        action="store_true",
        help="Fail if --report is not provided",
    )
    parser.add_argument(
        "--allow-platform-dev",
        action="store_true",
        help=(
            "Allow 'platform-dev' branch "
            "(default: only codex/platform-* branches are allowed)"
        ),
    )
    args = parser.parse_args()

    if args.require_report and args.report is None:
        print("ERROR: --require-report requires --report PATH")
        print()
        print("=" * 50)
        print("VERDICT: FAIL")
        sys.exit(1)

    repo_path = os.path.abspath(args.repo)

    print("Platform Agent Preflight Gate")
    print(f"Repository: {repo_path}")
    print()

    result = PreflightResult()

    print("[1/4] Checking branch...")
    branch = check_branch(result, repo_path, allow_platform_dev=args.allow_platform_dev)
    print()

    print("[2/4] Checking required shared-memory docs...")
    check_required_docs(result, repo_path)
    print()

    print("[3/4] Checking changed files for forbidden paths...")
    check_changed_files(result, repo_path)
    print()

    print("[4/4] Checking report...")
    if args.report:
        report_path = Path(args.report)
        if not report_path.is_absolute():
            report_path = Path(repo_path) / report_path
        validate_report(result, str(report_path))
    else:
        result.add_pass("no report validation requested")
    print()

    print("=" * 50)
    if result.passed:
        commit = get_current_commit(repo_path)
        print(f"VERDICT: PASS - All preflight checks passed")
        print(f"  Branch:  {branch or 'unknown'}")
        print(f"  Commit:  {commit or 'unknown'}")
        sys.exit(0)
    else:
        print(f"VERDICT: FAIL - {len(result.failures)} check(s) failed")
        for f in result.failures:
            print(f"  - {f}")
        sys.exit(1)


if __name__ == "__main__":
    main()
