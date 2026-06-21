#!/usr/bin/env python3
"""Platform Worktree Batch Runner - Mpango ERP (P16-D).

A governed batch wrapper around ``platform_worktree_executor``. It lets the
platform CTO define an ordered manifest of mission JSON files, run them
sequentially through the executor (each in its own isolated git worktree), stop
safely on the first failure, and produce one auditable batch report.

This slice is deliberately conservative:

* The default mode is DRY-RUN: every mission is parsed and validated and its
  worktree/worker/audit commands are constructed through the executor, but NO
  worktree is created and NO worker runs. Real execution requires an explicit
  ``--execute`` opt-in.
* By default the batch STOPS ON THE FIRST FAILED mission; remaining missions
  are recorded as ``skipped``. ``--continue-on-failure`` runs the remaining
  missions, but the aggregate verdict is still ``failed`` if any mission failed.
* Mission paths declared in the manifest must be relative, traversal-free, and
  confined under ``ai-ledger/platform/``. The batch report path is confined the
  same way and must end in ``.json`` -- it can never escape the platform ledger.
* Worker failure is never swallowed: the executor's verdict is recorded verbatim
  and any failed mission forces a failed aggregate verdict (and a non-zero
  process exit).

The per-mission changed-file counts, verdicts, report paths, and failure reasons
are the audit record. The batch report deliberately stores NO 40-char git SHA
(only integer counts and short reason strings) so it passes detect-secrets and
can be committed directly; the executor's raw per-mission reports are
regenerable on demand (see the P16-D ledger).

Path/forbidden rules are reused from ``platform_diff_auditor`` (via the
executor) so this harness stays in lockstep with the canonical, regression-
tested auditor.
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Reuse the canonical executor + its path/forbidden helpers (no drift).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import platform_worktree_executor as exe  # noqa: E402


LEDGER_PREFIX = exe.LEDGER_PREFIX  # "ai-ledger/platform/"

REQUIRED_MANIFEST_KEYS = ["phase", "missions", "report"]
OPTIONAL_MANIFEST_KEYS = ["notes"]


# ---------------------------------------------------------------------------
# Manifest path safety (mirrors the executor's report-path rules)
# ---------------------------------------------------------------------------

def validate_mission_path(path, label="mission"):
    """A mission path declared in the manifest must live under the ledger.

    Missions are JSON contract files stored under ``ai-ledger/platform/``; they
    must be relative, traversal-free, free of unsafe parts, ledger-confined,
    and end in ``.json``.
    """
    if not isinstance(path, str) or not path.strip():
        return f"{label} must be a non-empty string"
    if exe.is_absolute(path):
        return f"{label} '{path}' must be relative, not absolute or drive-qualified"
    if exe.is_traversal(path):
        return f"{label} '{path}' contains directory traversal"
    if exe.has_unsafe_path_part(path):
        return f"{label} '{path}' contains unsafe path part"
    normalized = exe.normalize_path(path)
    if not normalized.startswith(LEDGER_PREFIX):
        return f"{label} '{path}' must be under {LEDGER_PREFIX}"
    if not normalized.endswith(".json"):
        return f"{label} '{path}' must end with .json"
    return None


def validate_batch_report_path(path):
    """The batch report path is the executor's report-path rule verbatim."""
    return exe.validate_report_path(path)


# ---------------------------------------------------------------------------
# Manifest parsing + validation
# ---------------------------------------------------------------------------

def parse_manifest(path):
    """Load a manifest JSON file. Returns (data, issues)."""
    try:
        raw = Path(path).read_text(encoding="utf-8-sig")
    except OSError as exc:
        return None, [f"could not read manifest JSON: {exc}"]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, [f"malformed manifest JSON: {exc}"]
    return data, []


def validate_manifest(data):
    """Structural validation of the manifest. Returns a list of failures."""
    failures = []

    if not isinstance(data, dict):
        failures.append("manifest JSON must be an object")
        return failures

    for key in REQUIRED_MANIFEST_KEYS:
        if key not in data:
            failures.append(f"missing required key '{key}'")
    if failures:
        return failures

    allowed_keys = set(REQUIRED_MANIFEST_KEYS) | set(OPTIONAL_MANIFEST_KEYS)
    for key in data:
        if key not in allowed_keys:
            failures.append(f"unknown key '{key}'")

    phase = data["phase"]
    if not isinstance(phase, str) or not phase.strip():
        failures.append("'phase' must be a non-empty string")
    elif not phase.startswith("P"):
        failures.append(f"'phase' '{phase}' must begin with 'P'")

    missions = data["missions"]
    if not isinstance(missions, list) or len(missions) == 0:
        failures.append("'missions' must be a non-empty array")
    elif isinstance(missions, list):
        seen = set()
        for i, mission in enumerate(missions):
            issue = validate_mission_path(mission, f"missions[{i}]")
            if issue:
                failures.append(issue)
                continue
            normalized = exe.normalize_path(mission)
            if normalized in seen:
                failures.append(
                    f"missions[{i}] '{mission}' is a duplicate mission path"
                )
            seen.add(normalized)

    report_issue = validate_batch_report_path(data["report"])
    if report_issue:
        failures.append(report_issue)

    if "notes" in data and not isinstance(data["notes"], str):
        failures.append("'notes' must be a string")

    return failures


