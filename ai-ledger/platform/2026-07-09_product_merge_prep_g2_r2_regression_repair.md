# Product-Line Merge Preparation Gate 2-R2 -- Rehearsal Regression Repair

| Field | Value |
|---|---|
| **Task ID** | G2-R2 (Product Merge Prep Gate 2, Round 2 -- Regression Repair) |
| **Date** | 2026-07-09 |
| **Mode** | **REHEARSAL-ONLY** -- fixed D-class merge-introduced regressions on the G2 feature branch. NOT pushed to `product-dev-recovered`, no promotion. |
| **Branch** | `codex/product-merge-prep-g2-resolved-merge-rehearsal-2026-07-08` |
| **Worktree** | `_mergeresolve_g2_2026-07-08` |
| **Base (HEAD at start)** | `baf79d33` (G2-R1 failure classification ledger) |
| **Predecessor** | G2-R1 classified 98 failing tests: A=16, B=6, C=66, **D=10** (STOP before G3) |
| **Result** | **D=0 -- all 10 D-class failures resolved. 62/62 tests PASS. Ready for G3 gate.** |

---

## 1. Objective

Resolve the 10 D-class merge-introduced regressions identified by G2-R1 so the G2
resolved-merge-rehearsal branch can proceed to the G3 promotion-readiness gate.

The three D-class clusters:

| Cluster | Failures | Root cause (from G2-R1) |
|---|---|---|
| **D1** | 5 in `test_route_authorization_policy.py` | Harness `AUTH_DEPENDENCY_NAMES` didn't recognise platform guard `require_platform_operator`; 60+ routes flagged `non_compliant` |
| **D2** | 4 in `test_platform_p11c0_legacy_guard.py` | Merged `health.py` carried product's `RequirePlatformAdmin` on `/health` and `/info`; platform tests expect unauthenticated 200 |
| **D3** | 1 in `test_s6e_rbac_permission_registry_drift_gate.py` | Frontend scanner regex matched non-permission tokens (`node:fs`, `denied:acknowledge`) |

---

## 2. Constraint Compliance

- **No auth/RBAC weakening**: All sensitive platform routes (tenants/audit/stats/p23/p24/p10)
  remain guarded by `require_platform_operator`. Only non-sensitive endpoints (`/health`,
  `/info`) are public, matching the P11-C0 contract.
- **Rehearsal-only**: No push to `product-dev-recovered`. Feature branch only.
- **No backend business logic changes**: Only test harness and platform health endpoint.
- **No migration/deployment drift**: Zero Alembic, Docker, or k8s files touched.

---

## 3. D1 Fix -- `test_route_authorization_policy.py` (5 failures resolved)

### Problem

The product-side test harness classified platform routes guarded by
`require_platform_operator` (P10 identity-only guard, merged from platform-dev) as
`non_compliant` because:

1. `require_platform_operator` was not in `AUTH_DEPENDENCY_NAMES`.
2. The harness had no concept of platform operator guard wrappers
   (`require_platform_operator_with_pXX_audit`).
3. The classification engine fell through to `authenticated` (not `platform_permission`)
   because `found_platform_operator` was never set -- the `require_platform_operator`
   name matched the `AUTH_DEPENDENCY_NAMES` branch first, preventing the guard-detection
   `elif` from running.

### Changes

**`backend/tests/test_route_authorization_policy.py`**:

1. Added `require_platform_operator` to `AUTH_DEPENDENCY_NAMES` (for compliance counting).
2. Added `PLATFORM_OPERATOR_GUARD_PREFIX = "require_platform_operator_with_"` and helper
   `_is_platform_operator_guard(name)` to match the base guard and all audit-wrapper
   variants.
3. Added `PLATFORM_PUBLIC_ALLOWLIST` (`/api/v1/platform/health`, `/api/v1/platform/info`)
   for intentionally-public platform endpoints.
4. **Critical fix in `classify_route()`**: Reordered the dependency-detection if-elif
   chain so `_is_platform_operator_guard(name)` is checked FIRST, before the generic
   `name in AUTH_DEPENDENCY_NAMES` membership test. Without this, `require_platform_operator`
   (which is in both sets) hits the generic branch and `found_platform_operator` is never set.
5. Added `platform_permission` classification branch: `found_platform_operator and not
   found_require_permission` -> policy `platform_permission` with code `platform:operator`.
6. Added `PLATFORM_PUBLIC_ALLOWLIST` check in the classification priority chain.
7. Updated `test_all_platform_routes_require_platform_permission` to accept `public` policy
   for allowlisted routes.
8. Updated `test_platform_routes_have_auth_dependency` to exempt `PLATFORM_PUBLIC_ALLOWLIST`.
9. Updated `test_harness_detects_auth_dependencies_correctly` to exempt public routes.
10. Renamed `test_platform_routes_use_require_platform_admin` to
    `test_platform_routes_use_platform_guard` -- now accepts either `RequirePlatformAdmin`
    or any `_is_platform_operator_guard()` match, and exempts public routes.
11. Updated `test_platform_routes_reject_non_platform_admin_http` to remove `/health` and
    `/info` from `protected_paths` (they return 200 unauthenticated by design).

### Auth boundary preserved

- All 28 sensitive platform routes (audit, tenants, stats, p10, p23, p24) are classified
  as `platform_permission` and verified to reject non-platform-admin access.
