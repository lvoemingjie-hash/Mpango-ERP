# P25-EJ: P17 Registry Optional Source Read Transaction Poisoning Fix

**Date:** 2026-07-09
**Branch:** `codex/product-merge-prep-g2-resolved-merge-rehearsal-2026-07-08`
**Base:** `origin/product-dev-recovered` (via P25-EH `459f1075`)
**Verdict:** `P25-EJ_PROVEN_CLOSED` — real-stack smoke confirmed 0 backend 5xx.

---

## 1. Task Intent

Fix the `/api/v1/platform/p17/registry` HTTP 500 caused by optional source-read
exceptions poisoning the AsyncSession transaction.

**Root cause (confirmed in P25-EH):** `_load_backup_status_map` in
`p17/services.py` queries `platform_backup_outcome` / `platform_backup_policy`.
When the tables are absent (smoke DB without migration 030), PostgreSQL raises
`UndefinedTableError` and aborts the ENTIRE transaction. The `try/except` at
`services.py:358-360` swallowed the error and returned `None` but did NOT
rollback the session. `get_platform_db` (`database/session.py:145`) then ran
`await session.commit()` to flush the `ops_registry_view` audit-log INSERT
and raised `PendingRollbackError` -> HTTP 500.

The same swallow-without-cleanup anti-pattern existed in
`_load_provisioning_map` (`services.py:82-83`).

## 2. GitNexus Impact Analysis (pre-edit)

Ran `gitnexus impact` on all three target symbols (depth 2, repo
`_mergeresolve_g2_2026-07-08`):

### `_load_backup_status_map` — HIGH risk, 7 impacted
- **d=1 (WILL BREAK):** `list_tenant_registries`, `get_tenant_registry`
  (p17/services.py), `read_backup_check_source` (p22/source_probe.py)
- **d=2 (LIKELY AFFECTED):** `_resolve_action_source_status` (p18/services.py),
  `materialize_backup_check` (p23/sources.py), `backup_check_source_route`
  (p22/routes.py), `complete_governed_backup_check` (p22/governed_execution.py)

### `_load_provisioning_map` — HIGH risk, 3 impacted
- **d=1:** `list_tenant_registries`, `get_tenant_registry`
- **d=2:** `_resolve_action_source_status` (p18/services.py)

### `list_tenant_registries` — LOW risk, 0 impacted

**Assessment:** The change adds `db.begin_nested()` (SAVEPOINT) inside the
function bodies. The external contract (return values) is unchanged: None on
backup failure, {} on provisioning failure, dict on success. The savepoint is
an internal implementation detail -- callers see identical behavior except the
session is no longer poisoned after a swallowed error. The p22 caller
(`read_backup_check_source`) wraps `_load_backup_status_map` in its own
try/except and handles `None` correctly. **Safe to change.**

## 3. Changes Applied

### `backend/api/v1/platform/p17/services.py` (2 changes)

**Change 1 — `_load_provisioning_map` (line 63-83):**
Wrapped the `db.execute` query in `async with db.begin_nested():` so a query
failure (e.g. table absent) rolls back only the SAVEPOINT, not the outer
request transaction. The dict comprehension is moved outside the savepoint
since it needs no DB access.

**Change 2 — `_load_backup_status_map` (line 313-360):**
Wrapped both `db.execute` calls (outcomes + policies) in
`async with db.begin_nested():` with the same containment discipline. On
failure the except block returns `None` as before, but the SAVEPOINT rollback
keeps the outer session healthy for the subsequent audit-log commit.

**Design rationale (SAVEPOINT over explicit rollback):**
- `db.begin_nested()` creates a PostgreSQL SAVEPOINT. On exception the context
  manager issues `ROLLBACK TO SAVEPOINT`, restoring the outer transaction to a
  healthy state.
- An explicit `await db.rollback()` would roll back the ENTIRE outer transaction
  (including prior successful reads like `list_tenant_summaries`), which is
  undesirable for this read-only path where only the optional sub-source failed.
- SAVEPOINT is the SQLAlchemy-idiomatic containment for nested failure scopes.

### `backend/tests/test_platform_p17_registry.py` (3 changes)

**Change 1 — Import:** Added `from contextlib import asynccontextmanager`.

**Change 2 — `_mock_db()` helper:** Added `begin_nested()` as a no-op async
context manager so the savepoint code path works in all existing tests that use
mock sessions.

**Change 3 — New test class `TestP25EJTransactionPoisoningFix` (9 tests):**
1. `test_backup_loader_returns_none_on_query_error` — returns None (not raises)
2. `test_backup_loader_uses_savepoint_on_error` — begin_nested is called
3. `test_backup_loader_works_normally_on_success` — no regression on happy path
4. `test_provisioning_loader_returns_empty_on_query_error` — returns {} (not raises)
5. `test_provisioning_loader_works_normally_on_success` — no regression
6. `test_route_200_when_backup_source_fails` — route returns 200, not 500
7. `test_route_200_when_provisioning_source_fails` — same containment
8. `test_route_200_when_all_optional_sources_fail` — both fail -> still 200
9. `test_missing_backup_source_is_not_healthy` — source honesty: null, not fabricated

## 4. Validation Results

