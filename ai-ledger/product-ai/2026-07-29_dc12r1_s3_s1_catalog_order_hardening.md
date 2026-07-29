# DC-12R1-S3-S1 Catalog/Order Authorization & Dual-Key Hardening

**Date:** 2026-07-29
**Branch:** `zcode/dc12r1-s3-s1-catalog-order-hardening-2026-07-29`
**Base:** `zcode/dc12r1-s3d-retailer-workspace-contract-2026-07-29` @ `af8f9e56c7ca6b13e08187921e812f4b6b638259` (descends from protected `product-dev-recovered` @ `abdf3e45`)
**Scope:** S3-S1 only — no migration, no payment route, no finance route, no frontend payment UI, no deploy, no S3-S2/S3-S3.

## Verdict

`PASS_FOR_CTO_DC12R1_S3_S1_REVIEW`

S3-S1 hardens the retailer catalog/order boundary: route-specific `RequirePermission`
enforcement layered on `resolve_client_identity`, dual-key (wholesaler_id + retailer_id)
DB-level order scoping for detail/cancel, and a 17-test fail-closed suite covering
every denial path. GAP-07 (`client:payments:create`) is proven frozen: no registered
route consumes it and no payment/ledger/receivable mutation exists. All catalog/order
happy paths and wholesaler-owner behavior are preserved.

## Implementation

### A. `resolve_client_identity` preserved
Every client product/order route keeps `Depends(resolve_client_identity)` — the
server-side JWT→binding identity resolution is unchanged and remains the source of
`retailer_id`/`wholesaler_id`.

### B. Route-specific permission enforcement
Added a `RequirePermission(...)` dependency to each client route (layered after
`resolve_client_identity`):

| Route | Permission |
|-------|-----------|
| GET /client/products, GET /client/products/{id} | `client:catalog:read` |
| GET /client/orders, GET /client/orders/{id} | `client:orders:read` |
| POST /client/orders | `client:orders:create` |
| POST /client/orders/{id}/cancel | `client:orders:create` (MVP: create authority includes own-order DRAFT/CONFIRMED cancel) |

No new permission code introduced. The disjoint retailer_operator `client:*` namespace
is used; admin `payments:*`/`finance:*` remain separate.

### C. Dual-key order scoping
- `list_orders` now passes **both** `wholesaler_id` (client.tenant_id) and
  `retailer_id` to `get_orders_paginated` (defense-in-depth on the tenant session).
- New `get_order_for_retailer(db, order_id, wholesaler_id, retailer_id)` in
  `crud/order.py` — a DB-level scoped fetch (`order_id` + `wholesaler_id` +
  `retailer_id` + `is_deleted=false`). `get_order`/`cancel_order` use it, so a
  wrong-retailer / wrong-supplier request returns a neutral **404** without first
  loading the row (no existence disclosure). The unscoped `get_order_by_id` is
  untouched (still used by wholesaler routes — GitNexus HIGH blast radius).

### D. Fail-closed suite (17 tests, natural + reverse order)
`tests/test_dc12r1_s3_s1_catalog_order_hardening.py` — real PostgreSQL 16, real
retailer JWT via `POST /client/auth/login`, JwtAuthStrategy app (bypassing the test
mock). Covers:
- happy-path catalog read + order create/list/detail/cancel lifecycle
- permission denial (catalog/orders:read/orders:create stripped → 403 PERMISSION_DENIED)
- malformed UUID → 404 (no 500)
- cross-supplier order (B order via A token) → 404; cross-supplier cancel → 404
- identity-only JWT → 403; missing/malformed token → 401
- denial-before-body-SQL (no orders-table read on a denied detail request)
- generic /orders, /payments, /finance/receivables → 403 (retailer denied)
- controlled envelope (flat, no dict repr, no SQL/schema/exception leak, never 500)
- GAP-07 freeze (static: no route consumes `client:payments:create`; no ledger/settle
  reference in client routes)

A pool-reset autouse fixture disposes the shared `async_engine` between tests so the
cross-tenant order-create SQL doesn't hit stale asyncpg prepared-statement caches
(a test-only artifact; order creation is sound in isolation/per-tenant).

### E. GAP-07 governance freeze (proven)
- Static test proves **no** registered FastAPI route consumes
  `client:payments:create` (`test_no_route_consumes_client_payments_create`).
