# DC-12R1-S3-D Retailer Workspace Capability & Financial-Authority Truth Gate

**Date:** 2026-07-29
**Branch:** `zcode/dc12r1-s3d-retailer-workspace-contract-2026-07-29`
**Base:** `origin/product-dev-recovered` @ `abdf3e454f420cc825faeddb264d010eae9c6d72` (verified)
**Type:** Design / audit gate — **no product code, migrations, permissions, config or deployment modified.**

## Verdict

`PASS_FOR_CTO_DC12R1_S3_IMPLEMENTATION_PLANNING`

The existing relationship-scoped retailer workspace is fully mapped and audited.
The catalog/order surface and financial-authority boundary are **fundamentally
sound** (every read/write derives `wholesaler_id` + `retailer_id` from the
contextual JWT + active binding + tenant context; prices/totals are
server-authoritative; generic `/payments` and `/finance` are already blocked
from retailers via disjoint permission sets). No `CURRENT_PRODUCT_DEFECT` was
found that blocks planning. **One unresolved financial-authority decision** is
explicitly escalated (GAP-07): the registry declares `client:payments:create`
("Retailer: pay own orders") but requirement #7 forbids retailer payment
submission without explicit CTO approval — this must NOT be auto-implemented and
is held for CTO sign-off.

## Deliverables
- This report: `ai-ledger/product-ai/2026-07-29_dc12r1_s3_retailer_workspace_contract.md`
- Capability/gap matrix: `ai-ledger/product-ai/2026-07-29_dc12r1_s3_retailer_workspace_capability_matrix.csv`
  (28 EXISTS capabilities, 12 GAPs/defects, P0–P3 prioritized, each with evidence file:line + slice)

## 1. Existing Surface Map (backend)

Routes under `/api/v1/client/` (registered `backend/api/app.py:241-247`):

| Route | Method | Perm/dep | wholesaler_id source | retailer_id source |
|-------|--------|----------|----------------------|--------------------|
| `/client/auth/login` | POST | public | server (wholesaler_code→registrations) | server (email→user→binding) |
| `/client/auth/forgot-password` | POST | public | server | server |
| `/client/auth/reset-password` | POST | public | server | server |
| `/client/products` | GET | `resolve_client_identity` | JWT tenant_id (tenant session) | binding (JWT user_id→binding.retailer_id) |
| `/client/products/{id}` | GET | `resolve_client_identity` | JWT tenant_id | binding retailer_id |
| `/client/orders` | POST | `resolve_client_identity` | `client.tenant_id` (server) | `client.retailer_id` (server) |
| `/client/orders` | GET | `resolve_client_identity` | tenant session (implicit) | `client.retailer_id` |
| `/client/orders/{id}` | GET | `resolve_client_identity` | tenant session (implicit) | ownership check → 404 |
| `/client/orders/{id}/cancel` | POST | `resolve_client_identity` | tenant session (implicit) | ownership check → 404 |