| Gate | Result |
|------|--------|
| P17 registry suite (58) | PASS (58/58) |
| P10 contracts suite (173) | PASS (173/173) |
| P22 source probe + governed (54) | PASS (54/54) |
| git diff --check | OK (no whitespace/conflict) |
| detect-secrets-hook | OK (exit 0) |
| ASCII scan (both files) | OK (0 non-ASCII bytes) |
| .secrets.baseline | unchanged |
| **Real-stack smoke (G3-R3 backend variant)** | **PASS — 0 5xx, registry 200** |

## 5. Scope Diff Gate

```
M  backend/api/v1/platform/p17/services.py     (savepoint containment)
M  backend/tests/test_platform_p17_registry.py  (+184, 9 new tests)
2 files changed, 215 insertions(+), 23 deletions(-)
```

No task-scope violations: no migrations, no database/session.py changes, no
auth/RBAC, no product paths, no frontend, no lockfile/deploy drift.

## 6. P25-EH Preservation

The P25-EH UUID DTO fix (commit `459f1075`) is preserved unchanged:
- `PlatformTenantRegistry.tenant_id` uses lenient `validate_uuid_any_version`
- Strict `v4_v7` stays for `TenantLifecycleState.last_audit_event_id` and
  `TenantRegistryAuditEvent.event_id` / `tenant_id`
- All 9 P25-EH tests still pass within the 58-test suite

## 7. Source Honesty Verification

- Missing backup tables -> `backup_status=None` (NOT fabricated success)
- Missing provisioning rows -> `provisioning_status=None` (NOT fabricated)
- `unavailable_reason` surfaces the honest degradation
- `registry_source_status` reflects degraded/unknown, never healthy

## 8. Evidence Artifacts

- Unit tests: 58/58 P17, 173/173 P10, 54/54 P22 — all pass
- GitNexus impact: HIGH risk on loaders (7+3 impacted), LOW on orchestrator
- The fix is P17-local (services.py only); database/session.py untouched

## 9. G3-R3 Real-Stack Smoke (Backend Variant)

Since frontend node_modules were not installed in this worktree, the G3-R3 smoke
was run as a **backend-only variant** that directly hits all 19 backend API
endpoints (the same endpoints the frontend routes call) against the disposable
PostgreSQL on :5433 (Docker `mpango_p25ec_pg`).

**Evidence:** `verify/p25ef/p25ej_smoke_result.json`

### Identity Smoke — 6/6 PASS

| Case | Expected | Actual | Result |
|------|----------|--------|--------|
| operator_admit | 200 | 200 | PASS |
| test_override_reject | 403 | 403 | PASS |
| identity_super_admin_admit | 200 | 200 | PASS |
| no_credentials_deny | 401 | 401 | PASS |
| wrong_operator_deny | 403 | 403 | PASS |
| tenant_context_admin_deny | 401/403 | 401 | PASS (clean deny, NOT 500) |

### Route Smoke — 19/19 no 5xx

| # | Endpoint | Status | Notes |
|---|----------|--------|-------|
| 1 | `/api/v1/platform/health` | 200 | |
| 2 | `/api/v1/platform/p10/system/health` | 200 | |
| 3 | `/api/v1/platform/p10/tenants` | 200 | Legacy UUID-safe (P25-EG) |
| 4 | `/api/v1/platform/p10/tenants/{id}/health` | 404 | Expected (smoke tenant absent) |
| 5 | `/api/v1/platform/p10/audit/events` | 200 | result=recorded boundary (P25-EF) |
| 6 | **`/api/v1/platform/p17/registry`** | **200** | **P25-EJ CRITICAL — was 500, now 200** |
| 7 | `/api/v1/platform/stats/` | 200 | |
| 8 | `/api/v1/platform/p13/ops/health` | 200 | |
| 9 | `/api/v1/platform/p13/ops/errors` | 200 | source_status=unavailable (honest) |
| 10 | `/api/v1/platform/p13/ops/slow-routes` | 200 | source_status=unavailable (honest) |
| 11 | `/api/v1/platform/p13/ops/resources` | 200 | database=healthy |
| 12 | `/api/v1/platform/p13/ops/noisy-neighbors` | 200 | source_status=unavailable (honest) |
| 13 | `/api/v1/platform/p15/incidents/triage/snapshot` | 200 | |
| 14 | `/api/v1/platform/p18/actions/catalog` | 200 | |
| 15 | `/api/v1/platform/p19/approvals` | 200 | |
| 16 | `/api/v1/platform/p20/durable-approvals` | 200 | |
| 17 | `/api/v1/platform/p22/execution/catalog` | 200 | |
| 18 | `/api/v1/platform/p23/operator-tasks` | 200 | |
| 19 | `/api/v1/platform/p24/incident-closeouts` | 200 | |

### Backend Log Grep — All Zero

| Metric | Count |
|--------|-------|
| TenantContextMissingError | **0** |
| HTTP 500 / ERROR lines | **0** |
| PendingRollbackError | **0** |
| UndefinedTable errors | **0** |
| Traceback lines | **0** |

### Verdict

```
Identity smoke 6/6:              PASS
0 backend 5xx + registry 200:    PASS
0 TCM + 0 PendingRollback:       PASS
OVERALL: P25-EJ_PROVEN_CLOSED
```

The `/api/v1/platform/p17/registry` endpoint that previously returned HTTP 500
(PendingRollbackError from transaction poisoning) now returns HTTP 200 with
degraded-but-honest source data. The SAVEPOINT containment in
`_load_backup_status_map` and `_load_provisioning_map` successfully isolates
optional source-read failures from the outer request transaction.
