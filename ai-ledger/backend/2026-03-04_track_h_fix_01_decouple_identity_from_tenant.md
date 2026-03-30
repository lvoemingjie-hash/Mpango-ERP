# Track H-Fix-01: Decouple Identity from Tenant Context

**Date**: 2026-03-04  
**Priority**: P0 BLOCKER FIX  
**Status**: ✅ COMPLETE (code changes; requires integration test with live DB)

---

## Problem Statement

The `POST /auth/login` endpoint required a `tenant_code` field, coupling **identity verification** to **tenant context**.  This caused two blockers:

1. **Cold Start (FTUE)**: New users who don't yet know their tenant code cannot log in.
2. **Super Admin Lock-out**: Platform-level admins who don't belong to any specific tenant cannot authenticate.

Identity must be verified independently of context.

---

## Architecture: Two-Phase Authentication

```
Phase 1: Identity          Phase 2: Context
─────────────────          ─────────────────
POST /auth/login           POST /auth/select-tenant
  ↓                          ↓
email + password           tenant_id + Identity JWT
  ↓                          ↓
Identity JWT               Contextual JWT
(user_id, roles)           (user_id, roles, tenant_id, tenant_schema)
  ↓                          ↓
Frontend: tenant picker    Frontend: enter app with full tenant scope
```

### Token Types

| Token       | Claims                                        | Use Case                            |
|-------------|-----------------------------------------------|--------------------------------------|
| **Identity**    | `user_id`, `roles`                            | Login response, tenant picker, super admin system endpoints |
| **Contextual**  | `user_id`, `roles`, `tenant_id`, `tenant_schema` | All tenant-scoped business endpoints |

---

## Files Modified

### Core Security (`core/security.py`)
- `TokenPayload.tenant_id` → `Optional[str] = None`
- `TokenPayload.tenant_schema` → `Optional[str] = None`
- Added `TokenPayload.roles: List[str] = []`
- Added `TokenPayload.is_identity_only` property
- Added `TokenPayload.is_super_admin` property
- New: `create_identity_token(user_id, roles)` — no tenant claims
- New: `create_contextual_token(user_id, roles, tenant_id, tenant_schema)` — full claims
- Legacy `create_access_token` / `create_refresh_token` → wrappers around `create_contextual_token`

### Schemas (`schemas/auth.py`)
- `LoginRequest`: **removed** `tenant_code` field (now: email + password only)
- New: `TenantInfo(id, code, name)`
- New: `IdentityTokenData(access_token, refresh_token, user_id, roles, available_tenants)`
- New: `IdentityLoginResponse`
- New: `SelectTenantRequest(tenant_id)`
- `TokenData`: added `roles` field
- `CurrentUserData`: `tenant_id` and `tenant_schema` now Optional

### CRUD (`crud/user.py`)
- New: `TenantUserMatch` dataclass
- New: `find_user_across_tenants(db_public, email, password)` — scans all active tenant schemas, verifies password, returns list of matching tenants with roles

### Auth Endpoint (`api/v1/auth.py`)
- **`POST /login`**: Removed `tenant_code`. Calls `find_user_across_tenants`, returns `IdentityLoginResponse` with identity JWT + `available_tenants` list.
- **`POST /select-tenant`** (NEW): Accepts `tenant_id` + Identity JWT, verifies user access, returns Contextual JWT.
- **`POST /refresh`**: Updated to handle both identity and contextual refresh tokens.
- **`GET /me`**: Updated to return minimal info for identity-only tokens (no DB query needed), full user data for contextual tokens.

### JWT Strategy (`auth/strategies/jwt.py`)
- `resolve_tenant_context` returns `None` for identity-only tokens (was: always resolved)

### Mock Strategy (`auth/strategies/mock.py`)
- `_MockToken`: added `roles`, `is_identity_only`, `is_super_admin` properties for interface compatibility

### Auth Middleware (`api/middleware/auth.py`)
- `dispatch`: now checks if `tenant_ctx is not None` before attaching tenant context, setting tenant filter, and enforcing isolation. Identity-only JWTs pass through without tenant context.

### RBAC Middleware (`api/middleware/rbac.py`)
- `RequirePermission.__call__`: Identity JWT + `super_admin` role → bypass permission check (super admin has all permissions)
- Identity JWT without `super_admin` → returns 403 with "select a tenant first"
- Contextual JWT + `super_admin` → bypass permission check
- Contextual JWT + regular role → existing permission check

### Tests Updated
- `tests/test_request_validation.py`: Removed `tenant_code` from all login payloads, renamed test from `test_login_rejects_missing_tenant_code` to `test_login_rejects_missing_email`
- `tests/test_route_coverage.py`: Removed `tenant_code` from login test payload

---

## Unchanged Components

- **Tenant Guardrail** (`db/tenant_filter.py`): No changes. Global ORM filter still reads tenant context from ContextVar. Guardrails protect data access, not the login door.
- **Tenant Context** (`api/context/tenant.py`): No changes. Still requires `tenant_schema` from token to create session.
- **Wholesaler CRUD** (`crud/wholesaler.py`): No changes.
- **Wholesaler API** (`api/v1/wholesalers.py`): No changes needed — `RequirePermission` now handles super admin bypass.

---

## Login Flow (Before vs After)

### Before (v0.2.0)
```
POST /auth/login { tenant_code, email, password }
  → Contextual JWT (user_id + tenant_id + tenant_schema)
  → Frontend enters app directly
```

### After (H-Fix-01)
```
POST /auth/login { email, password }
  → Identity JWT (user_id + roles) + available_tenants[]

POST /auth/select-tenant { tenant_id }  [Authorization: Bearer <identity_jwt>]
  → Contextual JWT (user_id + roles + tenant_id + tenant_schema)
  → Frontend enters app with full tenant scope
```

---

## Super Admin Access Path

```
POST /auth/login { email, password }
  → Identity JWT with roles: ["super_admin"]
  → available_tenants: [] (or all tenants)

GET /api/v1/wholesalers  [Authorization: Bearer <identity_jwt>]
  → RequirePermission("wholesalers:read") → super_admin bypass → 200 OK
  → No tenant context needed for public schema operations
```

---

## Verification

- All 8 modified `.py` files pass `python -m py_compile`
- Test files updated to match new LoginRequest schema (no `tenant_code`)
- Full integration testing requires live DB with tenant schemas (not done in this session)

---

## Frontend Impact

The frontend auth flow needs to be updated to:
1. Remove `tenantCode` from login form / API call
2. Handle `available_tenants` in login response
3. Show tenant picker when `available_tenants.length > 1`
4. Auto-select when `available_tenants.length === 1`
5. Call `POST /auth/select-tenant` before entering the app
6. Store both identity and contextual tokens appropriately
