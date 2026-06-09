# P11-B0-R1 Auth Boundary Tightening + Evidence Fix

**Date**: 2026-06-09
**Branch**: `codex/platform-p11b0-auth-transport-2026-06-08`
**R1 Commit**: `b5e23ff2dcb904a102079c338487ef4c1e17f47a`
**Base**: `codex/platform-p11b0-auth-transport-2026-06-08` at P11-B0 commit
**Status**: R2 evidence + doc polish

---

## Objective

Tighten P11-B0 auth transport to require **identity-only** (global) super_admin
tokens for browser Bearer access to P10 platform endpoints.  Tenant-contextual
tokens with super_admin role are NO LONGER sufficient for platform API access.

This prevents a user who has selected a tenant (holding a contextual JWT) from
accessing platform-wide endpoints -- platform access is a global/identity-level
privilege that must be exercised before tenant selection.

## Problem (P11-B0 -> P11-B0-R1)

P11-B0 accepted *any* Bearer-authenticated super_admin, including
tenant-contextual tokens.  This was too broad:

- A user with super_admin role within a specific tenant could access
  platform-wide tenant lists, system health, and audit events.
- Platform access is a **global** privilege -- it should only be available
  before tenant selection (identity-only JWT), not during a tenant session
  (contextual JWT).

## Solution

Extended `_check_identity_super_admin` (renamed from `_get_super_admin_from_request`)
to verify **three** conditions instead of two:

1. Auth middleware attached an `AuthContext` to `request.state`
2. The token has `super_admin` in roles (`token.is_super_admin`)
3. **NEW**: The token is identity-only (`token.is_identity_only`)

A contextual token (with `tenant_id`/`tenant_schema`) is now rejected for P10
platform access, even if the user holds `super_admin` role within that tenant.

## Modified Files

| File | Action |
|------|--------|
| `backend/api/v1/platform/p10/guard.py` | Modified -- identity-only check tightened |
| `backend/tests/test_platform_p10_contracts.py` | Modified -- R1-specific tests added |
| `ai-ledger/platform/2026-06-09_p11b0_r1_auth_boundary_tightening.md` | New -- this ledger |

**Total**: 1 new file, 2 modified files, 0 deletions.

## Key Changes

### guard.py

| Before (P11-B0) | After (P11-B0-R1) |
|------------------|--------------------|
| `_get_super_admin_from_request()` | `_check_identity_super_admin()` |
| Checks `token.is_super_admin` | Checks `token.is_super_admin AND token.is_identity_only` |
| Any super_admin token accepted | Only identity-only super_admin accepted |
| Contextual super_admin -> ALLOW | Contextual super_admin -> DENY |

### Test Additions

**New test class `TestBearerSuperAdminAccess`** (16 tests):

| Test | What it proves |
|------|---------------|
| `test_identity_super_admin_bearer_allowed` | Identity-only super_admin via Bearer -> 200 |
| `test_identity_super_admin_system_health` | Identity-only super_admin -> system health 200 |
| `test_identity_super_admin_audit_events` | Identity-only super_admin -> audit events 200 |
| `test_contextual_super_admin_denied` | **Contextual super_admin -> DENIED** |
| `test_contextual_super_admin_denied_system_health` | **Contextual super_admin -> system health DENIED** |
| `test_admin_role_denied` | admin role NOT sufficient -> 401 |
| `test_user_role_denied` | user role NOT sufficient -> 401 |
| `test_empty_roles_denied` | no roles NOT sufficient -> 401 |
| `test_no_auth_context_denied` | no auth context -> 401 |
| `test_operator_secret_still_allowed` | X-Platform-Operator still works -> 200 |
| `test_wrong_operator_secret_still_denied` | wrong secret -> 403 |
| `test_test_override_still_denied_in_development` | test override in dev -> 403 |
| `test_test_override_still_denied_in_production` | test override in prod -> 403 |
| `test_test_override_allowed_in_test_env` | test override in test env -> 200 |
| `test_identity_super_admin_in_test_env` | identity super_admin in test -> 200 |
| `test_identity_super_admin_in_production` | identity super_admin in prod -> 200 |

**New test class `TestBearerRealMiddleware`** (5 real middleware + 1 manual auth-context):

Real middleware tests (prove full JWT decode + auth pipeline end-to-end):

