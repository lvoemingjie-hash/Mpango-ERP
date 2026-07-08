#!/usr/bin/env python3
"""Platform Runner Gate - Mpango ERP.

Invokes the platform agent preflight and, if it passes, executes
the requested command. Runner-grade: report is mandatory.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


def resolve_preflight_script():
    return Path(__file__).resolve().parent / "platform_agent_preflight.py"


def print_section(title):
    print(flush=True)
    print("=" * 60, flush=True)
    print(f"  {title}", flush=True)
    print("=" * 60, flush=True)


def main():
    parser = argparse.ArgumentParser(
        description="Mpango ERP Platform Runner Gate - preflight then command"
    )
    parser.add_argument(
        "--repo",
        required=True,
        help="Path to the git repository root",
    )
    parser.add_argument(
        "--report",
        required=True,
        help="Path to the report file (runner-grade: mandatory)",
    )
    parser.add_argument(
        "--allow-platform-dev",
        action="store_true",
        help=(
            "Allow 'platform-dev' branch "
            "(passes through to platform_agent_preflight.py)"
        ),
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="Optional command after -- to execute if preflight passes",
    )

    args = parser.parse_args()
    repo_path = os.path.abspath(args.repo)
    preflight_script = resolve_preflight_script()

    if not preflight_script.exists():
        print(f"ERROR: preflight script not found at {preflight_script}")
        sys.exit(1)

    if args.command and args.command[0] == "--":
        args.command = args.command[1:]

    report_path = args.report
    if not os.path.isabs(report_path):
        report_path = os.path.normpath(os.path.join(repo_path, report_path))

    preflight_cmd = [
        sys.executable,
        str(preflight_script),
        "--repo", repo_path,
        "--report", report_path,
        "--require-report",
    ]
    if args.allow_platform_dev:
        preflight_cmd.append("--allow-platform-dev")

    print_section("PREFLIGHT CHECK")
    print(f"  Command: {' '.join(preflight_cmd)}", flush=True)
    print(flush=True)

    result = subprocess.run(preflight_cmd)

    print()
    print_section("RUNNER VERDICT")
    if result.returncode != 0:
        print(f"  PREFLIGHT: FAIL (exit {result.returncode})", flush=True)
        print("  Verdict: BLOCKED - command will NOT be executed", flush=True)
        sys.exit(result.returncode)

    print(f"  PREFLIGHT: PASS", flush=True)
    if args.command:
        print(f"  COMMAND: {' '.join(args.command)}", flush=True)
    else:
        print("  COMMAND: (none - gate-only mode)", flush=True)

    if args.command:
        print()
        print_section("RUNNER COMMAND EXECUTION")
        print(f"  Running: {' '.join(args.command)}", flush=True)
        print(flush=True)
        cmd_result = subprocess.run(args.command, cwd=repo_path)
        if cmd_result.returncode == 0:
            print(f"  COMMAND: PASS (exit {cmd_result.returncode})", flush=True)
        else:
            print(f"  COMMAND: FAIL (exit {cmd_result.returncode})", flush=True)
        sys.exit(cmd_result.returncode)

    print("  Verdict: PASS - gate-only mode, no command to execute", flush=True)
    sys.exit(0)


if __name__ == "__main__":
    main()
