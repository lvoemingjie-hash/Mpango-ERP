# P25-EE -- Tenant Health ID Boundary Fix

| Field | Value |
|---|---|
| **Task ID** | P25-EE |
| **Date** | 2026-07-08 |
| **Branch** | `codex/platform-p25ee-tenant-health-id-boundary-fix-2026-07-08` |
| **Base** | `origin/platform-dev @ 158feaca` |
| **Scope** | Backend-only platform P10 tenant-health/summary UUID validation fix + tests + ledger. No frontend, no migration, no package/lockfile, no product business path, no auth/RBAC change. |
| **Verdict** | **P25-EE tenant-health UUID/slug boundary blocker: PROVEN CLOSED.** P25 customer readiness: **STILL BLOCKED** by independent P25-EF audit result closed-vocab defect (separate task, not in P25-EE scope). |

---

## 1. Problem Statement

P25-ED-R1 real-stack browser smoke recorded a backend HTTP 500 on the tenant-health
and tenant-summary platform endpoints when a non-UUID slug was passed as the
`tenant_id` path parameter.

### Trigger Path (Before P25-EE)

```
GET /api/v1/platform/p10/tenants/smoke-tenant-1/health
  -> P10 platform operator guard (admits)
  -> get_platform_db() (system scope, P25-ED fix)
  -> get_tenant_health(db, tenant_id="smoke-tenant-1")
    -> select(Wholesaler).where(Wholesaler.id == "smoke-tenant-1")
      -> Wholesaler.id is Mapped[uuid.UUID] (UUID column)
      -> asyncpg tries to cast "smoke-tenant-1" to UUID
      -> asyncpg.exceptions.DataError: invalid UUID
  -> Unhandled exception -> HTTP 500
```

The raw `tenant_id` path parameter string was passed directly into a `where` clause
against a UUID column. `Wholesaler.id` is declared as
`Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ...)` (via `PublicBaseModel`
in `models/base.py`). A non-UUID string like `"smoke-tenant-1"` causes an asyncpg
`DataError` that propagates as an unhandled exception -> HTTP 500 instead of a clean
404 (tenant not found).

The same defect existed in both `get_tenant_summary` and `get_tenant_health` in
`backend/api/v1/platform/p10/services.py`.

---

## 2. Fix Design

### Approach: Pre-Query UUID Coercion Short-Circuit

Add a `_coerce_tenant_id` helper that attempts to parse the path parameter as a UUID
before any database query. If parsing fails, return `None` from the service, which the
route layer translates into a clean HTTP 404. This short-circuits before asyncpg ever
sees the invalid value, eliminating the `DataError` -> HTTP 500 path.

**Rationale:**
- Returns a clean 404 (tenant not found) for any non-UUID identifier -- the semantically
  correct response since the tenant cannot exist with a non-UUID id.
- No changes to the P10 platform operator guard, route signatures, or product business paths.
- No changes to the P25-ED `get_platform_db` system-scope design.

### Implementation

#### New helper: `_coerce_tenant_id` in `backend/api/v1/platform/p10/services.py`

```python
def _coerce_tenant_id(tenant_id: str) -> Optional[uuid.UUID]:
    """Parse a tenant_id path parameter into a UUID.

    Returns None when the value is not a valid UUID so that callers translate
    invalid/slug identifiers into a clean 404 instead of letting the raw string
    reach a UUID column and raise an asyncpg DataError (HTTP 500).
    """
    try:
        return uuid.UUID(str(tenant_id))
    except (ValueError, AttributeError, TypeError):
        return None
```

#### Updated: `get_tenant_summary` (services.py ~line 209)

```python
async def get_tenant_summary(db, tenant_id):
    parsed = _coerce_tenant_id(tenant_id)
    if parsed is None:
        return None  # route layer raises HTTP 404
    result = await db.execute(
        select(Wholesaler).where(Wholesaler.id == parsed)
    )
    ...
```

#### Updated: `get_tenant_health` (services.py ~line 242)

Same pattern: parse -> None check -> short-circuit -> clean 404.

#### Route layer: NO CHANGES

Both `/tenants/{tenant_id}` and `/tenants/{tenant_id}/health` routes in
`backend/api/v1/platform/p10/routes.py` already raise
`HTTPException(status_code=404)` when the service returns `None`. No route changes
were needed.

---

## 3. P10 Guard / RBAC Preservation Proof

The fix does NOT change any access control:

1. **P10 platform operator guard** (`require_platform_operator`): completely unchanged.
   All three admission paths (X-Platform-Operator header, identity-only super_admin JWT,
   X-Platform-Test-Override in test env) remain identical.

2. **P25-ED `get_platform_db`**: completely unchanged. The system-scope session design
   from P25-ED is preserved.

3. **No product route changed**: Zero product route or product business path files were
   modified. Only `services.py` (P10 platform services) was touched, and only in the two
   tenant lookup functions.

