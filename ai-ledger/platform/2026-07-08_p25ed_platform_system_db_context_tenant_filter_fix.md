# P25-ED -- Platform System DB Context / Tenant Filter Boundary Fix

| Field | Value |
|---|---|
| **Task ID** | P25-ED |
| **Date** | 2026-07-08 |
| **Branch** | `codex/platform-p25ed-system-db-context-tenant-filter-fix-2026-07-08` |
| **Base** | `origin/platform-dev @ fd907a51` |
| **Scope** | Backend-only runtime fix + tests + ledger. No frontend, no migration, no package/lockfile. |
| **Verdict (R1)** | **P25-ED tenant-filter blocker: PROVEN CLOSED.** P25 customer readiness: **STILL BLOCKED** by independent P25-EE tenant-health UUID/slug validation defect (separate task, not in P25-ED scope). |

---

## 1. Problem Statement

P25-EC real-stack browser smoke recorded backend HTTP 5xx on platform routes
(P10-P25 console endpoints). Root cause: platform routes used `get_db()` which
sets `session.info["tenant_schema"] = "public"` but does NOT set a tenant_id
and does NOT mark the session as system scope. The global tenant filter
(`install_global_tenant_filter`) intercepts every ORM query on models that have
`tenant_id` or `wholesaler_id` columns (e.g. `PlatformAuditLog`, `Wholesaler`,
`PlatformTenant`) and raises `TenantContextMissingError` because no tenant_id is
present. This propagates as an unhandled exception -> HTTP 500.

### Trigger Path (Before P25-ED)

```
Platform route handler
  -> Depends(get_db)
    -> session.info["tenant_schema"] = "public"
    -> NO tenant_id
    -> NO system scope reason
  -> ORM query on model with tenant_id / wholesaler_id
    -> install_global_tenant_filter intercept
      -> _require_tenant_context()
        -> tenant_schema present but tenant_id missing
        -> raise TenantContextMissingError("...tenant_id required...")
  -> Unhandled exception -> HTTP 500
```

---

## 2. Fix Design

### Approach: Session-Level System Scope (mark_session_as_system)

The codebase already has three tenant-filter bypass mechanisms:

1. **`run_as_system(reason=...)`** -- ContextVar-based bypass via
   `_system_scope_reason`. Used in `crud/user.py` for cross-tenant login scan.
   Thread/task-scoped; affects all sessions in the context.

2. **`execution_options(ignore_tenant=True)`** -- Per-query bypass via execution
   option. Requires changing every individual query site.

3. **`mark_session_as_system(session, reason=...)`** -- Session-level bypass via
   `session.info["mpango_system_scope_reason"]`. Affects only the marked
   session; no cross-session leak. Already used nowhere in routes but is the
   safest mechanism for a DB dependency.

**Chosen: `mark_session_as_system`** (mechanism 3). Rationale:
- Session-scoped: no cross-session or cross-request leak.
- Dependency-level: one change in `get_platform_db()`, no per-query changes.
- Already vetted code path: the `_is_system_scope_bypass()` function checks
  `session.info` system scope reason (line 181 of `db/tenant_filter.py`).

### Implementation

#### New: `get_platform_db()` in `backend/database/session.py`

```python
async def get_platform_db() -> AsyncGenerator[AsyncSession, None]:
    """Get database session for platform/system operations.

    Marks the session as explicit system scope so that public-schema queries
    on models with tenant_id / wholesaler_id columns do not raise
    TenantContextMissingError from the global tenant filter.

    This bypass is ONLY for platform routes behind the P10 platform operator
    guard. Product tenant routes continue to use get_db / get_tenant_db which
    are unaffected and fully tenant-scoped.
    """
    async with AsyncSessionLocal() as session:
        try:
            session.info["tenant_schema"] = "public"
            mark_session_as_system(session, reason="platform_system_query")
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
```

#### Updated: `backend/api/dependencies.py`

```python
from database.session import get_db, get_platform_db
```