- Only 2 non-sensitive endpoints are public (health/info).
- The `RequirePlatformAdmin` boundary tests (identity-only super admin, contextual token
  rejection, partial-context rejection) are all unchanged and PASS.

---

## 4. D2 Fix -- `backend/api/v1/platform/health.py` (4 failures resolved)

### Problem

The G2 merge carried the product-side version of `health.py` which had
`Depends(RequirePlatformAdmin())` on both `/health` and `/info` endpoints. The platform
contract (`test_platform_p11c0_legacy_guard.py::TestHealthInfoUnauthenticated`) requires
these endpoints to return 200 without authentication -- they expose only non-sensitive
platform status (status, track, timestamp, version, boundaries).

### Changes

**`backend/api/v1/platform/health.py`**:

- Removed `from api.middleware.rbac import RequirePlatformAdmin` import.
- Removed `from core.security import TokenPayload` import.
- Removed `token: TokenPayload = Depends(RequirePlatformAdmin())` parameter from both
  `platform_health()` and `platform_info()`.
- Restored both endpoints to parameterless public handlers.
- Added G2-R2 comment block documenting the restoration rationale.

### Security assessment

- `/health` returns: `{"status": "ok", "track": "platform-p0", "timestamp": "..."}` -- no
  tenant data, no secrets, no operational metrics.
- `/info` returns: track metadata, version, and boundary documentation -- no tenant data,
  no secrets.
- All sensitive platform routes remain guarded by `require_platform_operator`.

---

## 5. D3 Fix -- `test_s6e_rbac_permission_registry_drift_gate.py` (1 failure resolved)

### Problem

The frontend permission scanner in `extract_frontend_permissions()` used regex
`['"]([a-z_]+:[a-z_]+)['"]` to find permission-code references in `.ts`/`.tsx` files.
After the G2 merge, the frontend gained new test files that contained string literals
matching this regex but are NOT permission codes:

| Token | Source file | Actual meaning |
|---|---|---|
| `node:fs` | `pages/platform/__tests__/p25/__helpers__/readiness.tsx` | Node.js built-in module import |
| `node:path` | Same + `P25_RouteInventory.test.tsx` | Node.js built-in module import |
| `denied:acknowledge` | `PlatformOperatorTasksPage.test.tsx` | Platform transition error fixture |
| `denied:close` | `PlatformIncidentCloseoutsPage.test.tsx` | Incident closeout error fixture |
| `denied:complete` | `platformOperatorTasksApi.test.ts` | Task transition denied status |

These false positives were not seeded in the backend permission registry, causing the
drift gate to fail.

### Changes

**`backend/tests/test_s6e_rbac_permission_registry_drift_gate.py`**:

1. **Exclude test files from scan**: Skip `__tests__` directories and `*.test.*` /
   `*.spec.*` files entirely. Permission codes are defined in production source only;
   test files contain mock fixtures and error-message literals that are not permissions.
2. **False-positive prefix denylist**: Added `_false_positive_prefixes = ("node:", "denied:")`
   as defense-in-depth to filter any remaining non-permission tokens that match the regex
   but are structurally not permission codes in this codebase.

### RBAC integrity preserved

- All genuine permission codes (e.g., `intake:create`, `exports:create`, `skus:import`)
  are still extracted and verified against the seed registry.
- The `test_api_route_permissions_are_seeded_in_all_tenant_provisioning_paths` test still
  validates that every API-route permission is seeded in all provisioning scripts.
- No permission codes were removed from the seed registry; only false positives were filtered.

---

## 6. Test Results

### D-Class Test Suite (after fixes)

```
python -m pytest tests/test_route_authorization_policy.py \
    tests/test_platform_p11c0_legacy_guard.py \
    tests/test_s6e_rbac_permission_registry_drift_gate.py \
    -v --tb=short

Result: 62 passed, 4 warnings in 23.51s
```

| File | Tests | Result |
|---|---|---|
| `test_route_authorization_policy.py` | 35 | 35 PASSED |
| `test_platform_p11c0_legacy_guard.py` | 23 | 23 PASSED |
| `test_s6e_rbac_permission_registry_drift_gate.py` | 4 | 4 PASSED |
| **Total** | **62** | **62 PASSED** |

---

## 7. Validation Gates

| Gate | Result |
|---|---|
| `git diff --check` (whitespace) | PASS (exit 0) |
| ASCII scan (all 3 changed files) | ALL CLEAN (pure ASCII, no em-dash/unicode) |
| `.secrets.baseline` unchanged | PASS (not in diff) |
| No backend business logic changes | PASS (only health.py endpoint + test harness) |
| No migration/deployment drift | PASS (zero Alembic/Docker/k8s files) |

---

## 8. Scope Diff Gate

Files committed in G2-R2 (staged selectively; pre-existing modified binary/lock files excluded):

```
M  backend/api/v1/platform/health.py
M  backend/tests/test_route_authorization_policy.py
M  backend/tests/test_s6e_rbac_permission_registry_drift_gate.py
```

Pre-existing modified files left in working tree (NOT committed -- from G2 rehearsal artifacts):
- `frontend/pnpm-lock.yaml`
- `verify/p25ef/screenshots/*.png`
- `verify/p25ef/smoke_result.json`

---

## 9. Verdict

**D count = 0. All 10 G2-R1 D-class merge-introduced failures resolved.**

The G2 resolved-merge-rehearsal branch is ready for the G3 promotion-readiness gate.
