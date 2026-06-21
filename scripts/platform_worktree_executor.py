#!/usr/bin/env python3
"""Platform Worktree Execution Harness - Mpango ERP.

P16-A/B foundation. Runs a CTO-defined mission inside an isolated git worktree
with machine-readable scope (expected_files), forbidden paths, validation gates,
stop conditions, and a machine-readable completion report.

This slice is deliberately conservative: the default mode is DRY-RUN, which
constructs and prints the worktree + worker commands and validates the mission
contract WITHOUT creating a worktree or executing the worker. Real execution
requires an explicit ``--execute`` opt-in.

Design invariants (enforced here and by the test suite):

* Forbidden paths (backend/, frontend/, product-dev-recovered/, .github/,
  .claude/, docs/ai/ and the auth/rbac/tenancy/migration/payment/session
  keywords) are reused from platform_diff_auditor so this harness stays in
  lockstep with the canonical, regression-tested auditor.
* The executor may never treat a file outside ``expected_files`` as in-scope.
  The post-run audit compares every changed file against the mission allowlist;
  any unexpected or forbidden file forces a FAIL.
* Worker command failure is never swallowed: a non-zero worker exit produces a
  ``failed`` report and a non-zero process exit.
* The completion report path is validated to be relative, traversal-free, and
  confined under ``ai-ledger/platform/`` ending in ``.json`` -- it can never
  escape the platform ledger.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# Reuse the canonical, regression-tested forbidden-path rules so this harness
# can never drift from platform_diff_auditor's safety boundary.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import platform_diff_auditor as diff_auditor  # noqa: E402


REQUIRED_KEYS = [
    "phase",
    "branch",
    "base_ref",
    "worktree_dir",
    "worker_command",
    "expected_files",
    "report",
    "timeout_seconds",
]

OPTIONAL_KEYS = ["forbidden_extra", "allow_edits", "notes"]

# Report artifacts are confined here; the worktree itself is a sibling directory.
LEDGER_PREFIX = "ai-ledger/platform/"

# Default worker timeout cap matches platform_agent_mission_gate (12 hours).
MAX_TIMEOUT_SECONDS = 43200

SHA40_RE = re.compile(r"(?<![0-9A-Fa-f])[0-9A-Fa-f]{40}(?![0-9A-Fa-f])")
SHORT_SHA_LEN = 12


def shorten_shas(text):
    return SHA40_RE.sub(lambda m: m.group(0)[:SHORT_SHA_LEN], text)


def sanitize_payload(payload):
    return json.loads(shorten_shas(json.dumps(payload, indent=2)))


# ---------------------------------------------------------------------------
# Path / safety helpers
# ---------------------------------------------------------------------------

def normalize_path(p):
    return p.replace("\\", "/")


def is_absolute(path):
    normalized = normalize_path(path)
    first_part = normalized.split("/", 1)[0]
    return (
        os.path.isabs(path)
        or normalized.startswith("/")
        or ":" in first_part
    )


def is_traversal(path):
    return ".." in normalize_path(path).split("/")


def has_unsafe_path_part(path):
    parts = normalize_path(path).split("/")
    return any(part in ("", ".") for part in parts)


def is_forbidden(path):
    """Delegate to the canonical auditor.

    Returns (is_forbidden: bool, reason: str or None).
    """
    return diff_auditor.is_forbidden(path)


def validate_safe_relative(path, label):
    if not isinstance(path, str) or not path.strip():
        return f"{label} must be a non-empty string"
    if is_absolute(path):
        return f"{label} '{path}' must be relative, not absolute or drive-qualified"
    if is_traversal(path):
        return f"{label} '{path}' contains directory traversal"
    if has_unsafe_path_part(path):
        return f"{label} '{path}' contains unsafe path part"
    forbidden, reason = is_forbidden(path)
    if forbidden:
        return f"{label} '{path}' is forbidden ({reason})"
    return None


def validate_report_path(path):
    """Completion report must live under ai-ledger/platform/ and end in .json."""
    if not isinstance(path, str) or not path.strip():
        return "report must be a non-empty string"
    if is_absolute(path):
        return f"report '{path}' must be relative, not absolute or drive-qualified"
    if is_traversal(path):
        return f"report '{path}' contains directory traversal"
    if has_unsafe_path_part(path):
        return f"report '{path}' contains unsafe path part"
    normalized = normalize_path(path)
    if not normalized.startswith(LEDGER_PREFIX):
        return f"report '{path}' must be under {LEDGER_PREFIX}"
    if not normalized.endswith(".json"):
        return f"report '{path}' must end with .json"
    return None


def validate_branch_name(name):
    """Reject branch names git would refuse or that smuggle path escapes."""
    if not isinstance(name, str) or not name.strip():
        return "branch must be a non-empty string"
    if name.startswith("-"):
        return f"branch '{name}' must not start with '-'"
    if name.startswith("/"):
        return f"branch '{name}' must not start with '/'"
    if name.endswith("/"):
        return f"branch '{name}' must not end with '/'"
    if name.endswith(".lock"):
        return f"branch '{name}' must not end with '.lock'"
    if ".." in name:
        return f"branch '{name}' must not contain '..'"
    for bad in (" ", "~", "^", ":", "?", "*", "[", "\\"):
        if bad in name:
            return f"branch '{name}' must not contain '{bad}'"
    return None


def validate_worktree_dir(path):
    """Worktree dir must be relative and outside the repo's product trees.

    Worktrees are normally sibling directories (``../<name>``); that is allowed.
    Absolute / drive-qualified paths and traversal into forbidden prefixes are
    not.
    """
    if not isinstance(path, str) or not path.strip():
        return "worktree_dir must be a non-empty string"
    if is_absolute(path):
        return f"worktree_dir '{path}' must be relative, not absolute or drive-qualified"
    normalized = normalize_path(path)
    forbidden, reason = is_forbidden(normalized.lstrip("./"))
    if forbidden:
        return f"worktree_dir '{path}' is forbidden ({reason})"
    return None


# ---------------------------------------------------------------------------
# Mission parsing + validation
# ---------------------------------------------------------------------------

def parse_mission(path):
    """Load a mission JSON file. Returns (data, issues)."""
    try:
        raw = Path(path).read_text(encoding="utf-8-sig")
    except OSError as exc:
        return None, [f"could not read mission JSON: {exc}"]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, [f"malformed mission JSON: {exc}"]
    return data, []


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

    allowed_keys = set(REQUIRED_KEYS) | set(OPTIONAL_KEYS)
    for key in data:
        if key not in allowed_keys:
            failures.append(f"unknown key '{key}'")

    phase = data["phase"]
    if not isinstance(phase, str) or not phase.strip():
        failures.append("'phase' must be a non-empty string")
    elif not phase.startswith("P"):
        failures.append(f"'phase' '{phase}' must begin with 'P'")

    branch_issue = validate_branch_name(data["branch"])
    if branch_issue:
        failures.append(branch_issue)

    base_ref = data["base_ref"]
    if not isinstance(base_ref, str) or not base_ref.strip():
        failures.append("'base_ref' must be a non-empty string")
    elif base_ref.startswith("-"):
        failures.append("'base_ref' must not start with '-'")

    worktree_issue = validate_worktree_dir(data["worktree_dir"])
    if worktree_issue:
        failures.append(worktree_issue)

    worker_command = data["worker_command"]
    if not isinstance(worker_command, list) or len(worker_command) == 0:
        failures.append("'worker_command' must be a non-empty array")
    elif not all(isinstance(c, str) and c for c in worker_command):
        failures.append("'worker_command' must be an array of non-empty strings")

    expected_files = data["expected_files"]
    if not isinstance(expected_files, list) or len(expected_files) == 0:
        failures.append("'expected_files' must be a non-empty array")
    elif isinstance(expected_files, list):
        for i, f in enumerate(expected_files):
            issue = validate_safe_relative(f, f"expected_files[{i}]")
            if issue:
                failures.append(issue)

    report_issue = validate_report_path(data["report"])
    if report_issue:
        failures.append(report_issue)

    timeout = data["timeout_seconds"]
    if not isinstance(timeout, int) or isinstance(timeout, bool):
        failures.append("'timeout_seconds' must be an integer")
    elif timeout < 1 or timeout > MAX_TIMEOUT_SECONDS:
        failures.append(
            f"'timeout_seconds' must be between 1 and {MAX_TIMEOUT_SECONDS}"
        )

    if "forbidden_extra" in data:
        fe = data["forbidden_extra"]
        if not isinstance(fe, list) or not all(
            isinstance(x, str) and x for x in fe
        ):
            failures.append("'forbidden_extra' must be an array of non-empty strings")

    if "allow_edits" in data and not isinstance(data["allow_edits"], bool):
        failures.append("'allow_edits' must be a boolean")

    if "notes" in data and not isinstance(data["notes"], str):
        failures.append("'notes' must be a string")

    return failures


# ---------------------------------------------------------------------------
# Command construction
# ---------------------------------------------------------------------------

def build_worktree_command(mission):
    """Construct the git worktree add command (NOT executed by this call)."""
    return [
        "git",
        "worktree",
        "add",
        "-b",
        mission["branch"],
        mission["worktree_dir"],
        mission["base_ref"],
    ]


def build_worker_command(mission):
    """The command to run inside the worktree (verbatim from the mission)."""
    return list(mission["worker_command"])


def build_audit_command(worktree_dir, base_ref):
    """Construct the git diff --name-only used by the post-run audit."""
    return [
        "git",
        "-C",
        worktree_dir,
        "diff",
        "--name-only",
        base_ref,
        "HEAD",
    ]


# ---------------------------------------------------------------------------
# Post-run changed-file audit
# ---------------------------------------------------------------------------

def allowed_files(mission):
    """Files the worker is permitted to touch (expected_files only)."""
    return {normalize_path(f) for f in mission["expected_files"]}


def audit_against_expected(changed_files, expected_files, forbidden_extra=None):
    """Compare changed files against the expected allowlist.

    A file is a violation if it is forbidden OR not in expected_files.
    Returns dict: passed, violations, unexpected, forbidden, missing, total.
    """
    expected = {normalize_path(f) for f in expected_files}
    changed = [normalize_path(f) for f in changed_files]
    extra = [normalize_path(p) for p in (forbidden_extra or [])]

    violations = []
    unexpected = []
    forbidden_hits = []

    for path in changed:
        is_forb, reason = is_forbidden(path)
        if not is_forb and path in extra:
            is_forb, reason = True, "forbidden_extra match"
        if is_forb:
            forbidden_hits.append(path)
            violations.append({"file": path, "reason": reason})
        elif path not in expected:
            unexpected.append(path)
            violations.append({"file": path, "reason": "outside expected_files"})

    missing = sorted(expected - set(changed))
    for f in missing:
        violations.append({"file": f, "reason": "missing expected file"})

    return {
        "passed": len(violations) == 0,
        "violations": violations,
        "unexpected": sorted(unexpected),
        "forbidden": sorted(forbidden_hits),
        "missing": missing,
        "total": len(changed),
    }


def run_git(args, cwd, timeout=30):
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            cwd=str(cwd),
            timeout=timeout,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return 1, "", "timeout"
    except FileNotFoundError:
        return 1, "", "git not found"


def collect_changed_files(worktree_dir, base_sha):
    """All files differing from the immutable base_sha.

    Covers committed (base_sha..HEAD), staged, unstaged, and untracked files.
    Using an immutable SHA (not a symbolic ref) closes the committed-change
    bypass: a file the worker committed still appears here.
    """
    files = []
    for args in (
        ["diff", "--no-renames", "--name-only", base_sha, "HEAD"],
        ["diff", "--no-renames", "--name-only", "--cached"],
        ["diff", "--no-renames", "--name-only"],
        ["ls-files", "--others", "--exclude-standard"],
    ):
        rc, out, _ = run_git(args, worktree_dir)
        if rc == 0:
            files.extend(f for f in out.splitlines() if f.strip())
    seen = set()
    unique = []
    for f in files:
        if f not in seen:
            seen.add(f)
            unique.append(f)
    return unique


# ---------------------------------------------------------------------------
# Worker execution (failure is never swallowed)
# ---------------------------------------------------------------------------

def run_worker(command, cwd, timeout):
    """Run the worker. Returns (returncode, stdout, stderr, timed_out)."""
    try:
        result = subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            cwd=str(cwd),
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr, False
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout or ""
        err = exc.stderr or ""
        if isinstance(out, bytes):
            out = out.decode("utf-8", "replace")
        if isinstance(err, bytes):
            err = err.decode("utf-8", "replace")
        return 124, out, err, True
    except FileNotFoundError as exc:
        return 127, "", str(exc), False


# ---------------------------------------------------------------------------
# Completion report (confined to ai-ledger/platform/)
# ---------------------------------------------------------------------------

def build_report(mission, verdict, details):
    audit = details.get("audit") or {}
    payload = {
        "phase": mission.get("phase"),
        "branch": mission.get("branch"),
        "base_ref": mission.get("base_ref"),
        "base_sha": details.get("base_sha"),
        "worktree_dir": mission.get("worktree_dir"),
        "verdict": verdict,
        "expected_files": [normalize_path(f) for f in mission.get("expected_files", [])],
        "audit_command": details.get("audit_command"),
        "changed_files": audit.get("total", 0),
        "details": details,
    }
    return sanitize_payload(payload)


def write_report(report_path, payload, repo_path):
    """Write the completion report. The path is validated to never escape.

    Returns (abs_path, issue). issue is None on success.
    """
    issue = validate_report_path(report_path)
    if issue:
        return None, issue
    repo = Path(repo_path).resolve()
    target = repo / normalize_path(report_path)
    try:
        target.resolve().relative_to(repo / LEDGER_PREFIX)
    except ValueError:
        return None, f"report {report_path} resolves outside {LEDGER_PREFIX}"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return str(target), None


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def execute(mission, repo_path, timeout=None, write_completion=True):
    """Create the worktree at an immutable base SHA, run the worker, audit, report.

    base_ref is resolved to an immutable commit SHA (base_sha) in the parent
    repo BEFORE the worktree is created. Both git worktree add and the post-run
    audit use base_sha, so a file the worker commits cannot hide from the audit
    (closes the committed-change bypass a symbolic HEAD would allow). Worker
    failure is never swallowed; the worktree is always removed.
    """
    repo = Path(repo_path).resolve()
    timeout = timeout or mission["timeout_seconds"]
    worktree_abs = (repo / mission["worktree_dir"]).resolve()
    base_ref = mission["base_ref"]
    details = {
        "base_ref": base_ref,
        "worktree_command": build_worktree_command(mission),
        "worker_command": build_worker_command(mission),
        "worktree_path": str(worktree_abs),
    }

    # 1. Resolve base_ref to an immutable commit SHA in the parent repo.
    rc, out, err = run_git(
        ["rev-parse", "--verify", base_ref + "^{commit}"], repo
    )
    details["base_resolve"] = {"returncode": rc, "stdout": out, "stderr": err}
    if rc != 0:
        details["base_sha"] = None
        details["failure"] = "unresolved base_ref"
        payload = build_report(mission, "failed", details)
        if write_completion:
            write_report(mission["report"], payload, repo)
        return "failed", payload
    base_sha = out
    details["base_sha"] = base_sha

    # 2. Create the worktree AT the immutable base_sha (not the symbolic ref).
    rc, out, err = run_git(
        ["worktree", "add", "-b", mission["branch"],
         mission["worktree_dir"], base_sha],
        repo,
    )
    details["worktree_add"] = {"returncode": rc, "stdout": out, "stderr": err}
    if rc != 0:
        payload = build_report(mission, "failed", details)
        if write_completion:
            write_report(mission["report"], payload, repo)
        return "failed", payload

    try:
        rc, out, err, timed_out = run_worker(
            mission["worker_command"], worktree_abs, timeout
        )
        details["worker"] = {
            "returncode": rc,
            "timed_out": timed_out,
            "stdout": out,
            "stderr": err,
        }

        # 3. Audit against the immutable base_sha (surfaces committed changes).
        changed = collect_changed_files(worktree_abs, base_sha)
        audit = audit_against_expected(
            changed, mission["expected_files"], mission.get("forbidden_extra")
        )
        details["audit"] = audit
        details["audit_command"] = build_audit_command(mission["worktree_dir"], base_sha)

        if timed_out:
            verdict = "failed"
            details["failure"] = "worker timed out"
        elif rc != 0:
            verdict = "failed"
            details["failure"] = f"worker exited {rc}"
        elif not audit["passed"]:
            verdict = "failed"
            details["failure"] = "scope_violation"
        else:
            verdict = "passed"
    finally:
        run_git(["worktree", "remove", "--force", mission["worktree_dir"]], repo)

    payload = build_report(mission, verdict, details)
    if write_completion:
        write_report(mission["report"], payload, repo)
    return verdict, payload


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def print_section(title):
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Mpango ERP Platform Worktree Execution Harness"
    )
    parser.add_argument("--repo", default=".", help="Path to the git repository root")
    parser.add_argument("--mission", required=True, help="Path to mission JSON file")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run", action="store_true", default=True,
        help="Construct + print commands and validate without executing (default)",
    )
    mode.add_argument(
        "--execute", action="store_true",
        help="Create the worktree, run the worker, audit, and write a report",
    )
    parser.add_argument(
        "--print-worktree-command", action="store_true",
        help="Print the git worktree add command and exit",
    )
    args = parser.parse_args()

    repo_path = Path(args.repo).resolve()
    mission_path = Path(args.mission)
    if not mission_path.is_absolute():
        mission_path = repo_path / args.mission

    print_section("PLATFORM WORKTREE EXECUTION HARNESS")
    print(f"Repository: {repo_path}")
    print(f"Mission:    {args.mission}")

    print_section("MISSION VALIDATION")
    mission, issues = parse_mission(mission_path)
    if issues:
        for issue in issues:
            print(f"  FAIL  {issue}")
        print()
        print("VERDICT: FAIL")
        sys.exit(1)

    issues = validate_mission(mission)
    if issues:
        for issue in issues:
            print(f"  FAIL  {issue}")
        print()
        print("=" * 50)
        print("VERDICT: FAIL")
        sys.exit(1)

    print("  PASS  phase")
    print("  PASS  branch")
    print("  PASS  base_ref")
    print("  PASS  worktree_dir")
    print("  PASS  worker_command")
    print("  PASS  expected_files")
    print("  PASS  report path")
    print("  PASS  timeout_seconds")

    worktree_cmd = build_worktree_command(mission)
    worker_cmd = build_worker_command(mission)
    audit_cmd = build_audit_command(mission["worktree_dir"], mission["base_ref"])

    print_section("WORKTREE COMMAND")
    print(" ".join(worktree_cmd))
    print_section("WORKER COMMAND")
    print(" ".join(worker_cmd))
    print_section("POST-RUN AUDIT COMMAND")
    print(" ".join(audit_cmd))

    if args.print_worktree_command:
        sys.exit(0)

    if not args.execute:
        print_section("HARNESS VERDICT")
        print("HARNESS VERDICT: DRY-RUN PASS")
        sys.exit(0)

    print_section("EXECUTION")
    verdict, payload = execute(mission, repo_path)
    print(json.dumps({"verdict": verdict}, indent=2))
    if verdict == "passed":
        print_section("HARNESS VERDICT")
        print("HARNESS VERDICT: PASS")
        sys.exit(0)
    print_section("HARNESS VERDICT")
    print(f"HARNESS VERDICT: FAIL - {payload['details'].get('failure', 'failed')}")
    sys.exit(1)


if __name__ == "__main__":
    main()