#### Updated: 13 Platform Route Files

All 13 platform route modules changed from:
```python
from api.dependencies import get_db
...
async def handler(db: AsyncSession = Depends(get_db)):
```
to:
```python
from api.dependencies import get_platform_db
...
async def handler(db: AsyncSession = Depends(get_platform_db)):
```

Files updated (53 DB dependency references total):

| File | Changes |
|---|---|
| `api/v1/platform/audit.py` | 4 |
| `api/v1/platform/tenants.py` | 3 |
| `api/v1/platform/stats.py` | 2 |
| `api/v1/platform/p10/routes.py` | 7 |
| `api/v1/platform/p12/routes.py` | 6 |
| `api/v1/platform/p13/routes.py` | 7 |
| `api/v1/platform/p15/routes.py` | 3 |
| `api/v1/platform/p17/routes.py` | 4 |
| `api/v1/platform/p18/routes.py` | 7 |
| `api/v1/platform/p19/routes.py` | 6 |
| `api/v1/platform/p20/routes.py` | 6 |
| `api/v1/platform/p22/routes.py` | 9 |
| `api/v1/platform/p23/routes.py` | 2 |

#### Updated: 18 Platform Test Files

Each test file updated to also override `get_platform_db`:
```python
from api.dependencies import get_db, get_platform_db
...
app.dependency_overrides[get_db] = override
app.dependency_overrides[get_platform_db] = app.dependency_overrides[get_db]
```

#### New: `backend/tests/test_p25ed_platform_system_db_context.py`

10 regression tests proving the fix works and tenant isolation is preserved.

---

## 3. Tenant Isolation Preservation Proof

The fix does NOT weaken tenant isolation for product routes:

1. **Product routes** (`api/v1/`, non-platform): still use `get_db()` or
   `get_tenant_db()`. These do NOT call `mark_session_as_system`. The tenant
   filter continues to enforce `tenant_id` requirements and apply WHERE clauses.

2. **Platform routes** (`api/v1/platform/`): now use `get_platform_db()`. These
   sit behind the P10 platform operator guard
   (`require_platform_operator`), which requires one of:
   - Shared platform secret header
   - Identity-only super_admin JWT
   - Test override key

3. **Session scope isolation**: `mark_session_as_system` only marks the specific
   session via `session.info`. It does NOT set a ContextVar, so it cannot leak
   to other sessions on the same thread/asyncio task. Regression test
   `test_session_system_scope_does_not_leak_to_other_sessions` proves this.

4. **No product route changed**: Zero product route files were modified. Only
   platform route files (under `api/v1/platform/`) were updated.

---

## 4. Regression Tests

### File: `backend/tests/test_p25ed_platform_system_db_context.py`

| # | Test | Proves |
|---|---|---|
| 1 | `test_product_query_without_tenant_context_fails_closed` | Product ORM query without context raises TenantContextMissingError |
| 2 | `test_product_query_without_tenant_id_fails_closed` | Query with schema but no tenant_id raises |
| 3 | `test_platform_query_with_mark_session_as_system_passes` | Platform system scope passes for wholesaler_id model |
| 4 | `test_platform_query_with_mark_session_as_system_passes_tenant_model` | Platform system scope works for tenant_id models (cross-tenant) |
| 5 | `test_platform_query_with_run_as_system_context_manager_passes` | Existing run_as_system pattern still works |
| 6 | `test_mark_session_as_system_requires_reason` | Empty reason rejected with ValueError |
| 7 | `test_tenant_filter_still_applies_when_context_set` | tenant_id filter narrows results when context active |
| 8 | `test_other_tenant_rows_excluded_when_filtered` | Other tenant rows excluded |
| 9 | `test_session_system_scope_does_not_leak_to_other_sessions` | System scope on one session does not affect another |
| 10 | `test_get_platform_db_marks_session_as_system` | get_platform_db sets system scope reason + tenant_schema on session (route-smoke equivalent) |

### Test Results

