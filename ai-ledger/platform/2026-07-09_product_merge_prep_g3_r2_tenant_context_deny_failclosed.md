# Product-Line Merge Preparation Gate 3-R2 -- Tenant-Context Platform Deny Fail-Closed Hardening

| Field | Value |
|---|---|
| **Task ID** | G3-R2 (Tenant-Context Platform Deny Fail-Closed Hardening) |
| **Date** | 2026-07-09 |
| **Mode** | **CODE** -- narrow fail-closed fix on the auth tenant-context resolution path |
| **Branch** | `codex/product-merge-prep-g2-resolved-merge-rehearsal-2026-07-08` |
| **Worktree** | `_mergeresolve_g2_2026-07-08` |
| **Base (HEAD at start)** | `39496c9c` (G3-R1 promotion plan refresh) |
| **Predecessor** | G3-R1 documented the `tenant_context_admin_deny` 500 issue as a CTO decision (Option A) |
| **Result** | **FIXED** -- missing tenant schema/table now returns clean 401, never 500, never admits |

---

## 1. Base Proof Gate

| Check | Result |
|---|---|
| `git fetch origin` | Executed 2026-07-09 (protected refs captured in G3-R1) |
| `origin/platform-dev` | `12c5ee55` -- **UNCHANGED** |
| `origin/product-dev-recovered` | `19f6afde` -- **UNCHANGED** since G3-R1 |
| Branch lineage | `codex/product-merge-prep-g2-resolved-merge-rehearsal-2026-07-08` carries G2/G2-R1/R2/R3/G3/G3-R1 commits atop product merge base |
| Working tree at edit start | Clean (no staged/modified source) |

---

## 2. Problem Statement

A tenant-contextual JWT (roles=`["super_admin"]`, tenant_id non-null,
tenant_schema=`t_smoke_r1`) hitting a platform route returns **HTTP 500**
instead of a clean deny when the tenant schema/table does not exist in the DB.

The access was already fail-closed (500 denies, never admits), but a raw 500
pollutes production logs, breaks identity smoke assertions, and provides a poor
error UX. G3-R1 raised this as Option A (fix before G4). This task implements
that fix.

---

## 3. Root Cause

```
AuthenticationMiddleware.dispatch  (backend/api/middleware/auth.py:49)
  -> JwtAuthStrategy.resolve_tenant_context  (backend/auth/strategies/jwt.py)
    -> api.context.tenant.resolve_tenant_context  (backend/api/context/tenant.py)
      -> get_user_with_permissions(session, ...)  -- queries tenant-scoped users table
        -> asyncpg UndefinedTableError (schema/table missing)
          -> SQLAlchemy wraps as ProgrammingError
            -> NOT an HTTPException
              -> falls through to middleware generic `except Exception` (auth.py:107)
                -> re-raise -> 500
```

Identity-only tokens (tenant_id is None) return early and never hit the DB, so
only contextual tokens are affected. The middleware already converts
`HTTPException` to a proper `JSONResponse` (auth.py:92-105); the gap was that
the DB error was never converted to an `HTTPException`.

---

## 4. Fix

**File**: `backend/api/context/tenant.py`

### 4.1 New helper -- `_is_missing_tenant_resource_error`

Detects DB errors caused by a missing tenant schema or table. Only matches
`sqlalchemy.exc.ProgrammingError` whose message references a missing
relation/schema (human-readable text + Postgres SQLSTATE codes `42p01` /
`3f000`). Connection faults (`OperationalError`), timeouts, and genuine code
bugs are **not** matched and keep propagating -- real auth bugs are never
silently hidden.

### 4.2 Modified `resolve_tenant_context` except block

```python
except Exception as exc:
    await session.close()
    if isinstance(exc, HTTPException):
        raise
    # G3-R2: tenant-context resolution failure caused by a missing tenant
    # schema/table must fail closed as a clean 401.
    if _is_missing_tenant_resource_error(exc):
        raise _http_exc(
            "TENANT_CONTEXT_UNRESOLVABLE",
            "Tenant context referenced by token is not available",
        )
    raise
```

The raised `HTTPException(401)` propagates to the middleware which converts it
to a clean `JSONResponse` -- no 500, no admission.

---

## 5. Preserved Behaviors

