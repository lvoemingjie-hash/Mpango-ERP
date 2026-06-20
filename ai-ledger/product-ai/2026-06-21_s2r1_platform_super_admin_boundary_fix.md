# S2-R1: Platform Super-Admin Boundary Fix

**Date:** 2026-06-21
**Branch:** `codebuddy/s2-r1-platform-super-admin-boundary-2026-06-21`
**Base:** `5bc3bf8` (S2 HEAD on `codebuddy/s2-route-authorization-production-fix-2026-06-21`)
**Status:** COMPLETE — 8 platform routes upgraded, 31/31 tests green
**Commit:** `4953718` — pushed to `origin/codebuddy/s2-r1-platform-super-admin-boundary-2026-06-21`

---

## 1. Objective

Fix the S2 boundary gap: platform routes used `RequirePermission("system:admin")`, which allows a **contextual tenant admin** whose tenant role grants `system:admin` to access cross-tenant platform data (tenant list, audit logs, platform stats). This is an authorization boundary violation: platform endpoints expose data across ALL tenants, so they must only be accessible from the **platform scope** (identity-only super admin), never from within a tenant boundary.

**Solution:** Introduce `RequirePlatformAdmin` — a dependency that requires **both** `token.is_identity_only == True` and `token.is_super_admin == True`. Any contextual token (one that has selected a tenant) is rejected with 403, regardless of roles or permissions.

---

## 2. Why S2's `system:admin` Is Insufficient

`RequirePermission("system:admin")` has three pass paths (see `rbac.py:31-75`):

| Path | Condition | S2 Result | S2-R1 Result |
|------|-----------|-----------|--------------|
| 1 | Identity-only + super_admin | Allowed | Allowed (RequirePlatformAdmin) |
| 2 | Contextual + super_admin | Allowed | **Rejected 403** |
| 3 | Contextual + tenant role has `system:admin` | **Allowed** | **Rejected 403** |

**Path 3 is the vulnerability.** A tenant admin whose tenant role grants `system:admin` permission can access `/api/v1/platform/tenants/` and see ALL tenants, `/api/v1/platform/audit/` and see ALL audit logs, etc. This is cross-tenant data leakage — the tenant admin should only see their own tenant's data.

**Path 2 is also a boundary violation.** Even a legitimate super_admin who has selected a tenant (contextual token) should not access platform data from within a tenant scope. Platform operations require the deliberate, tenant-unbound identity token.

`RequirePlatformAdmin` closes both paths by checking `token.is_identity_only and token.is_super_admin` — anything else gets 403.

---

## 3. Changed Files

| File | Change | Routes |
|------|--------|--------|
| `backend/api/middleware/rbac.py` | Added `RequirePlatformAdmin` class | (new dependency) |
| `backend/api/v1/platform/health.py` | `RequirePermission("system:admin")` → `RequirePlatformAdmin()` | health, info |
| `backend/api/v1/platform/tenants.py` | Same upgrade | list_tenants, get_tenant |
| `backend/api/v1/platform/audit.py` | Same upgrade | list_audit_logs, audit_summary, get_audit_log |
| `backend/api/v1/platform/stats.py` | Same upgrade | platform_stats |
| `backend/tests/test_route_authorization_policy.py` | Added `RequirePlatformAdmin` to harness; added 7 boundary tests; removed 1 duplicate HTTP smoke test | — |

**Unchanged files (by design):**
| File | Reason |
|------|--------|
| `backend/api/v1/profiling_test.py` | Internal diagnostic, not cross-tenant platform data. Keeps `RequirePermission("system:admin")`. |
| `backend/api/v1/exports.py` | Uses `get_current_user_context` + tenant ownership check. Not affected. |

---

## 4. RequirePlatformAdmin Implementation

```python
class RequirePlatformAdmin:
    """
    Platform-level dependency that ONLY accepts identity-only super admin tokens.
    """
    def __init__(self):
        self.permission = "platform:admin"  # for harness classification

    async def __call__(self, request: Request) -> TokenPayload:
        auth_ctx = get_auth_context(request)  # raises 401 if no auth
        token = auth_ctx.token

        if not (token.is_identity_only and token.is_super_admin):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "PLATFORM_ADMIN_REQUIRED",
                    "message": "Platform endpoints require an identity-only "
                               "super admin token (no tenant context).",
                },
            )
        return token
```

