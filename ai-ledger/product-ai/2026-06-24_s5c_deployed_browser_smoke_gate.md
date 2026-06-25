# S5-C Deployed Browser Smoke / Real Runtime Gate

**Date**: 2026-06-24 (cleanup revision R1: 2026-06-25)
**Branch**: `opencode/s5c-deployed-browser-smoke-gate-2026-06-24`
**Base**: `origin/product-dev-recovered` (contains `c958fae`)
**Author**: AI operator (agentic mode)
**Tool**: agent-browser (Chromium automation)

---

## Verdict

**`BROWSER_SMOKE_PASS_DEPLOYMENT_DRIFT_DETECTED`**

- Browser smoke over the 8 required pages **PASS** (no 401/403/500, all pages render).
- S5-A backend gate tests **3/3 FAIL** (deployed Docker image is behind source for the `returned` order-status reconciliation and the `import_runs` alembic migration).
- CSV Import API **404** on the deployed image (`sku_imports` module not present in container).
- Therefore this **cannot be treated as a full deployed runtime gate PASS**. The browser-only leg passed; the backend/import legs reveal deployment drift between the source repository and the running Docker image.

> This is a diagnostic report, not a release sign-off. No login credentials, DB passwords, or usable tokens are recorded here.

---

## 1. Real Runtime Environment

### Stack (Docker Compose prod)

| Service | Container | Status |
|---------|----------|--------|
| PostgreSQL 16 | `mpango_prod_db` | Healthy |
| Redis 7 | `mpango_prod_redis` | Healthy |
| Backend (FastAPI) | `mpango_prod_backend` | Healthy |
| Frontend (Nginx/React) | `mpango_prod_frontend` | Healthy |
| Gateway | `mpango_prod_gateway` | Healthy |

DB connection string and admin credentials are intentionally omitted. They are provisioned out-of-band via secret management and are not part of this report.

### Tenant Under Test

| Field | Value |
|-------|-------|
| Tenant code | `s5c_test` |
| Wholesaler UUID | `ec198175-3876-4445-a435-1c788c000657` |
| Schema (UUID-derived) | `t_ec19817538764445a4351c788c000657` |
| Admin user (login email) | **redacted** (delivered out-of-band) |
| Admin password | **redacted** (delivered out-of-band) |
| RBAC permissions | 37 (full admin set, including `skus:import`) |

### Tenant Bootstrap Notes

- The tenant was bootstrapped through the platform tenant lifecycle path used by the existing `bootstrap_tenant_schema.bootstrap()`.
- **Important**: Schema name MUST be derived from the Wholesaler UUID (`t_{uuid_without_dashes}`), NOT from the tenant code. A code-derived name like `t_s5c_test` will NOT be found by `find_user_across_tenants()` and must be renamed to the UUID-derived form.
- The bootstrap email must pass Pydantic `EmailStr` validation; reserved TLDs such as `.test` are rejected.

> The temporary diagnostic bootstrap script used during the original gate run was removed in R1 because it embedded credentials and was never intended as a deployment artifact.

---

## 2. Browser Smoke -- 8-Page Coverage

All pages verified via agent-browser (real Chromium), authenticated as the redacted admin user through the dual JWT flow (Identity + Contextual).

| # | Page | URL | Status | Notes |
|---|------|-----|--------|-------|
| 1 | Home | `/` | **PASS** | Dashboard rendered, "Welcome back, S5C Admin. (s5c_test)" |
| 2 | Sales | `/orders` | **PASS** | "0 orders found", no errors |
| 3 | Products | `/skus` | **PASS** | "Products (SKUs)", "No products found", Import button present |
| 4 | Stock | `/inventory` | **PASS** | "Stock", "0 SKUs in stock" |
| 5 | Money | `/finance` | **PASS** | "Accounts Receivable", zero balances |
| 6 | Payments | `/payments` | **PASS** | "No payments found" |
| 7 | Customers | `/retailers` | **PASS** | "No customers yet" |
| 8 | Pricing | `/pricing` | **PASS** | "Customer Pricing" with dropdown |

**401/403/500 errors**: None detected across all 8 pages.

### Network/API Check

- All page-load API calls succeeded with valid JWTs (Identity + Contextual dual-token flow).
- No 401 (unauthorized), 403 (forbidden), or 500 (server error) responses observed during navigation.

> Browser smoke is the only leg that reflects the **as-deployed** image behavior. Backend tests below required hot-copying source modules into the container and therefore reflect source semantics, not the deployed image.

---

## 3. Backend Gate Tests

### Important caveat -- diagnostic only

