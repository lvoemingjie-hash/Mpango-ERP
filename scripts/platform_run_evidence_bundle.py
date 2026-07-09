#!/usr/bin/env python3
"""Platform Run Evidence Bundle - Mpango ERP."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import platform_agent_mission_gate as mission_gate


FORBIDDEN_PREFIXES = ["backend/", "frontend/", ".github/", ".claude/"]
FORBIDDEN_SPECIFIC = ["docs/ai/PHASE4_FRONTEND_CONTRACT.md"]
FORBIDDEN_FRAGMENTS = ["auth", "rbac", "tenancy", "session", "migration", "payment"]
VALID_STATUS = ["done", "failed", "partial"]


def normalize_path(path):
    return path.replace("\\", "/")


def has_unsafe_path_part(path):
    return any(part in ("", ".", "..") for part in normalize_path(path).split("/"))


def is_forbidden_path(path):
    normalized = normalize_path(path)
    for prefix in FORBIDDEN_PREFIXES:
        if normalized.startswith(prefix):
            return True, f"matches forbidden prefix '{prefix}'"
    for specific in FORBIDDEN_SPECIFIC:
        if normalized == specific:
            return True, f"matches forbidden specific path '{specific}'"
    for part in normalized.split("/"):
        lowered = part.lower()
        for fragment in FORBIDDEN_FRAGMENTS:
            if fragment in lowered:
                return True, f"contains forbidden fragment '{fragment}' in '{part}'"
    return False, None


def validate_contract_path(value, label):
    if not isinstance(value, str) or not value:
        return None, f"{label} must be a non-empty string"
    normalized = normalize_path(value)
    first_part = normalized.split("/", 1)[0]
    if os.path.isabs(value) or normalized.startswith("/") or ":" in first_part:
        return normalized, f"{label} '{normalized}' must be relative"
    if has_unsafe_path_part(normalized):
        return normalized, f"{label} '{normalized}' contains unsafe path part"
    forbidden, reason = is_forbidden_path(normalized)
    if forbidden:
        return normalized, f"forbidden {label} '{normalized}' ({reason})"
    return normalized, None


def validate_ledger_path(value, label, suffix):
    normalized, issue = validate_contract_path(value, label)
    if issue:
        return normalized, issue
    if not normalized.startswith("ai-ledger/platform/"):
        return normalized, f"{label} '{normalized}' is not under ai-ledger/platform/"
    if not normalized.endswith(suffix):
        return normalized, f"{label} '{normalized}' must end in {suffix}"
    return normalized, None


def run_git(repo_path, args):
    result = subprocess.run(
        ["git"] + args,
        cwd=str(repo_path),
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def changed_paths(repo_path):
    rc, out, err = run_git(repo_path, ["status", "--porcelain=v1", "-uall"])
    if rc != 0:
        raise RuntimeError(f"git status failed: {err}")
    paths = []
    for line in out.splitlines():
        if not line:
            continue
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        paths.append(normalize_path(path.strip().strip('"')))
    return sorted(set(paths))


def load_json_file(path, label):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig")), []
    except OSError as exc:
        return None, [f"could not read {label}: {exc}"]
    except json.JSONDecodeError as exc:
        return None, [f"malformed {label}: {exc}"]


def validate_result(result):
    issues = []
    if not isinstance(result, dict):
        return ["result JSON must be an object"], []
    if result.get("status") not in VALID_STATUS:
        issues.append("'status' must be one of done, failed, partial")
    files_changed = result.get("files_changed")
    normalized_files = []
    if not isinstance(files_changed, list):
        issues.append("'files_changed' must be an array")
    else:
        for i, item in enumerate(files_changed):
            normalized, issue = validate_contract_path(item, f"files_changed[{i}]")
            if issue:
                issues.append(issue)
            else:
                normalized_files.append(normalized)
    if not isinstance(result.get("test_result"), str):
        issues.append("'test_result' must be a string")
    blocker = result.get("blocker")
    if blocker is not None and not isinstance(blocker, str):
        issues.append("'blocker' must be a string when present")
    return issues, sorted(set(normalized_files))


def read_events(path):
    diagnostics = []
    count = 0
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError as exc:
        return 0, [f"could not read events: {exc}"]
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        count += 1
        try:
            json.loads(line)
        except json.JSONDecodeError as exc:
            diagnostics.append(f"events line {line_number} malformed JSON: {exc}")
    return count, diagnostics


def write_report(output_abs, evidence):
    output_abs.parent.mkdir(parents=True, exist_ok=True)
    output_abs.write_text(render_report(evidence), encoding="utf-8")


def bullet_list(items):
    if not items:
        return "- None"
    return "\n".join(f"- `{item}`" for item in items)


def plain_list(items):
    if not items:
        return "- None"
    return "\n".join(f"- {item}" for item in items)


def render_report(evidence):
    lines = [
        "# Platform Run Evidence Bundle",
        "",
        f"**Phase:** `{evidence.get('phase', 'UNKNOWN')}`",
        f"**Agent:** `{evidence.get('agent', 'UNKNOWN')}`",
        f"**Verdict:** `{evidence['verdict']}`",
        f"**Base ref:** `{evidence['base_ref']}`",
        "",
        "## Paths",
        "",
        f"- Mission JSON: `{evidence['mission_path']}`",
        f"- Worker result: `{evidence['result_path']}`",
        f"- Worker events: `{evidence['events_path']}`",
        f"- Output bundle: `{evidence['output_path']}`",
        "",
        "## Mission Expected Files",
        "",
        bullet_list(evidence["expected_files"]),
        "",
        "## Worker Result",
        "",
        f"- Status: `{evidence['result_status']}`",
        f"- Test result: {evidence['test_result'] or 'None'}",
        f"- Blocker: {evidence['blocker'] or 'None'}",
        "",
        "### Result Files Changed",
        "",
        bullet_list(evidence["result_files_changed"]),
        "",
        "## Test Commands",
        "",
        plain_list(evidence["test_commands"]),
        "",
        "## Events",
        "",
        f"- Non-empty event lines: `{evidence['event_count']}`",
        "",
        "### Event Diagnostics",
        "",
        plain_list(evidence["event_diagnostics"]),
        "",
        "## Actual Changed Files",
        "",
        bullet_list(evidence["actual_changed_files"]),
        "",
        "## Unexpected Changed Files",
        "",
        bullet_list(evidence["unexpected_changed_files"]),
        "",
        "## Forbidden Changed Files",
        "",
        bullet_list(evidence["forbidden_changed_files"]),
        "",
        "## Validation Issues",
        "",
        plain_list(evidence["issues"]),
        "",
        f"FINAL VERDICT: {evidence['verdict']}",
        "",
    ]
    return "\n".join(lines)


def initial_evidence(args, mission_path, result_path, events_path, output_path):
    return {
        "phase": "UNKNOWN",
        "agent": "UNKNOWN",
        "mission_path": mission_path or args.mission,
        "result_path": result_path or args.result,
        "events_path": events_path or args.events,
        "output_path": output_path or args.output,
        "base_ref": args.base_ref,
        "expected_files": [],
        "result_status": "UNKNOWN",
        "test_result": "",
        "blocker": "",
        "result_files_changed": [],
        "test_commands": args.test_command or [],
        "event_count": 0,
        "event_diagnostics": [],
        "actual_changed_files": [],
        "unexpected_changed_files": [],
        "forbidden_changed_files": [],
        "issues": [],
        "verdict": "FAIL",
    }


def build_evidence(args):
    repo_path = Path(args.repo).resolve()

    output_path, output_issue = validate_ledger_path(args.output, "output", ".md")
    if output_issue:
        print(f"FAIL {output_issue}")
        return None, None, 1

    mission_path, mission_path_issue = validate_contract_path(args.mission, "mission_json")
    result_path, result_path_issue = validate_ledger_path(args.result, "result", ".json")
    events_path, events_path_issue = validate_ledger_path(args.events, "events", ".jsonl")

    evidence = initial_evidence(args, mission_path, result_path, events_path, output_path)
    path_issues = [
        issue for issue in [mission_path_issue, result_path_issue, events_path_issue]
        if issue
    ]
    evidence["issues"].extend(path_issues)

    mission = None
    if not mission_path_issue:
        mission, issues = load_json_file(repo_path / mission_path, "mission JSON")
        evidence["issues"].extend(issues)
        if mission is not None:
            mission_issues = mission_gate.validate_mission(mission)
            evidence["issues"].extend(mission_issues)
            if isinstance(mission, dict):
                evidence["phase"] = mission.get("phase", "UNKNOWN")
                evidence["agent"] = mission.get("agent", "UNKNOWN")
                if isinstance(mission.get("expected_files"), list):
                    evidence["expected_files"] = sorted(
                        set(normalize_path(item) for item in mission["expected_files"])
                    )

    result = None
    if not result_path_issue:
        result, issues = load_json_file(repo_path / result_path, "result JSON")
        evidence["issues"].extend(issues)
        if result is not None:
            result_issues, normalized_files = validate_result(result)
            evidence["issues"].extend(result_issues)
            if isinstance(result, dict):
                evidence["result_status"] = result.get("status", "UNKNOWN")
                evidence["test_result"] = result.get("test_result", "")
                evidence["blocker"] = result.get("blocker", "")
            evidence["result_files_changed"] = normalized_files

    if not events_path_issue:
        event_count, event_diagnostics = read_events(repo_path / events_path)
        evidence["event_count"] = event_count
        evidence["event_diagnostics"] = event_diagnostics
        evidence["issues"].extend(event_diagnostics)

    expected_set = set(evidence["expected_files"])
    extra_reported = sorted(set(evidence["result_files_changed"]) - expected_set)
    if extra_reported:
        evidence["issues"].append(
            "result files_changed outside expected_files: " + ", ".join(extra_reported)
        )

    if evidence["result_status"] != "done":
        evidence["issues"].append("result status is not done")

    output_abs = repo_path / output_path
    write_report(output_abs, evidence)

    try:
        actual = changed_paths(repo_path)
    except RuntimeError as exc:
        evidence["issues"].append(str(exc))
        actual = []
    evidence["actual_changed_files"] = actual

    allowed = set(evidence["expected_files"])
    if result_path:
        allowed.add(result_path)
    if events_path:
        allowed.add(events_path)
    allowed.add(output_path)

    evidence["unexpected_changed_files"] = sorted(set(actual) - allowed)
    forbidden = []
    for path in actual:
        is_forbidden, reason = is_forbidden_path(path)
        if is_forbidden:
            forbidden.append(f"{path} ({reason})")
    evidence["forbidden_changed_files"] = forbidden

    if evidence["unexpected_changed_files"]:
        evidence["issues"].append(
            "unexpected actual changed files: "
            + ", ".join(evidence["unexpected_changed_files"])
        )
    if evidence["forbidden_changed_files"]:
        evidence["issues"].append(
            "forbidden actual changed files: "
            + ", ".join(evidence["forbidden_changed_files"])
        )

    evidence["verdict"] = "PASS" if not evidence["issues"] else "FAIL"
    write_report(output_abs, evidence)
    exit_code = 0 if evidence["verdict"] == "PASS" else 1
    return evidence, output_abs, exit_code


def main():
    parser = argparse.ArgumentParser(
        description="Mpango ERP Platform Run Evidence Bundle"
    )
    parser.add_argument("--repo", required=True, help="Path to git repository")
    parser.add_argument("--mission", required=True, help="Mission JSON path")
    parser.add_argument("--result", required=True, help="Worker result JSON path")
    parser.add_argument("--events", required=True, help="Worker events JSONL path")
    parser.add_argument("--output", required=True, help="Output bundle markdown path")
    parser.add_argument("--test-command", action="append", default=[])
    parser.add_argument("--base-ref", default="HEAD")
    args = parser.parse_args()

    evidence, output_abs, exit_code = build_evidence(args)
    if evidence is None:
        sys.exit(exit_code)
    print(f"Evidence bundle: {output_abs}")
    print(f"FINAL VERDICT: {evidence['verdict']}")
    if evidence["issues"]:
        for issue in evidence["issues"]:
            print(f"FAIL {issue}")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
