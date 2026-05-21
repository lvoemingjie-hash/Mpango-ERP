#!/usr/bin/env python3
"""Platform Directive Gate - Mpango ERP.

Receives a JSON directive, validates it, and invokes platform_runner_gate.py
in a predictable way. Implements P1-C runner directive contract.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


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

REQUIRED_FIELDS = ["phase", "branch", "report", "risk", "command", "gate_only"]
VALID_RISK_LEVELS = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]


def print_section(title):
    print(flush=True)
    print("=" * 60, flush=True)
    print(f"  {title}", flush=True)
    print("=" * 60, flush=True)


def normalize_path(p):
    return p.replace("\\", "/")


def has_unsafe_path_part(path):
    parts = normalize_path(path).split("/")
    return any(part in ("", ".", "..") for part in parts)


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


def get_current_branch(repo_path):
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, cwd=str(repo_path), timeout=30,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def validate_directive(directive, repo_path):
    issues = []

    for field in REQUIRED_FIELDS:
        if field not in directive:
            issues.append(f"missing required field '{field}'")

    if issues:
        return issues

    if not isinstance(directive["phase"], str) or not directive["phase"]:
        issues.append("'phase' must be a non-empty string")

    if not isinstance(directive["branch"], str) or not directive["branch"]:
        issues.append("'branch' must be a non-empty string")

    if not isinstance(directive["report"], str) or not directive["report"]:
        issues.append("'report' must be a non-empty string")

    if directive["risk"] not in VALID_RISK_LEVELS:
        issues.append(f"'risk' must be one of {', '.join(VALID_RISK_LEVELS)}")

    if not isinstance(directive["command"], list):
        issues.append("'command' must be a list of strings")
    elif any(not isinstance(part, str) or not part for part in directive["command"]):
        issues.append("'command' must be a list of non-empty strings")
    elif not directive["command"] and not directive.get("gate_only", False):
        issues.append("command is empty but gate_only is not true")

    if not isinstance(directive.get("gate_only"), bool):
        issues.append("'gate_only' must be a boolean")

    if issues:
        return issues

    current_branch = get_current_branch(repo_path)
    if current_branch is None:
        issues.append("could not determine current git branch")
    elif directive["branch"] != current_branch:
        issues.append(
            f"directive branch '{directive['branch']}' does not match "
            f"current branch '{current_branch}'"
        )

    report = normalize_path(directive["report"])
    if os.path.isabs(directive["report"]) or ":" in report.split("/")[0]:
        issues.append(f"report '{report}' must be relative")
    elif has_unsafe_path_part(report):
        issues.append(f"report '{report}' contains unsafe path part")
    elif is_forbidden_path(report)[0]:
        issues.append(f"report '{report}' is forbidden")
    elif not report.startswith("ai-ledger/platform/"):
        issues.append(f"report '{report}' is not under ai-ledger/platform/")
    elif not report.endswith(".md"):
        issues.append(f"report '{report}' must end in .md")

    expected_files = directive.get("expected_files", [])
    if not isinstance(expected_files, list):
        issues.append("'expected_files' must be a list")
    else:
        for f in expected_files:
            if not isinstance(f, str) or not f:
                issues.append("expected_file must be a non-empty string")
                continue
            ef_norm = normalize_path(f)
            if os.path.isabs(f) or ":" in ef_norm.split("/")[0]:
                issues.append(f"expected_file '{ef_norm}' must be relative")
            elif has_unsafe_path_part(ef_norm):
                issues.append(f"expected_file '{ef_norm}' contains unsafe path part")
            else:
                forbidden, reason = is_forbidden_path(ef_norm)
                if forbidden:
                    issues.append(f"forbidden expected_file '{ef_norm}' ({reason})")

    allow_platform_dev = directive.get("allow_platform_dev", False)
    if not isinstance(allow_platform_dev, bool):
        issues.append("'allow_platform_dev' must be a boolean")
    elif directive.get("branch") == "platform-dev" and not allow_platform_dev:
        issues.append(
            "branch is 'platform-dev' but allow_platform_dev is not true"
        )
    elif directive.get("branch") != "platform-dev" and allow_platform_dev:
        issues.append("allow_platform_dev is only valid on platform-dev")

    return issues


def build_runner_cmd(directive, repo_path):
    runner_script = Path(__file__).resolve().parent / "platform_runner_gate.py"
    cmd = [
        sys.executable,
        str(runner_script),
        "--repo", str(repo_path),
        "--report", normalize_path(directive["report"]),
    ]

    if directive.get("allow_platform_dev"):
        cmd.append("--allow-platform-dev")

    command = directive.get("command", [])
    if command:
        cmd.append("--")
        cmd.extend(command)

    return cmd


def main():
    parser = argparse.ArgumentParser(
        description="Mpango ERP Platform Directive Gate - validate and invoke"
    )
    parser.add_argument(
        "--repo",
        required=True,
        help="Path to the git repository root",
    )
    parser.add_argument(
        "--directive",
        required=True,
        help="Path to the JSON directive file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the runner command without executing",
    )
    args = parser.parse_args()

    repo_path = os.path.abspath(args.repo)

    print_section("DIRECTIVE VALIDATION")

    try:
        with open(args.directive, "r", encoding="utf-8-sig") as f:
            directive = json.load(f)
    except (json.JSONDecodeError, IOError, OSError) as e:
        print(f"  FAIL  could not load directive: {e}", flush=True)
        print()
        print("=" * 50)
        print("VERDICT: FAIL")
        sys.exit(1)

    issues = validate_directive(directive, repo_path)
    if issues:
        for issue in issues:
            print(f"  FAIL  {issue}", flush=True)
        print()
        print("=" * 50)
        print("VERDICT: FAIL")
        sys.exit(1)

    print(f"  PASS  directive validation passed", flush=True)
    print()
    print("=" * 50)
    print("VERDICT: PASS - directive is valid", flush=True)

    runner_cmd = build_runner_cmd(directive, repo_path)
    runner_cmd_str = " ".join(runner_cmd)

    print()
    print_section("RUNNER INVOCATION")
    print(f"  {runner_cmd_str}", flush=True)
    print()

    if args.dry_run:
        print("=" * 50)
        print("VERDICT: DRY-RUN PASS")
        sys.exit(0)

    result = subprocess.run(runner_cmd, cwd=str(repo_path))
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