| Test | What it proves |
|------|---------------|
| `test_real_identity_super_admin_allowed` | Real JWT identity super_admin -> 200 |
| `test_real_identity_admin_denied` | Real JWT identity admin -> 401 |
| `test_real_identity_user_denied` | Real JWT identity user -> 401 |
| `test_real_no_auth_denied` | No Authorization header -> 401 |
| `test_real_identity_super_admin_system_health` | Real JWT identity super_admin -> system health 200 |

Manual auth-context guard test (contextual denial without real middleware):

| Test | What it proves |
|------|---------------|
| `test_contextual_super_admin_denied_with_auth_context` | Manual auth-context injection: contextual super_admin -> DENIED |

Note: The real middleware `resolve_tenant_context` requires a live DB for
contextual tokens, so contextual super_admin denial is proven by the manual
auth-context injection test above, and by `test_contextual_super_admin_denied`
in `TestBearerSuperAdminAccess`.

## Tests

| Suite | Count | Status |
|-------|-------|--------|
| P10 contract structure (CS-xxx) | 25 | [PASS] |
| P10 fixture conformance (FC-xxx) | 9 | [PASS] |
| P10 counterexample rejection (CR-xxx) | 6 | [PASS] |
| P10 read-only behavior (RO-xxx) | 17 | [PASS] |
| P10 API response shape | 11 | [PASS] |
| P10 no leakage | 4 | [PASS] |
| P10-R1/R2 platform guard | 26 | [PASS] |
| **P11-B0-R1 Bearer identity super_admin** | **16** | **[PASS]** |
| **P11-B0-R1 Real middleware** | **5** | **[PASS]** |
| **P11-B0-R1 Manual auth-context (contextual)** | **1** | **[PASS]** |
| P10-R1-B metadata redaction | 8 | [PASS] |
| **P10 total** | **see pytest** | **[ALL PASS]** |
| P0 regression (p0 + audit + audit_api + stats) | see pytest | [PASS] |
| **Grand total** | **see pytest** | **[ALL PASS]** |

Run command:
```bash
python -m pytest tests/test_platform_p10_contracts.py -v --tb=short
python -m pytest tests/test_platform_p0.py tests/test_platform_audit.py tests/test_platform_audit_api.py tests/test_platform_stats_api.py -v --tb=short
```

## GitNexus Risk

**HIGH** -- auth boundary runtime tightening. The P10 guard is modified to
reject contextual super_admin tokens that were previously accepted. This is a
**security tightening** -- it can only reduce access, never expand it.

Acceptable because:
- Tests prove deny-by-default is preserved (16 Bearer tests + 5 real middleware tests + 1 manual contextual test).
- No product/business paths are touched.
- Only identity-only `super_admin` passes -- admin, user, empty roles, and contextual
  super_admin all denied.
- Existing X-Platform-Operator and test override behavior fully preserved.
- Reuses existing auth infrastructure -- no parallel auth system.

## Forbidden Path Audit

| Path Pattern | Found |
|-------------|-------|
| `frontend/` | [NONE] |
| `backend/` outside P10 module | [NONE] |
| `.github/` | [NONE] |
| `.claude/` | [NONE] |
| `product-dev-recovered/` | [NONE] |
| `migration/` | [NONE] |
| `payment/` | [NONE] |
| `session/` | [NONE] |
| `auth/` (broad rewrite) | [NONE] -- reuses existing auth context |
| Only P10 guard + tests + ledger changed | [CONFIRMED] |

## Git Diff Summary

```
 backend/api/v1/platform/p10/guard.py         | 72 +++---
 backend/tests/test_platform_p10_contracts.py | 316 ++++++++++++++-----
 2 files changed, 303 insertions(+), 85 deletions(-)
```

Key renames:
- `_get_super_admin_from_request` -> `_check_identity_super_admin`
- `is_super_admin` -> `is_identity_super_admin` (parameter name)
- Added `token.is_identity_only` check alongside `token.is_super_admin`

## Auth Boundary Gap Audit (Broader Scan)

In addition to the R1 tightening, a scan of ALL endpoints in the working project
identified the following auth boundary status:

### [OK] Properly Guarded Endpoints

