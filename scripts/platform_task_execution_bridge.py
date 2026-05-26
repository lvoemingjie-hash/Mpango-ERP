#!/usr/bin/env python3
"""Platform Agent Task Execution Bridge - Mpango ERP.

Consumes a P1-E run packet, validates/emits a directive, then invokes
the P1-C platform_directive_gate so post-command changed-file contract
is enforced. Intended for longer opencode/goose tasks.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
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


def validate_keep_directive_path(value):
    if not isinstance(value, str) or not value:
        return "keep-directive path must be a non-empty string"

    normalized = normalize_path(value)
    if os.path.isabs(value) or ":" in normalized.split("/")[0]:
        return f"keep-directive path '{normalized}' must be relative (no absolute or drive-letter paths)"
    if has_unsafe_path_part(normalized):
        return f"keep-directive path '{normalized}' contains unsafe path part (empty, '.', or '..')"

    forbidden, reason = is_forbidden_path(normalized)
    if forbidden:
        return f"forbidden keep-directive path '{normalized}' ({reason})"

    return None


def print_section(title):
    print(flush=True)
    print("=" * 60, flush=True)
    print(f"  {title}", flush=True)
    print("=" * 60, flush=True)


def get_script_path(name):
    return Path(__file__).resolve().parent / name


def main():
    parser = argparse.ArgumentParser(
        description="Mpango ERP Platform Task Execution Bridge"
    )
    parser.add_argument(
        "--packet", required=True, help="Path to the JSON run packet file",
    )
    parser.add_argument(
        "--repo", required=True, help="Path to the git repository root",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Validate packet and directive gate without executing command",
    )
    parser.add_argument(
        "--keep-directive",
        help="Write emitted directive to this relative repo path after packet validation",
    )
    parser.add_argument(
        "--allow-unknown-agent", action="store_true",
        help="Pass through to platform_run_packet_gate.py",
    )
    parser.add_argument(
        "--skip-agent-tool-check", action="store_true",
        help="Disable --agent-tool-check passthrough to platform_run_packet_gate.py",
    )
    args = parser.parse_args()

    repo_path = os.path.abspath(args.repo)
    packet_path = args.packet
    if not os.path.isabs(packet_path):
        packet_path = os.path.join(repo_path, packet_path)

    if args.keep_directive:
        err = validate_keep_directive_path(args.keep_directive)
        if err:
            print(f"ERROR: {err}", flush=True)
            sys.exit(1)

    keep_directive_abs = None
    if args.keep_directive:
        keep_directive_abs = os.path.join(repo_path, normalize_path(args.keep_directive))
        keep_dir = os.path.dirname(keep_directive_abs)
        if keep_dir:
            os.makedirs(keep_dir, exist_ok=True)

    tmp_dir = tempfile.mkdtemp(prefix="p1f_bridge_")
    try:
        tmp_directive = os.path.join(tmp_dir, "directive.json")

        packet_gate = get_script_path("platform_run_packet_gate.py")

        print_section("RUN PACKET GATE")

        packet_cmd = [
            sys.executable, str(packet_gate),
            "--packet", packet_path,
            "--repo", repo_path,
            "--emit-directive", tmp_directive,
        ]
        if not args.skip_agent_tool_check:
            packet_cmd.append("--agent-tool-check")
        if args.allow_unknown_agent:
            packet_cmd.append("--allow-unknown-agent")

        packet_result = subprocess.run(packet_cmd)
        if packet_result.returncode != 0:
            print()
            print_section("EXECUTION BRIDGE VERDICT")
            print("  PACKET GATE: FAIL")
            print("  DIRECTIVE GATE: SKIPPED")
            print("  BRIDGE VERDICT: FAIL")
            sys.exit(packet_result.returncode)

        if args.keep_directive:
            shutil.copy2(tmp_directive, keep_directive_abs)
            print(flush=True)
            print(f"  NOTE: --keep-directive written to '{normalize_path(args.keep_directive)}'", flush=True)
            print(f"  NOTE: This creates a changed file outside normal gate flow.", flush=True)
            print(f"  NOTE: Intended for dry-run or explicit CTO review workflows.", flush=True)

        directive_gate = get_script_path("platform_directive_gate.py")

        print_section("DIRECTIVE GATE")

        directive_cmd = [
            sys.executable, str(directive_gate),
            "--repo", repo_path,
            "--directive", tmp_directive,
        ]
        if args.dry_run:
            directive_cmd.append("--dry-run")

        directive_result = subprocess.run(directive_cmd)

        print()
        print_section("EXECUTION BRIDGE VERDICT")
        print(f"  PACKET GATE: PASS", flush=True)
        if directive_result.returncode == 0:
            print(f"  DIRECTIVE GATE: PASS", flush=True)
            print(f"  BRIDGE VERDICT: PASS", flush=True)
        else:
            print(f"  DIRECTIVE GATE: FAIL", flush=True)
            print(f"  BRIDGE VERDICT: FAIL", flush=True)
        sys.exit(directive_result.returncode)

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
