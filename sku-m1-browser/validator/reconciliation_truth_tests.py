#!/usr/bin/env python3
"""Phase-A truth tests for B3 runtime reconciliation.

These tests mutate only task-owned generated result files, then restore them
byte-for-byte. They do not start backend/frontend runtime and do not create
author-diagnostic invocation records.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
RESULTS = HARNESS / "results"
VALIDATOR = HARNESS / "validator" / "static_validator.py"

NODES = [
    ("catalog-hist-001.spec.ts", "CATALOG-HIST-001", "sku-m1-browser/tests/catalog-hist-001.spec.ts::CATALOG-HIST-001"),
    ("catalog-id-001.spec.ts", "CATALOG-ID-001", "sku-m1-browser/tests/catalog-id-001.spec.ts::CATALOG-ID-001"),
]
VIEWPORTS = ["desktop", "mobile-390"]
RESULT_FILES = [
    RESULTS / "reconciliation-in.jsonl",
    RESULTS / "reconciliation.json",
    RESULTS / "playwright-report.json",
    RESULTS / "invocation-ledger.jsonl",
]


def snapshot() -> dict[Path, bytes | None]:
    return {p: p.read_bytes() if p.exists() else None for p in RESULT_FILES}


def restore(saved: dict[Path, bytes | None]) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    for path, data in saved.items():
        if data is None:
            path.unlink(missing_ok=True)
        else:
            path.write_bytes(data)


def combo_statuses(default: str = "passed") -> dict[tuple[str, str], str]:
    return {(node, viewport): default for _, _, node in NODES for viewport in VIEWPORTS}


def write_fixtures(
    statuses: dict[tuple[str, str], str],
    *,
    report_statuses: dict[tuple[str, str], str] | None = None,
    duplicate_first_record: bool = False,
    ledger_status: str = "passed",
) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    lines = []
    for (node, viewport), status in statuses.items():
        lines.append(json.dumps({
            "schema": "sku-m1-browser/reconciliation-record/1",
            "node": node,
            "viewport": viewport,
            "status": status,
            "failure_class": "NO_FAILURE" if status == "passed" else "ASSERTION_FAILURE",
            "assertions": ["truth_fixture"],
        }))
    if duplicate_first_record:
        lines.append(lines[0])
    (RESULTS / "reconciliation-in.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

    by_node = {node: [] for _, _, node in NODES}
    for (node, viewport), status in statuses.items():
        by_node[node].append({
            "schema": "sku-m1-browser/reconciliation-record/1",
            "node": node,
            "viewport": viewport,
            "status": status,
            "failure_class": "NO_FAILURE" if status == "passed" else "ASSERTION_FAILURE",
            "assertions": ["truth_fixture"],
        })
    pass_count = sum(1 for s in statuses.values() if s == "passed")
    fail_count = sum(1 for s in statuses.values() if s == "failed")
    reconciliation = {
        "schema": "sku-m1-browser/reconciliation/1",
        "nodes": by_node,
        "errors": [],
        "accounting": {
            "required_combinations": 4,
            "pass": pass_count,
            "fail": fail_count,
            "skipped": 0,
            "not_run": 0,
            "recorded_combinations": 4,
            "duplicates": 0,
            "unknown_nodes": 0,
            "unknown_viewports": 0,
            "report_disagreements": 0,
            "playwright_without_reconciliation": 0,
            "reconciliation_without_playwright": 0,
            "gap": 0,
        },
    }
    (RESULTS / "reconciliation.json").write_text(json.dumps(reconciliation, indent=2), encoding="utf-8")

    report_statuses = report_statuses or statuses
    suites = []
    for file_name, title, node in NODES:
        suites.append({
            "file": file_name,
            "title": file_name,
            "specs": [{
                "title": title,
                "file": file_name,
                "ok": all(report_statuses[(node, vp)] == "passed" for vp in VIEWPORTS),
                "tests": [
                    {
                        "projectName": viewport,
                        "status": report_statuses[(node, viewport)],
                        "results": [{"status": report_statuses[(node, viewport)], "errors": []}],
                    }
                    for viewport in VIEWPORTS
                ],
            }],
        })
    (RESULTS / "playwright-report.json").write_text(json.dumps({"suites": suites, "errors": [], "stats": {}}, indent=2), encoding="utf-8")
    ledger = [
        {
            "schema": "sku-m1-browser/invocation-ledger/1",
            "event": "start",
            "mode": "AUTHOR_DIAGNOSTIC",
            "candidate_sha": "truth-fixture",
            "invocation_count": 1,
            "status": "started",
            "workers": 1,
            "retries": 0,
            "expected_node_count": 4,
            "observed_node_count": 0,
        },
        {
            "schema": "sku-m1-browser/invocation-ledger/1",
            "event": "end",
            "mode": "AUTHOR_DIAGNOSTIC",
            "candidate_sha": "truth-fixture",
            "invocation_count": 1,
            "status": ledger_status,
            "workers": 1,
            "retries": 0,
            "expected_node_count": 4,
            "observed_node_count": 4,
        },
    ]
    (RESULTS / "invocation-ledger.jsonl").write_text("\n".join(json.dumps(r) for r in ledger) + "\n", encoding="utf-8")


def validator() -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(VALIDATOR)], cwd=HARNESS, text=True, capture_output=True)


def require(condition: bool, label: str, detail: str = "") -> None:
    if not condition:
        print(f"  {label:<58} FAIL {detail}".rstrip())
        raise SystemExit(1)
    print(f"  {label:<58} PASS")


def main() -> int:
    saved = snapshot()
    try:
        statuses = combo_statuses()
        write_fixtures(statuses)
        green = validator()
        require(green.returncode == 0, "T00-strict-fixture-green", green.stdout)

        failed = combo_statuses()
        failed[(NODES[0][2], "desktop")] = "failed"
        write_fixtures(failed, ledger_status="failed")
        red = validator()
        require(red.returncode != 0, "T01-assertion-failure-is-fail-not-not-run")
        require("pass_fail_not_4_0" in red.stdout, "T01-fail-count-observed")
        require("skipped_or_not_run_nonzero" not in red.stdout, "T01-not-run-not-used")

        write_fixtures(statuses, duplicate_first_record=True)
        red = validator()
        require(red.returncode != 0 and "duplicate_combination" in red.stdout, "T02-duplicate-stale-record-rejected")

        report_failed = combo_statuses()
        report_failed[(NODES[1][2], "mobile-390")] = "failed"
        write_fixtures(statuses, report_statuses=report_failed, ledger_status="failed")
        red = validator()
        require(red.returncode != 0 and "report_disagreement" in red.stdout, "T03-report-reconciliation-disagreement-rejected")

        before = {p: p.read_bytes() for p in RESULT_FILES if p.exists()}
        env = os.environ.copy()
        env.pop("B3_AUTHOR_DIAGNOSTIC", None)
        listed = subprocess.run(
            ["pnpm", "exec", "playwright", "test", "--list"],
            cwd=HARNESS,
            env=env,
            text=True,
            capture_output=True,
        )
        require(listed.returncode == 0, "T04-playwright-list-succeeds")
        after = {p: p.read_bytes() for p in before}
        require(after == before, "T04-list-does-not-overwrite-runtime-evidence")

        setup = (HARNESS / "src" / "global-setup.ts").read_text(encoding="utf-8")
        runtime = (HARNESS / "src" / "runtime.ts").read_text(encoding="utf-8")
        fixtures = (HARNESS / "src" / "fixtures.ts").read_text(encoding="utf-8")
        require("clearGeneratedRuntimeOutputs();" in setup and setup.find("clearGeneratedRuntimeOutputs();") < setup.find("runPreflight("),
                "T05-stale-results-cleared-before-genuine-run")
        require("second_author_diagnostic_invocation_refused" in runtime and "existing.length >= 1" in runtime,
                "T06-second-author-diagnostic-invocation-refused")
        require("testInfo.status === 'passed' ? 'passed' : 'failed'" in fixtures,
                "T07-recorder-maps-nonpass-to-failed")
    finally:
        restore(saved)
    print("RECONCILIATION TRUTH TESTS: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