4. **No schema/migration change**: The fix operates at the service layer; no database
   schema, model, or migration file was modified.

---

## 4. Regression Tests

### File: `backend/tests/test_platform_p10_contracts.py` -- `TestP25EETenantIdBoundary`

| # | Test | Proves |
|---|---|---|
| 1 | `test_coerce_tenant_id_helper` | Helper returns UUID for valid input, None for invalid |
| 2 | `test_health_invalid_uuid_returns_404_without_db_call` | Invalid UUID short-circuits before any DB query for health endpoint |
| 3 | `test_summary_invalid_uuid_returns_404_without_db_call` | Invalid UUID short-circuits before any DB query for summary endpoint |
| 4 | `test_health_valid_uuid_still_queries_db` | Valid UUID still reaches the DB (no false 404) |
| 5 | `test_summary_valid_uuid_still_queries_db` | Valid UUID still reaches the DB (no false 404) |

Invalid IDs tested: `smoke-tenant-1`, `nonexistent`, `123`, `not-a-uuid-at-all`.

### Test Results

```
tests/test_platform_p10_contracts.py ......................    [100%]
======================= 142 passed, 0 failed =======================
```

The 5 new P25-EE boundary tests verify:
- `db.execute.assert_not_awaited()` for all invalid UUIDs (no DB round-trip, no DataError).
- `db.execute.assert_awaited_once()` for valid UUIDs (correct behavior preserved).

---

## 5. Real-Stack Smoke Evidence

**Date:** 2026-07-08
**Stack:** Real Postgres 15 (Docker `mpango_p25ec_pg` @ :5433, alembic head) + real
backend (uvicorn :8000) + real frontend (Vite :5173, proxies `/api` -> :8000) + real
headless Chromium via Playwright.

### 5.1 Identity Smoke (6/6 PASS)

| # | Case | Expected | Actual | Result |
|---|---|---|---|---|
| 1 | operator_admit | 200 | 200 | PASS |
| 2 | test_override_reject | 403 | 403 | PASS |
| 3 | identity_super_admin_admit | 200 | 200 | PASS |
| 4 | no_credentials_deny | 401 | 401 | PASS |
| 5 | wrong_operator_deny | 403 | 403 | PASS |
| 6 | tenant_context_admin_deny | 401/403 | 401 | PASS |

### 5.2 19-Route Playwright Browser Smoke

| Metric | Result |
|---|---|
| Total routes | 19 |
| HTTP 200 (page load) | **19/19** |
| Redirected | 0 |
| Routes with forbidden controls | **0** |
| Screenshots captured | **19/19** |
| Routes with React page errors | 0 |
| `TenantContextMissingError` | **0** |

### 5.3 P25-EE Blocker: CLOSED

| Criterion | Required | Actual | Status |
|---|---|---|---|
| Route 4 Tenant Health page HTTP 200 | yes | 200 | PASS |
| Tenant Health invalid slug -> clean 404 (not 500) | yes | **404** | PASS |
| `TenantContextMissingError` in logs | 0 | **0** | PASS |
| Forbidden controls | 0 | 0 | PASS |
| Screenshots | 19/19 | 19 | PASS |
| Identity smoke | all pass | 6/6 | PASS |

**Before P25-EE** (P25-ED-R1 run): Route 4 Tenant Health `has_5xx: true`, backend log
showed `GET .../tenants/smoke-tenant-1/health HTTP/1.1" 500 Internal Server Error`.

**After P25-EE**: Route 4 Tenant Health `has_5xx: false`, console errors now show
`404 Not Found` (clean), no backend 500 on this endpoint.

The `_coerce_tenant_id` short-circuit is proven on the real stack: the non-UUID slug
`"smoke-tenant-1"` returns a clean 404 without reaching asyncpg.

### 5.4 Residual 5xx -- Separate Pre-Existing Root Cause (OUT OF SCOPE)

One route surfaced a backend 500 with a **different, unrelated root cause**:

- **Route:** `/platform/audit` (page HTTP 200; API call 500)
- **API:** `GET /api/v1/platform/p10/audit/events?limit=20&offset=0`
- **Exception:**
  ```
  pydantic_core.ValidationError: 1 validation error for PlatformAuditEvent
  result
    Input should be 'allowed', 'denied', 'failed' or 'completed'
    [type=literal_error, input_value='recorded', input_type=str]
  ```
- **Source:** `backend/api/v1/platform/p10/services.py:375` -- `list_audit_events`
  builds `PlatformAuditEvent(result=meta.get("result", "completed"))` from
  `platform_audit_logs` rows. The P10 schema `AuditResult` is
  `Literal["allowed", "denied", "failed", "completed"]`. Some rows in the DB have
  `audit_metadata->>'result' = 'recorded'` (written by P19/P20 route handlers),
  which is not in the allowed vocabulary.

