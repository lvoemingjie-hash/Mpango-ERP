# P5 Platform Code Build Plan

Date: 2026-05-30
Phase: P4-C planning for P5 execution
Lane: platform-dev / automation / runner / platform infra
Branch: codex/platform-p4c-code-build-plan-2026-05-30
Status: PASS after CTO polish; docs-only plan, not feature code

## Required Report Fields

| Field | Value |
|-------|-------|
| branch | `codex/platform-p4c-code-build-plan-2026-05-30` |
| commit | Pending before final commit; final commit is recorded in CTO report |
| modified files | `2026-05-30_p4c_platform_code_build_plan.md`, mission md/json, opencode result json, opencode events jsonl |
| tests | opencode bridge run, `git diff --check`, full platform harness suite, forbidden path audit, sanitized event audit, GitNexus detect_changes |
| report path | `ai-ledger/platform/2026-05-30_p4c_platform_code_build_plan.md` |
| risk | LOW for P4-C docs-only delta; P5 implementation slices are expected MEDIUM unless they edit existing harness behavior |

## P5 Objective

P5 begins real platform feature-code implementation, but only inside platform
infra, automation, runner, harness, and governance tooling.

P5 does not implement product business features. It does not touch backend
product endpoints, frontend product screens, auth, RBAC, tenancy, migrations,
payment, sessions, `.github`, `.claude`, `docs/ai`, or `product-dev-recovered`.

The desired P5 result is a small set of reusable platform CLIs that make future
agent work easier to audit, batch, and merge safely.

## Stage Plan

### P5-A: Platform Ledger Gap Audit CLI

Goal:
Create a CLI that scans `ai-ledger/platform/` and reports missing or inconsistent relationships among mission JSON, mission markdown, result JSON, events JSONL, and ledger reports.

Implementation target:

- `scripts/platform_ledger_gap_audit.py`
- `scripts/test_platform_ledger_gap_audit.py`
- `ai-ledger/platform/2026-05-31_p5a_ledger_gap_audit.md`
- P5-A mission/result/events files under `ai-ledger/platform/`

Expected result:
`python scripts/platform_ledger_gap_audit.py --repo .` exits 0 when no gaps are found and exits nonzero with a structured gap report when problems exist.

Effect / value:
Future agents and the CTO get a one-command health check for platform evidence artifacts instead of manually cross-checking ledgers.

Allowed files:
`scripts/platform_ledger_gap_audit.py`, `scripts/test_platform_ledger_gap_audit.py`, and P5-A files under `ai-ledger/platform/`.

Forbidden files:
`backend/`, `frontend/`, `product-dev-recovered/`, `.github/`, `.claude/`, `docs/ai/`, and any auth/RBAC/tenancy/migration/payment/session path.

Tests:
Add at least 10 tests covering clean ledgers, missing result, missing events, orphan markdown, malformed JSON, empty directory, duplicate mission, missing mission markdown, stale reference, and idempotent re-run.

GitNexus / impact gate:
New-file impact is expected LOW/MEDIUM. Run `detect_changes` before commit. If any existing symbol is edited, run `impact` first.

Stop conditions:
Stop if forbidden paths appear, tests fail, diff check fails, or GitNexus reports HIGH/CRITICAL.

Risk:
MEDIUM because this adds a new platform CLI and test file.

### P5-B: Platform Batch Mission Check CLI

Goal:
Create a CLI that validates all platform mission JSON files against the current mission contract.

Implementation target:

- `scripts/platform_batch_mission_check.py`
- `scripts/test_platform_batch_mission_check.py`
- `ai-ledger/platform/2026-06-01_p5b_batch_mission_check.md`
- P5-B mission/result/events files under `ai-ledger/platform/`

Expected result:
`python scripts/platform_batch_mission_check.py --repo .` exits 0 when every mission is valid and exits nonzero with per-file diagnostics when any mission is invalid.

Effect / value:
Before launching several workers, the CTO can batch-preflight all missions and catch schema drift early.

Allowed files:
`scripts/platform_batch_mission_check.py`, `scripts/test_platform_batch_mission_check.py`, and P5-B files under `ai-ledger/platform/`.

Forbidden files:
Same forbidden path set as P5-A.

Tests:
Add at least 8 tests covering all-valid, all-invalid, mixed, empty set, malformed JSON, missing required fields, unsafe paths, and JSON summary output.

GitNexus / impact gate:
If importing `platform_agent_mission_gate.py`, run impact/context review for read-only dependency assumptions. Run `detect_changes` before commit.

Stop conditions:
Stop on forbidden paths, mission gate regression, tests failing, diff check failing, or HIGH/CRITICAL GitNexus risk.

Risk:
MEDIUM because this new CLI depends on mission gate behavior.

### P5-C: Worker Reliability Summary CLI

Goal:
Create a CLI that summarizes worker outcomes from result JSON and events JSONL artifacts.

Implementation target:

- `scripts/platform_worker_reliability_summary.py`
- `scripts/test_platform_worker_reliability_summary.py`
- `ai-ledger/platform/2026-06-02_p5c_worker_reliability_summary.md`
- P5-C mission/result/events files under `ai-ledger/platform/`

Expected result:
`python scripts/platform_worker_reliability_summary.py --repo .` prints totals for success, partial, failed, timeout, elapsed seconds, sanitized-event status, and missing artifact counts.

