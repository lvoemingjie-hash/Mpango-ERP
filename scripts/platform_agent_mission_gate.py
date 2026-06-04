#!/usr/bin/env python3
"""Platform Agent Mission Contract Gate - Mpango ERP.

Validates a mission JSON contract for future long agent runs.
"""

import argparse
import json
import os
import sys


REQUIRED_KEYS = [
    "phase", "agent", "mission", "expected_files",
    "result", "events", "timeout_seconds",
]

OPTIONAL_KEYS = ["allow_edits", "notes"]

VALID_AGENTS = ["opencode", "claude", "goose"]


def normalize_path(p):
    return p.replace("\\", "/")


def is_traversal(path):
    parts = normalize_path(path).split("/")
    return ".." in parts


def has_unsafe_path_part(path):
    parts = normalize_path(path).split("/")
    return any(part in ("", ".") for part in parts)


def is_absolute(path):
    normalized = normalize_path(path)
    first_part = normalized.split("/", 1)[0]
    return (
        os.path.isabs(path)
        or normalized.startswith("/")
        or ":" in first_part
    )


def is_forbidden(path):
    normalized = normalize_path(path)
    prefixes = ["backend/", "frontend/", ".github/workflows/", ".claude/"]
    for prefix in prefixes:
        if normalized.startswith(prefix):
            return True
    specifics = ["docs/ai/PHASE4_FRONTEND_CONTRACT.md"]
    for specific in specifics:
        if normalized == specific:
            return True
    fragments = ["auth", "rbac", "tenancy", "session", "migration", "payment"]
    for part in normalized.split("/"):
        lowered = part.lower()
        for fragment in fragments:
            if fragment in lowered:
                return True
    return False


def validate_safe_relative(path, label):
    if not isinstance(path, str) or not path.strip():
        return f"{label} must be a non-empty string"
    if is_absolute(path):
        return f"{label} '{path}' must be relative, not absolute or drive-qualified"
    if is_traversal(path):
        return f"{label} '{path}' contains directory traversal"
    if has_unsafe_path_part(path):
        return f"{label} '{path}' contains unsafe path part"
    if is_forbidden(path):
        return f"{label} '{path}' is forbidden"
    return None


def validate_mission_path(value):
    issue = validate_safe_relative(value, "mission")
    if issue:
        return issue
    if not normalize_path(value).endswith(".md"):
        return f"mission '{value}' must end with .md"
    return None


def validate_ledger_output(value, label):
    issue = validate_safe_relative(value, label)
    if issue:
        return issue
    normalized = normalize_path(value)
    if not normalized.startswith("ai-ledger/platform/"):
        return f"{label} '{value}' must be under ai-ledger/platform/"
    if not normalized.endswith(".json") and not normalized.endswith(".jsonl"):
        return f"{label} '{value}' must end with .json or .jsonl"
    if label == "result" and not normalized.endswith(".json"):
        return f"{label} '{value}' must end with .json"
    if label == "events" and not normalized.endswith(".jsonl"):
        return f"{label} '{value}' must end with .jsonl"
    return None


