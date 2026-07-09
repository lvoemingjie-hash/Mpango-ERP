#!/usr/bin/env python3
"""Platform Agent Run Bundle Gate - Mpango ERP.

Executes a single platform agent run bundle by invoking the P1-H watchdog
and then the P1-I artifact collector.
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

REQUIRED_FIELDS = [
    "phase", "agent", "timeout_seconds", "risk", "command",
    "expected_files", "watchdog_report", "artifact_manifest",
]

VALID_RISK_LEVELS = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
TIMEOUT_EXIT_CODE = 124


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


def validate_ledger_path(value, label, extensions):
    normalized, issue = validate_contract_path(value, label)
    if issue:
        return normalized, issue
    if not normalized.startswith("ai-ledger/platform/"):
        return normalized, f"{label} '{normalized}' is not under ai-ledger/platform/"
    if not any(normalized.endswith(ext) for ext in extensions):
        joined = " or ".join(extensions)
        return normalized, f"{label} '{normalized}' must end in {joined}"
    return normalized, None


def load_bundle(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not load bundle: {exc}")


def validate_bundle(bundle):
    issues = []
    for field in REQUIRED_FIELDS:
        if field not in bundle:
            issues.append(f"missing required field '{field}'")
    if issues:
        return None, issues

    if not isinstance(bundle["phase"], str) or not bundle["phase"]:
        issues.append("'phase' must be a non-empty string")
    if not isinstance(bundle["agent"], str) or not bundle["agent"]:
        issues.append("'agent' must be a non-empty string")
    if bundle["risk"] not in VALID_RISK_LEVELS:
        issues.append(f"'risk' must be one of {', '.join(VALID_RISK_LEVELS)}")
    if not isinstance(bundle["timeout_seconds"], (int, float)):
        issues.append("'timeout_seconds' must be a number")
    elif bundle["timeout_seconds"] <= 0:
        issues.append("'timeout_seconds' must be greater than zero")

    if not isinstance(bundle["command"], list):
        issues.append("'command' must be a list")
    elif any(not isinstance(part, str) or not part for part in bundle["command"]):
        issues.append("'command' must be a list of non-empty strings")

    expected_files = bundle["expected_files"]
    normalized_expected = []
    if not isinstance(expected_files, list):
        issues.append("'expected_files' must be a list")
    else:
        for item in expected_files:
            normalized, issue = validate_contract_path(item, "expected_file")
            if issue:
                issues.append(issue)
            else:
                normalized_expected.append(normalized)

    watchdog_report, issue = validate_ledger_path(
        bundle["watchdog_report"], "watchdog_report", [".md"]
    )
    if issue:
        issues.append(issue)

    artifact_manifest, issue = validate_ledger_path(
        bundle["artifact_manifest"], "artifact_manifest", [".json", ".md"]
    )
    if issue:
        issues.append(issue)

    if issues:
        return None, issues

    normalized = dict(bundle)
    normalized["expected_files"] = sorted(set(normalized_expected))
    normalized["watchdog_report"] = watchdog_report
    normalized["artifact_manifest"] = artifact_manifest
    return normalized, []


def script_path(name):
    return str(Path(__file__).resolve().parent / name)


def print_section(title):
    print(flush=True)
    print("=" * 60, flush=True)
    print(f"  {title}", flush=True)
    print("=" * 60, flush=True)


def run_cmd(cmd, repo_path):
    return subprocess.run(cmd, cwd=str(repo_path))


def build_watchdog_cmd(bundle, repo_path):
    return [
        sys.executable,
        script_path("platform_agent_timeout_watchdog.py"),
        "--repo", str(repo_path),
        "--report", bundle["watchdog_report"],
        "--phase", bundle["phase"],
        "--agent", bundle["agent"],
        "--timeout-seconds", str(bundle["timeout_seconds"]),
        "--risk", bundle["risk"],
        "--",
    ] + bundle["command"]


def build_collector_cmd(bundle, repo_path):
    expected_for_collection = sorted(
        set(bundle["expected_files"] + [bundle["watchdog_report"]])
    )
    cmd = [
        sys.executable,
        script_path("platform_agent_artifact_collector.py"),
        "--repo", str(repo_path),
        "--output", bundle["artifact_manifest"],
        "--phase", bundle["phase"],
        "--risk", bundle["risk"],
    ]
    for path in expected_for_collection:
        cmd.extend(["--expected-file", path])
    return cmd


def final_exit_code(watchdog_rc, collector_rc):
    if watchdog_rc == 0 and collector_rc == 0:
        return 0
    if watchdog_rc == TIMEOUT_EXIT_CODE and collector_rc == 0:
        return TIMEOUT_EXIT_CODE
    if collector_rc != 0:
        return collector_rc
    return watchdog_rc


def main():
    parser = argparse.ArgumentParser(
        description="Mpango ERP Platform Agent Run Bundle Gate"
    )
    parser.add_argument("--repo", required=True, help="Path to git repository")
    parser.add_argument("--bundle", required=True, help="Path to bundle JSON")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Validate and print planned invocations without executing",
    )
    args = parser.parse_args()

    repo_path = Path(args.repo).resolve()

    print_section("BUNDLE VALIDATION")
    try:
        bundle = load_bundle(args.bundle)
        bundle, issues = validate_bundle(bundle)
    except ValueError as exc:
        print(f"  FAIL  {exc}", flush=True)
        print_section("BUNDLE VERDICT")
        print("  BUNDLE VERDICT: FAIL", flush=True)
        sys.exit(1)

    if issues:
        for issue in issues:
            print(f"  FAIL  {issue}", flush=True)
        print_section("BUNDLE VERDICT")
        print("  BUNDLE VERDICT: FAIL", flush=True)
        sys.exit(1)

    print("  PASS  bundle validation passed", flush=True)

    watchdog_cmd = build_watchdog_cmd(bundle, repo_path)
    collector_cmd = build_collector_cmd(bundle, repo_path)

    print_section("WATCHDOG INVOCATION")
    print("  " + " ".join(watchdog_cmd), flush=True)

    print_section("ARTIFACT COLLECTION")
    print("  " + " ".join(collector_cmd), flush=True)

    if args.dry_run:
        print_section("BUNDLE VERDICT")
        print("  BUNDLE VERDICT: DRY-RUN PASS", flush=True)
        sys.exit(0)

    watchdog_result = run_cmd(watchdog_cmd, repo_path)
    collector_result = run_cmd(collector_cmd, repo_path)
    exit_code = final_exit_code(watchdog_result.returncode, collector_result.returncode)

    print_section("BUNDLE VERDICT")
    print(f"  WATCHDOG: {watchdog_result.returncode}", flush=True)
    print(f"  COLLECTOR: {collector_result.returncode}", flush=True)
    print(
        "  BUNDLE VERDICT: " + ("PASS" if exit_code == 0 else "FAIL"),
        flush=True,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