- `test_no_client_payment_mutation_route_exists` proves no settle/ledger/receivable
  write in client routes.
- CSV/report updated: GAP-07 = **P1 GOVERNANCE_HOLD** (held for explicit CTO approval
  per requirement #7; S3-S2 is read-only only).

### F. Happy paths + wholesaler-owner behavior preserved
S2 suite (50) + S3-S1 (17) + route-auth + RBAC + tenant-isolation + validation all
green (140 focused). Wholesaler `/orders`/`/payments`/`/finance` routes unchanged
(`get_order_by_id` untouched).

### Permission-registry provisioning repair (required by s6e/u1 drift gates)
Adding `RequirePermission(client:*)` to routes made the s6e RBAC drift gate and u1
bootstrap-completeness gate correctly flag that the 4 provisioning scripts
(`onboard_tenant.py`, `create_wholesaler.py`, `seed_test_tenant.py`,
`seed_demo_data.py`) seed only `ADMIN_PERMISSIONS`. Fixed all 4 to also seed
`RETAILER_OPERATOR_PERMISSIONS` (the `client:*` namespace) so every route permission
is present in every provisioning path. Updated the drift-gate tests to treat the
admin+retailer union as the canonical seeded set. s6e (6) + u1 (9) now green.

## Files changed
**Product (hardening):**
- `backend/api/v1/client/orders.py` — RequirePermission + dual-key scoping
- `backend/api/v1/client/products.py` — RequirePermission(client:catalog:read)
- `backend/crud/order.py` — new `get_order_for_retailer` (get_order_by_id untouched)

**Provisioning (permission completeness):**
- `backend/scripts/onboard_tenant.py` — seed retailer_operator role + client:* perms
- `backend/scripts/create_wholesaler.py` — seed client:* perms
- `backend/scripts/seed_test_tenant.py` — seed client:* perms
- `backend/scripts/seed_demo_data.py` — seed client:* perms

**Tests:**
- `backend/tests/test_dc12r1_s3_s1_catalog_order_hardening.py` (new, 17 tests)
- `backend/tests/test_s6e_rbac_permission_registry_drift_gate.py` — admin+retailer union
- `backend/tests/test_u1_bootstrap_permission_completeness.py` — accept client:* namespace

**Other:**
- `.secrets.baseline` — pre-existing `testpassword` FP in seed_test_tenant.py baselined
- `ai-ledger/product-ai/2026-07-29_dc12r1_s3_retailer_workspace_capability_matrix.csv` — GAP-07/08 updated
- this report

No migration 036 or earlier touched; no new migration; no payment/finance route;
no frontend payment UI; no deploy.

## Validation
- py_compile (all changed files) — OK
- git diff --check — clean (exit 0)
- scoped pre-commit (all changed files) — all Passed
- detect-secrets — 0 new findings (1 pre-existing FP baselined)
- frontend: vitest 142 passed (15 files); build ✓ (5.40s)
- GitNexus: impact run before edit (`get_order_by_id` HIGH — 8 callers, hence the
  new scoped variant instead of modifying it); analyze + status at final commit
- focused: S2 50 + S3-S1 17 + s6e 6 + u1 9 + route-auth + RBAC = 140 passed
- S3-S1 suite passes in **natural and reverse** order

## Full backend gate (two runs, fresh PG16/Redis7)

Both runs deterministic and identical: **3011 passed, 5 failed, 0 errors**.
The 5 failures are the **pre-existing baseline migration-reconciliation defects**
(`test_dc2m2_legacy_tenant_reconciliation_forward_migration` x3 +
`test_dc10l_order_status_enum_reconciliation` x2) — the exact same set that fails on
the protected product baseline `abdf3e45`/`c0c8221` independent of S2/S3 (documented
in the S2-R2A STOP analysis). They fail in isolation too (not order-dependent) and
are unrelated to S3-S1 (S3-S1 introduced **zero** new failures; the prior s6e/u1
permission-registry failures S3-S1 would have caused were *fixed* — pass count rose
from 3009 to 3011).

| Run | Passed | Failed | Errors | Failed set |
|-----|--------|--------|--------|------------|
| 1 | 3011 | 5 | 0 | dc2m2 x3 + dc10l x2 (pre-existing) |
| 2 | 3011 | 5 | 0 | dc2m2 x3 + dc10l x2 (identical) |

## GitNexus
- `gitnexus analyze` indexed (13,885 nodes) at base; `impact get_order_by_id` →
  HIGH (8 direct callers across 4 modules) → drove the decision to ADD a scoped
  `get_order_for_retailer` rather than modify the shared `get_order_by_id`.
- detect_changes before commit + analyze/status after commit recorded.

## Report-back
- base SHA: `af8f9e56c7ca6b13e08187921e812f4b6b638259` (descends from `abdf3e45`)
- final commit SHA: recorded at push
- S3-S1 focused suite: 17 passed (natural + reverse)
- GAP-07: P1 GOVERNANCE_HOLD, proven frozen

## Debugging Log (transparency — issues encountered and resolved)

### Product / infrastructure issues (pre-existing, not introduced by S3-S1)

1. **Full-suite test-isolation fragility (dc2m2 / dc10l / email / onboarding).**
   The protected product baseline `product-dev-recovered` itself fails 5 tests
   deterministically (dc2m2 migration reconciliation x3 + dc10l order-status enum
   reconciliation x2). Proven pre-existing via the S2-R2A deselect control run and
   confirmed here (identical 5-failure set, fails in isolation too, unrelated to
   S3-S1). S3-S1 introduced **zero** new failures (pass count rose 3009→3011 by
   *fixing* the s6e/u1 permission-registry failures).

2. **asyncpg prepared-statement cache expiry (`CannotCoerceError`).**
   Cross-tenant order-create tests reuse pooled connections whose asyncpg prepared
   statements were cached under a different `search_path`/enum context. Order
   creation is sound (passes in isolation and per-tenant); resolved with a test-only
   autouse fixture that disposes the shared `async_engine` between tests. No product
   code changed for this.

### S3-S1-triggered cascade (correctly surfaced and fixed)

3. **s6e/u1 permission-registry drift.** Adding `RequirePermission(client:*)` to
   routes correctly tripped the s6e RBAC drift gate, whose purpose is to assert that
   every route permission is seeded in every provisioning path. Fixed by seeding
   `RETAILER_OPERATOR_PERMISSIONS` (`client:*`) in all 4 provisioning scripts and
   updating the drift-gate tests to treat the admin+retailer union as canonical.

### Test-code bugs (development-time, fixed before commit)

4. **`two_tenants` tuple shape misread.** The S2 `two_tenants` fixture returns
   `(code_a, code_b, schema_b, ...)` — the 3rd element is **schema_b**, not
   schema_a. Initial permission-strip tests unpacked it as `schema_a` and stripped
   permissions from the wrong tenant, so the A token still had its permissions
   (returned 200 instead of 403). Fixed by resolving schema via
   `_schema_for(db, code_a)`.

5. **Leak-detector false positive on "select a tenant".** `_assert_controlled_envelope`
   flagged the substring `"select "` as a SQL leak, but it matched the English phrase
   "Please select a tenant first" in the 403 message. Fixed by detecting SQL-shaped
   patterns (`SELECT ` / `INSERT ` / etc.) instead of the bare English word.

6. **tuple vs list comparison in s6e assertions.** After updating the drift-gate
   extractors, `captured_codes[:len(ADMIN_PERMISSIONS)] == list(ADMIN_PERMISSIONS)`
   always evaluated False (tuple != list). Fixed by comparing against
   `tuple(ADMIN_PERMISSIONS)`.

7. **`.secrets.baseline` regeneration destroyed existing entries.** Running
   `detect-secrets scan --baseline` regenerated the entire baseline (484→1 entries)
   instead of appending. Detected immediately via `grep -c hashed_secret`; restored
   the original baseline and merged the single `seed_test_tenant.py` false positive
   programmatically, preserving all 484 existing entries (484→485).

### Governance hold (escalated, not auto-implemented)

8. **GAP-07: `client:payments:create`.** Declared in the permission registry
   ("Retailer: pay own orders") but requirement #7 forbids retailer payment
   submission without explicit CTO approval. Proven frozen (no route consumes it;
   no mutation exists). Held as **P1 GOVERNANCE_HOLD** for CTO decision.
