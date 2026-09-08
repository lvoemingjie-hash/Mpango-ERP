# F1 Lubuntu V3 Stop Report

Status: `STOP_AND_REPORT_CTO_MPANGO_MVP_INVARIANTS_R1_R1_F1_LUBUNTU_V3`
Date: 2026-09-08

## Identity
- Candidate: `76ab895fe6e00c91af09cef7b938be074734b461`
- Candidate parent: `69495712ad408000317d53e9e8e275bc35f5bf78`
- Kilo report: `a83a78275675223f9137e91257851bfce228ee00`
- Product fix baseline: `a516d2b3257f782ce068e71e8730c05541f08931`
- Protected product baseline: `bd2373cbfeafde07f1771aba2089f0d1b5f0cd3f`

## Preflight
`VOID_ENVIRONMENT_PRECHECK`

The fresh PostgreSQL 16 runtime could not be brought into the required non-superuser minimal-privilege state. Using the stock `postgres:16-alpine` initialization path, attempts to reduce or reassign the bootstrap role failed with:

- `ERROR: permission denied to alter role`
- `DETAIL: The bootstrap user must have the SUPERUSER attribute.`

That blocks the required task-specific runtime precondition. The focused matrices were not started, and no Redis ownership, deletion, or pytest evidence was produced for this round.

## Evidence
- `evidence/manifests/range_manifest.json` SHA-256 `aa5d8372b8c423bce5144e54ab600dffa649c93fae0191710426c6334bc4a80b`
- `evidence/preflight.json` SHA-256 `59d5801c8f1093a67c2847a77bdc354af01026d60400583b5e3384c0972ed45d`

## GitNexus
`NOT_RUN_DUE_TO_VOID_ENVIRONMENT_PRECHECK`

No GitNexus impact analysis was produced in this round because the environment preflight blocked execution before the focused runtime could begin.

## Required Fields

### CHANGED_OR_ADDED_TESTS_COVERING_NEW_PATHS
`NOT_RUN_DUE_TO_VOID_ENVIRONMENT_PRECHECK`

Planned coverage for this task remains the three focused test modules and their support helper, but no execution evidence exists in this round:
- `backend/tests/mpango_invariants_r0_support.py`
- `backend/tests/test_mpango_invariants_r0_r1_guards.py`
- `backend/tests/test_mpango_mvp_invariants_r0_revocation.py`

### CODE_PATH_TO_TEST_MATRIX
`NOT_RUN_DUE_TO_VOID_ENVIRONMENT_PRECHECK`

Intended mapping, not executed here:
- support helper -> Redis ownership binding proof and exact-key deletion setup
- guards -> actual cached client binding, host / port / DB comparison, ping-before-delete ordering
- revocation helper -> exact key deletion path only, no SCAN or wildcard cleanup

### NEGATIVE_AND_FAILURE_PATHS
- PostgreSQL bootstrap privilege reduction failed before runtime setup completed.
- No focused pytest matrix was started.
- No Redis ownership guard, delete helper, or scan-negative path was exercised in this round.

### FALSIFICATION_RESULT
`NOT_RUN_THIS_ROUND`

### UNCOVERED_NEW_PATHS
- All runtime-focused F1 paths remain uncovered in this round because the environment preflight blocked execution.
- Product cache isolation remains an unresolved product issue and was not re-evaluated here.

### FULL_SUITE_RESULT
`NOT_RUN_THIS_ROUND`

### BROWSER_RUNTIME
`NOT_RUN_THIS_ROUND`

## Cleanup
The attempted `mpango-f1v3` PostgreSQL and Redis containers were not left running after the blocker was hit. The candidate worktree remained clean.