# ---------------------------------------------------------------------------
# Per-mission execution (always goes through the executor; never swallows)
# ---------------------------------------------------------------------------

def run_mission(mission_path, repo_path, execute):
    """Run one mission through the executor. Returns a result dict.

    Worker/executor failure is recorded as a ``failed`` verdict with a reason;
    it is never swallowed and never raises. Only the verdict, report path,
    changed-file count, and failure reason are captured -- no 40-char SHA.
    """
    repo = Path(repo_path).resolve()
    if os.path.isabs(mission_path):
        mission_abs = Path(mission_path)
    else:
        mission_abs = repo / exe.normalize_path(mission_path)

    result = {
        "mission": exe.normalize_path(mission_path),
        "mode": "execute" if execute else "dry-run",
        "verdict": None,
        "report": None,
        "changed_files": None,
        "failure": None,
    }

    # 1. Parse the mission file.
    data, issues = exe.parse_mission(str(mission_abs))
    if issues:
        result["verdict"] = "failed"
        result["failure"] = "; ".join(issues)
        return result

    # 2. Validate the mission contract (the dry-run level gate).
    failures = exe.validate_mission(data)
    if failures:
        result["verdict"] = "failed"
        result["failure"] = "; ".join(failures)
        return result

    result["report"] = exe.normalize_path(data.get("report", "")) or None

    if not execute:
        # Dry-run: validation + command construction is the whole gate. Building
        # the commands proves the mission is genuinely runnable; nothing runs.
        result["verdict"] = "passed"
        return result

    # 3. Execute mode: the real executor (worktree + worker + audit + report).
    verdict, payload = exe.execute(data, repo, write_completion=True)
    result["verdict"] = verdict
    result["changed_files"] = payload.get("changed_files")
    if verdict != "passed":
        result["failure"] = payload.get("details", {}).get("failure", "failed")
    return result


def _skipped_result(mission_path, execute, reason):
    return {
        "mission": exe.normalize_path(mission_path),
        "mode": "execute" if execute else "dry-run",
        "verdict": "skipped",
        "report": None,
        "changed_files": None,
        "failure": reason,
    }


# ---------------------------------------------------------------------------
# Batch orchestration + report
# ---------------------------------------------------------------------------

def run_batch(manifest, repo_path, execute=False, continue_on_failure=False,
              write_report=True):
    """Run all missions in order through the executor.

    Returns (aggregate_verdict, payload). aggregate_verdict is ``passed`` only
    if every mission that ran passed; ``failed`` if any ran mission failed.
    The batch report is written (when write_report) to ``manifest['report']``.
    """
    repo = Path(repo_path).resolve()
    missions = manifest["missions"]
    mode = "execute" if execute else "dry-run"
    results = []
    aggregate = "passed"
    stopped_early = False

    for idx, mission_path in enumerate(missions):
        res = run_mission(mission_path, repo, execute)
        results.append(res)

        if res["verdict"] != "passed":
            aggregate = "failed"
            if not continue_on_failure:
                # stop-on-first-failure: record the rest as skipped and stop.
                stopped_early = True
                rest = missions[idx + 1:]
                for remaining in rest:
                    results.append(_skipped_result(
                        remaining, execute,
                        "skipped: earlier mission failed (stop-on-first-failure)",
                    ))
                break

    payload = build_batch_payload(
        manifest, results, mode, continue_on_failure, aggregate, stopped_early
    )
    write_issue = None
    if write_report:
        _, write_issue = write_batch_report(manifest["report"], payload, repo)
        if write_issue:
            payload["write_error"] = write_issue
    return aggregate, payload


