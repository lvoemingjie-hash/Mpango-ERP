# P11-B0 Platform Auth Transport Decision -- Batch Readiness Packet

**Date**: 2026-06-08
**Branch**: `codex/platform-p11b0-auth-transport-2026-06-08`
**Base**: `origin/platform-dev` at `5d376d73d3d7d0211fd413c3fbb7b9df32167950`
**Status**: Ready for review

---

## Objective

Resolve the P11-B blocking auth transport question: backend P10 guard now accepts Bearer-authenticated `super_admin` users, while keeping `X-Platform-Operator` secret support for server/operator contexts. No secret material in browser frontend.

## CTO Decision

Do NOT put `PLATFORM_OPERATOR_SECRET` or `X-Platform-Operator` secret material in browser frontend. Extend backend guard to accept existing Bearer/JWT-authenticated `super_admin` users.

## Solution

Extended `require_platform_operator` guard in `backend/api/v1/platform/p10/guard.py` to check three credential types (any sufficient):

1. **Authenticated super_admin via Bearer/JWT** (new in P11-B0): reads `request.state.auth_context` set by existing auth middleware, checks `token.is_super_admin`. No parallel auth system -- reuses existing `AuthContext` and `TokenPayload`.

2. **X-Platform-Operator secret** (existing from P10-R1): header matches `PLATFORM_OPERATOR_SECRET` env var. Remains for server/operator contexts (CI, scripts, monitoring).

3. **X-Platform-Test-Override** (existing from P10-R2): exact secret match in `MPANGO_ENV=test|testing` only.

## Modified Files

| File | Action |
|------|--------|
| `backend/api/v1/platform/p10/guard.py` | Modified -- added Bearer super_admin check |
| `backend/tests/test_platform_p10_contracts.py` | Modified -- added 14 Bearer super_admin tests |
| `docs/ai/PLATFORM_PRODUCT_P11_FRONTEND_BOUNDARY.md` | Modified -- recorded auth transport resolution |
| `ai-ledger/platform/2026-06-08_p11b0_auth_transport.md` | New -- this ledger |

**Total**: 1 new file, 3 modified files, 0 deletions.

## How It Works

```
Request arrives at P10 endpoint
  |
  +--> require_platform_operator(request, ...)
         |
         +--> _get_super_admin_from_request(request)
         |      reads request.state.auth_context (set by auth middleware)
         |      returns True if token.is_super_admin
         |
         +--> _is_platform_operator(op, test, is_super_admin)
                - if is_super_admin -> ALLOW
                - if test override valid -> ALLOW
                - if operator secret valid -> ALLOW
                - else -> DENY
```

Key design decisions:
- Reuses `get_auth_context()` from `api.context.auth` -- no parallel auth system.
- Reuses `TokenPayload.is_super_admin` property -- no new role checking.
- `admin` role is NOT sufficient -- only `super_admin`.
- Auth context missing (unauthenticated) returns False gracefully -- not an error.
- Existing P10-R2 test override restrictions fully preserved.

## Tests

### New tests (14):

| Test | What it proves |
|------|---------------|
| test_super_admin_bearer_allowed | super_admin via Bearer -> 200 on tenants |
| test_super_admin_bearer_allowed_system_health | super_admin via Bearer -> 200 on system health |
| test_super_admin_bearer_allowed_audit_events | super_admin via Bearer -> 200 on audit events |
| test_admin_role_denied | admin role is NOT sufficient -> 401 |
| test_user_role_denied | user role is NOT sufficient -> 401 |
| test_empty_roles_denied | no roles is NOT sufficient -> 401 |
| test_no_auth_context_denied | no auth context -> 401 |
| test_operator_secret_still_allowed | X-Platform-Operator still works -> 200 |
| test_wrong_operator_secret_still_denied | wrong secret -> 403 |
| test_test_override_still_denied_in_development | test override still denied in dev -> 403 |
| test_test_override_still_denied_in_production | test override still denied in prod -> 403 |
| test_test_override_allowed_in_test_env | test override works in test env -> 200 |
| test_super_admin_in_test_env_allowed | super_admin works in test env too -> 200 |
| test_super_admin_in_production_allowed | super_admin works in prod via Bearer -> 200 |

### All test results:

| Suite | Count | Status |
|-------|-------|--------|
| P10 contracts (pre-B0) | 115 | PASS |
| P10 Bearer super_admin (B0) | 14 | PASS |
| **P10 total** | **129** | **PASS** |
| P0 regression | 71 | PASS |
| **Grand total** | **200** | **ALL PASS** |

## GitNexus Risk

**HIGH** -- auth boundary runtime change. The P10 guard is modified to accept a new credential type (Bearer super_admin). Acceptable because:
- Tests prove deny-by-default is preserved (14 new tests + 26 existing guard tests).
- No product/business paths are touched.
- Only `super_admin` role passes -- admin, user, empty roles all denied.
- Existing X-Platform-Operator and test override behavior fully preserved.
- Reuses existing auth infrastructure -- no parallel auth system.

GitNexus impact: `require_platform_operator` LOW (0 external callers). `_is_platform_operator` LOW (1 direct caller).

## Forbidden Path Audit

| Path Pattern | Found |
|-------------|-------|
| `frontend/` | X None |
| `backend/` outside P10 module | X None |
| `.github/` | X None |
| `.claude/` | X None |
| `product-dev-recovered/` | X None |
| `migration/` | X None |
| `payment/` | X None |
| `session/` | X None |
| `auth/` (broad rewrite) | X None -- reuses existing auth context, no rewrite |
| Only P10 guard + tests + docs changed | OK Confirmed |

## Push Status

Branch `codex/platform-p11b0-auth-transport-2026-06-08` pushed. Not merged to `platform-dev`.