**Design decisions:**
- `self.permission = "platform:admin"` — allows the S1 harness to classify routes as `platform_permission` (starts with `"platform:"` prefix) without requiring a separate policy category.
- 401 for no auth context (delegated to `get_auth_context`).
- 403 for wrong token type (not 401) — the caller IS authenticated, just not authorized for platform scope.

---

## 5. Test Evidence

### 5.1 Identity Super Admin Allowed

```
test_identity_only_super_admin_allowed PASSED
```
Token: `TokenPayload(user_id="sa-1", roles=["super_admin"])` — no tenant_id/tenant_schema.
Result: `RequirePlatformAdmin()` returns the token (access granted).

### 5.2 Contextual Tenant Admin Rejected

```
test_contextual_tenant_admin_rejected PASSED
```
Token: `TokenPayload(user_id="admin-1", tenant_id="...", tenant_schema="t_abc123", roles=["admin"])`.
Result: `HTTPException(403, PLATFORM_ADMIN_REQUIRED)`.

### 5.3 Contextual Super Admin Rejected

```
test_contextual_super_admin_rejected PASSED
```
Token: `TokenPayload(user_id="sa-1", tenant_id="...", tenant_schema="t_abc123", roles=["super_admin"])`.
Result: `HTTPException(403)` — even a super_admin who selected a tenant cannot access platform routes.

### 5.4 Unauthenticated Rejected

```
test_unauthenticated_rejected PASSED
```
Request: bare request, no auth context.
Result: `HTTPException(401, UNAUTHENTICATED)`.

### 5.5 HTTP-Level: Platform Routes Reject Mock Auth

```
test_platform_routes_reject_non_platform_admin_http PASSED
```
MockAuthStrategy authenticates with a contextual non-super-admin token (`tenant_id=t_dev, roles=[]`).
All 5 tested paths return 403 `PLATFORM_ADMIN_REQUIRED`.

### 5.6 Route Policy Harness: All Routes Classified

```
test_platform_routes_use_require_platform_admin PASSED
```
All 8 platform routes have `RequirePlatformAdmin` in their detected auth dependencies.

### 5.7 Full Test Suite

```
31 passed, 2 warnings in 26.00s
```

Breakdown:
- TestHarnessIntegrity: 5 tests
- TestRoutePolicyContract: 2 tests
- TestPlatformRoutePolicy: 3 tests
- TestPlatformAdminBoundary: **7 tests** (NEW)
- TestExportRoutePolicy: 4 tests
- TestInternalRoutePolicy: 2 tests
- TestPublicAllowlistIntegrity: 3 tests
- TestFindingsInventory: 1 test
- TestSmokeAuthGate: 4 tests (1 removed, was 5)

---

## 6. Explicit Confirmations

| Constraint | Status |
|------------|--------|
| `PUBLIC_ALLOWLIST` NOT expanded | CONFIRMED — unchanged: `{auth/login, auth/refresh, invitations/{code}, retailers/register}` |
| S1/S2 harness NOT relaxed | CONFIRMED — 31/31 green, no xfail markers added |
| Platform route tests NOT changed to "not 200" | CONFIRMED — tests assert specific 403 PLATFORM_ADMIN_REQUIRED |
| No deployment | CONFIRMED — code changes only |
| No push to `product-dev-recovered` | CONFIRMED — branch is `codebuddy/s2-r1-platform-super-admin-boundary-2026-06-21` |

---

## 7. Validation Outputs

| Check | Result |
|-------|--------|
| `pytest tests/test_route_authorization_policy.py -q -rxX --tb=short` | 31 passed in 26.00s |
| `git diff --check` | Clean (no whitespace errors) |
| Pre-commit hooks | All passed |
| Mojibake scan | Clean |

---

## 8. Branch Safety

This branch is based on S2 (`5bc3bf8`), which is itself based on S1 (`738395e`). The S2-R1 branch adds a stricter platform auth boundary on top. It should NOT be merged to `product-dev-recovered` without a separate code review by the CTO.

**Merge path:** `codebuddy/s2-r1-platform-super-admin-boundary-2026-06-21` → code review → cherry-pick or merge to `product-dev-recovered` (CTO approvals required).