The S5 test files and several import modules are **not present in the deployed Docker image**. To run the gate suites against the running DB, the following files were `docker cp`-ed from the source tree into the container at runtime:

- `backend/tests/test_s5a_fresh_tenant_real_user_journey_gate.py`
- `backend/tests/test_s5_order_state_machine.py`
- `backend/tests/test_s5_ledger.py`
- `backend/tests/test_s5_5_ledger_hardening.py`
- `backend/services/import_service.py`
- `backend/models/import_run.py`
- `backend/schemas/import_schemas.py`

**This hot-copy is a diagnostic technique to exercise the running database.** It does **not** mean the deployed Docker image contains these modules. The image itself is unchanged; the running process simply has additional files injected for the duration of the test. The 3 S5-A failures below are failures against the **deployed DB state / bootstrap logic baked into the image**, not against the copied source modules.

### Environment

- pytest 9.1.1 installed at runtime inside `mpango_prod_backend` (also not in the base image).
- `pytest-asyncio` installed at runtime.

### Results Summary

| Test Suite | Pass | Fail | Total |
|-----------|------|------|-------|
| S5 Order State Machine | 13 | 0 | 13 |
| S5 Ledger | 15 | 0 | 15 |
| S5.5 Ledger Hardening | 11 | 0 | 11 |
| S5-A Fresh Tenant User Journey | 0 | 3 | 3 |
| **Total** | **39** | **3** | **42** |

### S5 Order State Machine -- 13/13 PASS

All state transitions, validations, concurrent locking, and invariants pass.

### S5 Ledger -- 15/15 PASS

Double-entry accounting, immutability, balance projections, and multi-payment scenarios all pass.

### S5.5 Ledger Hardening -- 11/11 PASS

Database-level UPDATE/DELETE blocks, trigger functions, unbalanced-transaction rejection, and precision handling all pass.

### S5-A Fresh Tenant User Journey -- 3/3 FAIL

| Test | Failure | Root Cause |
|------|---------|------------|
| `test_fresh_tenant_bootstrap_supports_returned_order_status_for_real_return_journey` | `'returned'` not in `order_status` enum | The `bootstrap_tenant_schema.py` baked into the deployed image is older and does not add the `returned` status. Fix exists in source (commits `431db1b`, `8f1a622`) but is not in the image. |
| `test_existing_tenant_bootstrap_reconciles_missing_returned_order_status` | Same as above | Same root cause. Reconciliation logic in the deployed bootstrap does not add `returned`. |
| `test_s5a_fresh_tenant_real_user_journey_gate` | `FileNotFoundError: /app/alembic/versions/022_import_runs.py` | The `022_import_runs.py` alembic migration exists in source but was **not** included in the Docker image. Container only has migrations up to `021_tenant_payments_retailer_id_transaction_id.py`. |

---

## 4. Products Import -- CSV Import 3-Stage Pipeline

### Source Code (exists in repo)

- `backend/api/v1/sku_imports.py` -- 3 endpoints: `/preview`, `/{import_id}/validate`, `/{import_id}/apply`
- `backend/services/import_service.py` -- Core preview/validate/apply logic
- `backend/models/import_run.py` -- `ImportRun` model
- `backend/schemas/import_schemas.py` -- Request/response schemas
- `backend/alembic/versions/022_import_runs.py` -- DB migration

### Deployed Status

| Component | In Source | In Docker Image | Status |
|-----------|-----------|-----------------|--------|
| `api/v1/sku_imports.py` | Yes | **No** | Not deployed |
| `services/import_service.py` | Yes | **No** | Not deployed |
| `models/import_run.py` | Yes | **No** | Not deployed |
| `schemas/import_schemas.py` | Yes | **No** | Not deployed |
| `alembic/versions/022_import_runs.py` | Yes | **No** | Not deployed |
| Router registration in `app.py` | Yes (line 96) | Yes | Present |
| `skus:import` permission in RBAC seed | Yes | Yes | Present |

### API Contract Verification (source)

