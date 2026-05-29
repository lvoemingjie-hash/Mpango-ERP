# P4-B Pre-Code Readiness Closeout

You are opencode acting as the platform worker for Mpango ERP.

## Role

Create the final P4 pre-code readiness closeout packet. This is a docs-only
platform governance task. P4 is preparation; P5 will begin platform feature code.

## Allowed Files

You may create or modify only these files:

- `ai-ledger/platform/2026-05-30_p4b_precode_readiness_closeout.md`
- `ai-ledger/platform/2026-05-30_p4b_precode_readiness_mission.md`
- `ai-ledger/platform/2026-05-30_p4b_precode_readiness_mission.json`
- `ai-ledger/platform/2026-05-30_p4b_opencode_result.json`
- `ai-ledger/platform/2026-05-30_p4b_opencode_events.jsonl`

## Forbidden

- No `scripts/` edits.
- No backend or frontend edits.
- No product runtime edits.
- No auth, RBAC, tenancy, migration, payment, or session edits.
- No `.github`, `.claude`, or `docs/ai` edits.
- Do not modify `product-dev-recovered`.

## Deliverable

Write `ai-ledger/platform/2026-05-30_p4b_precode_readiness_closeout.md`.

The packet must:

1. State the new phase boundary:
   - P4 = complete pre-code readiness.
   - P5 = first platform feature-code implementation.
2. Summarize completed P1/P2/P3/P4 readiness layers.
3. List the remaining P4 readiness checks and mark them complete or blocked.
4. Define P5 start criteria.
5. Propose 3 to 5 first P5 feature-code slices, with:
   - phase name
   - purpose
   - allowed files
   - forbidden files
   - tests
   - GitNexus/impact expectations
   - risk
6. Recommend the first P5 slice.
7. Include merge policy:
   - isolated branches only
   - no platform-dev merge without CTO gate
   - batch review after 2 to 3 P5 slices
8. Include the exact required report fields:
   - branch
   - commit
   - modified files
   - tests
   - report path
   - risk

Be operational and concise. Do not invent product features.

## Result JSON

Write `ai-ledger/platform/2026-05-30_p4b_opencode_result.json` with:

```json
{
  "status": "done",
  "files_changed": [
    "ai-ledger/platform/2026-05-30_p4b_precode_readiness_closeout.md"
  ],
  "test_result": "P4 pre-code readiness closeout written; CTO must verify docs-only scope, diff check, tests, and GitNexus",
  "blocker": ""
}
```