def build_batch_payload(manifest, results, mode, continue_on_failure,
                        aggregate, stopped_early):
    """Assemble the batch report payload (no 40-char SHAs by construction)."""
    counts = {"passed": 0, "failed": 0, "skipped": 0}
    ordered = []
    for i, res in enumerate(results):
        entry = {
            "order": i,
            "mission": res["mission"],
            "mode": res["mode"],
            "verdict": res["verdict"],
            "report": res["report"],
            "changed_files": res["changed_files"],
            "failure": res["failure"],
        }
        if entry["verdict"] in counts:
            counts[entry["verdict"]] += 1
        ordered.append(entry)

    return {
        "evidence_kind": "platform_worktree_batch_report",
        "phase": manifest.get("phase"),
        "mode": mode,
        "continue_on_failure": bool(continue_on_failure),
        "aggregate_verdict": aggregate,
        "stopped_early": stopped_early,
        "total_missions": len(manifest["missions"]),
        "passed": counts["passed"],
        "failed": counts["failed"],
        "skipped": counts["skipped"],
        "report": exe.normalize_path(manifest["report"]),
        "missions": ordered,
        "notes": manifest.get("notes"),
    }


def write_batch_report(report_path, payload, repo_path):
    """Write the batch report. The path is validated to never escape.

    Returns (abs_path, issue). issue is None on success.
    """
    issue = validate_batch_report_path(report_path)
    if issue:
        return None, issue
    repo = Path(repo_path).resolve()
    target = repo / exe.normalize_path(report_path)
    try:
        target.resolve().relative_to(repo / LEDGER_PREFIX)
    except ValueError:
        return None, f"report {report_path} resolves outside {LEDGER_PREFIX}"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return str(target), None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def print_section(title):
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Mpango ERP Platform Worktree Batch Runner (P16-D)"
    )
    parser.add_argument(
        "--repo", default=".",
        help="Path to the git repository root (default: current directory)",
    )
    parser.add_argument(
        "--manifest", required=True,
        help="Path to batch manifest JSON file",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run", action="store_true", default=True,
        help="Validate + plan every mission through the executor without "
             "executing (default)",
    )
    mode.add_argument(
        "--execute", action="store_true",
        help="Run each mission through the executor (real worktrees + workers)",
    )
    parser.add_argument(
        "--continue-on-failure", action="store_true",
        help="Run remaining missions after a failure; aggregate still fails",
    )
    args = parser.parse_args(argv)

    repo_path = Path(args.repo).resolve()
    manifest_path = Path(args.manifest)
    if not manifest_path.is_absolute():
        manifest_path = repo_path / args.manifest

    execute = args.execute
    on_failure = "CONTINUE" if args.continue_on_failure else "STOP"

    print_section("PLATFORM WORKTREE BATCH RUNNER")
    print(f"Repository: {repo_path}")
    print(f"Manifest:   {args.manifest}")
    print(f"Mode:       {'EXECUTE' if execute else 'DRY-RUN'}")
    print(f"On failure: {on_failure}")

    # 1. Manifest parse + structural validation.
    manifest, issues = parse_manifest(str(manifest_path))
    if issues:
        print_section("MANIFEST VALIDATION")
        for issue in issues:
            print(f"  FAIL  {issue}")
        print("\nVERDICT: FAIL (manifest invalid)")
        return 1

    failures = validate_manifest(manifest)
    if failures:
        print_section("MANIFEST VALIDATION")
        for failure in failures:
            print(f"  FAIL  {failure}")
        print("\nVERDICT: FAIL (manifest invalid)")
        return 1

    print_section("MANIFEST VALIDATION")
    print("  PASS  phase")
    print(f"  PASS  missions ({len(manifest['missions'])}, ordered)")
    print("  PASS  report path (under ai-ledger/platform/, .json)")

    print(f"\nMissions:   {len(manifest['missions'])} (ordered)")
    for i, mission in enumerate(manifest["missions"]):
        print(f"  [{i}] {mission}")
    print(f"Report:      {manifest['report']}")

    # 2. Run the batch through the executor.
    print_section("BATCH EXECUTION")
    aggregate, payload = run_batch(
        manifest, repo_path,
        execute=execute,
        continue_on_failure=args.continue_on_failure,
        write_report=True,
    )

    for entry in payload["missions"]:
        marker = {"passed": "PASS ", "failed": "FAIL ", "skipped": "SKIP "}.get(
            entry["verdict"], "????"
        )
        line = f"  [{entry['order']}] {marker}{entry['verdict']:7s} {entry['mission']}"
        if entry["verdict"] == "failed" and entry["failure"]:
            line += f"  -- {entry['failure']}"
        print(line)

    print()
    print(json.dumps({
        "aggregate_verdict": aggregate,
        "mode": payload["mode"],
        "continue_on_failure": payload["continue_on_failure"],
        "passed": payload["passed"],
        "failed": payload["failed"],
        "skipped": payload["skipped"],
        "stopped_early": payload["stopped_early"],
        "report": payload["report"],
    }, indent=2))

    if aggregate == "passed":
        print_section("BATCH VERDICT: PASS")
        return 0
    print_section("BATCH VERDICT: FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
