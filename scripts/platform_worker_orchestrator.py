#!/usr/bin/env python3
"""Platform Worker Orchestrator - Mpango ERP.

Governed execution of platform worker commands with full evidence collection.
Validates mission, runs command with timeout, captures output, writes artifacts,
and audits post-command file changes against forbidden/unexpected paths.
"""

import argparse
import json
import os
import subprocess
import sys


def normalize_path(p):
    return p.replace("\\", "/")


# ---------------------------------------------------------------------------
# Output path validation
# ---------------------------------------------------------------------------

def validate_output_path(path, label, expected_ext=None):
    """Validate an output artifact path is safe.

    Must be relative, under ai-ledger/platform/, no traversal, no forbidden
    keywords, and match the expected extension if provided.
    """
    if not path or not isinstance(path, str):
        return f"{label} path is empty or not a string"
    normalized = normalize_path(path)
    if os.path.isabs(path):
        return f"{label} '{path}' is absolute"
    if len(path) >= 2 and path[1] == ":":
        return f"{label} '{path}' is drive-qualified"
    parts = normalized.split("/")
    if ".." in parts:
        return f"{label} '{path}' contains directory traversal"
    if any(p in ("", ".") for p in parts):
        return f"{label} '{path}' contains unsafe segment"
    if not normalized.startswith("ai-ledger/platform/"):
        return f"{label} '{path}' must be under ai-ledger/platform/"
    if expected_ext and not normalized.endswith(expected_ext):
        return f"{label} '{path}' must end with {expected_ext}"
    forbidden_keywords = [
        "auth", "rbac", "tenancy", "migration", "payment", "session",
    ]
    for kw in forbidden_keywords:
        if kw in normalized.lower():
            return f"{label} '{path}' contains forbidden keyword '{kw}'"
    return None


# ---------------------------------------------------------------------------
# Mission loading and validation
# ---------------------------------------------------------------------------

def load_and_validate_mission(mission_path, repo_path):
    """Load mission JSON and validate via platform_agent_mission_gate.

    Returns (mission_dict, failures_list).
    """
    abs_mission = mission_path
    if not os.path.isabs(abs_mission):
        abs_mission = os.path.join(repo_path, abs_mission)

    if not os.path.isfile(abs_mission):
        return None, [f"mission file '{mission_path}' does not exist"]

    try:
        with open(abs_mission, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return None, [f"malformed JSON: {e}"]
    except (IOError, OSError) as e:
        return None, [f"could not read mission: {e}"]

    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, scripts_dir)
    import platform_agent_mission_gate as gate
    failures = gate.validate_mission(data)
    if failures:
        return None, failures

    return data, []


# ---------------------------------------------------------------------------
# Command execution
# ---------------------------------------------------------------------------

def run_command(command, cwd, timeout_seconds):
    """Run command with timeout.

    Returns (exit_code, stdout, stderr, timed_out).
    """
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            cwd=str(cwd),
            timeout=timeout_seconds,
        )
        return result.returncode, result.stdout, result.stderr, False
    except subprocess.TimeoutExpired as e:
        return -1, (e.stdout or "") if isinstance(e.stdout, str) else "", \
                   (e.stderr or "") if isinstance(e.stderr, str) else "", True
    except FileNotFoundError:
        return -1, "", f"command not found: {command[0] if command else 'none'}", False


# ---------------------------------------------------------------------------
# Artifact writers
# ---------------------------------------------------------------------------

def write_events(events_path, events_list):
    """Write events JSONL file."""
    os.makedirs(os.path.dirname(events_path), exist_ok=True)
    with open(events_path, "w", encoding="utf-8") as f:
        for event in events_list:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")