| Module | Auth Mechanism | Status |
|--------|---------------|--------|
| `api/v1/platform/p10/*` | `require_platform_operator` (P11-B0-R1) | [OK] Guarded |
| `api/v1/auth/*` | Public (login/refresh) or `get_current_user_context` | [OK] Correct |
| `api/v1/orders/*` | `RequirePermission` | [OK] Guarded |
| `api/v1/users/*` | `RequirePermission` | [OK] Guarded |
| `api/v1/roles/*` | `RequirePermission` | [OK] Guarded |
| `api/v1/payments/*` | `RequirePermission` | [OK] Guarded |
| `api/v1/inventory/*` | `RequirePermission` | [OK] Guarded |
| `api/v1/skus/*` | `RequirePermission` | [OK] Guarded |
| `api/v1/finance/*` | `RequirePermission` | [OK] Guarded |
| `api/v1/wholesalers/*` | `RequirePermission` | [OK] Guarded |
| `api/v1/invitations/*` | `RequirePermission` | [OK] Guarded |
| `api/v1/retailers/*` | `RequirePermission` | [OK] Guarded |
| `api/v1/dashboards/*` | `RequirePermission` | [OK] Guarded |
| `api/v1/reports/*` | `RequirePermission` | [OK] Guarded |
| `api/v1/exports/*` (POST) | `RequirePermission("exports:create")` | [OK] Guarded |
| `api/v1/data_export/*` | `RequirePermission("exports:create")` | [OK] Guarded |
| `api/v1/client/*` | `resolve_client_identity` | [OK] Guarded |
| `api/v1/bi/assets/*` | `get_auth_context` + `get_tenant_context` (inline) | [OK] Guarded |
| `api/v1/metrics/*` (DELETE) | `RequirePermission("metrics:admin")` | [OK] Guarded |
| `api/v1/test/*` | `RequirePermission("system:admin")` + env gate | [OK] Guarded |

### [NOTE] Unauthenticated Endpoints (Intentional)

| Module | Endpoint | Reason |
|--------|----------|--------|
| `api/v1/health.py` | All health probes | K8s liveness/readiness -- must work without auth |
| `api/v1/prometheus.py` | `GET /metrics` | Internal monitoring -- network-level protection |
| `api/v1/metrics.py` (GET) | `GET /api/v1/metrics` | Requires auth via `get_current_user_context` [OK] |
| Root `/` | API info | Public metadata |

### [WARN] Known Auth Gap -- OLD P0 Platform Endpoints (Pre-P10, NOT in R1 scope)

| Module | Endpoint | Issue |
|--------|----------|-------|
| `api/v1/platform/health.py` | `GET /health`, `GET /info` | **No auth guard** |
| `api/v1/platform/tenants.py` | `GET /`, `GET /{id}` | **No auth guard** |
| `api/v1/platform/audit.py` | `GET /`, `GET /summary`, `GET /{id}` | **No auth guard** |
| `api/v1/platform/stats.py` | `GET /` | **No auth guard** |

These are P0 scaffold endpoints registered at `/platform/...` (not `/platform/p10/...`).
They predate the P10 guard module and expose similar data without authentication.

**Recommendation**: These should be either:
1. Removed (P10 endpoints are their guarded replacements), or
2. Wired with `require_platform_operator` dependency, or
3. Deprecated and routed to P10 equivalents with a redirect.

**This is NOT in P11-B0-R1 scope** -- R1 only tightens the existing P10 guard.
A separate P11-C or cleanup task should address the P0 unguarded endpoints.

## Known Limitations (unchanged from P10-R2)

1. Health signals return placeholder values (no telemetry infrastructure).
2. TenantSummary/TenantHealth/SystemHealth fields mostly null/unknown.
3. PlatformAuditEvent is a placeholder mapping from P0 audit logs.
4. No rate limiting specific to P10 endpoints.
5. Guard uses shared-secret header model for operator context.
6. **Old P0 platform endpoints unguarded** -- see gap audit above.

## Recommended Next Steps

1. **P11-C: Remove or guard P0 platform endpoints** -- eliminate the unguarded
   P0 scaffold that exposes tenant/audit/stats data without auth.
2. **P11-A: Health Signal Infrastructure** -- build tenant health check infrastructure,
   wire TenantHealth and SystemHealth to real data sources.

## Push Status

R1 pushed as `b5e23ff2dcb904a102079c338487ef4c1e17f47a` on branch `codex/platform-p11b0-auth-transport-2026-06-08`.
R2 evidence + doc polish applied to docs and ledger, pushed as `078a660fa89e0e25ed1a14bfcf9e5b74e9a5db07`.
Final reviewed HEAD: `078a66028e7630b5953cc608ccdcdaff2043804b`.