def validate_mission(data):
    failures = []

    if not isinstance(data, dict):
        failures.append("mission JSON must be an object")
        return failures

    for key in REQUIRED_KEYS:
        if key not in data:
            failures.append(f"missing required key '{key}'")

    if failures:
        return failures

    phase = data["phase"]
    if not isinstance(phase, str) or not phase.strip():
        failures.append("'phase' must be a non-empty string")
    elif not (
        phase.startswith("P1-")
        or phase.startswith("P2-")
        or phase.startswith("P3-")
        or phase.startswith("P4-")
        or phase.startswith("P5-")
        or phase.startswith("P6-")
        or phase.startswith("P7-")
        or phase.startswith("P8-")
    ):
        failures.append(f"'phase' '{phase}' must begin with P1- through P8-")

    agent = data["agent"]
    if not isinstance(agent, str) or agent not in VALID_AGENTS:
        failures.append(f"'agent' must be one of {', '.join(VALID_AGENTS)}")

    mission_issue = validate_mission_path(data["mission"])
    if mission_issue:
        failures.append(mission_issue)

    expected_files = data["expected_files"]
    if not isinstance(expected_files, list) or len(expected_files) == 0:
        failures.append("'expected_files' must be a non-empty array")
    elif isinstance(expected_files, list):
        for i, f in enumerate(expected_files):
            issue = validate_safe_relative(f, f"expected_files[{i}]")
            if issue:
                failures.append(issue)

    result_issue = validate_ledger_output(data["result"], "result")
    if result_issue:
        failures.append(result_issue)

    events_issue = validate_ledger_output(data["events"], "events")
    if events_issue:
        failures.append(events_issue)

    timeout = data["timeout_seconds"]
    if not isinstance(timeout, int) or isinstance(timeout, bool):
        failures.append("'timeout_seconds' must be an integer")
    elif timeout < 1 or timeout > 43200:
        failures.append("'timeout_seconds' must be between 1 and 43200")

    if "allow_edits" in data and not isinstance(data["allow_edits"], bool):
        failures.append("'allow_edits' must be a boolean")

    if "notes" in data and not isinstance(data["notes"], str):
        failures.append("'notes' must be a string")

    return failures


def build_runner_command(data):
    cmd_parts = [
        "python", "scripts/platform_opencode_worker_gate.py",
        "--repo", ".",
        "--mission", data["mission"],
        "--result", data["result"],
        "--events", data["events"],
    ]
    for f in data["expected_files"]:
        cmd_parts.extend(["--expected-file", f])
    cmd_parts.extend(["--timeout-seconds", str(data["timeout_seconds"])])
    if data.get("allow_edits"):
        cmd_parts.append("--allow-edits")
    return cmd_parts


def main():
    parser = argparse.ArgumentParser(
        description="Mpango ERP Platform Agent Mission Contract Gate"
    )
    parser.add_argument("--repo", default=".", help="Path to the git repository root")
    parser.add_argument("--mission", required=True, help="Path to mission JSON file")
    parser.add_argument(
        "--print-runner-command", action="store_true",
        help="Print the platform_opencode_worker_gate.py invocation (opencode only)",
    )
    args = parser.parse_args()

    repo_path = os.path.abspath(args.repo)
    mission_path = args.mission
    if not os.path.isabs(mission_path):
        mission_path = os.path.join(repo_path, mission_path)

    print("Platform Agent Mission Contract Gate")
    print(f"Repository: {repo_path}")
    print(f"Mission:    {args.mission}")
    print()

    if not os.path.isfile(mission_path):
        print(f"FAIL mission file '{args.mission}' does not exist")
        sys.exit(1)

    try:
        with open(mission_path, "r", encoding="utf-8") as f:
            raw = f.read()
    except (IOError, OSError) as e:
        print(f"FAIL could not read mission file: {e}")
        sys.exit(1)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"FAIL malformed JSON: {e}")
        sys.exit(1)

    failures = validate_mission(data)

    if failures:
        for f in failures:
            print(f"  FAIL  {f}")
        print()
        print("=" * 50)
        print("VERDICT: FAIL")
        sys.exit(1)

    print("  PASS  phase")
    print("  PASS  agent")
    print("  PASS  mission path")
    print("  PASS  expected_files")
    print("  PASS  result path")
    print("  PASS  events path")
    print("  PASS  timeout_seconds")

    if args.print_runner_command:
        print()
        agent = data.get("agent", "")
        if agent != "opencode":
            print(f"FAIL --print-runner-command is unsupported for agent '{agent}'")
            print("VERDICT: FAIL")
            sys.exit(1)
        cmd = build_runner_command(data)
        print("Runner command:")
        print(" ".join(cmd))

    print()
    print("=" * 50)
    print("VERDICT: PASS")
    sys.exit(0)


if __name__ == "__main__":
    main()
