#!/usr/bin/env python3
"""Platform Remote Runner Packet - Mpango ERP.

Generates a CTO/Lubuntu runner markdown handoff packet for validating
an isolated platform branch.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


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

VALID_RISK_LEVELS = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]


def normalize_path(path):
    return path.replace("\\", "/")


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

    for part in normalized.split("/"):
        part_lower = part.lower()
        for fragment in FORBIDDEN_FRAGMENTS:
            if fragment in part_lower:
                return True, f"contains forbidden fragment '{fragment}' in '{part}'"

    return False, None


def validate_md_path(value, label):
    if not isinstance(value, str) or not value:
        return None, f"{label} path must be a non-empty string"

    normalized = normalize_path(value)
    if os.path.isabs(value) or ":" in normalized.split("/")[0]:
        return normalized, f"{label} path '{normalized}' must be relative"
    if has_unsafe_path_part(normalized):
        return normalized, f"{label} path '{normalized}' contains unsafe path part"
    if not normalized.startswith("ai-ledger/platform/"):
        return normalized, f"{label} path '{normalized}' is not under ai-ledger/platform/"
    if not normalized.endswith(".md"):
        return normalized, f"{label} path '{normalized}' must end in .md"

    forbidden, reason = is_forbidden_path(normalized)
    if forbidden:
        return normalized, f"forbidden {label} path '{normalized}' ({reason})"

    return normalized, None


def validate_expected_file(value):
    if not isinstance(value, str) or not value:
        return None, "expected-file path must be a non-empty string"

    normalized = normalize_path(value)
    if os.path.isabs(value) or ":" in normalized.split("/")[0]:
        return normalized, f"expected-file path '{normalized}' must be relative"
    if has_unsafe_path_part(normalized):
        return normalized, f"expected-file path '{normalized}' contains unsafe path part"

    forbidden, reason = is_forbidden_path(normalized)
    if forbidden:
        return normalized, f"forbidden expected-file path '{normalized}' ({reason})"

    return normalized, None


def run_git(repo_path, args):
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return 1, "", "git command timed out"
    except FileNotFoundError:
        return 1, "", "git not found"
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def get_branch(repo_path):
    rc, out, err = run_git(repo_path, ["rev-parse", "--abbrev-ref", "HEAD"])
    if rc != 0:
        raise RuntimeError(f"could not determine branch: {err}")
    return out


def get_commit(repo_path):
    rc, out, err = run_git(repo_path, ["rev-parse", "HEAD"])
    if rc != 0:
        raise RuntimeError(f"could not determine commit: {err}")
    return out


def parse_diff_name_status(output):
    entries = []
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status = parts[0]
        path = parts[-1]
        entries.append((status, normalize_path(path)))
    return entries


def get_changed_files(repo_path, base_ref):
    rc, out, err = run_git(
        repo_path,
        ["diff", "--name-status", "--no-renames", f"{base_ref}..HEAD"],
    )
    if rc != 0:
        raise RuntimeError(f"could not diff against '{base_ref}': {err}")
    return parse_diff_name_status(out)


def parse_status_porcelain(output):
    files = []
    for line in output.splitlines():
        if not line:
            continue
        status = line[:2]
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        files.append((status, normalize_path(path.strip().strip('"'))))
    return files


def get_uncommitted_files(repo_path):
    rc, out, err = run_git(repo_path, ["status", "--porcelain=v1", "-uall"])
    if rc != 0:
        raise RuntimeError(f"could not collect git status: {err}")
    return parse_status_porcelain(out)


def audit_forbidden(entries):
    issues = []
    for status, path in entries:
        forbidden, reason = is_forbidden_path(path)
        if forbidden:
            issues.append((status, path, reason))
    return issues


def render_table(entries, empty_label):
    if not entries:
        return f"{empty_label}\n"

    lines = ["| Status | Path |", "|--------|------|"]
    for status, path in entries:
        lines.append(f"| `{status}` | `{path}` |")
    return "\n".join(lines) + "\n"


def render_packet(
    branch, commit, base_ref, report_path, risk,
    expected_files, changed, uncommitted, test_commands,
):
    expected_lines = "\n".join(f"- `{f}`" for f in expected_files) if expected_files else "None"
    test_lines = "\n".join(f"- `{cmd}`" for cmd in test_commands)

    audit_status = "PASS - no forbidden changed paths detected"

    uncommitted_note = (
        "Uncommitted files are present; do not merge until clean."
        if uncommitted
        else "No uncommitted files detected."
    )

    checklist = (
        "1. Fetch and verify `platform-dev` has not unexpectedly advanced.\n"
        "2. Checkout this branch and confirm HEAD matches the commit above.\n"
        "3. Run each test command in sequence; all must pass.\n"
        "4. Verify expected files exist and match checksums.\n"
        "5. Run GitNexus compare against `origin/platform-dev`.\n"
        "6. Confirm forbidden path audit is PASS.\n"
        "7. Record results in the report file.\n"
        "8. Merge only after CTO approval.\n"
    )

    return f"""# Phase P2-D: Remote Runner Handoff Packet

## Branch

`{branch}`

## Commit

`{commit}`

## Base Ref

`{base_ref}`

## Report Path

`{report_path}`

## Risk

`{risk}`

## Expected Files

{expected_lines}

## Changed Files

