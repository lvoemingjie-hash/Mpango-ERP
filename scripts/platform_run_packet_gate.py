#!/usr/bin/env python3
"""Platform Run Packet Gate - Mpango ERP.

Validates a JSON run packet given by CTO to opencode/goose before
long platform work. Can emit a platform_directive_gate-compatible
directive JSON.
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

REQUIRED_PACKET_FIELDS = [
    "phase", "branch", "agent", "report", "risk",
    "allowed_files", "expected_files", "command", "tests", "gate_only",
]

VALID_AGENTS = ["opencode", "goose", "codex"]
VALID_RISK_LEVELS = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]

DIRECTIVE_FIELDS = [
    "phase", "branch", "report", "risk", "command",
    "gate_only", "expected_files", "allow_platform_dev",
]


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


def validate_string_list(value, label, allow_empty=False):
    if not isinstance(value, list):
        return [f"'{label}' must be a list"]
    issues = []
    for i, item in enumerate(value):
        if not isinstance(item, str) or not item:
            issues.append(f"'{label}[{i}]' must be a non-empty string")
    if not allow_empty and not value:
        issues.append(f"'{label}' must be a non-empty list")
    return issues


def normalize_packet(packet):
    normalized = dict(packet)
    if isinstance(normalized.get("report"), str):
        normalized["report"] = normalize_path(normalized["report"])
    if isinstance(normalized.get("allowed_files"), list):
        normalized["allowed_files"] = [
            normalize_path(path) if isinstance(path, str) else path
            for path in normalized["allowed_files"]
        ]
    if isinstance(normalized.get("expected_files"), list):
        normalized["expected_files"] = [
            normalize_path(path) if isinstance(path, str) else path
            for path in normalized["expected_files"]
        ]
    return normalized


def get_template():
    return {
        "phase": "P1-E",
        "branch": "codex/platform-p1e-agent-run-packet-standardization-2026-05-26",
        "agent": "opencode",
        "report": "ai-ledger/platform/2026-05-26_p1e_agent_run_packet_standardization.md",
        "risk": "MEDIUM",
        "allowed_files": [
            "scripts/platform_run_packet_gate.py",
            "scripts/test_platform_run_packet_gate.py",
            "ai-ledger/platform/2026-05-26_p1e_agent_run_packet_standardization.md",
        ],
        "expected_files": [
            "scripts/platform_run_packet_gate.py",
            "scripts/test_platform_run_packet_gate.py",
            "ai-ledger/platform/2026-05-26_p1e_agent_run_packet_standardization.md",
        ],
        "command": [
            "python", "scripts/platform_run_packet_gate.py",
            "--packet", "packet.json", "--emit-directive", "directive.json",
        ],
        "tests": [
            "python scripts/test_platform_run_packet_gate.py",
        ],
        "gate_only": False,
        "allow_platform_dev": False,
        "notes": "Standardized run packet for P1-E agent task",
    }


def validate_packet(packet, repo_path, allow_unknown_agent=False):
    issues = []

    for field in REQUIRED_PACKET_FIELDS:
        if field not in packet:
            issues.append(f"missing required packet field '{field}'")

    if issues:
        return issues

    if not isinstance(packet.get("phase"), str) or not packet["phase"]:
        issues.append("'phase' must be a non-empty string")

    if not isinstance(packet.get("branch"), str) or not packet["branch"]:
        issues.append("'branch' must be a non-empty string")

    agent = packet.get("agent", "")
    if not isinstance(agent, str) or not agent:
        issues.append("'agent' must be a non-empty string")
    elif not allow_unknown_agent and agent not in VALID_AGENTS:
        issues.append(
            f"'agent' '{agent}' is not a known agent "
            f"({', '.join(VALID_AGENTS)}); "
            f"use --allow-unknown-agent to bypass"
        )

    if not isinstance(packet.get("report"), str) or not packet["report"]:
        issues.append("'report' must be a non-empty string")

    risk = packet.get("risk", "")
    if risk not in VALID_RISK_LEVELS:
        issues.append(f"'risk' must be one of {', '.join(VALID_RISK_LEVELS)}")

    if not isinstance(packet.get("command"), list):
        issues.append("'command' must be a list")
    else:
        for i, part in enumerate(packet["command"]):
            if not isinstance(part, str) or not part:
                issues.append(f"'command[{i}]' must be a non-empty string")
                break
        if not packet["command"] and not packet.get("gate_only", False):
            issues.append("command is empty but gate_only is not true")

    if not isinstance(packet.get("gate_only"), bool):
        issues.append("'gate_only' must be a boolean")

    branch = packet.get("branch", "")
    current_branch = _get_current_branch(repo_path)
    if current_branch is None:
        issues.append("could not determine current git branch")
    elif isinstance(branch, str) and branch and branch != current_branch:
        issues.append(
            f"packet branch '{branch}' does not match "
            f"current branch '{current_branch}'"
        )

    raw_report = packet.get("report", "")
    if isinstance(raw_report, str) and raw_report:
        report = normalize_path(raw_report)
        if os.path.isabs(raw_report) or ":" in report.split("/")[0]:
            issues.append(f"report '{report}' must be relative")
        elif has_unsafe_path_part(report):
            issues.append(f"report '{report}' contains unsafe path part")
        elif is_forbidden_path(report)[0]:
            issues.append(f"report '{report}' is forbidden")
        elif not report.startswith("ai-ledger/platform/"):
            issues.append(f"report '{report}' is not under ai-ledger/platform/")
        elif not report.endswith(".md"):
            issues.append(f"report '{report}' must end in .md")
    else:
        report = ""

    allowed_files = packet.get("allowed_files", [])
    expected_files = packet.get("expected_files", [])

    if not isinstance(allowed_files, list):
        issues.append("'allowed_files' must be a list")
    else:
        for f in allowed_files:
            _, issue = validate_contract_path(f, "allowed_file")
            if issue:
                issues.append(issue)

    if not isinstance(expected_files, list):
        issues.append("'expected_files' must be a list")
    else:
        for f in expected_files:
            _, issue = validate_contract_path(f, "expected_file")
            if issue:
                issues.append(issue)

    if isinstance(allowed_files, list) and isinstance(expected_files, list):
        allowed_set = set(normalize_path(f) for f in allowed_files)
        expected_set = set(normalize_path(f) for f in expected_files)

        not_allowed = expected_set - allowed_set
        if not_allowed:
            issues.append(
                "'expected_files' items not in 'allowed_files': "
                + ", ".join(sorted(not_allowed))
            )

        if report and report not in allowed_set:
            issues.append(f"report '{report}' must be in 'allowed_files'")

        if report and report not in expected_set:
            issues.append(f"report '{report}' must be in 'expected_files'")

    test_issues = validate_string_list(packet.get("tests", []), "tests")
    issues.extend(test_issues)

    if "notes" in packet:
        notes = packet["notes"]
        if isinstance(notes, list):
            issues.extend(validate_string_list(notes, "notes", allow_empty=True))
        elif not isinstance(notes, str):
            issues.append("'notes' must be a string or list of strings")

    allow_platform_dev = packet.get("allow_platform_dev", False)
    if not isinstance(allow_platform_dev, bool):
        issues.append("'allow_platform_dev' must be a boolean")
    elif packet.get("branch") == "platform-dev" and not allow_platform_dev:
        issues.append(
            "branch is 'platform-dev' but allow_platform_dev is not true"
        )
    elif packet.get("branch") != "platform-dev" and allow_platform_dev:
        issues.append("allow_platform_dev is only valid on platform-dev")

    return issues


def _get_current_branch(repo_path):
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, cwd=str(repo_path), timeout=30,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def build_directive(packet):
    directive = {}
    for field in DIRECTIVE_FIELDS:
        if field == "allow_platform_dev":
            directive[field] = packet.get(field, False)
        elif field in packet:
            directive[field] = packet[field]
    return directive


def run_toolchain_check(tool_name):
    toolchain_script = Path(__file__).resolve().parent / "platform_toolchain_gate.py"
    if not toolchain_script.exists():
        print(f"  SKIP  platform_toolchain_gate.py not found at {toolchain_script}", flush=True)
        return False

    cmd = [sys.executable, str(toolchain_script), "--tool", tool_name, "--skip-version"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    print(result.stdout, flush=True)
    if result.stderr:
        print(result.stderr, flush=True)
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(
        description="Mpango ERP Platform Run Packet Gate - validate run packets"
    )
    parser.add_argument(
        "--packet", help="Path to the JSON run packet file",
    )
    parser.add_argument(
        "--repo", default=".", help="Path to the git repository root (default: .)",
    )
    parser.add_argument(
        "--print-template", action="store_true",
        help="Print a valid JSON run packet template and exit",
    )
    parser.add_argument(
        "--emit-directive",
        help="Write normalized directive JSON to this path after validation",
    )
    parser.add_argument(
        "--agent-tool-check", action="store_true",
        help="Run platform_toolchain_gate.py for the packet agent",
    )
    parser.add_argument(
        "--allow-unknown-agent", action="store_true",
        help="Allow agent names not in the known list",
    )
    args = parser.parse_args()

    if args.print_template:
        template = get_template()
        print(json.dumps(template, indent=2))
        sys.exit(0)

    if not args.packet:
        print("ERROR: --packet PATH is required (use --print-template to see a template)", flush=True)
        sys.exit(1)

    repo_path = os.path.abspath(args.repo)

    print_section("RUN PACKET VALIDATION")

    try:
        with open(args.packet, "r", encoding="utf-8-sig") as f:
            packet = json.load(f)
    except (json.JSONDecodeError, IOError, OSError) as e:
        print(f"  FAIL  could not load packet: {e}", flush=True)
        print()
        print("=" * 50)
        print("RUN PACKET VERDICT: FAIL")
        sys.exit(1)

    issues = validate_packet(packet, repo_path, args.allow_unknown_agent)
    if issues:
        for issue in issues:
            print(f"  FAIL  {issue}", flush=True)
        print()
        print("=" * 50)
        print("RUN PACKET VERDICT: FAIL")
        sys.exit(1)

    print(f"  PASS  run packet validation passed", flush=True)

    normalized_packet = normalize_packet(packet)

    print_section("NORMALIZED RUN PACKET")
    print(json.dumps(normalized_packet, indent=2), flush=True)

    directive = build_directive(normalized_packet)
    print_section("EMITTED DIRECTIVE")
    print(json.dumps(directive, indent=2), flush=True)

    if args.emit_directive:
        dpath = os.path.abspath(args.emit_directive)
        os.makedirs(os.path.dirname(dpath) or ".", exist_ok=True)
        with open(dpath, "w", encoding="utf-8") as f:
            json.dump(directive, f, indent=2)
        print(f"\n  Directive written to: {dpath}", flush=True)

    if args.agent_tool_check:
        print_section("TOOLCHAIN CHECK")
        agent = packet.get("agent", "opencode")
        print(f"  Checking agent tool: {agent}", flush=True)
        ok = run_toolchain_check(agent)
        if ok:
            print(f"  PASS  toolchain check for '{agent}'", flush=True)
        else:
            print(f"  FAIL  toolchain check for '{agent}'", flush=True)
            print()
            print("=" * 50)
            print("RUN PACKET VERDICT: FAIL")
            sys.exit(1)

    print()
    print("=" * 50)
    print("RUN PACKET VERDICT: PASS")
    sys.exit(0)


if __name__ == "__main__":
    main()
