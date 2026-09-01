#!/usr/bin/env python3
"""Reconciliation + authority-mode truth tests for the SKU browser harness.

Scope:
  * Phase-A (B3) reconciliation truth tests: mutate only task-owned generated
    result files, then restore them byte-for-byte.
  * Phase-B (B4) authority-mode truth tests: compile src/runtime.ts into an
    isolated probe worktree and drive the REAL control plane with crafted
    environment blocks and ledgers. Each probe gets its own results directory,
    so it models one fresh task worktree.

No test here starts a backend/frontend runtime and none launches a browser.
Probes never select INDEPENDENT_AUTHORITY for a real Playwright run.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
RESULTS = HARNESS / "results"
VALIDATOR = HARNESS / "validator" / "static_validator.py"
RUNTIME_SRC = HARNESS / "src" / "runtime.ts"

AUTHOR = "AUTHOR_DIAGNOSTIC"
INDEPENDENT = "INDEPENDENT_AUTHORITY"
RUNTIME_MODES = (AUTHOR, INDEPENDENT)

CANDIDATE_SHA = "b4-truth-fixture-candidate-sha"
AUTHOR_ENV = {"B3_AUTHOR_DIAGNOSTIC": "1"}
INDEPENDENT_ENV = {"B4_INDEPENDENT_AUTHORITY": "1"}

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
    RESULTS / "authority-report.json",
    RESULTS / "live-execution-contract.json",
]

PROBE_ROOT = Path(tempfile.mkdtemp(prefix="sku-m1-b4-probe-"))
COMPILED_RUNTIME: Path | None = None


# --------------------------------------------------------------------------
# result-file fixtures
# --------------------------------------------------------------------------
def snapshot() -> dict[Path, bytes | None]:
    return {p: p.read_bytes() if p.exists() else None for p in RESULT_FILES}


def restore(saved: dict[Path, bytes | None]) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    for path, data in saved.items():
        if data is None:
            path.unlink(missing_ok=True)
        else:
            path.write_bytes(data)


def snapshot_tree(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def combo_statuses(default: str = "passed") -> dict[tuple[str, str], str]:
    return {(node, viewport): default for _, _, node in NODES for viewport in VIEWPORTS}


def write_fixtures(
    statuses: dict[tuple[str, str], str],
    *,
    mode: str = INDEPENDENT,
    candidate_sha: str = CANDIDATE_SHA,
    report_statuses: dict[tuple[str, str], str] | None = None,
    duplicate_first_record: bool = False,
    ledger_status: str = "passed",
    ledger_mode: str | None = None,
    ledger_sha: str | None = None,
    contract_mode: str | None = None,
    contract_sha: str | None = None,
    authority_mode: str | None = None,
    authority_sha: str | None = None,
    report_mode: str | None = None,
    report_sha: str | None = None,
    record_mode: str | None = None,
    record_sha: str | None = None,
) -> None:
    """Write a complete, self-consistent evidence set. Every per-source mode /
    candidate-SHA override defaults to `mode` / `candidate_sha`, so a single
    override injects exactly one attributable disagreement."""
    ledger_mode = ledger_mode or mode
    ledger_sha = ledger_sha if ledger_sha is not None else candidate_sha
    contract_mode = contract_mode or mode
    contract_sha = contract_sha if contract_sha is not None else candidate_sha
    authority_mode = authority_mode or mode
    authority_sha = authority_sha if authority_sha is not None else candidate_sha
    report_mode = report_mode or mode
    report_sha = report_sha if report_sha is not None else candidate_sha
    record_mode = record_mode or mode
    record_sha = record_sha if record_sha is not None else candidate_sha

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
            "mode": record_mode,
            "candidate_sha": record_sha,
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
            "mode": record_mode,
            "candidate_sha": record_sha,
        })
    pass_count = sum(1 for s in statuses.values() if s == "passed")
    fail_count = sum(1 for s in statuses.values() if s == "failed")
    duplicates = 1 if duplicate_first_record else 0
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
            "duplicates": duplicates,
            "unknown_nodes": 0,
            "unknown_viewports": 0,
            "report_disagreements": 0,
            "playwright_without_reconciliation": 0,
            "reconciliation_without_playwright": 0,
            "mode_mismatches": 0,
            "candidate_sha_mismatches": 0,
            "gap": duplicates,
        },
    }
    (RESULTS / "reconciliation.json").write_text(json.dumps(reconciliation, indent=2), encoding="utf-8")

    report_statuses = report_statuses or statuses
    binding = {"execution_mode": report_mode, "candidate_sha": report_sha, "workers": 1, "retries": 0}
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
    (RESULTS / "playwright-report.json").write_text(json.dumps({
        "config": {
            "rootDir": str(HARNESS),
            "metadata": binding,
            "projects": [
                {"name": "desktop", "id": "desktop", "metadata": binding, "retries": 0},
                {"name": "mobile-390", "id": "mobile-390", "metadata": binding, "retries": 0},
            ],
        },
        "suites": suites,
        "errors": [],
        "stats": {},
    }, indent=2), encoding="utf-8")

    ledger = [
        {
            "schema": "sku-m1-browser/invocation-ledger/1",
            "event": "start",
            "mode": ledger_mode,
            "candidate_sha": ledger_sha,
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
            "mode": ledger_mode,
            "candidate_sha": ledger_sha,
            "invocation_count": 1,
            "status": ledger_status,
            "workers": 1,
            "retries": 0,
            "expected_node_count": 4,
            "observed_node_count": 4,
        },
    ]
    (RESULTS / "invocation-ledger.jsonl").write_text(
        "\n".join(json.dumps(r) for r in ledger) + "\n", encoding="utf-8")

    (RESULTS / "live-execution-contract.json").write_text(json.dumps({
        "schema": "sku-m1-browser/live-execution-contract/1",
        "execution_mode": contract_mode,
        "candidate_sha": contract_sha,
        "workers": 1,
        "retries": 0,
        "expected_execution_count": 4,
        "frozen_at_invocation_start": True,
    }, indent=2), encoding="utf-8")

    executions = [
        {
            "node": node,
            "viewport": viewport,
            "status": statuses[(node, viewport)],
            "failure_class": "NO_FAILURE" if statuses[(node, viewport)] == "passed" else "ASSERTION_FAILURE",
        }
        for _, _, node in NODES
        for viewport in VIEWPORTS
    ]
    (RESULTS / "authority-report.json").write_text(json.dumps({
        "schema": "sku-m1-browser/authority-report/1",
        "execution_mode": authority_mode,
        "candidate_sha": authority_sha,
        "workers": 1,
        "retries": 0,
        "expected_execution_count": 4,
        "observed_execution_count": len(executions),
        "status": ledger_status,
        "executions": executions,
    }, indent=2), encoding="utf-8")


def validator(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VALIDATOR), *args], cwd=HARNESS, text=True, capture_output=True,
    )


def require(condition: bool, label: str, detail: str = "") -> None:
    if not condition:
        print(f"  {label:<62} FAIL {detail}".rstrip())
        raise SystemExit(1)
    print(f"  {label:<62} PASS")


# --------------------------------------------------------------------------
# compiled control-plane probes (one fresh results dir per probe)
# --------------------------------------------------------------------------
def compile_runtime() -> Path:
    out = PROBE_ROOT / "build" / "src"
    out.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        ["npx", "tsc", str(RUNTIME_SRC),
         "--rootDir", str(HARNESS / "src"),
         "--outDir", str(out),
         "--module", "commonjs", "--target", "ES2022",
         "--strict", "--esModuleInterop", "--skipLibCheck", "--types", "node"],
        cwd=HARNESS, text=True, capture_output=True,
    )
    compiled = out / "runtime.js"
    if proc.returncode != 0 or not compiled.exists():
        print(f"  probe compile FAIL\n{proc.stdout}\n{proc.stderr}")
        raise SystemExit(1)
    return compiled


def fresh_probe(name: str) -> Path:
    workdir = PROBE_ROOT / name
    (workdir / "src").mkdir(parents=True, exist_ok=True)
    shutil.copy(COMPILED_RUNTIME, workdir / "src" / "runtime.js")
    return workdir


def probe(workdir: Path, body: str, env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("B3_AUTHOR_DIAGNOSTIC", None)
    env.pop("B4_INDEPENDENT_AUTHORITY", None)
    env.update(env_extra or {})
    js = workdir / "src" / "runtime.js"
    script = f"const r = require({str(js)!r});\n{body}\n"
    return subprocess.run(
        ["node", "-e", script], cwd=str(workdir), env=env, text=True, capture_output=True,
    )


def require_probe(workdir: Path, body: str, env_extra: dict[str, str] | None, label: str) -> None:
    proc = probe(workdir, body, env_extra)
    require(
        proc.returncode == 0 and proc.stdout.strip().splitlines()[-1:][0].startswith("OK")
        if proc.stdout.strip() else False,
        label,
        f"rc={proc.returncode} out={proc.stdout.strip()[:200]} err={proc.stderr.strip()[:200]}",
    )


def playwright_run(env_extra: dict[str, str] | None, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("B3_AUTHOR_DIAGNOSTIC", None)
    env.pop("B4_INDEPENDENT_AUTHORITY", None)
    env.update(env_extra or {})
    return subprocess.run(
        ["pnpm", "exec", "playwright", "test", *args],
        cwd=HARNESS, env=env, text=True, capture_output=True,
    )


# --------------------------------------------------------------------------
# tests
# --------------------------------------------------------------------------
MODE_ACCEPT_BODY = """
const mode = r.beginInvocation('probe-candidate-sha', 1, 0);
const ledger = r.readInvocationLedger();
const starts = ledger.filter((x) => x.event === 'start');
if (mode !== EXPECTED) { console.log('BAD_MODE ' + mode); process.exit(2); }
if (starts.length !== 1) { console.log('BAD_START_COUNT ' + starts.length); process.exit(3); }
if (starts[0].mode !== EXPECTED) { console.log('BAD_LEDGER_MODE ' + starts[0].mode); process.exit(4); }
if (starts[0].candidate_sha !== 'probe-candidate-sha') { console.log('BAD_LEDGER_SHA'); process.exit(5); }
if (starts[0].workers !== 1 || starts[0].retries !== 0) { console.log('BAD_WORKERS_RETRIES'); process.exit(6); }
if (r.recordedMode() !== EXPECTED) { console.log('BAD_RECORDED_MODE'); process.exit(7); }
console.log('OK ' + mode);
"""

MODE_REJECT_BODY = """
let caught = null;
try { r.beginInvocation('probe-candidate-sha', 1, 0); } catch (e) { caught = e; }
if (!caught) { console.log('NO_THROW'); process.exit(2); }
if (caught.code !== EXPECTED_CODE) { console.log('BAD_CODE ' + caught.code); process.exit(3); }
const fs = require('fs');
if (fs.existsSync(r.INVOCATION_LEDGER)) { console.log('LEDGER_WRITTEN'); process.exit(4); }
if (fs.existsSync(r.LIVE_EXECUTION_CONTRACT)) { console.log('CONTRACT_WRITTEN'); process.exit(5); }
console.log('OK ' + caught.code);
"""


def test_author_mode_accepted() -> None:
    body = MODE_ACCEPT_BODY.replace("EXPECTED", f"'{AUTHOR}'")
    require_probe(fresh_probe("t01-author-accepted"), body, AUTHOR_ENV,
                  "T01-author-mode-accepted-and-recorded")


def test_independent_mode_accepted() -> None:
    body = MODE_ACCEPT_BODY.replace("EXPECTED", f"'{INDEPENDENT}'")
    require_probe(fresh_probe("t02-independent-accepted"), body, INDEPENDENT_ENV,
                  "T02-independent-mode-accepted-and-recorded")


def test_no_mode_rejected() -> None:
    body = MODE_REJECT_BODY.replace("EXPECTED_CODE", "'mode_unset'")
    require_probe(fresh_probe("t03-no-mode"), body, None, "T03-no-mode-rejected")
    before = snapshot_tree(RESULTS)
    proc = playwright_run(None)
    require(proc.returncode != 0, "T03-no-mode-playwright-aborts", f"rc={proc.returncode}")
    require("[mode_unset]" in proc.stdout + proc.stderr, "T03-no-mode-marker-observed")
    require(snapshot_tree(RESULTS) == before, "T03-no-mode-zero-runtime-writes")


def test_both_modes_rejected() -> None:
    body = MODE_REJECT_BODY.replace("EXPECTED_CODE", "'both_modes_set'")
    env = {**AUTHOR_ENV, **INDEPENDENT_ENV}
    require_probe(fresh_probe("t04-both-modes"), body, env, "T04-both-modes-rejected")
    before = snapshot_tree(RESULTS)
    proc = playwright_run(env)
    require(proc.returncode != 0, "T04-both-modes-playwright-aborts", f"rc={proc.returncode}")
    require("[both_modes_set]" in proc.stdout + proc.stderr, "T04-both-modes-marker-observed")
    require(snapshot_tree(RESULTS) == before, "T04-both-modes-zero-runtime-writes")


def test_unknown_mode_rejected() -> None:
    body = MODE_REJECT_BODY.replace("EXPECTED_CODE", "'mode_value_unknown'")
    env = {"B4_INDEPENDENT_AUTHORITY": "YES"}
    require_probe(fresh_probe("t05-unknown-mode"), body, env, "T05-unknown-mode-value-rejected")
    before = snapshot_tree(RESULTS)
    proc = playwright_run(env)
    require(proc.returncode != 0, "T05-unknown-mode-playwright-aborts", f"rc={proc.returncode}")
    require("[mode_value_unknown]" in proc.stdout + proc.stderr, "T05-unknown-mode-marker-observed")
    require(snapshot_tree(RESULTS) == before, "T05-unknown-mode-zero-runtime-writes")

    body2 = MODE_REJECT_BODY.replace("EXPECTED_CODE", "'mode_value_unknown'")
    require_probe(fresh_probe("t05b-unknown-author"), body2, {"B3_AUTHOR_DIAGNOSTIC": "0"},
                  "T05b-unknown-author-mode-value-rejected")


def test_author_evidence_not_independent() -> None:
    write_fixtures(combo_statuses(), mode=AUTHOR)
    green = validator()
    require(green.returncode == 0, "T06a-author-evidence-self-consistent-green", green.stdout)
    required = validator("--require-mode", INDEPENDENT)
    require(required.returncode != 0, "T06b-author-evidence-fails-independent-reconciliation")
    require("required_mode_not_met" in required.stdout,
            "T06b-author-evidence-not-relabelled", required.stdout.strip()[:200])


def test_independent_evidence_not_author() -> None:
    write_fixtures(combo_statuses(), mode=INDEPENDENT)
    green = validator()
    require(green.returncode == 0, "T07a-independent-evidence-self-consistent-green", green.stdout)
    required = validator("--require-mode", AUTHOR)
    require(required.returncode != 0, "T07b-independent-evidence-fails-author-reconciliation")
    require("required_mode_not_met" in required.stdout,
            "T07b-independent-evidence-not-relabelled", required.stdout.strip()[:200])


def test_second_invocation_refused() -> None:
    body = """
