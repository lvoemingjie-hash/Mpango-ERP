# P8 Governed Worker Orchestrator

**Date**: 2026-06-04
**Agent**: claude
**Branch**: codex/platform-p8-governed-worker-orchestrator-2026-06-04
**Base**: platform-dev (6c1f982)
**Phase**: P8-A

---

## Objective

Build the platform layer's first real function orchestrator. A governed execution engine that validates missions, runs worker commands with timeout and evidence collection, captures stdout/stderr/exit code, writes result/events/report artifacts, and audits post-command file changes. Also fixes merge readiness reporter to detect merge commit context and use smart base ref resolution.

## Scope

1. **P8-A Platform Worker Orchestrator** - Governed execution engine. Validates mission via `platform_agent_mission_gate`, supports `--dry-run`, runs worker command with timeout, captures stdout/stderr/exit code, writes events JSONL + result JSON + markdown report, runs post-command diff audit, fails on nonzero exit / timeout / forbidden files / unexpected changed files / missing expected artifacts / unsafe output paths.
2. **Merge Readiness Reporter Fix** - Add `detect_merge_commit()` and `smart_base_ref()`. Reporter now detects merge commits and resolves the best base ref automatically (merge parent, origin/platform-dev, or HEAD~1 fallback). Adds `merge_context` and `resolved_base_ref` to report output.
3. **Mission Gate P8 Expansion** - Phase validation accepts P1-P8.

## Expected Artifacts

- `scripts/platform_worker_orchestrator.py` + `scripts/test_platform_worker_orchestrator.py` (35 tests)
- `scripts/platform_merge_readiness_reporter.py` (modified: merge context detection)
- `scripts/platform_agent_mission_gate.py` (modified: P8 phase acceptance)
- `scripts/test_platform_agent_mission_gate.py` (modified: P8 test, P9 rejection)
- `ai-ledger/platform/2026-06-04_p8_governed_worker_orchestrator.md` (this file)
- `ai-ledger/platform/2026-06-04_p8_governed_worker_orchestrator_mission.json`
- `ai-ledger/platform/2026-06-04_p8_governed_worker_orchestrator_result.json`
- `ai-ledger/platform/2026-06-04_p8_governed_worker_orchestrator_events.jsonl`
- `ai-ledger/platform/2026-06-04_p8_merge_readiness_report.md`

## Out of Scope

- No backend/frontend/product code changes.
- No `.github/`, `.claude/`, `docs/ai/`, auth/RBAC/tenancy/migration/payment/session paths.
- No merge to platform-dev (isolated branch only).

## Commit History

| Commit | Description |
|--------|-------------|
| 22d73f1 | feat(platform): P8 governed worker orchestrator |
| 22324a3 | docs(platform): P8 evidence commit chain update |
| cead48d | docs(platform): P8 evidence alignment - 10 expected files |
| 8f090f3 | docs(platform): P8 final commit chain closure |
| (pending) | fix(platform): P8-R1 artifact audit contract fix |

## Evidence Strategy

- The `result.json` `commit_chain` field records the full commit history.
- A self-referential SHA is not used (circular).
- Live merge gate must regenerate the report after merge candidate checkout.
- **R1 fix**: Orchestrator artifacts (result, events, report) are written BEFORE the final diff audit. The audit covers ALL changed files including orchestrator's own output. No file escapes the expected_files check.

## Changed Files vs origin/platform-dev (10 files)

| # | File |
|---|------|
| 1 | `scripts/platform_worker_orchestrator.py` |
| 2 | `scripts/test_platform_worker_orchestrator.py` |
| 3 | `scripts/platform_merge_readiness_reporter.py` |
| 4 | `scripts/platform_agent_mission_gate.py` |
| 5 | `scripts/test_platform_agent_mission_gate.py` |
| 6 | `ai-ledger/platform/2026-06-04_p8_governed_worker_orchestrator.md` |
| 7 | `ai-ledger/platform/2026-06-04_p8_governed_worker_orchestrator_mission.json` |
| 8 | `ai-ledger/platform/2026-06-04_p8_governed_worker_orchestrator_result.json` |
| 9 | `ai-ledger/platform/2026-06-04_p8_governed_worker_orchestrator_events.jsonl` |
| 10 | `ai-ledger/platform/2026-06-04_p8_merge_readiness_report.md` |
