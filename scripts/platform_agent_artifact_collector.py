#!/usr/bin/env python3
"""Platform Agent Artifact Allowlist Collector - Mpango ERP.

Collects git changed files after an agent task and compares them with an
expected artifact allowlist. Emits a compact JSON manifest for later batch
review packets.
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


def validate_contract_path(value, label):
    if not isinstance(value, str) or not value:
        return None, f"{label} must be a non-empty string"

    normalized = normalize_path(value)
    if os.path.isabs(value) or ":" in normalized.split("/")[0]:
        return normalized, f"{label} '{normalized}' must be relative"
    if has_unsafe_path_part(normalized):
        return normalized, f"{label} '{normalized}' contains unsafe path part"

    forbidden, reason = is_forbidden_path(normalized)
    if forbidden:
        return normalized, f"forbidden {label} '{normalized}' ({reason})"

    return normalized, None


def validate_output_path(value):
    normalized, issue = validate_contract_path(value, "output")
    if issue:
        return normalized, issue
    if not normalized.startswith("ai-ledger/platform/"):
        return normalized, f"output '{normalized}' is not under ai-ledger/platform/"
    if not (normalized.endswith(".json") or normalized.endswith(".md")):
        return normalized, f"output '{normalized}' must end in .json or .md"
    return normalized, None


def run_git(repo_path, args):
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return 1, "", str(exc)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def get_branch(repo_path):
    rc, out, _ = run_git(repo_path, ["rev-parse", "--abbrev-ref", "HEAD"])
    return out if rc == 0 else "unknown"


def get_commit(repo_path):
    rc, out, _ = run_git(repo_path, ["rev-parse", "HEAD"])
    return out if rc == 0 else "unknown"


def parse_status_porcelain(output):
    entries = []
    for line in output.splitlines():
        if not line:
            continue
        status = line[:2].strip() or "?"
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        path = normalize_path(path.strip().strip('"'))
        entries.append({"status": status, "path": path})
    return entries


def get_changed_files(repo_path):
    rc, out, err = run_git(repo_path, ["status", "--porcelain=v1", "-uall"])
    if rc != 0:
        raise RuntimeError(f"git status failed: {err}")
    return parse_status_porcelain(out)


def load_expected_file_list(repo_path, list_path):
    normalized, issue = validate_contract_path(list_path, "expected_file_list")
    if issue:
        raise ValueError(issue)

    abs_path = Path(repo_path) / normalized
    try:
        data = json.loads(abs_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not load expected file list '{normalized}': {exc}")

    if not isinstance(data, list):
        raise ValueError(f"expected file list '{normalized}' must be a JSON array")
    if any(not isinstance(item, str) or not item for item in data):
        raise ValueError(
            f"expected file list '{normalized}' must contain non-empty strings"
        )
    return data


def normalize_expected_files(values):
    expected = []
    issues = []
    for value in values:
        normalized, issue = validate_contract_path(value, "expected_file")
        if issue:
            issues.append(issue)
        else:
            expected.append(normalized)
    return sorted(set(expected)), issues


def audit(changed_files, expected_files):
    actual_paths = sorted({entry["path"] for entry in changed_files})
    expected_set = set(expected_files)
    actual_set = set(actual_paths)

    unexpected = sorted(actual_set - expected_set)
    missing = sorted(expected_set - actual_set)

    forbidden = []
    for entry in changed_files:
        forbidden_hit, reason = is_forbidden_path(entry["path"])
        if forbidden_hit:
            forbidden.append({
                "status": entry["status"],
                "path": entry["path"],
                "reason": reason,
            })

    ok = not unexpected and not missing and not forbidden
    return {
        "actual_paths": actual_paths,
        "unexpected": unexpected,
        "missing": missing,
        "forbidden": forbidden,
        "ok": ok,
    }


def render_manifest(branch, commit, phase, risk, expected_files, changed_files, result):
    return {
        "phase": phase,
        "branch": branch,
        "commit": commit,
        "risk": risk,
        "expected_files": expected_files,
        "changed_files": changed_files,
        "actual_paths": result["actual_paths"],
        "unexpected": result["unexpected"],
        "missing": result["missing"],
        "forbidden": result["forbidden"],
        "verdict": "PASS" if result["ok"] else "FAIL",
    }


def write_output(repo_path, output_path, manifest):
    output_abs = Path(repo_path) / output_path
    output_abs.parent.mkdir(parents=True, exist_ok=True)
    if output_path.endswith(".json"):
        output_abs.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    else:
        lines = [
            f"# Artifact Manifest: {manifest['phase']}",
            "",
            f"- **Branch:** `{manifest['branch']}`",
            f"- **Commit:** `{manifest['commit']}`",
            f"- **Risk:** `{manifest['risk']}`",
            f"- **Verdict:** `{manifest['verdict']}`",
            "",
            "## Expected Files",
            "",
        ]
        lines.extend(f"- `{path}`" for path in manifest["expected_files"])
        lines.extend(["", "## Changed Files", ""])
        lines.extend(
            f"- `{entry['status']}` `{entry['path']}`"
            for entry in manifest["changed_files"]
        )
        lines.extend(["", "## Unexpected", ""])
        lines.extend(f"- `{path}`" for path in manifest["unexpected"] or ["none"])
        lines.extend(["", "## Missing", ""])
        lines.extend(f"- `{path}`" for path in manifest["missing"] or ["none"])
        lines.extend(["", "## Forbidden", ""])
        if manifest["forbidden"]:
            lines.extend(
                f"- `{item['status']}` `{item['path']}` ({item['reason']})"
                for item in manifest["forbidden"]
            )
        else:
            lines.append("- none")
        output_abs.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(
        description="Mpango ERP Platform Agent Artifact Allowlist Collector"
    )
    parser.add_argument("--repo", required=True, help="Path to git repository")
    parser.add_argument("--output", required=True, help="Manifest output path")
    parser.add_argument("--phase", required=True, help="Phase label")
    parser.add_argument(
        "--risk", choices=VALID_RISK_LEVELS, default="MEDIUM",
        help="Risk classification",
    )
    parser.add_argument(
        "--expected-file", action="append", default=[],
        help="Expected changed file path (repeatable)",
    )
    parser.add_argument(
        "--expected-file-list",
        help="Repo-relative JSON array of expected changed file paths",
    )
    args = parser.parse_args()

    repo_path = Path(args.repo).resolve()
    output_path, output_issue = validate_output_path(args.output)
    if output_issue:
        print(f"ERROR: {output_issue}", flush=True)
        sys.exit(1)

    raw_expected = list(args.expected_file)
    if args.expected_file_list:
        try:
            raw_expected.extend(load_expected_file_list(repo_path, args.expected_file_list))
        except ValueError as exc:
            print(f"ERROR: {exc}", flush=True)
            sys.exit(1)

    expected_files, expected_issues = normalize_expected_files(raw_expected)
    if expected_issues:
        for issue in expected_issues:
            print(f"ERROR: {issue}", flush=True)
        sys.exit(1)

    try:
        changed_files = get_changed_files(repo_path)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", flush=True)
        sys.exit(1)

    result = audit(changed_files, expected_files)
    manifest = render_manifest(
        branch=get_branch(repo_path),
        commit=get_commit(repo_path),
        phase=args.phase,
        risk=args.risk,
        expected_files=expected_files,
        changed_files=changed_files,
        result=result,
    )
    write_output(repo_path, output_path, manifest)

    print(f"ARTIFACT VERDICT: {manifest['verdict']}", flush=True)
    print(f"Output: {output_path}", flush=True)
    if result["unexpected"]:
        print("Unexpected: " + ", ".join(result["unexpected"]), flush=True)
    if result["missing"]:
        print("Missing: " + ", ".join(result["missing"]), flush=True)
    if result["forbidden"]:
        print(
            "Forbidden: " + ", ".join(item["path"] for item in result["forbidden"]),
            flush=True,
        )

    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
