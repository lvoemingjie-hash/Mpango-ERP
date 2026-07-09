# P25-EH: P17 Registry Legacy UUID Robustness

**Date:** 2026-07-09
**Branch:** `codex/product-merge-prep-g2-resolved-merge-rehearsal-2026-07-08`
**Base:** `origin/product-dev-recovered` (via P25-EG `6b1a7616` + G3-R2 `040e6e0a`)
**Verdict:** `STOP_AND_REPORT_CTO` -- the Pydantic UUID fix is correct and kept, but the
registry 500 persists for a root cause outside P25-EH scope.

---

## 1. Task Intent

Fix the `/api/v1/platform/p17/registry` HTTP 500 surfaced by G3-R3 real-stack smoke.
Hypothesis: strict `validate_uuid_v4_v7` on `PlatformTenantRegistry.tenant_id` rejected
legacy UUIDs from `public.wholesalers.id` and caused the 500. Apply the lenient
`validate_uuid_any_version` (P25-EG pattern) to the read-only registry DTO, keeping
strict v4/v7 for audit events / lifecycle state. Allowed files: `p17/schemas.py` + tests
+ ledger only. Final gate: 0 backend 5xx -> PROVEN_CLOSED; else STOP_AND_REPORT_CTO.

## 2. Changes Applied (in scope, kept)

### `backend/api/v1/platform/p17/schemas.py`
- **Import** (lines 31-36): added `validate_uuid_any_version` to the p10 import block.
- **DTO validator** (lines 381-387): changed `PlatformTenantRegistry.tenant_id` from
  strict `validate_uuid_v4_v7` to lenient `validate_uuid_any_version`. The read-only
  registry DTO now accepts any valid UUID format (v1-v8) and only rejects slugs/garbage.
  Strict v4/v7 is unchanged for `TenantLifecycleState.last_audit_event_id` (line 95-96)
  and `TenantRegistryAuditEvent.event_id` / `tenant_id` (lines 461-462).

### `backend/tests/test_platform_p17_registry.py`
- Added `TestP25EHRegistryLegacyUUID` class (9 tests):
  legacy v1 UUID accept, valid v4 accept, slug reject, garbage reject, empty reject,
  audit-event tenant_id stays strict, audit-event event_id stays strict, lifecycle
  audit-event-id stays strict, endpoint no-500 on legacy UUID summary row.
- All 9 pass; full registry suite = 49/49 pass.

## 3. Validation Results

| Gate | Result |
|------|--------|
| P25-EH tests (9) | PASS (9/9) |
| Registry suite (49) | PASS (49/49) |
| git diff --check | OK (no whitespace/conflict) |
| Scope diff (files) | OK -- only `p17/schemas.py` + test file |
| **Real-stack smoke 5xx** | **FAIL -- `/p17/registry` still returns HTTP 500** |

The Pydantic UUID fix is correct and tested, but it does NOT achieve "0 backend 5xx".

## 4. Definitive Root Cause of the Persistent 500

A direct DB diagnostic (asyncpg against the smoke Postgres on :5433) ran every query in
the registry read path in isolation:

```
QUERY 1  public.wholesalers count   -> OK
QUERY 2  public.wholesalers select  -> OK  (4 rows, ALL valid v4 UUIDs)
QUERY 3  platform_tenants IN(...)   -> OK  (0 rows)
QUERY 4  platform_backup_outcomes   -> FAIL: UndefinedTableError: relation does not exist
QUERY 5  platform_backup_policies   -> FAIL: UndefinedTableError: relation does not exist
```

**The tables `public.platform_backup_outcomes` and `public.platform_backup_policies` do
not exist in the smoke database.** There are NO legacy/non-v4 UUIDs in the smoke data --
all four `wholesalers.id` values are valid v4 UUIDs. The Pydantic UUID path was never the
trigger for this instance.

### Error chain (confirmed via fresh backend repro)
1. `list_tenant_summaries(db)` runs OK (4 wholesalers).
2. `_load_backup_status_map(db, ...)` in `p17/services.py` issues
   `SELECT ... FROM platform_backup_outcomes WHERE ...` -> PostgreSQL raises
   `UndefinedTableError` -> **PostgreSQL aborts the entire transaction**.
3. The `try/except` at `p17/services.py:358-360` swallows the error and returns `None`.
   The service builds degraded registries and returns 200-level data.
4. `get_platform_db` (`database/session.py:145`) runs `await session.commit()` to flush the
   pending `ops_registry_view` audit-log INSERT -> the transaction is already aborted ->
   `asyncpg.exceptions.InFailedSQLTransactionError` -> `PendingRollbackError` -> **HTTP 500**.

The swallowed `UndefinedTableError` poisons the session; the audit-log commit then fails.

## 5. Scope Analysis -- Why This Is Out of P25-EH Scope

P25-EH allows ONLY `p17/schemas.py` + tests + ledger. Every viable fix for the real root
cause touches a forbidden surface:

| Fix | Files | In scope? |
|-----|-------|-----------|
| (a) Create the missing tables | DB migration | NO -- migrations forbidden |
| (b) Rollback the session after the backup-map error | `p17/services.py` | NO -- not `schemas.py` |
| (c) Make `get_platform_db` tolerate a poisoned session | `database/session.py` | NO |
| (d) Make the audit INSERT robust / best-effort | audit service / middleware | NO |

No in-scope edit can eliminate this 500. Therefore per the task spec
("0 backend 5xx -> PROVEN_CLOSED; else STOP_AND_REPORT_CTO"):

## 6. Verdict: `STOP_AND_REPORT_CTO`

### Recommendation for a follow-up task (e.g. P25-EJ)
Two independent gaps need closing to reach 0 backend 5xx on `/p17/registry`:

1. **Missing backup tables (schema gap):** `platform_backup_outcomes` and
   `platform_backup_policies` must be created (migration) OR the `_load_backup_status_map`
   query must be guarded so an `UndefinedTableError` degrades without poisoning the
   transaction. The correct robustness fix is to issue `await db.rollback()` (or use a
   SAVEPOINT) inside the `try/except` in `_load_backup_status_map` and
   `_load_provisioning_map` so a swallowed query error does not leave the session
   transaction-aborted. This is a `p17/services.py` change.
2. **Session hygiene in `get_platform_db`:** the cleanup `session.commit()` should detect a
   poisoned session and rollback instead of surfacing `PendingRollbackError` as a 500.

The P25-EH Pydantic UUID fix (kept) is still valuable: it eliminates a *latent* 500 path
if legacy UUIDs ever appear in `wholesalers.id`. It is necessary but not sufficient.

### Scope Diff Gate
```
M  backend/api/v1/platform/p17/schemas.py       (+8 -1)
M  backend/tests/test_platform_p17_registry.py  (+144)
2 files changed, 152 insertions(+), 1 deletion(-)
git diff --check: clean
```
No task-scope violations; no migrations/auth/product/frontend/lockfile/deploy drift.

## 7. Evidence Artifacts
- DB diagnostic: `platform_backup_outcomes` / `platform_backup_policies` -> UndefinedTableError
- Backend repro log: `PendingRollbackError` on `session.commit()` flushing
  `INSERT INTO public.platform_audit_logs ... ops_registry_view`
- wholesalers.id values (all v4): `428620e1-...`, `2b187e1a-...`, `83cd5c3a-...`,
  `11111111-1111-1111-1111-111111111111`
