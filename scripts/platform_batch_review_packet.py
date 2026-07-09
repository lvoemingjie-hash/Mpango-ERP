#!/usr/bin/env python3
"""Platform Batch Review Packet - Mpango ERP.

Generates a CTO-facing markdown review packet for a stacked platform
harness branch before merge review.
"""

import argparse
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

VALID_RISK_LEVELS = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]

TEST_PLAN = [
    "python scripts/test_platform_batch_review_packet.py",
    "python scripts/test_platform_task_execution_bridge.py",
    "python scripts/test_platform_run_packet_gate.py",
    "python scripts/test_platform_toolchain_gate.py",
    "python scripts/test_platform_directive_gate.py",
    "python scripts/test_platform_runner_gate.py",
    "python scripts/test_platform_agent_preflight.py",
    "git diff --check",
    "npx gitnexus analyze",
    "GitNexus detect_changes(scope=compare, base_ref=origin/platform-dev)",
]


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


def validate_output_path(value):
    if not isinstance(value, str) or not value:
        return None, "output path must be a non-empty string"

    normalized = normalize_path(value)
    if os.path.isabs(value) or ":" in normalized.split("/")[0]:
        return normalized, f"output path '{normalized}' must be relative"
    if has_unsafe_path_part(normalized):
        return normalized, f"output path '{normalized}' contains unsafe path part"
    if not normalized.startswith("ai-ledger/platform/"):
        return normalized, f"output path '{normalized}' is not under ai-ledger/platform/"
    if not normalized.endswith(".md"):
        return normalized, f"output path '{normalized}' must end in .md"

    forbidden, reason = is_forbidden_path(normalized)
    if forbidden:
        return normalized, f"forbidden output path '{normalized}' ({reason})"

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
    branch, commit, base_ref, phases, changed, uncommitted, risk, output_path
):
    phase_lines = "\n".join(f"- {phase}" for phase in phases)
    test_lines = "\n".join(f"- `{test}`" for test in TEST_PLAN)

    audit_status = "PASS - no forbidden changed paths detected"
    if uncommitted:
        uncommitted_note = "Uncommitted files are present; do not merge until clean."
    else:
        uncommitted_note = "No uncommitted files detected."

    return f"""# Phase P1-G: Platform Batch Review Packet

## Branch

`{branch}`

## Commit

`{commit}`

## Base Ref

`{base_ref}`

## Stack Phases

{phase_lines}

## Changed Files

{render_table(changed, "No committed changed files detected.")}
## Uncommitted Files

{render_table(uncommitted, "No uncommitted files detected.")}
{uncommitted_note}

## Test Plan

{test_lines}

## Forbidden Path Audit

{audit_status}

## Risk

`{risk}`

## Agent Execution Note

`opencode run` was attempted for this platform phase. In this Windows
worktree it did not return a completion event before the external timeout,
so Codex Platform CTO completed and verified the bounded platform changes.
Future long agent runs should use the P1-F execution bridge plus an external
timeout and explicit artifact checks.

## Merge Instructions

1. Fetch and verify `platform-dev` has not unexpectedly advanced.
2. Review this stacked platform branch against `origin/platform-dev`.
3. Run the full test plan above.
4. Run GitNexus compare against `origin/platform-dev`.
5. Merge only after CTO approval. Do not merge product branches from this packet.

## Report Fields

- **Branch:** `{branch}`
- **Commit:** `{commit}`
- **Modified files:** see Changed Files
- **Tests:** see Test Plan
- **Report path:** `{output_path}`
- **Risk:** `{risk}`
"""


def main():
    parser = argparse.ArgumentParser(
        description="Mpango ERP Platform Batch Review Packet"
    )
    parser.add_argument("--repo", required=True, help="Path to git repository")
    parser.add_argument("--base-ref", required=True, help="Base ref for diff")
    parser.add_argument("--output", required=True, help="Markdown output path")
    parser.add_argument(
        "--risk", required=True, choices=VALID_RISK_LEVELS,
        help="Batch risk classification",
    )
    parser.add_argument(
        "--phase", action="append", default=[],
        help="Stack phase label (repeatable)",
    )
    parser.add_argument(
        "--require-clean", action="store_true",
        help="Fail if the repository has uncommitted changes",
    )
    args = parser.parse_args()

    if not args.phase:
        print("ERROR: at least one --phase is required", flush=True)
        sys.exit(1)

    output_path, output_error = validate_output_path(args.output)
    if output_error:
        print(f"ERROR: {output_error}", flush=True)
        sys.exit(1)

    repo_path = Path(args.repo).resolve()

    try:
        branch = get_branch(repo_path)
        commit = get_commit(repo_path)
        changed = get_changed_files(repo_path, args.base_ref)
        uncommitted = get_uncommitted_files(repo_path)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", flush=True)
        sys.exit(1)

    if args.require_clean and uncommitted:
        print("ERROR: uncommitted files present and --require-clean was set", flush=True)
        for status, path in uncommitted:
            print(f"  {status} {path}", flush=True)
        sys.exit(1)

    forbidden = audit_forbidden(changed + uncommitted)
    if forbidden:
        print("ERROR: forbidden changed path(s) detected", flush=True)
        for status, path, reason in forbidden:
            print(f"  {status} {path} ({reason})", flush=True)
        sys.exit(1)

    content = render_packet(
        branch=branch,
        commit=commit,
        base_ref=args.base_ref,
        phases=args.phase,
        changed=changed,
        uncommitted=uncommitted,
        risk=args.risk,
        output_path=output_path,
    )

    output_abs = repo_path / output_path
    output_abs.parent.mkdir(parents=True, exist_ok=True)
    output_abs.write_text(content, encoding="utf-8")

    print(f"Batch review packet written to {output_path}", flush=True)
    print(f"Branch: {branch}", flush=True)
    print(f"Commit: {commit}", flush=True)
    print(f"Risk: {args.risk}", flush=True)
    sys.exit(0)


if __name__ == "__main__":
    main()