| Behavior | Preserved? |
|---|---|
| Identity-only global super_admin admitted to platform route | YES -- identity-only tokens return before DB query |
| Tenant-context super_admin denied | YES -- now clean 401 (was 500) |
| Normal tenant product auth when schema/table exists | YES -- query succeeds, no exception path |
| Product U6 onboarding/auth chain | YES -- untouched (no product files modified) |

---

## 6. Tests

**File**: `backend/tests/test_platform_p10_contracts.py` -- appended
`TestG3R2TenantContextFailClosed` class (9 tests).

| Test | Covers |
|---|---|
| `test_helper_detects_undefined_table` | ProgrammingError "undefined table" -> True |
| `test_helper_detects_undefined_schema` | ProgrammingError "undefined schema" -> True |
| `test_helper_detects_sqlstate_42p01` | SQLSTATE code marker -> True |
| `test_helper_rejects_non_db_error` | Non-ProgrammingError -> False |
| `test_helper_rejects_connection_error` | OperationalError -> False (must not mask conn faults) |
| `test_resolve_converts_missing_table_to_401` | resolve_tenant_context raises HTTPException(401) on missing table |
| `test_resolve_converts_invalid_schema_to_401` | resolve_tenant_context raises HTTPException(401) on invalid schema |
| `test_resolve_connection_error_propagates` | OperationalError re-raised unchanged (not converted) |
| `test_resolve_http_exception_passthrough` | Pre-existing HTTPException re-raised unchanged |

### Test results

| Suite | Result |
|---|---|
| `TestG3R2TenantContextFailClosed` (targeted, 9 tests) | **9/9 PASS** |
| `test_platform_p10_contracts.py` (full file, regression) | **160 passed** |

---

## 7. Validation Gates

| Gate | Result |
|---|---|
| `git diff --check` | PASS (no whitespace/conflict errors) |
| Added-line ASCII scan | tenant.py = 0 non-ASCII bytes (CLEAN); test file additions ASCII-only (162 pre-existing non-ASCII bytes unchanged from HEAD) |
| `detect-secrets scan --baseline .secrets.baseline` | EXIT 0 (clean, no new secrets) |
| `.secrets.baseline` | **UNCHANGED** (restored after scan) |
| Targeted auth/platform tests | 9/9 PASS |
| P10 contracts regression | 160 passed, 0 failed |
| `npx gitnexus analyze` | Repository indexed successfully (12,133 nodes, 36,666 edges, 772 clusters, 300 flows) |
| Worktree clean | Only 2 intended source files modified |

---

## 8. Scope Diff

```
M  backend/api/context/tenant.py                 (+44 -1)
M  backend/tests/test_platform_p10_contracts.py   (+201)
A  ai-ledger/platform/2026-07-09_product_merge_prep_g3_r2_tenant_context_deny_failclosed.md  (new)
```

2 source files modified (auth tenant-context path + targeted tests), 1 ledger
added. **0 migrations, 0 lockfile, 0 frontend runtime, 0 product business
logic, 0 protected branch push.**

---

## 9. Stop Condition Check

| Stop Condition | Triggered? |
|---|---|
| Out-of-scope file modified | NO |
| Broad auth/RBAC rewrite | NO (single narrow except block + helper) |
| Migration drift | NO |
| Backend deploy drift | NO |
| Large file deletion | NO |
| Protected branch push | NO |

**No stop conditions triggered.**

---

## 10. Risk Assessment

| Risk | Level | Mitigation |
|---|---|---|
| Over-broad exception catch hides real bugs | LOW | Only `ProgrammingError` with missing-relation markers matched; `OperationalError` and all other exceptions re-raised unchanged |
| Existing HTTPException swallowed | NONE | Explicit `isinstance(exc, HTTPException): raise` passthrough |
| Product auth regression | NONE | No product files touched; full P10 regression 160 passed |
| Performance | NONE | Error-path only; no change to success path |

---

## 11. Protected Branches

| Ref | SHA | Status |
|---|---|---|
| `origin/platform-dev` | `12c5ee55` | **UNCHANGED** |
| `origin/product-dev-recovered` | `19f6afde` | **UNCHANGED** |

Feature branch `codex/product-merge-prep-g2-resolved-merge-rehearsal-2026-07-08`
pushed only. No protected branch touched.

---

## 12. Blockers

**None.** The fix is complete, tested, and validated. Ready for G4 promotion
inclusion.