**Ownership/authority proof (requirement #2):** `resolve_client_identity`
(`backend/api/v1/client/dependencies.py:44-127`) derives both IDs entirely
server-side: `token.tenant_id` (wholesaler) and `token.user_id →
public.wholesaler_retailer_bindings (WHERE wholesaler_id=tenant_id AND
tenant_user_id=user_id AND is_deleted IS FALSE).retailer_id`. **Email is never
used** to infer retailer_id; **nothing is read from request body/query**. The
`ClientCreateOrderRequest` schema (`schemas/client.py:87-90`) accepts only
`items[].{sku_code,quantity}` and `notes` — no `retailer_id`/`wholesaler_id`/
`unit_price`/`total`. Confirmed across all 4 order/product route files.

## 2. Existing Surface Map (frontend)

The retailer portal is **substantially built** (not just a login page):
- Branded shell `ClientLayout` (`components/layout/ClientLayout.tsx:14`) — header + bottom-tab nav.
- Catalog browser `/client`, detail `/client/products/:id`
  (`ProductListPage.tsx:16`, `ProductDetailPage.tsx:14`).
- Orders list `/client/orders`, detail `/client/orders/:id`, create `/client/orders/new`
  (`OrderListPage.tsx:25`, `OrderDetailPage.tsx:16`, `CreateOrderPage.tsx:16`).
- Dedicated services `clientProductService` / `clientOrderService` — **zero** generic
  wholesaler `/payments` or `/finance` calls (grep-confirmed).
- Guards: `RetailerRoute` (retailer_operator only, `guards.tsx:75`),
  `WholesalerRoute` (blocks retailer from ERP routes, `guards.tsx:103`).
- authStore holds a single `retailerPortalCode` — **no** `available_tenants`,
  supplier-picker, or cross-supplier comparison state.

## 3. A/B Supplier Isolation Matrix (requirement #3)

Same retailer identity (email) provisioned in supplier A and supplier B:

| Action via portal A | Reaches A data? | Reaches B data? | Enforcement |
|---------------------|-----------------|-----------------|-------------|
| Login `?w=A` | yes (contextual JWT → A's schema) | **no** | login joins `tenant_registrations` by A's code; JWT carries A's tenant_id/tenant_schema |
| GET /client/products | yes (A's skus/prices) | **no** | tenant-scoped session = A's schema |
| GET /client/orders | yes (A's orders) | **no** | session = A's schema + retailer_id filter |
| GET /client/orders/{B-order-id} | **no (404)** | **no** | B's order not in A's schema; ownership 404 |
| POST /client/orders | writes to A only | **no** | `wholesaler_id`=A (server) |

Cross-supplier leakage is structurally prevented at the **tenant-schema boundary**
(the session's `search_path` is the JWT's `tenant_schema`) plus the
`wholesaler_id`-bound binding lookup. No row from B is reachable through A's
contextual token. (S2 SQL-capture proof already established login through A never
references B's schema.)

## 4. Defects / Stale Contracts (requirement #4)

| ID | Severity | Finding | Mitigation |
|----|----------|---------|------------|
| GAP-01 | P1 | Client routes use `resolve_client_identity`, **not** `RequirePermission(client:*)`. The `client:*` codes are declared in the registry but never enforced. | Binding+role check is stricter than a perm string; defensible, but an asymmetry vs wholesaler routes. Address in S3-S1. |
| GAP-02 | P1 | `list_orders` does not pass `wholesaler_id` to `get_orders_paginated`. | Tenant-scoped session prevents cross-wholesaler rows; defense-in-depth gap. |
| GAP-03 | P1 | `get_order`/`cancel` ownership check is `retailer_id`-only (not `+ wholesaler_id`). | Session prevents cross-wholesaler; explicit check more robust. |
| GAP-12 | P2 | `crud.get_order_by_id` has no DB-layer scope filter. | Ownership enforced in handler; future callers could skip. |
| GAP-10 | P3 | `ClientLayout` logout navigates to `/client/login` (loses `?w=` in URL). | Store retains code; UX inconsistency. |
| GAP-11 | P3 | `CreateOrderPage` picker silently swallows load errors. | No UI feedback. |

**No price-trust, retailer_id-injection, email-identity-confusion, or
cross-supplier-leak defect was found.** The create-order flow is financially
server-authoritative (GAP-free).

## 5. Financial-Authority Boundary (requirements #5–#8)

**Server-authoritative (verified):**
- Prices: `unit_price` = server-side `retailer_prices.price`
  (`orders.py:153`); client never supplies price; create rejects if no price or
  price ≤ 0 (`orders.py:145-160`).
- Totals: computed server-side in `crud_create_order` (`crud/order.py:224-231`).
- Balances: not exposed to retailers at all today (no client route reads ledger
  balances).

**Generic financial routes blocked from retailers (proven):**
- `/api/v1/payments` requires `RequirePermission("payments:read"/"payments:create")`
  (`payments.py:42,86`); `/api/v1/finance/receivables` requires
  `RequirePermission("finance:read")` (`finance.py:171`).
- The retailer_operator permission set (`permission_registry.py:64-71`) contains
  only `client:*` codes; the wholesaler `payments:*`/`finance:*` codes
  (`permission_registry.py:48-55`) are **disjoint** (enforced by the registry's
  runtime assertion `permission_registry.py:97`). Therefore a retailer JWT
  cannot pass these gates. (Already proven end-to-end by the S2-R2A real-route
  denial suite: orders/payments/finance → 403 PERMISSION_DENIED.)

**Retailers cannot mark payment settled, mutate ledger entries, or alter
receivables:** no such client route exists, and the generic mutation routes are
permission-blocked. Confirmed.

## 6. Separate Client-Scoped Payment/Finance READ Contracts (requirement #5)

These are **MISSING** and defined for S3-S2 (read-only, server-authoritative):

| Planned route | Scope | Read-only | Authority |
|---------------|-------|-----------|-----------|
| `GET /client/payments` | payments for `wholesaler_id`=tenant + `retailer_id`=client, joined to the retailer's own orders only | yes (no settle/create) | balances server-derived |
| `GET /client/finance/balance` | outstanding-balance projection (unpaid/partially-paid of the retailer's own orders) | yes | server-computed from ledger |

Contracts MUST filter by both `wholesaler_id` (tenant) AND `retailer_id`
(client identity), expose only `CLIENT_VISIBLE` payment fields (no internal
ledger account numbers / settlement internals), and never accept a mutation.
**Payment submission (`client:payments:create`) is excluded** — see GAP-07.

## 7. Unresolved Financial-Authority Decision (escalated)

**GAP-07 (UNRESOLVED_DECISION, P0, CTO):** `core/permission_registry.py:69`
declares `("client:payments:create", "Retailer: pay own orders")` in
`RETAILER_OPERATOR_PERMISSIONS`. This **anticipates** retailer payment
submission, but:
- No implementing route exists today.
- Requirement #7: *"Payment submission semantics require explicit CTO approval"*
  and *"Do not permit a retailer to mark payment settled, mutate ledger entries
  or alter receivables."*

**Decision needed from CTO:** should `client:payments:create` be (a) removed
from the registry, (b) retained as a future capability gated behind a separate
approval, or (c) implemented under a separately-scoped, CTO-approved payment
flow? Until decided, S3-S2 implements **read-only** payment/finance visibility
only and **must not** add any payment-submission route. The declared permission
is left untouched in this design gate (no code change).

## 8. Test Plan (requirement #10)

A new backend suite (`tests/test_dc12r1_s3_retailer_workspace_*.py`, to be added
in implementation slices) and frontend component tests will cover:
- Malformed UUID on `/client/orders/{id}` → 404, no body execution.
- Inactive binding → 403 `BINDING_NOT_ACTIVE`; missing binding → 403
  `BINDING_NOT_FOUND`; deleted binding (`is_deleted`) → 403.
- Deleted order/SKU row → 404 (no existence disclosure).
- Stale/expired JWT → 401; valid-but-wrong-tenant → 403/404.
- Cross-supplier: order id from B requested via A token → 404, zero B-schema SQL.
- Generic `/payments`, `/finance/receivables` with retailer token → 403
  `PERMISSION_DENIED`, flat envelope, no dict repr, no route-body SQL.
- Sanitized-error contract (no schema/SQL/exception class leaks; never 500).
- Price-trust: order-create with tampered price field ignored/rejected.
- Frontend: catalog/order page render + assertion that **no** payment/finance
  service call is made from retailer context.

## 9. Implementation Slices (requirement #11)

| Slice | Scope | Priority items |
|-------|-------|----------------|
| **S3-S1** Catalog/order hardening | Add explicit `wholesaler_id` ownership checks (GAP-02/03/12); add `RequirePermission(client:*)` enforcement or document the binding-based equivalent (GAP-01); add the requirement-#10 denial/sanitized-error test suite (GAP-08). **No behavior change to happy paths.** | P1/P0 |
| **S3-S2** Read-only payment/finance visibility | Add `GET /client/payments` + `GET /client/finance/balance` (read-only, dual-key scoped, server-authoritative balances); corresponding frontend statement/balance pages + `clientPaymentService`/`clientFinanceService` (read-only). **Excludes** `client:payments:create` (GAP-07 held for CTO). | P1 |
| **S3-S3** Branded responsive workspace/browser closure | Polish `ClientLayout` responsiveness; fix logout portal-code URL (GAP-10) and picker error feedback (GAP-11); add frontend component tests (GAP-09); final browser-state closure. | P2/P3 |

Each slice is independently mergeable and reuses (does not duplicate) the
existing client routes/pages/services.

## 10. GitNexus
- `gitnexus analyze` → indexed successfully (13,905 nodes / 42,730 edges / 923
  clusters / 300 flows) at `abdf3e4`.
- `gitnexus status` → **✅ up-to-date** at `abdf3e4`.
- `gitnexus impact resolve_client_identity -d upstream` → LOW graph (0 static
  callers; consumed via FastAPI `Depends()` injection, which the static graph
  under-resolves — effective blast radius is the 4 client route files + their
  CRUD chain). `context` view documents the outgoing dependency chain
  (`get_auth_context` → `get_tenant_context` → `_has_retailer_operator_role` →
  binding lookup).

## 11. Files Touched (design gate — documentation only)
- `ai-ledger/product-ai/2026-07-29_dc12r1_s3_retailer_workspace_contract.md` (this report)
- `ai-ledger/product-ai/2026-07-29_dc12r1_s3_retailer_workspace_capability_matrix.csv`

**No product code, tests, migrations, permissions, config, Docker, lockfiles,
deployment, or protected branches were modified.** This is a pure planning gate.

## 12. Branch / SHA / Cleanup Proof
- Branch: `zcode/dc12r1-s3d-retailer-workspace-contract-2026-07-29`
- Base: `abdf3e454f420cc825faeddb264d010eae9c6d72` (verified == expected)
- Commit: recorded at push (documentation-only: report + CSV)
- GitNexus: ✅ up-to-date at base; impact/context captured for `resolve_client_identity`
- Cleanup: isolated audit worktree; no temp artifacts committed; worktree-clean

## Recommendation
Proceed to **S3-S1** (catalog/order hardening + denial/error test suite) as the
first bounded implementation slice. **Hold GAP-07 (`client:payments:create`) for
explicit CTO decision** before any payment-submission work; S3-S2 delivers
read-only visibility only.