```
tests/test_p25ed_platform_system_db_context.py .........    [100%]
======================= 10 passed, 2 warnings in 0.18s ========================

# Existing tenant filter tests (no regression)
tests/test_global_tenant_filter.py ......
======================= 6 passed ========================

# Combined
======================= 16 passed, 2 warnings in 0.23s ========================

# Platform route tests (subset)
test_platform_p10_contracts + audit_api + stats_api + p12 + p13 + p22 + p22g
======================= 406 passed, 5 warnings in 9.38s =======================
```

**Total: 422 passed, 0 failed.**

---

## 5. Route Smoke Equivalent

The P25-EC route smoke could not be re-run in this environment (requires live
server + browser stack). The reduced equivalent is:

1. **Root-cause proof** (tests 1-2): ORM queries on tenant_id/wholesaler_id
   models without system scope raise `TenantContextMissingError` -- this is the
   exact exception that caused the HTTP 500 in P25-EC.

2. **Fix proof** (tests 3-5): ORM queries with `mark_session_as_system` or
   `run_as_system` bypass the filter and return results without raising.

3. **Wiring proof** (test 10): `get_platform_db()` -- the new dependency used by
   all 13 platform route modules -- correctly calls
   `mark_session_as_system(session, reason="platform_system_query")` before
   yielding the session. This is the direct causal link between the fix and the
   route behavior: platform routes now receive a system-scoped session, so ORM
   queries no longer raise `TenantContextMissingError`, so routes return HTTP
   200 instead of HTTP 500.

4. **Route-level proof** (406 platform route tests): All platform route tests
   using FastAPI TestClient pass, confirming endpoints respond correctly with
   the new dependency.

**Conclusion: 0 backend 5xx from TenantContextMissingError on platform routes.**

---

## 6. Base Proof Gate

```
git fetch origin platform-dev
git worktree add _p25ed_2026-07-08 -b codex/platform-p25ed-system-db-context-tenant-filter-fix-2026-07-08 origin/platform-dev
```

Verification (before any edits):

```
git rev-parse HEAD          -> fd907a513e5a6c5e91424a84889064fa8ad6158d
git rev-parse origin/platform-dev -> fd907a513e5a6c5e91424a84889064fa8ad6158d
git diff --name-status origin/platform-dev..HEAD -> (empty)
git status --short -> (clean)
```

**Base Proof Gate: PASS**

---

## 7. Scope Diff Gate

### Changed Files (34 total)

**Runtime fix (2 files):**
- `backend/database/session.py` -- added `get_platform_db()`
- `backend/api/dependencies.py` -- re-export `get_platform_db`

**Platform route updates (13 files):**
- `backend/api/v1/platform/audit.py`
- `backend/api/v1/platform/p10/routes.py`
- `backend/api/v1/platform/p12/routes.py`
- `backend/api/v1/platform/p13/routes.py`
- `backend/api/v1/platform/p15/routes.py`
- `backend/api/v1/platform/p17/routes.py`
- `backend/api/v1/platform/p18/routes.py`
- `backend/api/v1/platform/p19/routes.py`
- `backend/api/v1/platform/p20/routes.py`
- `backend/api/v1/platform/p22/routes.py`
- `backend/api/v1/platform/p23/routes.py`
- `backend/api/v1/platform/stats.py`
- `backend/api/v1/platform/tenants.py`

**Test updates (18 files):**
- 17 existing platform test files -- dependency override for `get_platform_db`
- 1 new test file: `backend/tests/test_p25ed_platform_system_db_context.py`

**Ledger (1 file):**
- `ai-ledger/platform/2026-07-08_p25ed_platform_system_db_context_tenant_filter_fix.md`

### Diff Stat

```
33 files changed, 137 insertions(+), 88 deletions(-)
```

### Scope Audit

- No frontend files modified.
- No migration files added or modified.
- No `package.json`, `package-lock.json`, `pnpm-lock.yaml`, `requirements.txt`, or `pyproject.toml` changes.
- No backend/deploy or infrastructure files modified.
- No deletions of existing files.
- All changes are backend runtime + tests + ledger.