Effect / value:
The CTO gets an operational view of opencode/goose reliability across platform phases, including timeout patterns and schema failures.

Allowed files:
`scripts/platform_worker_reliability_summary.py`, `scripts/test_platform_worker_reliability_summary.py`, and P5-C files under `ai-ledger/platform/`.

Forbidden files:
Same forbidden path set as P5-A.

Tests:
Add at least 8 tests covering all-success, all-failure, mixed outcomes, timeout-only, missing events, malformed events, empty directory, and large dataset performance.

GitNexus / impact gate:
Run `detect_changes` before commit. If importing worker gate helpers, review dependency impact.

Stop conditions:
Stop if raw event content would be committed, tests fail, forbidden paths appear, or GitNexus reports HIGH/CRITICAL.

Risk:
MEDIUM because this adds platform reporting over worker evidence artifacts.

### P5-D: Harness Index Consistency Check

Goal:
Add a check mode to the existing harness index flow so stale script/test/ledger inventory fails fast.

Implementation target:

- `scripts/platform_harness_index.py`
- `scripts/test_platform_harness_index.py`
- `ai-ledger/platform/2026-06-03_p5d_harness_index_check.md`
- P5-D mission/result/events files under `ai-ledger/platform/`

Expected result:
`python scripts/platform_harness_index.py --repo . --check` exits 0 when the current index is consistent and exits nonzero with drift diagnostics when scripts, tests, or ledgers are stale or missing.

Effect / value:
The harness index becomes enforceable, not just descriptive. Batch reviews can prove the platform tool inventory is current.

Allowed files:
`scripts/platform_harness_index.py`, `scripts/test_platform_harness_index.py`, and P5-D files under `ai-ledger/platform/`.

Forbidden files:
Same forbidden path set as P5-A.

Tests:
Add at least 6 tests covering consistent check, missing script, missing test, stale ledger, check mode no-write behavior, and fix/update behavior if a fix mode is approved.

GitNexus / impact gate:
Run `impact` before editing existing `platform_harness_index.py` symbols. Run full `test_platform_harness_index.py` and broader platform harness tests after edits.

Stop conditions:
Stop on existing behavior regression, tests failing, HIGH/CRITICAL GitNexus risk, or any product/runtime path touch.

Risk:
MEDIUM-HIGH because this edits an existing harness script. Keep behavior additive and backwards-compatible.

## Recommended Execution Order

1. P5-A Ledger Gap Audit CLI
2. P5-B Batch Mission Check CLI
3. P5-C Worker Reliability Summary CLI
4. P5-D Harness Index Consistency Check

Reasoning:
P5-A and P5-B create the evidence and mission health checks needed by later
slices. P5-C gives operational feedback on worker reliability. P5-D is last
because it edits existing harness behavior and has the highest regression risk.

## Definition Of Done

Each P5 slice is done only when:

1. The isolated branch is clean except expected files.
2. The slice ledger includes `branch`, `commit`, `modified files`, `tests`, `report path`, and `risk`.
3. Focused tests pass.
4. Relevant existing platform harness tests pass.
5. `git diff --check` passes.
6. Forbidden path audit passes.
7. GitNexus impact is run before existing symbol edits.
8. GitNexus detect_changes is reviewed before commit.
9. Worker result/events artifacts are present and sanitized.
10. CTO review accepts the scope and risk.

P5 as a whole is done when:

1. P5-A through P5-D are complete.
2. A P5 batch readiness packet summarizes all slices.
3. Full platform harness tests pass.
4. Ledger gap audit reports no blocking gaps.
5. Batch mission check reports valid missions.
6. Worker reliability summary is generated.
7. Harness index check passes.
8. CTO approves merge readiness for platform-dev.

## Worker Delegation Model

- Codex CTO writes or approves each mission.
- opencode or goose performs the bounded implementation.
- Worker output must include code, tests, ledger, result JSON, and events JSONL.
- Codex CTO reviews diffs, tests, GitNexus, forbidden paths, and evidence quality.
- The worker never merges `platform-dev`.
- Platform-dev merges happen only after CTO merge-readiness gate.

## Batch Reporting Cadence

- Per slice: run focused tests, diff check, forbidden audit, GitNexus, and ledger.
- After P5-A/P5-B: create an interim batch review packet.
- After P5-C/P5-D: create final P5 batch readiness packet.
- If any slice touches existing harness behavior, increase verification breadth.

## P4-C Verification Notes

P4-C is docs-only. It creates the code build plan and associated mission/result/events artifacts. It does not implement P5 code.

opencode execution:

- `python scripts/platform_mission_worker_bridge.py --repo . --mission ai-ledger/platform/2026-05-30_p4c_code_build_plan_mission.json`: PASS
- opencode exit: 0
- worker result validation: PASS
- bridge post-command changed-file audit: PASS

The CTO polished this plan to remove unstable non-ASCII rendering and to keep the P5 backlog strictly within platform infra / automation / runner / harness tooling.

CTO verification:

- Full platform harness suite: PASS, 16 test files
- `git diff --check`: PASS
- forbidden path audit: PASS
- sanitized event audit: PASS
- GitNexus detect_changes: pending until staged, final result recorded in CTO report
