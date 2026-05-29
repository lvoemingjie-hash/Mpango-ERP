# P4-A Governed Real Platform Task Trial Goal

You are opencode acting as the platform worker for Mpango ERP.

## Role

Create a CTO-facing P4 objective ledger. This is a docs-only platform governance
task. Do not edit runtime code.

## Scope

Allowed files:

- `ai-ledger/platform/2026-05-30_p4a_real_task_trial_goal.md`
- `ai-ledger/platform/2026-05-30_p4a_real_task_trial_mission.md`
- `ai-ledger/platform/2026-05-30_p4a_real_task_trial_mission.json`
- `ai-ledger/platform/2026-05-30_p4a_opencode_result.json`
- `ai-ledger/platform/2026-05-30_p4a_opencode_events.jsonl`

Forbidden:

- No backend edits.
- No frontend edits.
- No product runtime edits.
- No auth, RBAC, tenancy, migration, payment, session edits.
- No `.github`, `.claude`, or `docs/ai` edits.
- Do not modify product-dev-recovered.

## Deliverable

Write `ai-ledger/platform/2026-05-30_p4a_real_task_trial_goal.md`.

The ledger must define P4 as the stage where the platform harness is used for
real but bounded platform tasks, not just harness self-tests. Include:

1. P3 completion state and why P4 can start.
2. P4 objective.
3. P4 non-goals.
4. The first 3 to 5 P4 slices, each with scope, expected artifacts, tests, and stop gates.
5. The first real platform task trial candidate.
6. Merge policy: isolated branches only; no platform-dev merge without CTO gate.
7. Required report fields: branch, commit, modified files, tests, report path, risk.
8. Risk classification.

Keep the ledger concise and operational.

## Result JSON

Write `ai-ledger/platform/2026-05-30_p4a_opencode_result.json` with this schema:

```json
{
  "status": "done",
  "files_changed": [
    "ai-ledger/platform/2026-05-30_p4a_real_task_trial_goal.md"
  ],
  "test_result": "docs-only P4 goal ledger created; CTO must run diff/check/GitNexus",
  "blocker": ""
}
```