const first = r.beginInvocation('probe-candidate-sha', 1, 0);
let caught = null;
try { r.beginInvocation('probe-candidate-sha', 1, 0); } catch (e) { caught = e; }
if (!caught || caught.code !== 'second_invocation_refused') {
  console.log('BAD ' + (caught && caught.code)); process.exit(2);
}
const ledger = r.readInvocationLedger();
const starts = ledger.filter((x) => x.event === 'start');
const refused = ledger.filter((x) => x.event === 'refused');
if (starts.length !== 1) { console.log('BAD_START_COUNT ' + starts.length); process.exit(3); }
if (refused.length !== 1 || refused[0].reason !== 'second_invocation_refused') {
  console.log('BAD_REFUSED ' + JSON.stringify(refused)); process.exit(4);
}
if (starts[0].mode !== first) { console.log('MODE_DRIFT'); process.exit(5); }
console.log('OK');
"""
    require_probe(fresh_probe("t08-second-invocation"), body, AUTHOR_ENV,
                  "T08-second-author-invocation-refused")
    require_probe(fresh_probe("t08b-second-invocation"), body, INDEPENDENT_ENV,
                  "T08b-second-independent-invocation-refused")


def test_cross_mode_second_invocation_refused() -> None:
    body = """
r.beginInvocation('probe-candidate-sha', 1, 0);
delete process.env.B3_AUTHOR_DIAGNOSTIC;
delete process.env.B4_INDEPENDENT_AUTHORITY;
process.env[SECOND_ENV] = '1';
let caught = null;
try { r.beginInvocation('probe-candidate-sha', 1, 0); } catch (e) { caught = e; }
if (!caught || caught.code !== 'cross_mode_invocation_refused') {
  console.log('BAD ' + (caught && caught.code)); process.exit(2);
}
const refused = r.readInvocationLedger().filter((x) => x.event === 'refused');
if (refused.length !== 1 || refused[0].reason !== 'cross_mode_invocation_refused') {
  console.log('BAD_REFUSED ' + JSON.stringify(refused)); process.exit(3);
}
console.log('OK');
"""
    require_probe(fresh_probe("t09-author-then-independent"),
                  body.replace("SECOND_ENV", "'B4_INDEPENDENT_AUTHORITY'"), AUTHOR_ENV,
                  "T09-author-then-independent-refused")
    require_probe(fresh_probe("t09b-independent-then-author"),
                  body.replace("SECOND_ENV", "'B3_AUTHOR_DIAGNOSTIC'"), INDEPENDENT_ENV,
                  "T09b-independent-then-author-refused")


def test_stale_candidate_ledger_rejected() -> None:
    body = """
