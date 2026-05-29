#!/usr/bin/env python3
"""Platform Opencode Worker Mission Gate - Mpango ERP."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


FORBIDDEN_PREFIXES = ["backend/", "frontend/", ".github/workflows/", ".claude/"]
FORBIDDEN_SPECIFIC = ["docs/ai/PHASE4_FRONTEND_CONTRACT.md"]
FORBIDDEN_FRAGMENTS = ["auth", "rbac", "tenancy", "session", "migration", "payment"]
VALID_STATUS = ["done", "failed", "partial"]
TIMEOUT_EXIT_CODE = 124


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
    if os.path.isabs(value) or ":" in normalized.split("/")[0]:
        return normalized, f"{label} '{normalized}' must be relative"
    if has_unsafe_path_part(normalized):
        return normalized, f"{label} '{normalized}' contains unsafe path part"
    forbidden, reason = is_forbidden_path(normalized)
    if forbidden:
        return normalized, f"forbidden {label} '{normalized}' ({reason})"
    return normalized, None


def validate_ledger_path(value, label, suffixes):
    normalized, issue = validate_contract_path(value, label)
    if issue:
        return normalized, issue
    if not normalized.startswith("ai-ledger/platform/"):
        return normalized, f"{label} '{normalized}' is not under ai-ledger/platform/"
    if not any(normalized.endswith(suffix) for suffix in suffixes):
        return normalized, f"{label} '{normalized}' must end in {' or '.join(suffixes)}"
    return normalized, None


def resolve_opencode(explicit=None):
    if explicit:
        return explicit if Path(explicit).is_file() else None
    appdata = os.environ.get("APPDATA", "")
    known = Path(appdata) / "npm" / "node_modules" / "opencode-ai" / "bin" / "opencode.exe"
    if known.is_file():
        return str(known)
    return shutil.which("opencode.exe") or shutil.which("opencode")


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


def validate_result(path):
    try:
        result = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, [f"could not load result JSON: {exc}"]
    issues = []
    if result.get("status") not in VALID_STATUS:
        issues.append("'status' must be one of done, failed, partial")
    files_changed = result.get("files_changed")
    if not isinstance(files_changed, list) or any(
        not isinstance(item, str) or not item for item in files_changed
    ):
        issues.append("'files_changed' must be an array of non-empty strings")
    if not isinstance(result.get("test_result"), str):
        issues.append("'test_result' must be a string")
    blocker = result.get("blocker")
    if blocker is not None and not isinstance(blocker, str):
        issues.append("'blocker' must be a string when present")
    return result, issues


def print_section(title):
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)


def run_worker(cmd, repo_path, timeout_seconds):
    start = time.monotonic()
    proc = subprocess.Popen(
        cmd,
        cwd=str(repo_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout_seconds)
        return proc.returncode, False, time.monotonic() - start, stdout, stderr
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate()
        return TIMEOUT_EXIT_CODE, True, time.monotonic() - start, stdout, stderr


def write_sanitized_events(path, stdout, stderr, rc, timed_out, elapsed):
    stdout = stdout or ""
    stderr = stderr or ""
    lines = [
        {
            "type": "opencode_invocation_summary",
            "redacted": True,
            "raw_stdout_committed": False,
            "raw_stderr_committed": False,
            "stdout_bytes": len(stdout.encode("utf-8")),
            "stderr_bytes": len(stderr.encode("utf-8")),
            "stdout_nonempty_lines": len([line for line in stdout.splitlines() if line.strip()]),
            "stderr_nonempty_lines": len([line for line in stderr.splitlines() if line.strip()]),
            "exit_code": rc,
            "timed_out": timed_out,
            "elapsed_seconds": round(elapsed, 2),
        },
        {
            "type": "opencode_event_redaction_policy",
            "redacted": True,
            "reason": "raw opencode streams may contain high-entropy session identifiers",
        },
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in lines),
        encoding="utf-8",
    )


def write_timeout_result(path, expected, actual, elapsed):
    files_changed = sorted(set(actual) & set(expected))
    result = {
        "status": "partial",
        "files_changed": files_changed,
        "test_result": f"opencode timed out after {elapsed:.2f}s before writing result JSON",
        "blocker": "timeout with missing worker result JSON",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Mpango platform opencode worker gate")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--mission", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--events", required=True)
    parser.add_argument("--expected-file", action="append", default=[])
    parser.add_argument("--timeout-seconds", type=float, default=600)
    parser.add_argument("--opencode")
    parser.add_argument("--allow-edits", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print_section("WORKER VALIDATION")
    repo_path = Path(args.repo).resolve()
    mission, issue = validate_contract_path(args.mission, "mission")
    if issue:
        print(f"FAIL {issue}")
        sys.exit(1)
    result_path, issue = validate_ledger_path(args.result, "result", [".json"])
    if issue:
        print(f"FAIL {issue}")
        sys.exit(1)
    events_path, issue = validate_ledger_path(args.events, "events", [".jsonl", ".json"])
    if issue:
        print(f"FAIL {issue}")
        sys.exit(1)
    if args.timeout_seconds <= 0:
        print("FAIL timeout must be greater than zero")
        sys.exit(1)

    expected = []
    for item in args.expected_file:
        normalized, issue = validate_contract_path(item, "expected_file")
        if issue:
            print(f"FAIL {issue}")
            sys.exit(1)
        expected.append(normalized)
    expected = sorted(set(expected))
    expected_with_gate_outputs = sorted(set(expected + [result_path, events_path]))

    opencode = resolve_opencode(args.opencode)
    if not opencode:
        print("FAIL opencode executable not found")
        sys.exit(1)

    mission_text = (repo_path / mission).read_text(encoding="utf-8-sig")
    cmd = [opencode, "run", "--pure", "--format", "json", "--dir", str(repo_path)]
    if args.allow_edits:
        cmd.append("--dangerously-skip-permissions")
    cmd.append(mission_text)
    print("PASS worker contract validated")

    print_section("OPENCODE INVOCATION")
    print(" ".join(cmd[:7] + ["<mission-text>"]))
    if args.dry_run:
        print_section("WORKER VERDICT")
        print("WORKER VERDICT: DRY-RUN PASS")
        sys.exit(0)

    rc, timed_out, elapsed, stdout, stderr = run_worker(cmd, repo_path, args.timeout_seconds)
    events_abs = repo_path / events_path
    write_sanitized_events(events_abs, stdout, stderr, rc, timed_out, elapsed)
    if stderr:
        print("stderr captured and redacted from events output")
    print(f"opencode_exit={rc} elapsed={elapsed:.2f}s timed_out={timed_out}")

    print_section("RESULT VALIDATION")
    result_abs = repo_path / result_path
    if timed_out and not result_abs.exists():
        try:
            actual_for_timeout = changed_paths(repo_path)
        except RuntimeError as exc:
            print(f"FAIL could not collect timeout changed files: {exc}")
            sys.exit(TIMEOUT_EXIT_CODE)
        write_timeout_result(result_abs, expected, actual_for_timeout, elapsed)

    result, issues = validate_result(result_abs)
    hard_failure = False
    if issues:
        for item in issues:
            print(f"FAIL {item}")
        hard_failure = True

    changed_by_worker = []
    if result is not None:
        for item in result.get("files_changed", []):
            normalized, issue = validate_contract_path(item, "files_changed")
            if issue:
                print(f"FAIL {issue}")
                hard_failure = True
                continue
            changed_by_worker.append(normalized)
        extra_reported = sorted(set(changed_by_worker) - set(expected))
        if extra_reported:
            print("FAIL files_changed outside expected: " + ", ".join(extra_reported))
            hard_failure = True
        if not hard_failure:
            print("PASS result JSON schema and files_changed allowlist")

    print_section("ARTIFACT AUDIT")
    actual = changed_paths(repo_path)
    unexpected = sorted(set(actual) - set(expected_with_gate_outputs))
    if unexpected:
        print("FAIL unexpected actual changed files: " + ", ".join(unexpected))
        hard_failure = True
    else:
        print("PASS actual changed files within expected allowlist")

    print_section("WORKER VERDICT")
    if hard_failure:
        print("WORKER VERDICT: FAIL")
        sys.exit(TIMEOUT_EXIT_CODE if rc == TIMEOUT_EXIT_CODE else 1)
    if rc == 0 and result.get("status") == "done":
        print("WORKER VERDICT: PASS")
        sys.exit(0)
    if rc == TIMEOUT_EXIT_CODE:
        print("WORKER VERDICT: TIMEOUT")
        sys.exit(TIMEOUT_EXIT_CODE)
    print("WORKER VERDICT: FAIL")
    sys.exit(rc if rc != 0 else 1)


if __name__ == "__main__":
    main()
