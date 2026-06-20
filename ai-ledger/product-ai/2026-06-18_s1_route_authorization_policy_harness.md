# S1 Route Authorization Policy Harness

**Date:** 2026-06-18
**Status:** Test/contract-only. Phase 1 delivered.
**Production code changed:** NO (test + ledger only)

> **WARNING -- DO NOT MERGE THIS BRANCH TO `product-dev-recovered`.**
> This is a **test / contract evidence branch**, not a merge candidate.
> The master contract gate (`TestRoutePolicyContract::test_no_unclassified_business_routes`)
> is **intentionally designed to FAIL** (per CTO requirement #5: "routes without
> policy and not on allowlist must fail tests"). Merging this branch into the
> product line would break CI. The branch exists only to (a) land the harness
> infrastructure and (b) freeze the findings inventory as governance evidence.
> Once Phase 2 fixes the underlying routes in production code, the master gate
> will turn green on the Phase 2 branch -- at that point the harness file can be
> cherry-picked, but this specific S1 branch should remain archived, not merged.

## Findings Summary (R1 clarification)

| Bucket | Count | Mechanism | Routes |
|--------|-------|-----------|--------|
| **Master gate hard-fail routes** | **10** | `pytest.fail()` in `TestRoutePolicyContract::test_no_unclassified_business_routes` | 8 P0 platform + 2 P1 export |
| **Strict xfail findings** | **2** | `@pytest.mark.xfail(strict=True)` in `TestInternalRoutePolicy` | 2 P2 internal profiling |
| **TOTAL non-compliant findings** | **12** | -- | 8 P0 + 2 P1 + 2 P2 |

The 10 master-gate routes and the 2 P2 xfail routes are distinct, non-overlapping sets.

---

## 1. Branch / Commit / Base

| Item | Value |
|------|-------|
| Branch | `codebuddy/s1-route-authorization-policy-harness-2026-06-18` |
| Base commit | `53ca2143f5e43b918c258e3f488e6944c5a7a41b` (= `origin/product-dev-recovered` HEAD) |
| Current commit (post-R1) | see `git log -1` on the branch |
| Files added | 2 (1 test file + 1 ledger) |
| Production code modified | 0 |
| Mergeable to `product-dev-recovered` | **NO** (master gate intentionally fails) |

## 2. Changed Files

| File | Status | Purpose |
|------|--------|---------|
| `backend/tests/test_route_authorization_policy.py` | A (new) | Route authorization policy harness; scans FastAPI app, classifies every `/api/v1/**` route |
| `ai-ledger/product-ai/2026-06-18_s1_route_authorization_policy_harness.md` | A (new) | This ledger |

**Zero production code changes.** No `.py` service/model/router/middleware modified, no migration, no frontend.

---

## 3. Route Policy Classification Rules

The harness imports the FastAPI `app`, enumerates every registered `APIRoute` whose `path` starts with `/api/v1/`, and walks the **full dependency tree** of each route recursively (`route.dependant.dependencies[].dependencies[]...`).

### 3.1 Dependency name resolution

For each dependency callable in the tree, the harness resolves a canonical name:
- Plain function / lambda -> `dep.__name__` (e.g. `get_current_user_context`)
- `functools.partial` -> `dep.func.__name__`
- Class instance used as `Depends(...)` -> `type(dep).__name__` (e.g. `RequirePermission`)

This is critical: `type(func).__name__` returns `"function"` for every plain dependency and is useless for classification. The harness must use `__name__` directly.

### 3.2 Policy categories

Every route is classified into exactly one policy bucket:

| Category | Meaning | Detection rule |
|----------|---------|----------------|
| `public` | Pre-auth endpoint (login, refresh, invitation validation, retailer signup) | Path is in explicit `PUBLIC_ALLOWLIST` |
| `authenticated` | Any logged-in user, no specific permission | Has `get_current_user_context` / `resolve_client_identity` / `get_policy_subject` but NO `RequirePermission` |
| `tenant_permission:<code>` | Tenant-scoped RBAC permission required | Has `RequirePermission` whose `.permission` does NOT start with `platform:` / `system:` |
| `platform_permission:<code>` | Platform-scoped RBAC permission required | Has `RequirePermission` whose `.permission` starts with `platform:` or `system:` |
| `internal_only` | Diagnostic / test endpoints; must additionally require `system:admin` | Path under `/api/v1/test/` |
| `non_compliant` | NONE of the above; no explicit auth policy and not allowlisted | Catch-all FAIL bucket |

### 3.3 Known auth vs non-auth dependencies

```python
AUTH_DEPENDENCY_NAMES = {
    "RequirePermission",          # class instance, has .permission attr
    "RequireBIPermission",        # BI asset-level enforcement
    "get_current_user_context",   # JWT validation -> request.state.identity
    "resolve_client_identity",    # Client API JWT + retailer binding
    "get_policy_subject",         # BI trust boundary builder
}

NON_AUTH_DEPENDENCY_NAMES = {
    "get_db", "get_db_session", "get_tenant_db_session",
    "get_job_queue", "get_reporting_session",
}
```

A route whose only dependency is `get_db` is NOT authenticated -- it is classified `non_compliant`.

### 3.4 PUBLIC_ALLOWLIST (minimal, CTO sign-off required)

```python
{
    "/api/v1/auth/login",          # credentials exchange -> tokens
    "/api/v1/auth/refresh",        # refresh token in body
    "/api/v1/invitations/{code}",  # pre-auth invitation validation (retailer signup flow)
    "/api/v1/retailers/register",  # pre-auth retailer self-registration via invitation code
}
```

No platform, export, or business-data routes are on this list.

---

## 4. Harness Design: How it satisfies CTO requirement #6

> Requirement #6: tests must NOT only scan for `RequirePermission`; they must discover routes that have NO `RequirePermission` at all.

The harness does NOT grep source for the string `RequirePermission`. It walks the actual FastAPI dependency tree at runtime. A route with `Depends(get_db)` and nothing else resolves to dependency name set `{"get_db"}`, which intersects `AUTH_DEPENDENCY_NAMES` as empty -> classified `non_compliant`.

Verification test `TestHarnessIntegrity::test_harness_detects_routes_with_zero_auth_deps` asserts that `NON_COMPLIANT_ROUTES` is non-empty, proving the harness is functional (otherwise the platform routes would have slipped through).

---

## 5. Findings: Non-Compliant Route Inventory

### P0 BLOCKERS - `/api/v1/platform/**` routes (8 routes)

These routes expose platform-wide multi-tenant data (tenant list, audit logs, provisioning status, platform stats) with NO authentication dependency at all -- only `get_db`.

| Method | Path | Deps | Risk |
|--------|------|------|------|
| GET | `/api/v1/platform/health` | `[]` | Low (info) but sets bad precedent |
| GET | `/api/v1/platform/info` | `[]` | Low (info) but sets bad precedent |
| GET | `/api/v1/platform/tenants/` | `[get_db]` | **CRITICAL**: lists ALL tenants + provisioning status |
| GET | `/api/v1/platform/tenants/{wholesaler_id}` | `[get_db]` | **CRITICAL**: arbitrary tenant detail |
| GET | `/api/v1/platform/audit/` | `[get_db]` | **CRITICAL**: full audit log dump |
| GET | `/api/v1/platform/audit/summary` | `[get_db]` | HIGH: audit summary |
| GET | `/api/v1/platform/audit/{log_id}` | `[get_db]` | HIGH: arbitrary log read |
| GET | `/api/v1/platform/stats/` | `[get_db]` | HIGH: platform KPIs |

**Required fix (Phase 2):** Add `Depends(RequirePermission("platform:admin"))` (or finer `platform:tenants:read`, `platform:audit:read`, `platform:stats:read`) to every `/api/v1/platform/**` route. Health/info may use a lighter `platform:health` if desired but MUST have an explicit policy.

### P1 FINDINGS - Export status/download (2 routes)

| Method | Path | Deps | Risk |
|--------|------|------|------|
| GET | `/api/v1/exports/{job_id}` | `[]` | Export job status |
| GET | `/api/v1/exports/{job_id}/download` | `[]` | Export file download |

**Root cause:** Tenant ownership IS verified inside the function body via `get_tenant_context()`, but this is invisible to the dependency scanner. The policy is implicit, not declarative.

**Required fix (Phase 2):** Add `Depends(get_current_user_context)` to make authentication explicit at the dependency level. The body-level tenant ownership check can remain as defense-in-depth.

### P2 FINDINGS - Internal test routes (2 routes)

| Method | Path | Deps | Risk |
|--------|------|------|------|
| GET | `/api/v1/test/profiling-test` | `[get_db]` | Low (only registered when `MPANGO_ENV != production`) |
| GET | `/api/v1/test/profiling-test-slow` | `[get_db]` | Low (only registered when `MPANGO_ENV != production`) |

**Required fix (Phase 2):** Add `Depends(RequirePermission("system:admin"))` so even if `MPANGO_ENV` is misconfigured, these routes cannot be hit by non-admin callers. Note `jobs_test.py` routes ARE correctly gated and serve as the reference pattern.

---

## 6. Test Results

```
20 tests collected
14 passed
5 xfailed  (8 P0 platform + 2 P1 export are surfaced by per-category xfails;
            2 P2 internal profiling are surfaced by a separate xfail test)
1 FAILED   (master gate -- intentionally hard-fails to surface the 10-route
            findings inventory: 8 platform + 2 export)
```

### 6.1 Master-gate vs xfail breakdown

The 10 routes that trigger the master-gate hard-fail are exactly:

- 8 P0 `/api/v1/platform/**` routes (health, info, tenants/, tenants/{id}, audit/, audit/summary, audit/{id}, stats/)
- 2 P1 `/api/v1/exports/{job_id}` and `/api/v1/exports/{job_id}/download`

The 2 additional routes surfaced only via strict xfail (not part of the master-gate count) are:

- 2 P2 `/api/v1/test/profiling-test` and `/api/v1/test/profiling-test-slow` (gated by `MPANGO_ENV != production`, lower severity)

**Total non-compliant findings: 10 (master gate) + 2 (strict xfail) = 12.**

### 6.2 Why the master gate hard-fails instead of xfailing

Per CTO requirement #5 ("routes without policy and not on allowlist must fail tests"), the master contract gate `TestRoutePolicyContract::test_no_unclassified_business_routes` does NOT xfail -- it `pytest.fail()`s with the full 10-route findings list. This guarantees the policy gap stays visible in CI until Phase 2 fixes land.

The P2 internal profiling routes are tracked via a separate strict xfail test rather than the master gate, because they are non-production diagnostic endpoints (only registered when `MPANGO_ENV != production`). Keeping them out of the master-gate count keeps the gate focused on real production exposure while still surfacing the P2 gap.

When Phase 2 fixes the underlying routes:
- The 5 strict xfails will flip to xpass; with `strict=True`, xpass itself becomes a failure, signaling that the xfail marker should be removed.
- The master gate will turn green once all 10 master-gate routes have explicit auth policies.

### 6.3 Test classes

| Class | Tests | Purpose |
|-------|-------|---------|
| `TestHarnessIntegrity` | 5 | Harness works: scans all `/api/v1/` routes, finds zero-auth routes, classifies known-good routes, printable |
| `TestRoutePolicyContract` | 2 | Master contract gate: all routes classified, NO business routes unclassified (this is the FAIL) |
| `TestPlatformRoutePolicy` | 3 | All `/api/v1/platform/**` must require `platform:*` permission (2 xfail P0) |
| `TestExportRoutePolicy` | 4 | Export create/streaming compliant; status/download lack explicit permission (2 xfail P1) |
| `TestInternalRoutePolicy` | 2 | `/api/v1/test/**` must require `system:admin` (1 xfail P2 covering both profiling routes) |
| `TestPublicAllowlistIntegrity` | 3 | Allowlist minimal, no platform routes, allowlisted routes resolve as public |
| `TestFindingsInventory` | 1 | Prints full classification table for human review |

---

## 7. Verifications Run (R1)

| Check | Result |
|-------|--------|
| Test suite runs | YES -- `pytest tests/test_route_authorization_policy.py -q -rxX --tb=short` -> 20 tests: 14 passed, 5 xfailed, 1 failed (intentional) |
| Findings list printed | YES -- master gate prints 10 non-compliant routes with deps; full classification table printed by `TestFindingsInventory` |
| `git diff --check` | PASS (no whitespace errors) |
| Mojibake / non-ASCII scan | PASS -- both files pure ASCII (0 non-ASCII bytes) |
| Pre-commit hooks | PASS 5/5 (trim-trailing-whitespace, end-of-file-fixer, check-yaml skip, check-large-files, detect-secrets with pragma allowlist) |
| `git diff --name-status origin/product-dev-recovered..HEAD` | 2 files: `A ai-ledger/product-ai/2026-06-18_s1_route_authorization_policy_harness.md`, `A backend/tests/test_route_authorization_policy.py` -- zero production code touched |
| GitNexus detect_changes | CLI has no `detect_changes` subcommand (only `status`); scope verified manually via `git diff --stat` |
| Production code modified | NO |
| Migration modified | NO |
| Frontend modified | NO |

---

## 8. Test / Contract-Only Confirmation

This task is **strictly test + contract only**:
- 1 new test file (`backend/tests/test_route_authorization_policy.py`)
- 1 new ledger file (this document)
- ZERO production code modifications
- ZERO migrations
- ZERO frontend changes
- ZERO `.py` files outside `backend/tests/`

The harness DOES NOT relax any test to make unsafe behavior pass. The 5 xfail markers explicitly document each finding with its category, root cause, and recommended fix. When Phase 2 fixes the underlying routes, the xfails will flip to xpass (strict=True will then signal the fix landed).

---

## 9. No-Deploy / No-Product-Branch-Push Confirmation

| Confirmation | Status |
|--------------|--------|
| No deployment triggered | CONFIRMED -- no CloudBase/Lighthouse/EdgeOne/CloudStudio/AnyDev invocation |
| No push to `product-dev-recovered` | CONFIRMED -- `origin/product-dev-recovered` still at `53ca2143`; this branch's commit will live only on isolated branch `codebuddy/s1-route-authorization-policy-harness-2026-06-18` |
| No migration run | CONFIRMED -- zero migration files touched |
| No frontend build/publish | CONFIRMED -- frontend untouched |

---

## 10. Deliverables

- Isolated branch: `codebuddy/s1-route-authorization-policy-harness-2026-06-18`
- Pushed to remote: yes
- Commit hash: see `git log -1` on the branch
- Test file: `backend/tests/test_route_authorization_policy.py`
- Ledger: this file
- Findings inventory: section 5 above (10 master-gate routes: 8 P0 + 2 P1; plus 2 P2 strict-xfail routes = 12 total)

---

## 11. Task Status / Closure Table

| Step | Status | Notes |
|------|--------|-------|
| Explore backend route structure and permission decorators | DONE | Examined `api/app.py`, `api/middleware/rbac.py`, `api/middleware/auth.py`, `api/middleware/bi_access.py`, all `api/v1/**/*.py` route files, `api/dependencies.py`, `api/v1/client/dependencies.py` |
| Build route scanning helper | DONE | Integrated into test file: `_collect_all_dependencies()`, `_dependency_name()`, `classify_route()` |
| Create `test_route_authorization_policy.py` | DONE | 20 tests across 7 test classes; harness walks full FastAPI dependency tree recursively |
| Run tests / capture findings / write ledger | DONE | 14 passed, 5 xfailed, 1 failed (master gate); findings: 10 master-gate + 2 P2 xfail = 12 total |
| Verify (diff --check, mojibake, pre-commit, detect scope) | DONE | All checks pass; `git diff --name-status` confirms only 2 new files, 0 production code |
| Self-iteration Round 3 | NOT NEEDED | R1 (initial build) resolved all harness logic bugs (dependency name resolution, MPANGO_ENV bootstrap). S1-R1 (this correction) is a ledger-clarity pass, not a logic iteration. No test logic changed. |
| Final report completed | DONE | This document |

### Self-iteration history

| Round | What happened |
|-------|---------------|
| **R1 (initial)** | Built harness. Fixed 3 bugs during build: (1) `_dependency_name` returning `"function"` instead of actual function name; (2) `APIRoute` import path; (3) `MPANGO_ENV` hard-set to override `.env=production`. Also discovered 2 pre-auth public routes (invitations, retailers/register) that belonged on allowlist. |
| **S1-R1 (this round)** | Ledger clarity correction only. Clarified 10 master-gate vs 2 P2 xfail distinction, added DO-NOT-MERGE warning, added closure table. No test logic or failure semantics changed. |