{render_table(changed, "No committed changed files detected.")}
## Uncommitted Files

{render_table(uncommitted, "No uncommitted files detected.")}
{uncommitted_note}

## Test Commands

{test_lines}

## Forbidden Path Audit

{audit_status}

## Runner Checklist

{checklist}
## Report Fields

- **Branch:** `{branch}`
- **Commit:** `{commit}`
- **Base ref:** `{base_ref}`
- **Modified files:** see Changed Files
- **Tests:** see Test Commands
- **Report path:** `{report_path}`
- **Risk:** `{risk}`
"""


def render_report(branch, commit, base_ref, risk, changed, uncommitted):
    changed_summary = (
        "\n".join(f"- `{path}` ({status})" for status, path in changed)
        if changed else "None"
    )
    uncommitted_summary = (
        "\n".join(f"- `{path}` ({status})" for status, path in uncommitted)
        if uncommitted else "None"
    )

    return f"""# P2-D Remote Runner Report

## Branch

`{branch}`

## Commit

`{commit}`

## Base Ref

`{base_ref}`

## Risk

`{risk}`

## Changed Files

{changed_summary}

## Uncommitted Files

{uncommitted_summary}

## Status

PENDING - awaiting runner validation
"""


def main():
    parser = argparse.ArgumentParser(
        description="Mpango ERP Platform Remote Runner Packet"
    )
    parser.add_argument("--repo", required=True, help="Path to git repository")
    parser.add_argument("--base-ref", required=True, help="Base ref for diff")
    parser.add_argument("--output", required=True, help="Packet markdown output path")
    parser.add_argument("--report", required=True, help="Report markdown output path")
    parser.add_argument(
        "--risk", required=True, choices=VALID_RISK_LEVELS,
        help="Risk classification",
    )
    parser.add_argument(
        "--test-command", action="append", default=[],
        dest="test_commands",
        help="Test command to run (repeatable, at least one required)",
    )
    parser.add_argument(
        "--expected-file", action="append", default=[],
        dest="expected_files",
        help="Expected file path (repeatable)",
    )
    parser.add_argument(
        "--allow-platform-dev", action="store_true",
        help="Allow platform-dev branch for read-only checks",
    )
    parser.add_argument(
        "--require-clean", action="store_true",
        help="Fail if the repository has uncommitted changes",
    )
    args = parser.parse_args()

    if not args.test_commands:
        print("ERROR: at least one --test-command is required", flush=True)
        sys.exit(1)

    output_path, output_error = validate_md_path(args.output, "output")
    if output_error:
        print(f"ERROR: {output_error}", flush=True)
        sys.exit(1)

    report_path, report_error = validate_md_path(args.report, "report")
    if report_error:
        print(f"ERROR: {report_error}", flush=True)
        sys.exit(1)

    validated_expected = []
    for ef in args.expected_files:
        norm, err = validate_expected_file(ef)
        if err:
            print(f"ERROR: {err}", flush=True)
            sys.exit(1)
        validated_expected.append(norm)

    repo_path = Path(args.repo).resolve()

    try:
        branch = get_branch(repo_path)
        commit = get_commit(repo_path)
        changed = get_changed_files(repo_path, args.base_ref)
        uncommitted = get_uncommitted_files(repo_path)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", flush=True)
        sys.exit(1)

    branch_allowed = branch.startswith("codex/platform-") or (
        args.allow_platform_dev and branch == "platform-dev"
    )
    if not branch_allowed:
        print(
            f"ERROR: branch '{branch}' must start with 'codex/platform-' "
            f"or be platform-dev with --allow-platform-dev",
            flush=True,
        )
        sys.exit(1)

    if args.require_clean and uncommitted:
        print(
            "ERROR: uncommitted files present and --require-clean was set",
            flush=True,
        )
        for status, path in uncommitted:
            print(f"  {status} {path}", flush=True)
        sys.exit(1)

    forbidden = audit_forbidden(changed + uncommitted)
    if forbidden:
        print("ERROR: forbidden changed path(s) detected", flush=True)
        for status, path, reason in forbidden:
            print(f"  {status} {path} ({reason})", flush=True)
        sys.exit(1)

    packet_content = render_packet(
        branch=branch,
        commit=commit,
        base_ref=args.base_ref,
        report_path=report_path,
        risk=args.risk,
        expected_files=validated_expected,
        changed=changed,
        uncommitted=uncommitted,
        test_commands=args.test_commands,
    )

    report_content = render_report(
        branch=branch,
        commit=commit,
        base_ref=args.base_ref,
        risk=args.risk,
        changed=changed,
        uncommitted=uncommitted,
    )

    output_abs = repo_path / output_path
    output_abs.parent.mkdir(parents=True, exist_ok=True)
    output_abs.write_text(packet_content, encoding="utf-8")

    report_abs = repo_path / report_path
    report_abs.parent.mkdir(parents=True, exist_ok=True)
    report_abs.write_text(report_content, encoding="utf-8")

    print(f"Remote runner packet written to {output_path}", flush=True)
    print(f"Report written to {report_path}", flush=True)
    print(f"Branch: {branch}", flush=True)
    print(f"Commit: {commit}", flush=True)
    print(f"Risk: {args.risk}", flush=True)
    sys.exit(0)


if __name__ == "__main__":
    main()