def write_result(result_path, data):
    """Write result JSON file."""
    os.makedirs(os.path.dirname(result_path), exist_ok=True)
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def write_report(report_path, data):
    """Write markdown orchestrator report."""
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    lines = [
        "# Platform Worker Orchestrator Report",
        "",
        f"**Phase:** {data.get('phase', 'unknown')}",
        f"**Agent:** {data.get('agent', 'unknown')}",
        f"**Status:** {data.get('status', 'unknown')}",
        f"**Exit Code:** {data.get('exit_code', 'N/A')}",
        f"**Timed Out:** {data.get('timed_out', False)}",
        "",
        "## Command",
        "```",
        " ".join(str(c) for c in data.get("command", [])),
        "```",
        "",
        "## Diff Audit",
        f"- **Expected files:** {len(data.get('expected_files', []))}",
        f"- **Changed files:** {len(data.get('changed_files', []))}",
        f"- **Forbidden violations:** {len(data.get('forbidden_violations', []))}",
        f"- **Unexpected files:** {len(data.get('unexpected_files', []))}",
        f"- **Missing files:** {len(data.get('missing_files', []))}",
        "",
    ]
    if data.get("forbidden_violations"):
        lines.append("### Forbidden Violations")
        for v in data["forbidden_violations"]:
            lines.append(f"- {v.get('file', '?')}: {v.get('reason', '?')}")
        lines.append("")
    if data.get("unexpected_files"):
        lines.append("### Unexpected Files")
        for f in data["unexpected_files"]:
            lines.append(f"- {f}")
        lines.append("")
    if data.get("missing_files"):
        lines.append("### Missing Files")
        for f in data["missing_files"]:
            lines.append(f"- {f}")
        lines.append("")
    if data.get("stdout_preview"):
        lines.append("## stdout (first 500 chars)")
        lines.append("```")
        lines.append(data["stdout_preview"][:500])
        lines.append("```")
        lines.append("")
    if data.get("stderr_preview"):
        lines.append("## stderr (first 500 chars)")
        lines.append("```")
        lines.append(data["stderr_preview"][:500])
        lines.append("```")
        lines.append("")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        f.write("\n")


# ---------------------------------------------------------------------------
# File change detection
# ---------------------------------------------------------------------------