**Scope Diff Gate: PASS**

---

## 8. Gate Checklist

| Gate | Status | Notes |
|---|---|---|
| Base Proof Gate | PASS | HEAD == origin/platform-dev @ fd907a51 |
| Targeted backend tests | PASS | 422 passed, 0 failed |
| Product tenant isolation preserved | PASS | Tests 1, 2, 7, 8, 9 prove fail-closed + filter + no-leak |
| Platform 5xx cleared | PASS | Tests 3-5, 10 prove system scope bypass works + wiring correct |
| P10 platform operator guard intact | PASS | No changes to `require_platform_operator`; guard still required on all platform routes |
| `git diff --check` | PASS | No whitespace errors |
| ASCII scan | PASS | No non-ASCII characters in new/modified source files |
| `detect-secrets` | PASS | No secrets detected |
| Forbidden path audit | PASS | No frontend, migration, deploy, lockfile paths in diff |
| GitNexus analyze | PASS | |
| GitNexus status | PASS | |
| GitNexus detect_changes | PASS | |
| platform-dev NOT pushed | PASS | Only feature branch pushed |

---

## 9. Verdict

**P25-ED tenant-filter blocker: PROVEN CLOSED.**
**P25 customer readiness: STILL BLOCKED by independent P25-EE tenant-health UUID/slug validation defect.**

CTO decision (2026-07-08): P25-ED-R1 evidence is committed as-is; the tenant-health
UUID/slug validation defect is tracked separately as **P25-EE** and is explicitly out
of P25-ED scope (no product business path touched in P25-ED).

P25-ED deliverable proven (see Section 10 for real-stack evidence):
1. Product tenant isolation preserved (regression tests prove fail-closed behavior unchanged).
2. Platform real-stack 5xx root cause identified and fixed (`TenantContextMissingError` from global tenant filter on public-schema platform queries).
3. Fix is scoped to platform routes only -- zero product route files modified.
4. Fix uses existing vetted mechanism (`mark_session_as_system`) with no new security surface.
5. All platform routes now sit behind both the P10 platform operator guard AND the system-scoped DB dependency.

P25-ED is **not** declaring "P25 overall ready": the tenant-health endpoint's
independent UUID/slug validation defect (Section 10.4) keeps P25 customer readiness blocked
until P25-EE resolves it.

---

## 10. P25-ED-R1: Real-Stack Evidence Completion

**Date:** 2026-07-08
**Tip:** `be347318`
**Stack:** Real Postgres 15 (Docker `mpango_p25ec_pg` @ :5433, alembic head) + real
backend (uvicorn :8000) + real frontend (Vite :5173, proxies `/api` -> :8000) + real
headless Chromium via Playwright.

### 10.1 Identity Smoke (6/6 PASS)

| # | Case | Headers | Expected | Actual | Result |
|---|---|---|---|---|---|
| 1 | operator_admit | `X-Platform-Operator` | 200 | 200 | PASS |
| 2 | test_override_reject | `X-Platform-Test-Override` (production) | 403 | 403 | PASS |
| 3 | identity_super_admin_admit | identity-only Bearer | 200 | 200 | PASS |
| 4 | no_credentials_deny | (none) | 401 | 401 | PASS |
| 5 | wrong_operator_deny | bad operator secret | 403 | 403 | PASS |
| 6 | tenant_context_admin_deny | tenant-context Bearer | 401/403 | **401** | PASS |

Case 6 is the critical P25-ED boundary: a tenant-context super_admin JWT is denied
with a **clean 401, NOT a 500**. The P10 guard rejects tenant-context tokens before
any DB query runs.

### 10.2 19-Route Playwright Browser Smoke

| Metric | Result |
|---|---|
| Total routes | 19 |
| HTTP 200 (page load) | **19/19** |
| Redirected | 0 |
| Routes with forbidden controls | **0** |
| Screenshots captured | **19/19** |
| Routes with React page errors | 0 |
| Routes with backend 5xx on an API call | 1 (route 4) |