**This is NOT the P25-EE blocker.** It is an independent closed-vocab mismatch between
the P10 audit event schema and the audit log values written by P19/P20 route handlers.
It was previously **not visible** in P25-ED-R1 because that was the first smoke run on
the shared Docker Postgres; the offending `result='recorded'` rows were written during
that first run by the P19/P20 pages.

P25-EE scope explicitly excludes audit/events, P10 audit schemas/services, and product
business paths (per CTO directive). This residual 5xx requires its own task (**P25-EF**:
audit result closed-vocab defect) and is **not** addressable under P25-EE.

---

## 6. Base Proof Gate

```
git fetch origin platform-dev
git worktree add _p25ee_2026-07-08 -b codex/platform-p25ee-tenant-health-id-boundary-fix-2026-07-08 origin/platform-dev
```

Verification (before any edits):

```
git rev-parse HEAD          -> 158feacac1e8862ac40e7e8b4b33a61748acd5d0
git rev-parse origin/platform-dev -> 158feacac1e8862ac40e7e8b4b33a61748acd5d0
git diff --name-status origin/platform-dev..HEAD -> (empty)
git status --short -> (clean)
```

**Base Proof Gate: PASS**

---

## 7. Scope Diff Gate

### Changed Files

**Runtime fix (1 file):**
- `backend/api/v1/platform/p10/services.py` -- added `_coerce_tenant_id` helper + updated `get_tenant_summary` and `get_tenant_health`

**Test updates (1 file):**
- `backend/tests/test_platform_p10_contracts.py` -- added `TestP25EETenantIdBoundary` class (5 tests)

**Evidence (verify/p25ee/):**
- `verify/p25ee/run_smoke.py` -- real-stack smoke orchestrator
- `verify/p25ee/smoke_result.json` -- smoke results
- `verify/p25ee/backend_stdout.log` -- backend log
- `verify/p25ee/frontend_stdout.log` -- frontend log
- `verify/p25ee/screenshots/` -- 19 route screenshots

**Ledger (1 file):**
- `ai-ledger/platform/2026-07-08_p25ee_tenant_health_id_boundary_fix.md`

### Scope Audit

- No frontend runtime files modified.
- No migration files added or modified.
- No `package.json`, `package-lock.json`, `pnpm-lock.yaml`, `requirements.txt`, or `pyproject.toml` changes.
- No backend/deploy or infrastructure files modified.
- No auth/RBAC files modified.
- No product business path files modified.
- No audit/events, P10 audit schemas, or `list_audit_events` modified.
- No deletions of existing files.

**Scope Diff Gate: PASS**

---

## 8. Gate Checklist

| Gate | Status | Notes |
|---|---|---|
| Base Proof Gate | PASS | HEAD == origin/platform-dev @ 158feaca |
| Targeted backend tests | PASS | 142 passed, 0 failed |
| P10 platform operator guard intact | PASS | No changes to `require_platform_operator` |
| P25-ED system-scope DB dependency intact | PASS | `get_platform_db` unchanged |
| Tenant health 500 -> 404 proven on real stack | PASS | Route 4: clean 404, no backend 500 |
| `git diff --check` | PASS | No whitespace errors |
| ASCII scan | PASS | No non-ASCII characters in added source lines |
| `detect-secrets` | PASS | Throwaway test creds marked with `# pragma: allowlist secret` |
| `.secrets.baseline` unchanged | PASS | Baseline not modified |
| Forbidden path audit | PASS | No frontend, migration, deploy, lockfile, product path in diff |
| GitNexus analyze | PASS | |
| GitNexus status | PASS | |
| platform-dev NOT pushed | PASS | Only feature branch pushed |

---

## 9. Verdict

**P25-EE tenant-health UUID/slug boundary blocker: PROVEN CLOSED.**
**P25 customer readiness: STILL BLOCKED by independent P25-EF audit result closed-vocab defect.**

CTO decision (2026-07-08): P25-EE is accepted as a scoped fix proven closed; the
audit/events `result='recorded'` closed-vocab defect is tracked separately as **P25-EF**
and is explicitly out of P25-EE scope (no audit/services/schemas change, no product
business path touched).

P25-EE deliverable proven:
1. Non-UUID `tenant_id` returns a clean HTTP 404 (no DBAPI 500) -- proven by 5 boundary
   tests + real-stack smoke (Route 4: 500 -> 404).
2. Valid UUID `tenant_id` still queries the DB correctly -- proven by tests 4-5.
3. P10 platform operator guard unchanged.
4. P25-ED `get_platform_db` system-scope design unchanged.
5. Zero product business path, migration, frontend, auth/RBAC, or package/lockfile changes.

P25-EE is **not** declaring "P25 overall ready": the independent P25-EF audit/events
`result='recorded'` closed-vocab defect (Section 5.4) keeps P25 customer readiness blocked
until P25-EF resolves it.
