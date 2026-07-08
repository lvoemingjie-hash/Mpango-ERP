# P25-EC: Platform Frontend Real-Stack Browser Smoke + Screenshot Evidence

| Field | Value |
|-------|-------|
| **Task ID** | P25-EC (R4 ledger base ref correction) |
| **Date** | 2026-07-08 |
| **Branch** | `codex/platform-p25ec-real-stack-browser-smoke-evidence-2026-07-08` |
| **Base** | `origin/platform-dev @ 6de86015` |
| **Scope** | Validation scripts, logs, screenshots, ledger ONLY. No backend/frontend runtime code, no migrations, no package/lockfile, no auth/RBAC rewrites. |
| **Verdict** | **STOP_AND_REPORT_CTO** (Part A: 0-backend-5xx blocked by global tenant filter; Part B: identity smoke PASS; Part C: artifact cleanup PASS) |

---

## 1. Objective

Validate the platform frontend (P10-P24 surface, 19 routes) against a **real**
backend (uvicorn in production mode) + **real** database (Docker Postgres 15) +
**real** browser (Chromium headless via Playwright), producing screenshot
evidence and auth-boundary proof.

R1 correction re-runs all tests with stricter success criteria:
- **Part A (route smoke):** 0 backend 5xx console/network errors required.
- **Part B (identity smoke):** `tenant_context_admin_deny` must be a clean
  401/403, NOT 500.

## 2. Base Proof Gate