Every platform page renders (HTTP 200). 18/19 routes have zero console errors and
zero page errors. **0 `TenantContextMissingError`** in the backend log across all
requests.

### 10.3 P25-ED Blocker: CLOSED

| Criterion | Required | Actual | Status |
|---|---|---|---|
| Platform routes HTTP 200 | 19/19 | 19 | PASS |
| `TenantContextMissingError` in logs | 0 | **0** | PASS |
| tenant-context super_admin denied | clean 401/403 not 500 | 401 | PASS |
| Forbidden controls | 0 | 0 | PASS |
| Screenshots | 19/19 | 19 | PASS |
| Identity smoke | all pass | 6/6 | PASS |

The original P25-EC blocker (platform routes using `get_db` ->
`TenantContextMissingError` -> HTTP 500 on 15/19 routes) is **proven closed** by the
real stack. 0 occurrences of `TenantContextMissingError`; all 19 pages load; the P10
identity boundary is clean (401/403, never 500).

### 10.4 Residual 5xx -- Separate Pre-Existing Root Cause (OUT OF SCOPE)

One route surfaced a backend 500 with a **different, unrelated root cause**:

- **Route:** `/platform/tenants/smoke-tenant-1/health` (page HTTP 200; API call 500)
- **API:** `GET /api/v1/platform/p10/tenants/smoke-tenant-1/health`
- **Exception:**
  ```
  asyncpg.exceptions.DataError: invalid input for query argument $1: 'smoke-tenant-1'
  (invalid UUID 'smoke-tenant-1': length must be between 32..36 characters, got 14)
  [SQL: SELECT ... FROM public.wholesalers WHERE public.wholesalers.id = $1::UUID]
  [parameters: ('smoke-tenant-1',)]
  ```
- **Source:** `backend/api/v1/platform/p10/services.py:248` --
  `select(Wholesaler).where(Wholesaler.id == tenant_id)` where `Wholesaler.id` is a
  UUID column but the path param `tenant_id = "smoke-tenant-1"` is a slug that cannot
  cast to UUID.

**This is NOT the P25-ED blocker.** It is a pre-existing product business-path
defect (the tenant-health service does not validate/parse `tenant_id` as UUID before
querying, so an invalid UUID string bubbles up as a raw DBAPI 500 instead of a clean
404/422). It was previously **masked** by the `TenantContextMissingError` which fired
earlier in the request pipeline (the `get_db` dependency); now that P25-ED fixed that
dependency, the request proceeds further and hits this separate validation gap.

P25-ED scope explicitly excludes product business paths (per task directive: do not
touch product business paths).
This residual 5xx requires its own task (e.g. P25-EE: tenant-health UUID validation +
graceful 404) and is **not** addressable under P25-ED.

### 10.5 R1 Verdict

Per the R1 pass criteria, one residual 5xx remains (unrelated to P25-ED). CTO
decision (2026-07-08): **commit P25-ED-R1 evidence as-is; do not fix the
tenant-health UUID/slug validation defect inside P25-ED** (it is a product business
path and is tracked separately as **P25-EE**).

- **P25-ED tenant-filter blocker: PROVEN CLOSED.** The `TenantContextMissingError`
  -> HTTP 500 blocker is closed on the real stack: 0 occurrences across all requests,
  19/19 platform pages load HTTP 200, identity boundaries clean (401/403, never 500),
  0 forbidden controls, 19/19 screenshots, 6/6 identity smoke cases pass.

- **P25 customer readiness: STILL BLOCKED** by the independent P25-EE tenant-health
  UUID/slug validation defect (Section 10.4). P25-ED does **not** declare P25 overall ready.

- **R1 evidence committed** to the feature branch (`verify/p25ed/` + this ledger
  R1 section). No runtime code changed in R1; no `services.py`, no product business
  path, no migration, no frontend, no package/lockfile.
