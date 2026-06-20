# S2-R3: Platform API Test Alignment

**Date:** 2026-06-21
**Branch:** `codebuddy/s2-r3-platform-api-test-alignment-2026-06-21`
**Base:** `4e92498` (S2-R2 HEAD on `codebuddy/s2-r2-platform-admin-strict-identity-context-2026-06-21`)
**Status:** COMPLETE — all platform tests aligned, 0 production code changes
**Commit:** `589f1ca` — pushed to `origin/codebuddy/s2-r3-platform-api-test-alignment-2026-06-21`

---

## 1. Why S2-R2 Code Was Accepted but S2 Merge Was Blocked

S2-R2's `RequirePlatformAdmin` fix was code-reviewed and accepted — the dependency correctly enforces `tenant_id is None AND tenant_schema is None AND is_super_admin`. However, S2 could not merge because the **old platform API tests** (`test_platform_stats_api.py` and `test_platform_audit_api.py`) were written under the assumption that platform routes were public (no auth required). When S2-R1/R2 added `RequirePlatformAdmin` to all 8 platform routes, those tests broke:

- Stats tests: 6 business tests expected `200`, got `401` (no auth context in bare test app)
- Audit tests: 19 tests expected `200`/`400`/`404`, got `401` (auth check runs before business logic)
- JWT boundary tests: 11 tests — all passed (they don't hit platform routes)

**Result before S2-R3:** 25 failed, 27 passed.

**S2-R3 fixes only test code** — zero production code changes. The tests now run business assertions under a mock platform-admin auth context, while new boundary tests verify auth rejection.

---

## 2. How Tests Were Upgraded

### Pattern: Auth-aware test client

Each test file now provides three auth modes via a middleware-injected auth context:

| Mode | Token | RequirePlatformAdmin Result |
|------|-------|-----------------------------|
| `"platform_admin"` | `TokenPayload(user_id="...", roles=["super_admin"])` — identity-only | **Allowed** — business logic runs |
| `"contextual"` | `TokenPayload(user_id="...", tenant_id="...", tenant_schema="...", roles=["super_admin"])` | **403** PLATFORM_ADMIN_REQUIRED |
| `"none"` | No middleware — no auth context on request.state | **401** UNAUTHENTICATED |

The middleware attaches `AuthContext` to `request.state.auth_context` via `attach_auth_context()`, exactly replicating what `AuthenticationMiddleware` does in production.

### Stats API changes

- **New class `TestStatsAuthBoundary`** (3 tests): unauthenticated → 401, contextual admin → 403, platform admin → 200
- **Preserved all business tests**: `TestStatsEndpoint` (6 tests) and `TestStatsReadOnlyContract` (4 tests) now run with `auth="platform_admin"` (default)
- All original assertions (response shape, tenant keys, provisioning keys, audit keys, empty counts, ISO timestamp) are intact

### Audit API changes

- **New class `TestAuditAuthBoundary`** (4 tests): unauthenticated list/summary/detail → 401, contextual admin list → 403
- **Preserved all business tests**: `TestAuditListEndpoint` (6), `TestAuditTimeRangeFiltering` (7), `TestAuditSummaryEndpoint` (5), `TestAuditDetailEndpoint` (1), `TestReadOnlyContract` (12) — all run with `auth="platform_admin"`
- All 400/404/405 assertions preserved exactly as before

### JWT boundary tests

**No changes needed.** These tests verify token structure, strategy behavior, and middleware branching — they do not hit platform routes via TestClient. All 11 tests passed both before and after S2-R3.

---

## 3. Changed Files

| File | Change | Tests |
|------|--------|-------|
| `backend/tests/test_platform_stats_api.py` | Added auth middleware helpers + 3 boundary tests; updated business tests to use authed client | 13 total (was 10) |
| `backend/tests/test_platform_audit_api.py` | Same pattern; 4 boundary tests added | 35 total (was 31) |
| `backend/tests/security/test_jwt_boundaries.py` | **No changes** | 11 (unchanged) |
| `ai-ledger/product-ai/2026-06-21_s2r3_platform_api_test_alignment.md` | New ledger | — |

---

## 4. Unauthenticated / Non-Platform-Admin Rejected Evidence

### Stats API

```
test_unauthenticated_rejected PASSED — 401
test_contextual_admin_rejected PASSED — 403 (PLATFORM_ADMIN_REQUIRED)
```

### Audit API

```
test_unauthenticated_list_rejected PASSED — 401
test_contextual_admin_list_rejected PASSED — 403 (PLATFORM_ADMIN_REQUIRED)
test_unauthenticated_summary_rejected PASSED — 401
test_unauthenticated_detail_rejected PASSED — 401
```

---

## 5. Identity-Only Super Admin Allowed Evidence

### Stats API

```
test_platform_admin_allowed PASSED — 200
test_response_shape PASSED — 200 with all keys present
test_empty_counts PASSED — 200 with zero counts
```

### Audit API

```
test_empty_list PASSED — 200 with items=[], total=0
test_summary_empty PASSED — 200 with action_counts={}
test_detail_404 PASSED — 404 (auth passes, business logic returns 404)
```

---

## 6. Business Semantics Preserved Evidence

All original business assertions are intact and pass under platform-admin auth:

**Stats:**
- `test_response_shape` — checks `tenants`, `provisioning`, `audit`, `generated_at` keys
- `test_tenant_keys` — checks `total`, `active`, `suspended`, `other`
- `test_provisioning_keys` — checks `complete`, `pending`, `failed`
- `test_audit_keys` — checks `total_entries`, `last_24h`
- `test_empty_counts` — verifies all counts are 0
- `test_generated_at_is_iso` — verifies timestamp parses as ISO
- 4 read-only contract tests (405 for POST/PUT/PATCH/DELETE)

**Audit:**
- 6 list endpoint tests (empty, pagination, 3 filters, response shape)
- 7 time-range tests (valid params, invalid format, since>before, range>90 days)
- 5 summary tests (empty, time-range, invalid since, invalid range, exceeds max)
- 1 detail test (404)
- 12 read-only contract tests (405 for all write methods on list/summary/detail)

---

## 7. Validation Outputs

| Check | Result |
|-------|--------|
| `pytest tests/test_route_authorization_policy.py -q -rxX --tb=short` | **33 passed** in 25.86s |
| `pytest tests/test_platform_stats_api.py tests/test_platform_audit_api.py tests/security/test_jwt_boundaries.py -q --tb=short` | **59 passed** in 1.38s |
| `git diff --check` | Clean |
| Mojibake scan | ASCII-clean (no non-ASCII in changed test code) |

**Before S2-R3:** 25 failed, 27 passed (52 total)
**After S2-R3:** 0 failed, 59 passed (7 new boundary tests added)

---

## 8. Explicit Confirmations

| Constraint | Status |
|------------|--------|
| No production code changed (`rbac.py`, route handlers) | CONFIRMED — only test files changed |
| No `PUBLIC_ALLOWLIST` expansion | CONFIRMED — unchanged |
| No route authorization harness relaxation | CONFIRMED — 33/33 green, no xfail added |
| No `xfail` or `skip` added to old platform tests | CONFIRMED |
| No `product-dev-recovered` push | CONFIRMED — branch is `codebuddy/s2-r3-platform-api-test-alignment-2026-06-21` |
| No deployment | CONFIRMED — test-only changes |

---

## 9. Branch Safety

This branch contains **test-only changes** on top of S2-R2 (`4e92498`). No production code was modified. The branch aligns legacy platform tests with the new security boundary introduced in S2-R1/R2.

**Merge path:** `codebuddy/s2-r3-platform-api-test-alignment-2026-06-21` → CTO review → merge.