r.beginInvocation('stale-other-candidate-sha', 1, 0);
let caught = null;
try { r.beginInvocation('probe-candidate-sha', 1, 0); } catch (e) { caught = e; }
if (!caught || caught.code !== 'candidate_sha_mismatch_void') {
  console.log('BAD ' + (caught && caught.code)); process.exit(2);
}
const refused = r.readInvocationLedger().filter((x) => x.event === 'refused');
if (refused.length !== 1 || refused[0].reason !== 'candidate_sha_mismatch_void') {
  console.log('BAD_REFUSED ' + JSON.stringify(refused)); process.exit(3);
}
console.log('OK');
"""
    require_probe(fresh_probe("t10-stale-sha-author"), body, AUTHOR_ENV,
                  "T10-stale-candidate-ledger-rejected-author")
    require_probe(fresh_probe("t10b-stale-sha-independent"), body, INDEPENDENT_ENV,
                  "T10b-stale-candidate-ledger-rejected-independent")


def test_recorded_mode_cannot_be_overridden() -> None:
    workdir = fresh_probe("t11-frozen-in-process")
    body = """
const mode = r.beginInvocation('probe-candidate-sha', 1, 0);
delete process.env.B3_AUTHOR_DIAGNOSTIC;
process.env.B4_INDEPENDENT_AUTHORITY = '1';
if (r.recordedMode() !== mode) { console.log('OVERRIDE ' + r.recordedMode()); process.exit(2); }
console.log('OK');
"""
    require_probe(workdir, body, AUTHOR_ENV, "T11-recorded-mode-frozen-in-process")

    # Worker-path proof: a NEW process sees the on-disk contract while the
    # environment now selects the other mode. The recorded mode must win.
    body2 = """
