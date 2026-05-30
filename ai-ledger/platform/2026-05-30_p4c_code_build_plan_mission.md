# P4-C Platform Code Build Plan Mission

You are opencode acting as the platform worker for Mpango ERP.

## Role

Create a docs-only P5 platform code build plan. This is still P4 preparation;
do not implement feature code.

## Scope Boundary

P5 platform code means platform infra / automation / runner / harness tooling
only. Do not plan backend product features, frontend product features, auth,
RBAC, tenancy, migrations, payment, or business logic.

## Allowed Files

You may create or modify only:

- `ai-ledger/platform/2026-05-30_p4c_platform_code_build_plan.md`
- `ai-ledger/platform/2026-05-30_p4c_code_build_plan_mission.md`
- `ai-ledger/platform/2026-05-30_p4c_code_build_plan_mission.json`
- `ai-ledger/platform/2026-05-30_p4c_opencode_result.json`
- `ai-ledger/platform/2026-05-30_p4c_opencode_events.jsonl`

## Forbidden

- No `scripts/` edits in this P4-C planning task.
- No backend or frontend edits.
- No product runtime edits.
- No auth, RBAC, tenancy, migration, payment, or session edits.
- No `.github`, `.claude`, or `docs/ai` edits.
- Do not modify `product-dev-recovered`.

## Deliverable

Write `ai-ledger/platform/2026-05-30_p4c_platform_code_build_plan.md`.

The plan must be operational and include:

1. P5 objective.
2. Stage table with at least 4 stages.
3. For every stage:
   - phase name
   - goal
   - implementation target
   - expected result
   - effect / value
   - allowed files
   - forbidden files
   - tests
   - GitNexus/impact gate
   - stop conditions
   - risk
4. Recommended execution order.
5. Definition of done for each stage and for P5 as a whole.
6. Worker delegation model: opencode/goose writes, Codex CTO reviews.
7. Batch reporting cadence.
8. Required report fields: branch, commit, modified files, tests, report path, risk.

Recommended P5 stage candidates:

- P5-A: Platform Ledger Gap Audit CLI
- P5-B: Platform Batch Mission Check CLI
- P5-C: Worker Reliability Summary CLI
- P5-D: Harness Index Consistency Check

## Result JSON

Write `ai-ledger/platform/2026-05-30_p4c_opencode_result.json` with:

```json
{
  "status": "done",
  "files_changed": [
    "ai-ledger/platform/2026-05-30_p4c_platform_code_build_plan.md"
  ],
  "test_result": "P5 platform code build plan written; CTO must verify docs-only scope, diff check, tests, and GitNexus",
  "blocker": ""
}
```