The import API contract defined in `sku_imports.py`:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/skus/import/preview` | POST | Upload CSV, parse columns, store raw rows |
| `/api/v1/skus/import/{import_id}/validate` | POST | Apply field mapping, run validation rules |
| `/api/v1/skus/import/{import_id}/apply` | POST | Write validated rows to SKU table |

All endpoints require `skus:import` permission. The frontend `SKUListPage.tsx` checks `user?.permissions.includes('skus:import') || user?.roles.includes('admin')` to show the Import button.

### Finding -- CSV Import returns 404 on the deployed image

The complete import pipeline (API endpoints, service, model, schemas, migration) exists in the source repository but was **NOT included in the current Docker production image**. On the deployed environment, `POST /api/v1/skus/import/preview` returns `{"code":"RESOURCE_NOT_FOUND","message":"Not Found"}` (404).

This means the Products Import feature is **not actually exercisable end-to-end on the deployed image**, even though the Import button renders (because the frontend visibility check is satisfied by the `admin` role / `skus:import` permission that are present). Clicking the Import button and uploading a CSV would fail at the preview call.

---

## 5. Deployment Drift Summary

Two independent drifts between the source repository and the running Docker image:

1. **`returned` order status not reconciled in deployed bootstrap** -- source commits `431db1b` and `8f1a622` ship the fix, but the image predates them.
2. **CSV import module not in the image** -- `sku_imports.py`, `import_service.py`, `import_run.py`, `import_schemas.py`, and `022_import_runs.py` are all absent from `/app` in the container.

Both are blockers for treating S5-C as a full deployed runtime gate PASS.

---

## 6. Next Step -- OPS rebuild / redeploy

The next step belongs to OPS, not to this branch:

1. **Rebuild the backend Docker image from the latest `product-dev-recovered` HEAD** so that the `returned` status reconciliation and the full import pipeline (modules + `022_import_runs.py` migration) are baked in.
2. **Redeploy** the prod stack with the rebuilt image.
3. **Re-run S5-C** (and especially S5-A) against the freshly deployed image **without** any `docker cp` hot-copies. Only a clean run on the as-shipped image qualifies as a true deployed runtime gate PASS.
4. If S5-C-R2 is chartered, it should be executed against the rebuilt image and must not rely on runtime file injection.

This branch does **not** perform any rebuild, redeploy, or production code change. It only documents the drift.

---

## 7. Git & Code Hygiene

| Check | Result |
|-------|--------|
| `git diff --check` | **PASS** -- no whitespace errors |
| Changed-line secret scan (DB password / admin password / token) | **PASS** -- none present after R1 cleanup |
| `gitnexus analyze` | **PASS** -- index refreshed |
| Branch base contains `c958fae` | **PASS** -- verified via `merge-base --is-ancestor` |
| No production code changes | **PASS** -- ledger/docs only |
| No secrets modification | **PASS** |
| No deploy attempted | **PASS** |

### Files Changed (this branch, after R1)

```
A  ai-ledger/product-ai/2026-06-24_s5c_deployed_browser_smoke_gate.md   (this report)
```

R1 removed:
```
D  ai-ledger/ops/s5c_bootstrap_tenant.py    (contained credentials; not a deploy artifact)
D  ai-ledger/ops/s5c_test_import.csv        (sample data tied to the removed script)
```

---

## 8. Findings & Recommendations

### Critical

None (no live incident; drift is contained to the test/staging image under evaluation).

### High

1. **Deployed Docker image is behind source** for both the `returned` status fix and the CSV import pipeline. OPS must rebuild from latest `product-dev-recovered` HEAD.

### Medium

1. **CSV import module not deployed** -- end-to-end Products Import cannot be verified on the current image; the Import button is cosmetic until the module ships.
2. **Hot-copy diagnostics must not be confused with deployed coverage** -- the 39 passing backend tests reflect source semantics against the live DB, not the as-shipped image.

### Low

1. Consider baking the S5 gate test files into a staging image variant so future gates can run without runtime injection.

### Observations

- The frontend `SKUListPage.tsx` Import button visibility condition is satisfied by both `skus:import` permission and the `admin` role, so the button renders even when the backend module is absent.
- Schema derivation must follow `Wholesaler.get_tenant_schema()` (`t_{uuid_without_dashes}`); a code-derived schema name will break `find_user_across_tenants()`.

---

## Sign-off

- [x] Browser smoke: 8/8 pages pass, no 401/403/500 (as-deployed image behavior)
- [x] Network/API verified during page navigation
- [x] Backend gate tests: 39/42 pass, **3 S5-A FAIL** due to deployment drift (diagnostic run with hot-copied source modules)
- [x] CSV Import: **404** on deployed image (module not in image)
- [x] Verdict: `BROWSER_SMOKE_PASS_DEPLOYMENT_DRIFT_DETECTED`
- [x] No credentials, DB passwords, admin passwords, or tokens in this report
- [x] git diff --check clean
- [x] GitNexus analyze updated
- [x] No deploy, no secrets, no production code changes
- [x] Isolated branch only; not pushed to `product-dev-recovered`
