#!/usr/bin/env python3
"""Platform Mission-to-Worker Bridge - Mpango ERP."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import platform_agent_mission_gate as mission_gate
import platform_opencode_worker_gate as worker_gate


def print_section(title):
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)


def normalize_path(path):
    return path.replace("\\", "/")


def load_mission(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig")), []
    except OSError as exc:
        return None, [f"could not read mission JSON: {exc}"]
    except json.JSONDecodeError as exc:
        return None, [f"malformed mission JSON: {exc}"]


def repo_path_for(value):
    return Path(value).resolve()


def mission_path_for(repo_path, value):
    path = Path(value)
    if path.is_absolute():
        return path
    return repo_path / path


def worker_script_path(default_dir, override):
    if override:
        return Path(override)
    return default_dir / "platform_opencode_worker_gate.py"


def build_worker_command(repo_path, mission, worker_script):
    cmd = [
        sys.executable,
        str(worker_script),
        "--repo",
        str(repo_path),
        "--mission",
        mission["mission"],
        "--result",
        mission["result"],
        "--events",
        mission["events"],
        "--timeout-seconds",
        str(mission["timeout_seconds"]),
    ]
    for expected in mission["expected_files"]:
        cmd.extend(["--expected-file", expected])
    if mission.get("allow_edits"):
        cmd.append("--allow-edits")
    return cmd


def allowed_changed_files(mission):
    allowed = set(mission["expected_files"])
    allowed.add(mission["result"])
    allowed.add(mission["events"])
    return {normalize_path(item) for item in allowed}


def audit_actual_changes(repo_path, allowed):
    actual = set(worker_gate.changed_paths(repo_path))
    unexpected = sorted(actual - allowed)
    forbidden = []
    for path in sorted(actual):
        is_forbidden, reason = worker_gate.is_forbidden_path(path)
        if is_forbidden:
            forbidden.append((path, reason))
    return sorted(actual), unexpected, forbidden


def print_changed_diagnostics(actual, unexpected, forbidden):
    print("Actual changed files:")
    if actual:
        for path in actual:
            print(f"  - {path}")
    else:
        print("  (none)")

    if unexpected:
        print("Unexpected changed files:")
        for path in unexpected:
            print(f"  - {path}")

    if forbidden:
        print("Forbidden changed files:")
        for path, reason in forbidden:
            print(f"  - {path} ({reason})")


def main():
    parser = argparse.ArgumentParser(
        description="Mpango platform mission-to-worker bridge"
    )
    parser.add_argument("--repo", required=True)
    parser.add_argument("--mission", required=True)
    parser.add_argument("--worker-script")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    repo_path = repo_path_for(args.repo)
    mission_path = mission_path_for(repo_path, args.mission)
    default_script_dir = Path(__file__).resolve().parent
    worker_script = worker_script_path(default_script_dir, args.worker_script)

    print_section("MISSION VALIDATION")
    mission, issues = load_mission(mission_path)
    if issues:
        for issue in issues:
            print(f"FAIL {issue}")
        sys.exit(1)

    issues = mission_gate.validate_mission(mission)
    if issues:
        for issue in issues:
            print(f"FAIL {issue}")
        sys.exit(1)

    if mission["agent"] != "opencode":
        print(f"FAIL bridge currently supports opencode only, not '{mission['agent']}'")
        sys.exit(1)

    allowed = allowed_changed_files(mission)
    print("PASS mission contract validated")
    print("Allowed changed files:")
    for path in sorted(allowed):
        print(f"  - {path}")

    cmd = build_worker_command(repo_path, mission, worker_script)
    print_section("WORKER COMMAND")
    print(" ".join(cmd))

    if args.dry_run:
        print_section("BRIDGE VERDICT")
        print("BRIDGE VERDICT: DRY-RUN PASS")
        sys.exit(0)

    print_section("WORKER EXECUTION")
    worker_result = subprocess.run(cmd, cwd=str(repo_path))
    print(f"worker_exit={worker_result.returncode}")

    print_section("POST-COMMAND CHANGED FILE AUDIT")
    try:
        actual, unexpected, forbidden = audit_actual_changes(repo_path, allowed)
    except RuntimeError as exc:
        print(f"FAIL could not collect changed files: {exc}")
        sys.exit(1)
    print_changed_diagnostics(actual, unexpected, forbidden)

    if unexpected or forbidden:
        print_section("BRIDGE VERDICT")
        print("BRIDGE VERDICT: FAIL - changed files outside mission allowlist")
        sys.exit(1)

    if worker_result.returncode != 0:
        print_section("BRIDGE VERDICT")
        print("BRIDGE VERDICT: FAIL - worker command failed")
        sys.exit(worker_result.returncode)

    print_section("BRIDGE VERDICT")
    print("BRIDGE VERDICT: PASS")
    sys.exit(0)


if __name__ == "__main__":
    main()