const mode = r.recordedMode();
if (mode !== 'AUTHOR_DIAGNOSTIC') { console.log('OVERRIDE ' + mode); process.exit(2); }
if (r.recordedCandidateSha() !== 'probe-candidate-sha') { console.log('SHA_OVERRIDE'); process.exit(3); }
console.log('OK');
"""
    probe_workdir = fresh_probe("t11b-contract-wins")
    setup = probe(
        probe_workdir,
        "const m = r.beginInvocation('probe-candidate-sha', 1, 0);\n"
        "r.writeLiveExecutionContract(m, 'probe-candidate-sha', 1, 0);\n"
        "console.log('OK');",
        AUTHOR_ENV,
    )
    require(setup.returncode == 0, "T11b-contract-written", setup.stderr[:200])
    require_probe(probe_workdir, body2, INDEPENDENT_ENV,
                  "T11b-env-cannot-override-recorded-mode")


def test_list_is_read_only() -> None:
    write_fixtures(combo_statuses(), mode=INDEPENDENT)
    before = snapshot_tree(RESULTS)
    for label, env in (
        ("no-mode", None),
        ("author", AUTHOR_ENV),
        ("independent", INDEPENDENT_ENV),
        ("both", {**AUTHOR_ENV, **INDEPENDENT_ENV}),
    ):
        listed = playwright_run(env, "--list")
        require(listed.returncode == 0, f"T12-list-succeeds-{label}", listed.stdout[-200:])
        require("Total: 4 tests in 2 files" in listed.stdout,
                f"T12-list-exactly-4-executions-{label}", listed.stdout.strip()[-200:])
        require(snapshot_tree(RESULTS) == before,
                f"T12-list-zero-runtime-writes-{label}")


def test_report_reconciliation_mode_mismatch() -> None:
    write_fixtures(combo_statuses(), mode=INDEPENDENT, record_mode=AUTHOR)
    red = validator()
    require(red.returncode != 0, "T13-report-record-mode-mismatch-rejected")
    require("mode_mismatch_across_sources" in red.stdout,
            "T13-mode-mismatch-attributed", red.stdout.strip()[:300])

    write_fixtures(combo_statuses(), mode=INDEPENDENT, report_mode=AUTHOR)
    red = validator()
    require(red.returncode != 0, "T13b-report-metadata-mode-mismatch-rejected")
    require("mode_mismatch_across_sources" in red.stdout,
            "T13b-mode-mismatch-attributed", red.stdout.strip()[:300])


def test_candidate_sha_mismatch() -> None:
    write_fixtures(combo_statuses(), mode=INDEPENDENT, report_sha="another-candidate-sha")
    red = validator()
    require(red.returncode != 0, "T14-candidate-sha-mismatch-rejected")
    require("candidate_sha_mismatch_across_sources" in red.stdout,
            "T14-sha-mismatch-attributed", red.stdout.strip()[:300])
    write_fixtures(combo_statuses(), mode=INDEPENDENT)
    require(validator().returncode == 0, "T14b-matching-sha-green")


def test_failed_execution_stays_fail_with_mode() -> None:
    statuses = combo_statuses()
    statuses[(NODES[0][2], "desktop")] = "failed"
    write_fixtures(statuses, mode=INDEPENDENT, ledger_status="failed")
    red = validator()
    require(red.returncode != 0, "T15-failed-execution-is-red")
    require("pass_fail_not_4_0" in red.stdout, "T15-fail-count-observed")
    require("skipped_or_not_run_nonzero" not in red.stdout, "T15-not-run-not-used")
    require("authority:mode_mismatch" not in red.stdout, "T15-mode-still-recorded", red.stdout.strip()[:300])
    require("authority:unknown_mode" not in red.stdout and "invocation:unknown_mode" not in red.stdout,
            "T15-mode-label-known", red.stdout.strip()[:300])
    require("report_status_not_passed" in red.stdout, "T15-authority-report-status-failed")
    required = validator("--require-mode", INDEPENDENT)
    require("required_mode_not_met" not in required.stdout,
            "T15-failed-evidence-still-independent", required.stdout.strip()[:300])
    require(required.returncode != 0, "T15-failed-evidence-red-under-required-mode")


def test_phase_a_reconciliation() -> None:
    statuses = combo_statuses()
    write_fixtures(statuses)
    green = validator()
    require(green.returncode == 0, "T00-strict-fixture-green", green.stdout)

    failed = combo_statuses()
    failed[(NODES[0][2], "desktop")] = "failed"
    write_fixtures(failed, ledger_status="failed")
    red = validator()
    require(red.returncode != 0, "T16-assertion-failure-is-fail-not-not-run")
    require("pass_fail_not_4_0" in red.stdout, "T16-fail-count-observed")
    require("skipped_or_not_run_nonzero" not in red.stdout, "T16-not-run-not-used")

    write_fixtures(statuses, duplicate_first_record=True)
    red = validator()
    require(red.returncode != 0 and "duplicate_combination" in red.stdout,
            "T17-duplicate-stale-record-rejected")

    report_failed = combo_statuses()
    report_failed[(NODES[1][2], "mobile-390")] = "failed"
    write_fixtures(statuses, report_statuses=report_failed, ledger_status="failed")
    red = validator()
    require(red.returncode != 0 and "report_disagreement" in red.stdout,
            "T18-report-reconciliation-disagreement-rejected")

    setup = (HARNESS / "src" / "global-setup.ts").read_text(encoding="utf-8")
    runtime = (HARNESS / "src" / "runtime.ts").read_text(encoding="utf-8")
    fixtures = (HARNESS / "src" / "fixtures.ts").read_text(encoding="utf-8")
    require("clearGeneratedRuntimeOutputs();" in setup
            and setup.find("clearGeneratedRuntimeOutputs();") < setup.find("runPreflight("),
            "T19-stale-results-cleared-before-genuine-run")
    require("second_invocation_refused" in runtime and "starts.length >= 1" in runtime,
            "T20-second-invocation-guard-present")
    require("testInfo.status === 'passed' ? 'passed' : 'failed'" in fixtures,
            "T21-recorder-maps-nonpass-to-failed")
    require("isAuthorDiagnosticMode" not in fixtures,
            "T21b-recorder-not-author-mode-only")


def main() -> int:
    global COMPILED_RUNTIME
    saved = snapshot()
    COMPILED_RUNTIME = compile_runtime()
    try:
        test_author_mode_accepted()
        test_independent_mode_accepted()
        test_no_mode_rejected()
        test_both_modes_rejected()
        test_unknown_mode_rejected()
        test_author_evidence_not_independent()
        test_independent_evidence_not_author()
        test_second_invocation_refused()
        test_cross_mode_second_invocation_refused()
        test_stale_candidate_ledger_rejected()
        test_recorded_mode_cannot_be_overridden()
        test_list_is_read_only()
        test_report_reconciliation_mode_mismatch()
        test_candidate_sha_mismatch()
        test_failed_execution_stays_fail_with_mode()
        test_phase_a_reconciliation()
    finally:
        restore(saved)
        shutil.rmtree(PROBE_ROOT, ignore_errors=True)
    print("RECONCILIATION TRUTH TESTS: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