P25-EC is a continuation branch. The authoritative diff base is
`origin/platform-dev = 6de86015` ("merge: P25-EB P22 durable approval resolver
alignment"), which is the parent commit of the P25-EC commits. All scope diff
gates compare against `6de86015`.

```
git rev-parse 6de86015                  = 6de86015 (origin/platform-dev)
git log --oneline -1 6de86015           = 6de86015 merge: P25-EB P22 ...
git rev-parse HEAD                      = 67db3ec3 (P25-EC-R2)
git diff --name-status 6de86015..HEAD   = 30 files (all verify/p25ec/ + ledger)
git status --short                      = clean
```

Base proof gate: PASS -- branch is a clean continuation on top of
`origin/platform-dev = 6de86015`; no staged/modified files.

## 3. Part A -- Route Smoke Test (19 Routes)

### 3.1 Success Criteria (R1)

- 19/19 routes load (HTTP 200 from Vite)
- 0 React page errors (pageerror)
- **0 backend 5xx console/network errors**
- 0 forbidden controls
- Screenshots captured

### 3.1 Results

| Metric | Value | Criterion Met? |
|--------|-------|----------------|
| Total routes navigated | 19 | -- |
| HTTP 200 (page loaded) | 19/19 | PASS |
| Screenshots captured | 19/19 | PASS |
| Routes with page errors (React crash) | 0/19 | PASS |
| Routes with forbidden controls | 0/19 | PASS |
| **Routes with 5xx console errors** | **15/19** | **FAIL** |
| Routes redirected (to /login) | 4/19 | -- |

### 3.2 Root Cause of 500 Errors

The 500 errors originate from the **global tenant filter**
(`install_global_tenant_filter` in `backend/db/tenant_filter.py`).

The filter intercepts ALL SQLAlchemy ORM execute events via
`Session.do_orm_execute`. For any model with a `tenant_id` or `wholesaler_id`
column, it raises `TenantContextMissingError` unless both:

1. A tenant schema is present in the session (`session.info["tenant_schema"]`)
2. A tenant_id is present in the session (`session.info["tenant_id"]`)

Platform routes use `get_db()` which sets `session.info["tenant_schema"] =
"public"` but does NOT set a `tenant_id`. Therefore, any platform endpoint that
queries a model with `tenant_id` or `wholesaler_id` (e.g.
`PlatformAuditLog.wholesaler_id`) triggers:

```
TenantContextMissingError: Tenant context missing: tenant_id required for
tenant-scoped query
```

This produces HTTP 500 on 15 of 19 platform routes.

### 3.3 Why This Cannot Be Fixed Without Runtime Code Changes

The R1 directive states: "If you cannot make the real stack representative
without runtime code changes, STOP_AND_REPORT_CTO."

The fixes for the 500 errors all require modifying runtime code:

1. **`run_as_system(reason=...)`** wrapper in platform route handlers
   (used in `crud/user.py` for cross-tenant login scan)
2. **`execution_options(ignore_tenant=True)`** per-statement bypass
3. **Modify the tenant filter** to skip public-schema models

All three are explicitly OUT OF SCOPE for P25-EC (evidence-only task, no
runtime code changes).

### 3.4 Part A Verdict: STOP_AND_REPORT_CTO

**0 backend 5xx** is NOT achievable without runtime code changes to exempt
platform/public-schema queries from the global tenant filter.

### 3.5 Route-Level Detail

Routes WITH 500 errors (15):
`/platform/tenants`, `/platform/tenants/:id/health`, `/platform/audit`,
`/platform/registry`, `/platform/ops/health`, `/platform/ops/errors`,
`/platform/ops/slow-routes`, `/platform/ops/resources`,
`/platform/ops/noisy-neighbors`, `/platform/ops/incidents/triage`,
`/platform/approvals`, `/platform/durable-approvals`,
`/platform/controlled-execution`, `/platform/operator-tasks`,
`/platform/incident-closeouts`

Routes WITHOUT 500 errors (4) -- NOTE: these are NOT customer-readiness passes;
they merely had no backend 5xx observed in the smoke window. 3 of 4 redirect to
`/login` (401), which means the route was never actually exercised against a
backend query. Only 1 route (`/platform/support`) is genuinely clean.
- `/platform` -- redirected to /login (401 console errors only; not exercised)
- `/platform/system/health` -- redirected to /login (401 console errors only; not exercised)
- `/platform/controlled-actions` -- redirected to /login (mixed 401/500; not exercised)
- `/platform/support` -- **clean** (0 errors, 0 forbidden controls; genuinely exercised)

Evidence:
- JSON: `verify/p25ec/playwright_route_smoke_result.json`
- Log: `verify/p25ec/playwright_route_smoke_log.txt`
- Screenshots: `verify/p25ec/screenshots/*.png` (19 files)

## 4. Part B -- Identity Smoke Test (P10 Auth Boundary)

### 4.1 R1 Correction

The previous run accepted HTTP 500 for `tenant_context_admin_deny` (caused by
missing tenant schema crashing the middleware before the P10 guard). R1
provisions a throwaway tenant schema (`t_smoke_r1`) with RBAC tables and a seed
user, so `resolve_tenant_context` succeeds cleanly and the P10 guard can
evaluate `is_identity_only` properly.

### 4.2 Tenant Schema Provisioning

Schema `t_smoke_r1` created with minimal RBAC structure:
- Tables: `users`, `roles`, `permissions`, `user_roles`, `role_permissions`
- Seed user: `00000000-0000-0000-0000-000000000002` (super_admin role)
- SQL: `verify/p25ec/tenant_setup_r1.sql`

### 4.3 Results (6/6 PASS)

| # | Test Case | Credential | Expected | Actual | Result |
|---|-----------|-----------|----------|--------|--------|
| 1 | `operator_admit` | `X-Platform-Operator` header | 200 | 200 | PASS |
| 2 | `test_override` | `X-Platform-Test-Override` header | 403 (prod) | 403 | PASS |
| 3 | `identity_super_admin_admit` | Identity-only super_admin JWT | 200 | 200 | PASS |
| 4 | `no_credentials_deny` | (none) | 401 | 401 | PASS |
| 5 | `wrong_operator_deny` | Wrong `X-Platform-Operator` | 403 | 403 | PASS |
| 6 | `tenant_context_admin_deny` | Tenant-context super_admin JWT | **401 or 403** | **401** | **PASS** |

### 4.4 Boundary Analysis

- **P10 guard correctly admits** operator-secret and identity-only super_admin
  JWT credentials (HTTP 200 with empty `closeouts: []` response).
- **P10 guard correctly denies** missing credentials (401) and wrong secrets
  (403). The 401-vs-403 distinction is correct: 401 = no credentials at all,
  403 = credentials present but insufficient.
- **Test override rejected in production** (403) -- the
  `X-Platform-Test-Override` path is correctly gated to test environment only.
- **R1 FIX:** `tenant_context_admin_deny` now returns **clean 401** (not 500).
  With the provisioned `t_smoke_r1` schema, the middleware's
  `resolve_tenant_context` succeeds, loads the seed user, and the P10 guard
  cleanly rejects because `is_identity_only=False`. This proves the identity
  boundary: `identity_context != identity_only` is correctly enforced.

Evidence:
- Script: `verify/p25ec/identity_smoke.py`
- Result: `verify/p25ec/identity_smoke_r1_result.txt`

### 4.5 Part B Verdict: PASS

All 6 identity boundary tests pass with clean HTTP status codes (no 500s).

## 5. Frontend Build Gate

**Command:** `cd frontend && pnpm run build`

**Result:** PASS (exit 0)

- Vite v5.4.21 transformed 1258 modules in 8.66s.
- `dist/` generated successfully.
- Warnings: browserslist data age (non-blocking), chunk size > 500 kB
  (non-blocking).

## 6. Real-Stack Configuration

### 6.1 Docker Postgres 15

- Container: `mpango_p25ec_pg` (postgres:15)
- Port: `5433` (host) -> `5432` (container)
- Database: `mpango_erp`, user: `mpango`

### 6.2 Uvicorn (Production Mode)

- `MPANGO_ENV=production` -- activates `JwtAuthStrategy` (real JWT decode).
- Port: `8000` (for Vite proxy) and `8001` (for identity smoke).
- `SECRET_KEY`: 64-char throwaway smoke value.
- `DATABASE_URL`: `postgresql://mpango:...@127.0.0.1:5433/mpango_erp`
- `REDIS_URL`: `redis://localhost:6379/1`
- `REPORTING_DATABASE_URL`: same as DATABASE_URL (smoke override).
- `PLATFORM_OPERATOR_SECRET`: `test-operator-secret`
- `PLATFORM_TEST_OVERRIDE_SECRET`: `test-platform-override-secret`

## 7. Artifact Cleanup (R2 -- Completed)

R2 removes all root-level `_p25ec_*` evidence files and migrates evidence to
`verify/p25ec/`.

**Completed (R2):**
- All root-level `_p25ec_*.txt` files deleted from git index (9 files).
- `_p25ec_evidence/` directory deleted from git index (scripts, logs,
  screenshots, JSON results).
- New evidence in `verify/p25ec/` (scripts, results, screenshots, SQL).
- ANSI escape codes stripped from all committed logs.
- JSON output uses `ensure_ascii=True` (ASCII-only).
- Tenant schema provisioning SQL documented.
- ASCII scan: all committed text files are ASCII-clean.
- detect-secrets: no secrets detected (`"results": {}`).

## 8. Scope Diff Gate

Authoritative diff base: `origin/platform-dev = 6de86015`.

Net diff `6de86015..HEAD` (30 files, all added -- no deletions, no runtime code):
- Added: `verify/p25ec/` (scripts, results, screenshots, SQL, logs)
- Added: `ai-ledger/platform/2026-07-08_p25ec_real_stack_browser_smoke_evidence.md`

(The root-level `_p25ec_*` files were created and deleted within P25-EC commits
73282ad5/67db3ec3, so they do not appear in the net diff against `6de86015`.)

No backend code, frontend code, migrations, package files, lockfiles, auth/RBAC
code, or deployment configuration modified.

## 9. Evidence Inventory

| Artifact | Location |
|----------|----------|
| Identity smoke script (R1) | `verify/p25ec/identity_smoke.py` |
| Identity smoke result (R1) | `verify/p25ec/identity_smoke_r1_result.txt` |
| Playwright route smoke script (R1) | `verify/p25ec/playwright_route_smoke.py` |
| Playwright route smoke JSON | `verify/p25ec/playwright_route_smoke_result.json` |
| Playwright route smoke log | `verify/p25ec/playwright_route_smoke_log.txt` |
| 19 route screenshots | `verify/p25ec/screenshots/*.png` |
| Uvicorn startup log | `verify/p25ec/uvicorn_r1.log` |
| Tenant setup SQL | `verify/p25ec/tenant_setup_r1.sql` |
| Vite startup log | `verify/p25ec/vite_r1_out.log` |

## 10. Conclusion

**STOP_AND_REPORT_CTO**

### Summary

| Part | Criterion | Result |
|------|-----------|--------|
| A.1 | 19/19 routes load (HTTP 200) | PASS |
| A.2 | 0 React page errors | PASS |
| A.3 | **0 backend 5xx console errors** | **FAIL (15/19 routes have 500)** |
| A.4 | 0 forbidden controls | PASS |
| A.5 | Screenshots captured | PASS (19/19) |
| B.1 | P10 admits identity-only tokens | PASS |
| B.2 | P10 denies tenant-context tokens cleanly | PASS (401, not 500) |
| B.3 | 6/6 identity boundary tests pass | PASS |
| C | Artifact cleanup | PASS (R2: old root `_p25ec_*` files deleted, evidence in `verify/p25ec/`, ASCII-clean) |
| Build | `pnpm run build` exit 0 | PASS |

### Blocking Issue

The global tenant filter (`install_global_tenant_filter`) blocks platform API
queries because platform models (e.g. `PlatformAuditLog`) have `wholesaler_id`.
Platform routes use `get_db()` (public schema, no `tenant_id` in session),
which triggers `TenantContextMissingError` -> HTTP 500 on 15 of 19 routes.

**This requires a runtime code change** (run_as_system wrapper, ignore_tenant
flag, or filter exemption for public-schema models) which is **out of scope**
for P25-EC.

### Recommended Next Step (CTO Decision)

Create a follow-up task (e.g. P25-ED) to add `run_as_system(reason="platform
query")` or `execution_options(ignore_tenant=True)` to platform route handlers
that query tenant-scoped models through the public-schema session. Then re-run
the route smoke test to achieve 0 backend 5xx.