def get_changed_files(repo_path):
    """Get files that differ between working tree and HEAD."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True, text=True,
            cwd=str(repo_path), timeout=10,
        )
        if result.returncode != 0:
            return []
        return [f for f in result.stdout.strip().splitlines() if f.strip()]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


def get_untracked_files(repo_path):
    """Get untracked files (excluding .gitignore entries)."""
    try:
        result = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            capture_output=True, text=True,
            cwd=str(repo_path), timeout=10,
        )
        if result.returncode != 0:
            return []
        return [f for f in result.stdout.strip().splitlines() if f.strip()]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


# ---------------------------------------------------------------------------
# Diff audit
# ---------------------------------------------------------------------------

def audit_files(expected_files, all_changed, repo_path):
    """Audit changed files against expected list and forbidden rules.

    Returns dict with forbidden_violations, unexpected_files, missing_files.
    """
    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, scripts_dir)
    import platform_diff_auditor as auditor

    audit_result = auditor.audit_files(all_changed)
    forbidden_violations = audit_result.get("violations", [])

    expected_set = set(normalize_path(f) for f in expected_files)
    changed_normalized = set(normalize_path(f) for f in all_changed)
    unexpected = changed_normalized - expected_set

    missing = []
    for f in expected_files:
        abs_path = os.path.join(repo_path, normalize_path(f))
        if not os.path.isfile(abs_path):
            missing.append(normalize_path(f))

    return {
        "forbidden_violations": forbidden_violations,
        "unexpected_files": sorted(unexpected),
        "missing_files": sorted(missing),
    }


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def orchestrate(repo_path, mission_path, command=None, dry_run=False,
                timeout_override=None, report_path=None):
    """Orchestrate a governed worker run.

    Contract: ALL files written by the orchestrator (result, events, report)
    are included in the final diff audit. Mission expected_files MUST cover
    worker output AND orchestrator artifacts. The audit runs AFTER all files
    are written, so no file escapes the expected_files check.

    Returns (status, events, result_data, blockers).
    """
    events = []
    blockers = []

    # --- Step 1: Load and validate mission ---
    mission, failures = load_and_validate_mission(mission_path, repo_path)
    if failures:
        events.append({
            "event": "mission_validation_failed",
            "failures": failures,
        })
        return ("FAIL", events,
                {"status": "FAIL", "failures": failures}, failures)

    events.append({
        "event": "mission_validated",
        "phase": mission["phase"],
        "agent": mission["agent"],
        "expected_files_count": len(mission["expected_files"]),
    })

    # --- Step 2: Validate output paths ---
    result_rel = normalize_path(mission["result"])
    events_rel = normalize_path(mission["events"])

    result_err = validate_output_path(result_rel, "result", ".json")
    if result_err:
        blockers.append(result_err)
        events.append({"event": "unsafe_path", "path": result_rel, "error": result_err})

    events_err = validate_output_path(events_rel, "events", ".jsonl")
    if events_err:
        blockers.append(events_err)
        events.append({"event": "unsafe_path", "path": events_rel, "error": events_err})

    if report_path:
        report_err = validate_output_path(report_path, "report", ".md")
        if report_err:
            blockers.append(report_err)
            events.append({"event": "unsafe_path", "path": report_path, "error": report_err})

    if blockers:
        events.append({"event": "orchestration_blocked", "blockers": blockers})
        return ("FAIL", events,
                {"status": "FAIL", "blockers": blockers}, blockers)

    # Resolve absolute paths
    result_abs = os.path.join(repo_path, result_rel)
    events_abs = os.path.join(repo_path, events_rel)
    report_rel = normalize_path(report_path) if report_path else \
        result_rel.replace("_result.json", "_orchestrator_report.md")
    report_abs = os.path.join(repo_path, report_rel)

    # --- Step 3: Build command if not provided ---
    if command is None:
        scripts_dir = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, scripts_dir)
        import platform_agent_mission_gate as gate
        command = gate.build_runner_command(mission)
        command[0] = sys.executable

    timeout = timeout_override or mission.get("timeout_seconds", 300)

    # --- Step 4: Dry-run artifact authorization check ---
    # In dry-run mode, if artifact paths are not in expected_files, we must
    # NOT write them (would leave unauthorized changed files).
    expected_set = set(normalize_path(f) for f in mission["expected_files"])
    artifact_paths = {result_rel, events_rel, report_rel}
    unauthorized_artifacts = artifact_paths - expected_set

    if dry_run and unauthorized_artifacts:
        for p in sorted(unauthorized_artifacts):
            blockers.append(
                f"dry-run would leave unauthorized artifact: {p}")
        events.append({
            "event": "dry_run_unauthorized",
            "unauthorized": sorted(unauthorized_artifacts),
        })
        return ("FAIL", events, {
            "status": "FAIL",
            "phase": mission["phase"],
            "agent": mission["agent"],
            "blockers": blockers,
        }, blockers)

    # --- Step 5: Run command (skip in dry-run) ---
    exit_code = 0
    stdout = ""
    stderr = ""
    timed_out = False

    if dry_run:
        events.append({
            "event": "dry_run",
            "command": command,
            "timeout": timeout,
            "result_path": result_rel,
            "events_path": events_rel,
            "report_path": report_rel,
        })
    else:
        events.append({
            "event": "command_start",
            "command": command,
            "timeout": timeout,
        })
        exit_code, stdout, stderr, timed_out = run_command(
            command, repo_path, timeout)
        events.append({
            "event": "command_end",
            "exit_code": exit_code,
            "timed_out": timed_out,
            "stdout_len": len(stdout),
            "stderr_len": len(stderr),
        })
        if timed_out:
            blockers.append(f"command timed out after {timeout}s")
        elif exit_code != 0:
            blockers.append(f"command exited with code {exit_code}")

    # --- Step 6: Write initial artifacts (BEFORE final audit) ---
    # Artifacts are written now so the final audit includes them.
    preliminary_result = {
        "status": "PENDING_AUDIT",
        "phase": mission["phase"],
        "agent": mission["agent"],
        "exit_code": exit_code,
        "timed_out": timed_out,
        "expected_files": [normalize_path(f) for f in mission["expected_files"]],
        "blockers": list(blockers),
    }
    write_events(events_abs, events)
    write_result(result_abs, preliminary_result)
    write_report(report_abs, {
        **preliminary_result,
        "command": command,
        "stdout_preview": stdout[:500] if stdout else "",
        "stderr_preview": stderr[:500] if stderr else "",
    })

    # --- Step 7: Final diff audit (AFTER all artifacts written) ---
    changed_tracked = get_changed_files(repo_path)
    changed_untracked = get_untracked_files(repo_path)
    all_changed = sorted(set(
        normalize_path(f) for f in changed_tracked + changed_untracked
    ))

    audit = audit_files(mission["expected_files"], all_changed, repo_path)

    if audit["forbidden_violations"]:
        blockers.append(
            f"{len(audit['forbidden_violations'])} forbidden file violation(s)")
    if audit["unexpected_files"]:
        sample = ", ".join(audit["unexpected_files"][:5])
        blockers.append(
            f"{len(audit['unexpected_files'])} unexpected file(s): {sample}")
    # In dry-run, worker command did not execute so expected worker output
    # may not exist on disk — skip missing_files check.
    if not dry_run and audit["missing_files"]:
        sample = ", ".join(audit["missing_files"][:5])
        blockers.append(
            f"{len(audit['missing_files'])} missing expected file(s): {sample}")

    # --- Step 8: Determine final status ---
    status = "DRY_RUN" if (dry_run and not blockers) else \
             ("PASS" if not blockers else "FAIL")

    # --- Step 9: Append audit event and finalize artifacts ---
    events.append({
        "event": "final_audit",
        "changed_files": len(all_changed),
        "forbidden_violations": len(audit["forbidden_violations"]),
        "unexpected_files": len(audit["unexpected_files"]),
        "missing_files": len(audit["missing_files"]),
        "status": status,
    })

    final_result = {
        "status": status,
        "phase": mission["phase"],
        "agent": mission["agent"],
        "exit_code": exit_code,
        "timed_out": timed_out,
        "expected_files": [normalize_path(f) for f in mission["expected_files"]],
        "changed_files": sorted(all_changed),
        "forbidden_violations": audit["forbidden_violations"],
        "unexpected_files": audit["unexpected_files"],
        "missing_files": audit["missing_files"],
        "blockers": blockers,
    }

    # Overwrite artifacts with final status and audit results
    events.append({
        "event": "artifacts_finalized",
        "result": result_rel,
        "events": events_rel,
        "report": report_rel,
    })
    write_events(events_abs, events)
    write_result(result_abs, final_result)
    write_report(report_abs, {
        **final_result,
        "command": command,
        "stdout_preview": stdout[:500] if stdout else "",
        "stderr_preview": stderr[:500] if stderr else "",
    })

    return status, events, final_result, blockers


# ---------------------------------------------------------------------------
# Human output
# ---------------------------------------------------------------------------

def format_human(status, result_data):
    """Format human-readable orchestrator summary."""
    lines = [
        "Platform Worker Orchestrator",
        "=" * 40,
        f"Status: {status}",
        f"Phase: {result_data.get('phase', 'N/A')}",
        f"Agent: {result_data.get('agent', 'N/A')}",
    ]
    if "exit_code" in result_data:
        lines.append(f"Exit Code: {result_data['exit_code']}")
    if result_data.get("timed_out"):
        lines.append("TIMED OUT")
    if result_data.get("blockers"):
        lines.append("")
        lines.append("Blockers:")
        for b in result_data["blockers"]:
            lines.append(f"  - {b}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Mpango ERP Platform Worker Orchestrator"
    )
    parser.add_argument("--repo", default=".",
                        help="Path to git repository root")
    parser.add_argument("--mission", required=True,
                        help="Path to mission JSON file")
    parser.add_argument("--command", nargs=argparse.REMAINDER, default=None,
                        help="Override worker command (must be last arg)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate only, do not execute")
    parser.add_argument("--timeout-seconds", type=int,
                        help="Override timeout in seconds")
    parser.add_argument("--report",
                        help="Explicit report path (under ai-ledger/platform/)")
    parser.add_argument("--json", action="store_true",
                        help="Output result as JSON")
    args = parser.parse_args()

    repo_path = os.path.abspath(args.repo)
    command = args.command if args.command else None

    status, events, result_data, blockers = orchestrate(
        repo_path, args.mission,
        command=command,
        dry_run=args.dry_run,
        timeout_override=args.timeout_seconds,
        report_path=args.report,
    )

    if args.json:
        print(json.dumps(result_data, indent=2, ensure_ascii=False))
    else:
        print(format_human(status, result_data))

    sys.exit(0 if status in ("PASS", "DRY_RUN") else 1)


if __name__ == "__main__":
    main()
