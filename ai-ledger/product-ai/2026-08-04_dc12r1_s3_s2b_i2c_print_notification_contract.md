# DC-12R1-S3-S2B-I2C-D — Printable Records and Notification-Event Contract

**Status:** PASS_FOR_CTO_DC12R1_S3_S2B_I2C_IMPLEMENTATION_PLANNING_R2
**Revision:** R2 — Historical Ledger Scope and Receipt-Link Truth (historical scope ignores `orders.is_deleted`; movements and settled payments are two independent lists with no amount/timestamp/order-only correlation; one customer-facing ledger-derived balance; binding cache is internal-only; orphan-ledger fail-closed). Preserves all R1 corrections.
**Task type:** Design / audit gate only. No implementation, no product code, no migration, no provider integration.
**Base:** `origin/product-dev-recovered` @ `044f7c5cb6ebcb6efbda1d14729c432ea743f1d7`
**Branch:** `zcode/dc12r1-s3-s2b-i2c-d-print-notification-contract-2026-08-04`
**Date:** 2026-08-04
**Executor:** local Zcode (real source audit via Grep/Glob/Read + GitNexus; no static guesswork)

---

## 0. Executive Summary

This document defines the **authoritative MVP contracts** for four printable
records (order, payment declaration, confirmed receipt, relationship account
statement) and four **future** notification events, plus binding isolation,
read-only, and MVP-boundary rules. It is grounded entirely in audited source
truth — every capability, field, route, permission, table, and column cited
below was verified against the codebase at the base SHA. **No field, route,
permission, or table in this contract is invented.** Where a capability does
not yet exist, it is explicitly marked **GAP** with the exact implementation
slice required.

The headline finding of the audit: **the server-authoritative data backbone
required for all four printable documents already exists and is enforced.**
Order unit prices and totals are resolved server-side and never accepted from
the client (`api/v1/client/orders.py:164-186`). Canonical receipt numbers are
allocated atomically in a single transaction with a partial unique index
(`payment_repository.py:336-363`, migration `037:753-764`). The receivable
ledger (`ledger_entries`) is **immutable** (DB trigger
`prevent_ledger_modification`) and is the authoritative source for the
relationship balance trajectory. Tenant isolation is dual-layer (JWT-derived
`search_path` + explicit dual-key SQL predicates). The remaining work is
**read-only print rendering and ledger-sourced statement arithmetic on top of
authoritative data**, not new financial machinery.

> **R1 correction note.** The original §8 sourced statement balance from
> `payments`/`binding.outstanding_balance`. R1 corrects this: the balance
> trajectory is sourced from **immutable `ledger_entries`** (charges `+T` and
> collections `-P`, scoped through `orders`); `binding.outstanding_balance` is
> a credit-exposure cache that **diverges** from the ledger for cash
> relationships, so the statement now performs a **fail-closed reconciliation**
> and never prints an unbalanced statement. Dedup keys are now **deterministic**
> on persisted transition timestamps; timezone display is a **fixed** EAT zone
> (no unsupported tenant-config claim); statement permissions are exactly
> `client:finance:read` / `finance:read`.
>
> **R2 correction note.** (a) Historical scope **ignores `orders.is_deleted`** —
> a soft-deleted order's immutable ledger movements always remain. (b) The
> statement renders **two independent lists**: `movements[]` (ledger only, no
> method/receipt) and `settled_payments[]` (canonical payments only, with
> receipt) — never correlated by amount/timestamp/order_id alone, because **no
> persisted key links a ledger movement to a payment** (audit: `post_payment_received`
> writes `reference_id=order_id` only). (c) **One** customer-facing balance
> (ledger-derived); the binding cache is an **internal diagnostic**, never on
> the document. (d) Orphan ledger reference → 409
> `STATEMENT_LEDGER_SCOPE_INCOMPLETE`, zero partial document.

The single most important integrity rule carried through every contract below:

> **A pending or rejected payment declaration is NOT a receipt and must NEVER be
> renderable as one.** Only a `confirmed` declaration whose
> `confirmation_payment_id` resolves to a `payments` row with a non-null
> `receipt_number` is receipt-eligible. This is enforced at render time by a
> fail-closed predicate, not by UI convention.

---

## 1. Base Proof Gate (executed)

```
git fetch --all --prune                                   # clean
git rev-parse origin/product-dev-recovered
  => 044f7c5cb6ebcb6efbda1d14729c432ea743f1d7            # exact match ✓
git merge-base --is-ancestor \
  753048f029c4eede86fb11857677db57b865900e \
  044f7c5cb6ebcb6efbda1d14729c432ea743f1d7
  => exit 0                                              # I2B merge is ancestor ✓
```

Isolated worktree `_i2c_d_2026-08-04` created on
`zcode/dc12r1-s3-s2b-i2c-d-print-notification-contract-2026-08-04`. Working tree
clean before authoring. **PASS.**

---

## 2. Source Truth Audit (consolidated)

All `file:line` references are against the base SHA. Verified by four parallel
read-only audits (services/repos, routes/permissions, frontend, migration) and
corroborated by GitNexus `context` queries against
`PaymentDeclarationService`, `CanonicalPaymentService`,
`PaymentDeclarationRepository`, `PaymentRepository.allocate_receipt_number`,
and `configure_app`.

### 2.1 Service / repository layer

| Symbol | Location | Role |
|---|---|---|
| `PaymentDeclarationService` | `backend/services/payment_declaration_service.py:59` | submit / confirm / reject; **no list method** (routes call the repo directly) |
| `PaymentDeclarationRepository` | `backend/repositories/payment_declaration_repository.py:19` | dual-key reads, `create`, `mark_confirmed`, `mark_rejected`, `list_by_retailer`, `list_by_wholesaler`, `list_statement_lines` |
| `CanonicalPaymentService` | `backend/services/canonical_payment_service.py:105` | `confirm_payment(...)` — the single canonical-payment write path |
| `PaymentRepository.allocate_receipt_number` | `backend/repositories/payment_repository.py:336` | atomic `RCT-YYYYMMDD-NNNNNN` allocation inside the caller transaction |
| `OrderService.transition` | `backend/services/order_service.py:53` | the ONLY order-state mutation path |

**Declaration lifecycle:** `pending → confirmed | rejected` (both terminal).
`confirmed` is replayable (returns the same canonical payment + receipt, zero
new writes). `rejected` is terminal. CHECK constraint at migration `037:795-798`
enforces `status IN ('pending','confirmed','rejected')`. The
`payment_declarations` table is **immutable** (no `is_deleted`, no update path
except `mark_confirmed`/`mark_rejected`).

**Confirmation → receipt:** `PaymentDeclarationService.confirm_declaration`
(`:167`) delegates the entire financial write to
`CanonicalPaymentService.confirm_payment(force_completed=True,
skip_prechecks=False, allocate_receipt=True)` (`:210`), then links the resulting
payment via `mark_confirmed` setting `confirmation_payment_id` (`:224`). The
receipt number is allocated only when `allocate_receipt AND payment_status ==
"completed"` (`canonical_payment_service.py:318-320`) and only on this path —
direct `pay_order` does not allocate a receipt.

**Receipt number format & atomicity:** `RCT-YYYYMMDD-NNNNNN` where the date is
aware UTC business date and `NNNNNN` is a zero-padded per-tenant, per-UTC-day
sequence from `receipt_sequences(business_date CHAR(8) PK, next_seq INT)`
(migration `037:815-825`). Allocation uses `INSERT ... ON CONFLICT
(business_date) DO UPDATE SET next_seq = next_seq + 1 RETURNING next_seq`
(`payment_repository.py:350-362`) **inside the caller's transaction**; a failed
confirmation rolls back the increment (no gap, no leak). Validation regex
`^RCT-[0-9]{8}-[0-9]{6}$` at `canonical_payment_service.py:61-67`. Stored on
`payments.receipt_number VARCHAR(32)` with partial unique index
`ux_payments_receipt_number WHERE receipt_number IS NOT NULL`.

### 2.2 Identity, binding, and order authority

**Binding (the relationship):** `public.wholesaler_retailer_bindings`
(`backend/models/binding.py:14`). Dual-key `UNIQUE(wholesaler_id, retailer_id)`
(`:19`). Identity resolution via `tenant_user_id` partial unique index
`ux_bindings_wholesaler_tenant_user (wholesaler_id, tenant_user_id) WHERE
tenant_user_id IS NOT NULL AND is_deleted IS FALSE` (`:31-39`). `status`
column is `active|inactive` (app-enforced; **no DB CHECK**). Soft-delete is a
separate `is_deleted`/`deleted_at` pair. "Deleted/inactive binding" therefore
means `is_deleted = TRUE` OR `status != 'active'`.

**Client identity resolution:** `resolve_client_identity`
(`backend/api/v1/client/dependencies.py:45`). Enforces, in order: token must
NOT be identity-only (`:58`, 403 `TENANT_CONTEXT_REQUIRED`); user must carry
`retailer_operator` role (`:78`); then a direct SQL lookup
`SELECT retailer_id, status FROM public.wholesaler_retailer_bindings WHERE
wholesaler_id = :tenant_id AND tenant_user_id = :user_id AND is_deleted IS
FALSE` (`:91-103`) — 403 `BINDING_NOT_FOUND` / `BINDING_NOT_ACTIVE` on failure.
`retailer_id` is **always server-derived, never from the request body or
query**.

**Order authority:** `ClientOrderItemRequest` input schema
(`backend/schemas/client.py:81`) contains **only `sku_code` + `quantity`** — no
`unit_price`. The client order-create route resolves price server-side from
`retailer_prices.price` (`api/v1/client/orders.py:164-186`) and rejects if the
resolved price is null or `<= 0`. `unit_price` and `subtotal` are stored per
`order_items` row (`models/order.py:130-137`); `orders.total_amount` is a stored
`Numeric(12,2)` column (`:74-78`). **No client-side total recomputation path
exists.** The client order view returns these server-authoritative values
(`ClientOrderView` / `ClientOrderItemView`, `schemas/client.py:93-104`).

**Order statuses:** `draft, confirmed, partially_paid, paid, fulfilled,
cancelled, voided, returned` (`models/order.py:17-35`). Client-visible status
is mapped via `map_order_status_for_client` (`schemas/client.py:146-158`):
`paid → CONFIRMED`, `fulfilled → DELIVERED`. The client never sees the internal
`partially_paid`/`paid` distinction directly — it is collapsed to `CONFIRMED`.

### 2.3 Routes (client + cashier)

| file:line | METHOD path | permission | printable-relevant behaviour |
|---|---|---|---|
| `api/v1/client/orders.py:280` | GET `/api/v1/client/orders/{order_id}` | `client:orders:read` | Order detail; dual-key; returns server-authoritative items + `total_amount` |
| `api/v1/client/declarations.py:32` | GET `/api/v1/client/declarations` | `client:payments:read` | Declaration history; `receipt_number` joined (confirmed only) |
| `api/v1/client/declarations.py:69` | GET `/api/v1/client/declarations/{declaration_id}` | `client:payments:read` | Declaration detail; triple-key |
| `api/v1/client/payments.py:42` | GET `/api/v1/client/payments` | `client:payments:read` | Canonical payment history; **no `receipt_number` on view** |
| `api/v1/client/finance.py:31` | GET `/api/v1/client/finance/balance` | `client:finance:read` | Outstanding balance from binding; no open/close |
| `api/v1/client/statements.py:28` | GET `/api/v1/client/statements` | `client:payments:read` | Statement of **completed** payments; line-item; no open/close |
| `api/v1/declarations.py:120` | GET `/api/v1/declarations/{declaration_id}` | `payments:read` | Cashier declaration detail; dual-key |
| `api/v1/declarations.py:151` | POST `/api/v1/declarations/{declaration_id}/confirm` | `payments:confirm_declaration` | Confirm → canonical payment + receipt |

**Critical gap — no receipt lookup endpoint.** `receipt_number` is **never a
path parameter anywhere**. There is no `GET …/{receipt_number}` route and no
dedicated receipt endpoint. It exists only as a returned field joined from
`payments.receipt_number` via `confirmation_payment_id`. **Contract C (confirmed
receipt) requires a new read-only receipt route** (see §6.C).

**Statement arithmetic gap (R1 truth).** `GET /api/v1/client/statements` returns
completed payment lines (`list_statement_lines`,
`payment_declaration_repository.py:421`) but computes **no opening or closing
balance** (file docstring explicitly defers this, "contract DD-06"). The audit
(R1) established that the balance trajectory must be sourced from the
**immutable `ledger_entries`** (receivable charges `+T` and collections `-P`,
scoped through `orders`), **not** from `payments` alone; and that
`binding.outstanding_balance` tracks credit-exposure only and is **not** a
general receivable balance, with **no reconciliation** to the ledger today.
**Contract D (account statement) therefore requires server-side ledger-sourced
opening/closing arithmetic + a fail-closed reconciliation check** (see §8).

### 2.4 Frontend

| Component | Location | Current capability |
|---|---|---|
| `DeclarePaymentPage` | `frontend/src/pages/client/DeclarePaymentPage.tsx:6` | Submit form; amount has `htmlFor`/`id`; method/transfer-ref labels lack `htmlFor`; no `aria-*`; no success print view |
| `DeclarationHistoryPage` | `frontend/src/pages/client/DeclarationHistoryPage.tsx:29` | Card list; **already distinguishes** confirmed (`Payment Received · RCT-…`) from pending (`Payment Declaration — Not Received`) |
| `DeclarationQueuePage` | `frontend/src/pages/finance/DeclarationQueuePage.tsx:23` | Cashier queue; confirm + reject (reason required, 1-256 chars) |

**No print/PDF infrastructure exists.** Exhaustive search confirms: no
`window.print`, no `@media print`, no `jspdf`/`pdfmake`/`react-pdf`/`pdf-lib`/
`html2pdf` in `package.json`, no `/receipts/:id` route, no receipt rendering
component, no print button. The only "download" is a **JSON invoice download**
(`OrderListPage.tsx:312-331`, `FinancePage.tsx:173-186`) — not a printable or
PDF artifact.

**Dead statement scaffolding.** `frontend/src/types/declaration.ts:21-28`
defines `StatementLine` and `declarationService.ts:44-50` defines
`getClientStatement`, but **no component imports or calls it**. The account
statement has backend data but no rendered UI.

**Orphaned nav.** `/client/declarations` (retailer history) and `/declarations`
(cashier queue) have **no entry in their respective nav menus**
(`ClientLayout.tsx:11-16`, `Sidebar.tsx:31-43`) — reachable only by direct URL.

### 2.5 Migration

Migration head is **`037_payment_declarations_schema`**
(`backend/alembic/versions/037_payment_declarations_schema.py`), forward-only
(`downgrade()` raises). **No `038` exists.** This contract introduces **no
migration**. The `payment_declarations` table (17 columns, immutable) and
`receipt_sequences` allocator (2 columns) are the only new tables from 037;
`payments` was widened (`transaction_id → VARCHAR(128)`) and extended
(`receipt_number VARCHAR(32)` + partial unique index).

---

## 3. Cross-Cutting Contract Rules (apply to all four documents)

These rules are binding on every printable document defined below. Any
implementation slice that violates one is a contract breach.

### 3.1 Read-only / zero-mutation
- Every print operation is **read-only**. A print request must not mutate
  `payments`, `orders`, `payment_declarations`, ledger entries, receivables,
  settlements, the binding's `outstanding_balance`, or `receipt_sequences`.
- The print route's transaction fingerprint must be zero-write. The required
  test (`PRINT-ZM-01`) asserts no row count change across the relevant tables
  before vs after a print request.
- **Printing does not emit a financial or notification event** (§7.6).

### 3.2 Authority is never client-supplied
- `wholesaler_id` and `retailer_id` are **never accepted from the request** —
  not in the body, not in the query string, not as a path parameter claiming
  authority. They are derived exclusively from the contextual JWT
  (`token.tenant_id` = wholesaler_id) and the active binding
  (`resolve_client_identity` → `retailer_id`).
- For cashier/wholesaler print routes, `wholesaler_id =
  token.tenant_id` (`api/v1/declarations.py:71`); the tenant `search_path` is
  JWT-derived only (`backend/api/context/tenant.py:80`).
- No generic wholesaler/platform route may serve a retailer token, and vice
  versa. The route guard (`RetailerRoute` / `WholesalerRoute` /
  `PlatformRoute` in `frontend/src/router/guards.tsx`) plus the backend
  `RequirePermission` + `resolve_client_identity` enforce this.

### 3.3 Dual-key ownership predicates (fail-closed 404)
- Every print query is scoped by the **dual-key** `(wholesaler_id,
  retailer_id)` for client routes, or `(declaration_id, wholesaler_id)` /
  `(order_id, wholesaler_id)` for cashier routes — exactly mirroring the
  existing repository methods (`get_detail_by_retailer`,
  `get_detail_by_wholesaler`, `get_order_for_retailer`).
- An ownership mismatch returns a **neutral 404** (`DECLARATION_NOT_FOUND` /
  `ORDER_NOT_FOUND`), **never a 403**, to avoid confirming existence of
  another tenant's record. This matches the existing convention
  (`payment_declaration_service.py` wrong-wholesaler path returns 404).

### 3.4 Binding liveness
- A print operation requires an **active, non-deleted binding** at request
  time. `resolve_client_identity` already enforces this for client routes
  (`status='active'`, `is_deleted IS FALSE`). Cashier routes must additionally
  assert the binding is live for the declaration's `(wholesaler_id,
  retailer_id)` — consistent with the confirm path
  (`payment_declaration_service.py:307-321`).
- A **deleted or inactive binding** denies print (fail-closed), even if the
  underlying declaration/order/payments still exist in the schema.

### 3.5 Currency, timezone, and display
- All money is `NUMERIC(12,2)` stored as KES. The contract does not introduce
  multi-currency. Money is rendered with 2 decimal places, locale-stable
  grouping, prefixed by the `KES` label (matching the existing `Amount (KES)`
  UI label).
- **Stored timestamps are aware UTC** (`TIMESTAMPTZ`). The printable document
  shows two things, clearly separated: (a) the **authoritative UTC timestamp**
  (machine truth, used for replay/dedup, displayed verbatim) and (b) a
  **clearly-labelled fixed `Africa/Nairobi` (EAT) display** derived
  **server-side**. The client must not recompute the timezone offset.
  **Truth correction (D-tz):** no tenant-configurable timezone setting exists in
  the platform today (no tenant timezone column/field was found in the audit).
  The MVP therefore uses a **single fixed display zone `Africa/Nairobi`**,
  labelled "EAT", computed server-side. A tenant-configurable timezone is
  **post-MVP**; this contract makes no claim that such configuration already
  exists.
- The receipt number's date component (`RCT-YYYYMMDD-…`) is the **UTC business
  date** of allocation (`payment_repository.py:349`), which may differ from the
  local display date near midnight. The contract renders the receipt number
  verbatim (it is the canonical identifier) and separately shows the local
  confirmation time. It must **not** reformat or "correct" the receipt number.

### 3.6 Sensitive-field redaction and leak prevention
- Print responses must never include: another supplier's identity, raw JWT or
  credential material, internal SQL/schema names, internal exception text,
  `tenant_user_id`, internal cashier user ids, or `confirmation_payment_id`
  (the payment row UUID). The existing `ClientDeclarationView`
  (`schemas/declaration.py:84`) already omits these; print views must follow
  suit.
- Rejection reasons are rendered as **sanitized text** (the reject route already
  sanitizes 1-256 chars, `api/v1/declarations.py:223-242`). They must be
  rendered as text content, never injected as HTML. No `dangerouslySetInnerHTML`.
- No ` wholesaler_id`/`retailer_id` UUID is shown to the end user; the document
  uses the **business name** of the supplier and retailer (resolved
  server-side from `public.wholesalers`/`public.retailers`). If a name is
  missing, the field is shown as a controlled placeholder, never the UUID.

### 3.7 Empty and error states
- **No data:** the document renders a controlled empty state ("No records in
  this range" / "Order not found") — never a blank page, never a stack trace.
- **Malformed/missing ID:** a malformed `order_id`/`declaration_id`/
  `receipt_number` returns 400 (`INVALID_ID`) for syntactic failure and 404
  for not-found-after-scope. Receipt number format is validated against
  `^RCT-[0-9]{8}-[0-9]{6}$` before any DB lookup.
- **Fail-closed on any ambiguity:** if a confirmed declaration's
  `confirmation_payment_id` is null, or the joined payment row is missing,
  soft-deleted (`is_deleted`), or lacks a `receipt_number`, the receipt
  document **refuses to render** (404 / controlled error) rather than render a
  partial receipt.

### 3.8 Printable HTML vs browser-print CSS (MVP direction)
- **Decision (binding, see decision register D1):** the MVP uses
  **browser-printable, accessible HTML** with a dedicated `@media print`
  stylesheet. No PDF generation library is introduced. This is preferred
  because (a) no PDF infrastructure exists today and adding one is out of
  scope, (b) the data is already server-authoritative, and (c) browser print
  satisfies the MVP "I can hand a printed record to my supplier/retailer"
  need.
- Each printable document is a **dedicated route** that returns a clean,
  semantic HTML view (or a JSON payload the existing SPA renders into a print
  view) with `@media print` rules that hide nav/chrome and lay out the document
  for paper. A "Print" button calls `window.print()`. There is **no server-side
  PDF**, no headless browser, no PDF library.
- The print view is **a separate route** from the data view, so the data view's
  interactivity (nav, filters) never leaks into the printed page.

---

## 4. Printable Document Contracts — overview

Four independent contracts. Each is printable by the actor who owns the record
(retailer prints their own order/declaration/receipt/statement; supplier
prints their side of the same relationship). Each is read-only and
dual-key-scoped.

| # | Document | Actor | Authority source | Status terminology |
|---|---|---|---|---|
| A | Order | retailer (own) or supplier | `orders` + `order_items` | client-mapped (`CREATED/CONFIRMED/DELIVERED/CANCELLED/RETURNED`) |
| B | Payment Declaration | retailer (own) or supplier | `payment_declarations` | `pending / confirmed / rejected` |
| C | Confirmed Receipt | retailer (own) or supplier | `payment_declarations` ⋈ `payments` (receipt-eligible only) | `Receipt` (only confirmed+receipt) |
| D | Relationship Account Statement | retailer (own) or supplier | `payments` (completed) + `orders` + binding balance | settled vs pending separation |

Each document's detailed contract follows. For every document the same 13
decision points are resolved (source, route, permission, ownership predicate,
status terms, currency/tz, pagination/range, HTML vs print CSS, accessibility,
filename/title, empty/error, redaction, cross-tenant denial).

---

## 5. Contract A — Order Document

**Purpose:** a printable record of a single retailer order, showing
server-authoritative items, quantities, unit prices, subtotals, and the order
total, with supplier and retailer business identity and the order date.

### 5.1 Source tables / services
- `orders` (tenant schema) — `wholesaler_id`, `retailer_id`, `status`,
  `total_amount`, `notes`, `created_at`.
- `order_items` (tenant schema) — `product_name`, `sku_code`, `quantity`,
  `unit_price`, `subtotal`.
- `public.wholesalers` / `public.retailers` — business names for identity
  (resolved server-side; **never** show the UUID).
- Read path: existing `get_order_for_retailer(order_id, wholesaler_id,
  retailer_id)` (`crud/order.py:137`) for the retailer; an equivalent
  wholesaler-scoped read for the supplier. **No new write path.**

### 5.2 Server-side route and response contract
- **Retailer route:** `GET /api/v1/client/orders/{order_id}/print` — returns
  the existing `ClientOrderView` payload (`schemas/client.py:104`) **plus**
  supplier/retailer business names and a server-formatted `Africa/Nairobi`
  (EAT) display timestamp. Permission `client:orders:read` (reuse). Reuses
  `resolve_client_identity` for `retailer_id`.
- **Supplier route:** `GET /api/v1/orders/{order_id}/print` — wholesaler-scoped,
  permission `orders:read`. `wholesaler_id = token.tenant_id`.
- Response is JSON consumed by a dedicated frontend print view (HTML +
  `@media print`). **No client-side price/total recomputation** — the view
  renders the server values verbatim.

### 5.3 Required permission
- Retailer: `client:orders:read`. Supplier: `orders:read`. **No new permission**
  (decision D5 — reuse existing read permission for print; a separate
  `*:print` permission is deferred to post-MVP).

### 5.4 Dual-key ownership predicate
- Retailer: `order_id` + `wholesaler_id` (= token tenant) + `retailer_id` (=
  binding). Supplier: `order_id` + `wholesaler_id` (= token tenant).
  Mismatch → neutral 404 `ORDER_NOT_FOUND`.

### 5.5 Status terminology
- Rendered with the **client-mapped** status (`map_order_status_for_client`,
  `schemas/client.py:146`): `CREATED, CONFIRMED, DELIVERED, CANCELLED,
  RETURNED`. The internal `partially_paid`/`paid`/`voided` terms are **not
  shown** on the order document (they are payment states, surfaced on the
  receipt/statement instead).

### 5.6 Currency / timezone
- KES, `NUMERIC(12,2)`, 2 dp, `KES` label. Order date shown as authoritative
  UTC + fixed `Africa/Nairobi` (EAT) display (truth correction D-tz; no
  tenant-configurable timezone in MVP).

### 5.7 Pagination / range
- N/A — single order. No pagination.

### 5.8 Printable HTML vs print CSS
- Dedicated print route + `@media print` stylesheet. "Print" button →
  `window.print()`. No PDF.

### 5.9 Accessibility and mobile
- Semantic HTML (`<table>` for line items with `<th scope>`), label/input
  associations, `lang` attribute, sufficient colour contrast, responsive layout
  that degrades to a single column on mobile. Printable area sized for A4.

### 5.10 Filename / title convention
- Browser tab title: `Order {order_short_id} — {supplier_name}`. Suggested
  print filename: `order-{order_short_id}.pdf` (browser-generated from the
  title via the print dialog; the app does not generate the PDF).

### 5.11 Empty / error state
- Order not found / wrong scope → 404 `ORDER_NOT_FOUND` rendered as a
  controlled error page, not a blank. Malformed `order_id` → 400
  `INVALID_ID`.

### 5.12 Sensitive-field redaction
- No UUIDs shown (use business names). No internal cashier user ids. `notes`
  rendered as sanitized text. No SQL/schema names.

### 5.13 Cross-tenant denial
- Supplier A cannot print supplier B's order: the `wholesaler_id = token.
  tenant_id` predicate plus JWT-derived `search_path` prevent it. Retailer A
  cannot print retailer B's order: the `retailer_id` from the binding
  predicate prevents it. Both return neutral 404.

---

## 6. Contract B — Payment Declaration Document

**Purpose:** a printable record of a single payment declaration, **clearly
labelled "Payment Declaration"**, showing its pending/confirmed/rejected state
and — prominently — that a **pending or rejected declaration is NOT a receipt
and does not prove settlement.**

### 6.1 Source tables / services
- `payment_declarations` (tenant schema) — `declared_amount`, `method`,
  `transfer_reference`, `status`, `submitted_at`, `confirmed_at`/`confirmed_by`,
  `rejected_at`/`rejected_by`, `reason`, `confirmation_payment_id`.
- Joined `orders` (for order context: order id/status) and `payments` (for
  `receipt_number`, **only when confirmed**) via the existing
  `get_detail_by_retailer` / `get_detail_by_wholesaler`
  (`payment_declaration_repository.py:126,94`).
- `public.wholesalers`/`public.retailers` for business names.

### 6.2 Server-side route and response contract
- **Retailer:** `GET /api/v1/client/declarations/{declaration_id}/print` —
  permission `client:payments:read`. **Supplier:** `GET
  /api/v1/declarations/{declaration_id}/print` — permission `payments:read`.
- Response: `ClientDeclarationView` / `DeclarationView` payload **plus**
  business names + `Africa/Nairobi` (EAT) display timestamps + a `is_receipt` boolean (true only
  when confirmed AND receipt-eligible per §7.4). The view uses `is_receipt` to
  decide whether to render the receipt block or the "not a receipt" notice.

### 6.3 Required permission
- Retailer `client:payments:read`; supplier `payments:read`. Reuse (D5).

### 6.4 Ownership predicate
- Retailer: triple-key `(declaration_id, retailer_id, wholesaler_id)` via
  `get_detail_by_retailer`. Supplier: dual-key `(declaration_id,
  wholesaler_id)` via `get_detail_by_wholesaler`. Mismatch → neutral 404
  `DECLARATION_NOT_FOUND`.

### 6.5 Status terminology + the non-receipt notice
- Status rendered verbatim from the enum: `Pending`, `Confirmed`, `Rejected`.
- **Mandatory prominent notice** whose text depends on status:
  - `pending` → **"Payment Declaration — Not Received. This declaration has
    not been confirmed by {supplier_name} and is not a receipt. It does not
    prove that payment was received or settled."**
  - `rejected` → **"Payment Declaration — Rejected. {supplier_name} did not
    confirm this declaration. Reason: {sanitized reason}. This is not a
    receipt."**
  - `confirmed` → renders the **Receipt** (Contract C), not a standalone
    declaration view. If for some reason the receipt block cannot be rendered
    (missing payment row / null receipt number), the document **fails closed**
    (§3.7) rather than showing a confirmed declaration without a receipt.

### 6.6 Currency / timezone
- KES, 2 dp. `submitted_at`/`confirmed_at`/`rejected_at` shown as authoritative
  UTC + fixed `Africa/Nairobi` (EAT) display (D-tz). Receipt number rendered
  verbatim.

### 6.7–6.13
- Pagination: N/A (single declaration).
- HTML/print CSS: dedicated route + `@media print` (D1).
- Accessibility: semantic, labelled, `lang`, contrast, mobile-responsive.
- Filename/title: `Declaration {decl_short_id} — {status}`; print filename
  `declaration-{decl_short_id}.pdf`.
- Empty/error: 404 `DECLARATION_NOT_FOUND` on wrong scope; 400 `INVALID_ID` on
  malformed UUID.
- Redaction: no UUIDs, no cashier user ids, no `confirmation_payment_id`.
  Rejection reason is sanitized text only.
- Cross-tenant: dual/triple-key predicate + `search_path` → neutral 404.

---

## 7. Contract C — Confirmed Receipt

**Purpose:** a printable receipt, available **only** for a completed canonical
payment, carrying the canonical receipt number `RCT-YYYYMMDD-NNNNNN`. This is
the single document that proves settlement.

### 7.1 Receipt eligibility predicate (binding, fail-closed)
A declaration is **receipt-eligible** if and only if **all** of the following
hold. If any fails, the receipt route returns 404 / controlled error and
renders nothing:

1. `payment_declarations.status = 'confirmed'` (CHECK-enforced enum).
2. `payment_declarations.confirmation_payment_id IS NOT NULL`.
3. The joined `payments` row exists, `payments.is_deleted IS FALSE`, and
   `payments.status = 'completed'`.
4. `payments.receipt_number IS NOT NULL` AND matches
   `^RCT-[0-9]{8}-[0-9]{6}$`.
5. The binding for `(wholesaler_id, retailer_id)` is active and non-deleted
   at request time.

**No pending or rejected declaration is ever receipt-eligible.** This is the
single most important integrity rule and is enforced **at render time**, not by
UI hiding.

### 7.2 Source tables / services
- `payment_declarations` ⋈ `payments` (on `confirmation_payment_id`) ⋈ `orders`
  (on `order_id`) ⋈ `public.wholesaler_retailer_bindings` (liveness) ⋈
  `public.wholesalers`/`public.retailers` (names).
- This join already exists in `get_detail_by_retailer` /
  `get_detail_by_wholesaler` (`payment_declaration_repository.py:94-159`). The
  receipt route reuses it and applies the eligibility predicate above.

### 7.3 Server-side route and response contract (NEW — gap)
- **Gap:** there is no receipt endpoint today (§2.3). Required new read-only
  routes:
  - **Retailer:** `GET /api/v1/client/declarations/{declaration_id}/receipt` —
    permission `client:payments:read`. Applies §7.1; on success returns a
    `ReceiptView`.
  - **Supplier:** `GET /api/v1/declarations/{declaration_id}/receipt` —
    permission `payments:read`.
- `ReceiptView` fields (all server-authoritative):
  - `receipt_number` (verbatim `RCT-YYYYMMDD-NNNNNN`)
  - `confirmed_amount` (= `payments.amount`, `NUMERIC(12,2)`)
  - `method` (= `payments.method`)
  - `confirmed_at` (= `payments.created_at` / declaration `confirmed_at`,
    aware UTC) + `confirmed_at_local` (server-formatted `Africa/Nairobi`/EAT)
  - `order_id`, `order_total_amount`, `order_status_client_mapped`
  - `declaration_id`, `declared_amount`
  - `supplier_name`, `retailer_name`
  - `is_receipt = true` (constant for this view; the predicate guarantees it)
- **Replay returns the same identity:** because `payment_declarations` is
  immutable post-confirmation and the receipt number is stored on `payments`
  (not recomputed), repeated `GET …/receipt` calls return byte-identical
  receipt identity. Required test (`T-RCPT-REPLAY-01`) asserts two calls return the
  same `receipt_number`, `confirmed_amount`, and `confirmed_at`.

### 7.4 Required permission
- Retailer `client:payments:read`; supplier `payments:read`. Reuse (D5).

### 7.5 Ownership predicate
- Same triple/dual-key as Contract B, **plus** the §7.1 eligibility predicate.
  Mismatch or ineligibility → neutral 404 `RECEIPT_NOT_AVAILABLE` (the 404 does
  not distinguish "wrong tenant" from "not yet confirmed" — both are neutral).

### 7.6 Status terminology
- The receipt has a single status: **"Receipt"** (it is, by construction,
  confirmed). It is not labelled pending/rejected. The body states "Payment
  received and confirmed by {supplier_name}".

### 7.7 Currency / timezone
- KES, 2 dp. `confirmed_at` UTC + fixed `Africa/Nairobi` (EAT) display
  (D-tz). Receipt number verbatim (its date
  component is the UTC business date of allocation and must not be
  "corrected").

### 7.8–7.13
- Pagination: N/A.
- HTML/print CSS: dedicated route + `@media print` (D1).
- Accessibility: semantic, labelled, `lang`, contrast, mobile.
- Filename/title: `Receipt {receipt_number}`; print filename
  `receipt-{receipt_number}.pdf`.
- Empty/error: 404 `RECEIPT_NOT_AVAILABLE` for pending/rejected/missing;
  400 `INVALID_RECEIPT_NUMBER` for a malformed receipt-number lookup if a
  receipt-number-keyed variant is added later (MVP keys on declaration_id).
- Redaction: no UUIDs, no payment row id, no cashier user id. Only
  `receipt_number`, amounts, names, method, timestamps.
- Cross-tenant: triple/dual-key + binding liveness + `search_path` → 404.

### 7.14 Relationship to the declaration
- The receipt shows the originating declaration (`declaration_id`,
  `declared_amount`) and the order, so the three records are visibly linked.
- A receipt exists **only** for a confirmed declaration. The declaration's
  `confirmation_payment_id` is the sole link; it is never shown to the user
  (redacted), only used server-side to resolve the receipt.

---

## 8. Contract D — Relationship Account Statement

**Purpose:** a printable account statement for **one supplier ↔ one retailer
relationship**, over a controlled date range, with an authoritative opening
balance, itemised **receivable movements** (charges and collections) and
confirmed payments, and an authoritative closing balance. Pending declarations
are **excluded from settled/accounting totals** (shown in a separate
non-accounting section if shown at all).

> **R1 truth correction (binding).** The relationship balance trajectory is
> driven by **immutable `ledger_entries`** (charges and collections), not by
> `payments` alone. `payments` are the display/receipt source; the
> authoritative balance path is the receivable ledger. See §8.3.
>
> **R2 truth correction (binding).** (1) Accounting scope ignores
> `orders.is_deleted` — a soft-deleted order's immutable ledger movements are
> always included. (2) Movements and settled payments are **two separate
> lists**; they are never correlated by amount, timestamp, or `order_id` alone.
> (3) The customer document shows **exactly one** authoritative balance (the
> ledger-derived value); the binding cache is an internal diagnostic, never a
> second customer-facing balance. See §8.1.1, §8.2, §8.3.4, §8.5.

### 8.1 Source tables / services (audited source truth)
- **`ledger_entries` (tenant schema)** — the authoritative, **immutable**
  receivable ledger (`backend/models/ledger.py:46`, table `ledger_entries`).
  Immutability is enforced by a DB trigger `prevent_ledger_modification`
  (`backend/alembic/versions/010_s5_5_ledger_hardening.py:40-116`) on UPDATE OR
  DELETE, plus a balanced-transaction app check (`ledger_service.py:141-157`).
  Columns used: `account_type` (`receivable`/`revenue`/`cash`),
  `amount` (`Numeric(20,4)`, **positive = debit, negative = credit**;
  `ledger.py:88-92`), `reference_type` (`'order'`/`'refund'`),
  `reference_id` (UUID — the **order** id; see §8.1.1), `transaction_date`
  (`TIMESTAMPTZ`), `is_deleted`.
  **There is no `wholesaler_id`/`retailer_id`/`order_id` column and no FK** —
  per-counterparty scoping requires a JOIN through `orders` (§8.5).
- **`orders` (tenant schema)** — for relationship scoping
  (`orders.wholesaler_id`, `orders.retailer_id`, `models/order.py:56-67`) and
  order context on each line. Note these FKs are soft/un-enforced (skeleton).
  **R2:** `orders.is_deleted` is **not filtered** for accounting scope (§8.5).
- **`payments` (tenant schema, `status='completed'`, `is_deleted IS FALSE`)** —
  the **display/receipt source** for settled-payment lines (amount, method,
  `receipt_number`), via the existing `list_statement_lines`
  (`payment_declaration_repository.py:421`). Payments are NOT the balance
  trajectory and NOT a source of ledger movements.
- **`public.wholesaler_retailer_bindings.outstanding_balance`**
  (`models/binding.py:75`, `Numeric(12,2)`) — an **internal credit-exposure
  diagnostic only** (§8.3.4). It is a mutable cache mutated by deltas
  (`payment_service.py:169-216`); it tracks **credit exposure** (credit sales
  +, credit collections −; **cash/transfer never touch it**). It is **not** a
  customer-facing balance and is **never rendered** as a balance on the
  printable statement.
- `public.wholesalers`/`public.retailers` for business names.
- **NEW server-side computation (gap):** opening/closing balance and signed
  movement arithmetic from `ledger_entries` (§8.3). Read-only; no new write
  path, no new table.

#### 8.1.1 Ledger ↔ payment association truth (R2, binding)
The audit established that **there is no persisted key linking a ledger
collection movement to the specific `payments` row or `receipt_number`:**
- `LedgerService.post_payment_received` (`ledger_service.py:281-317`) writes
  `reference_type='order', reference_id=<order_id>` — the **order** id, never
  the payment id. There is **no `payment_id`/`receipt_number` column** on
  `ledger_entries` (`models/ledger.py:46-123`; confirmed across all migrations),
  and `post_payment_received` has no `payment_id` parameter. The canonical
  service creates the `payments` row (`canonical_payment_service.py:322-333`)
  but does **not** thread its id into the ledger post.
- Therefore a receipt and its ledger movement share **only `order_id`**. For a
  single-payment order this is an unambiguous 1:1 by `order_id`; for a
  **multi-payment order** (partial payments, credit + collection) a specific
  receipt cannot be unambiguously tied to a specific ledger movement except by
  amount/timestamp inference — which this contract **forbids** (§8.2).
- **Binding consequence:** the statement therefore renders **two independent
  lists** — `movements[]` (ledger, no method/receipt) and `settled_payments[]`
  (canonical payments, with method/receipt) — and **never** attaches payment
  method or `receipt_number` to a ledger movement unless a real persisted key
  proves the association. Because no such key exists for multi-payment orders,
  ledger movements carry **no** `method`/`receipt_number`. This is the only
  honest representation; it avoids false receipt association (test
  `T-STMT-NOCROSSASSOC-01`).

### 8.2 Server-side route and response contract (R2 — two independent lists)
- **Retailer:** `GET /api/v1/client/statements/print?from=&to=` — permission
  **`client:finance:read`** (decision D5-R1). `retailer_id` from binding;
  `wholesaler_id` from token.
- **Supplier:** `GET /api/v1/statements/print?retailer_id=&from=&to=` —
  permission **`finance:read`** (decision D5-R1; no "or" wording).
  **`retailer_id` is validated against an active binding for `wholesaler_id =
  token.tenant_id`** — it is not trusted as authority, only as a filter within
  the already-scoped relationship.
- Response: `StatementPrintView`:
  - `supplier_name`, `retailer_name`, `from`, `to` (UTC + EAT display)
  - `opening_balance` (`Numeric(12,2)`, ledger-derived, §8.3.2) — **the single
    authoritative customer-facing opening balance**
  - `movements[]` — **from `ledger_entries` only.** Each: `date` (UTC + EAT),
    `order_id`, `description`, `kind` (`charge` | `collection`),
    `signed_amount` (`Numeric(20,4)`: positive charge, negative collection),
    `display_amount` (`Numeric(12,2)` absolute).
    **No `method`, no `receipt_number`** on movements (§8.1.1).
  - `charge_total` (sum of positive signed movements in range, from `movements[]`)
  - `collection_total` (sum of |negative| signed movements in range, from `movements[]`)
  - `net_movement` (`charge_total - collection_total`, from `movements[]`)
  - `closing_balance` (`Numeric(12,2)`, ledger-derived, §8.3.2) — **the single
    authoritative customer-facing closing balance**
  - `settled_payments[]` — **from canonical completed `payments` only.** Each:
    `payment_date` (UTC + EAT), `order_id`, `amount` (`Numeric(12,2)`),
    `method`, `receipt_number`.
  - `settled_total` (sum of `settled_payments[].amount` in range — from
    `settled_payments[]` only, distinct from `net_movement`)
  - `pending_declarations[]` (separate, clearly-labelled **non-accounting**
    section: `declaration_id`, `declared_amount`, `submitted_at`) — included
    only if requested (`?include_pending=1`), never folded into
    `opening_balance`/`closing_balance`/`net_movement`/`settled_total`.
- **The `StatementPrintView` does NOT contain `binding.outstanding_balance`
  or any `reconciliation`/`matched` field.** Those are internal diagnostics
  evaluated server-side (§8.3.4) and never serialized to the customer document
  (test `T-STMT-CACHE-ABSENT-01`).

### 8.3 Balance arithmetic — receivable-ledger-sourced (binding, R1)

#### 8.3.1 Scope and signed movement source (R2 — ledger only, no payment enrichment)
- Relationship `movements[]` are sourced from **immutable `ledger_entries`**
  rows where `account_type = 'receivable'`, scoped through `orders` by
  `(wholesaler_id, retailer_id)` (§8.5). A **charge** (order confirmed) is a
  receivable row with `amount > 0` (posted by
  `LedgerService.post_order_confirmation`, `ledger_service.py:243-279`,
  reference_type `'order'`). A **collection** (payment received) is a
  receivable row with `amount < 0` (posted by
  `LedgerService.post_payment_received`, `ledger_service.py:281-317`,
  reference_type `'order'`; also the credit-collection path in
  `canonical_payment_service.py:337-348`). Returns post `reference_type
  'refund'` (`ledger_service.py:319`).
- Each movement carries a **signed amount** with a `kind`: `charge`
  (signed_amount `+T`) or `collection` (signed_amount `-P`). **Movements carry
  no `method` and no `receipt_number`** (§8.1.1) — they are ledger records,
  not payment records. The balance path (`opening`/`closing`/`net_movement`)
  uses `movements[]` only.

#### 8.3.2 Exact date boundaries (inclusive/exclusive)
- `from` is **inclusive** (`transaction_date >= from`).
- `to` is **inclusive** (`transaction_date <= to`), to a whole-day boundary.
  The range is therefore `[from, to]` inclusive on both ends.
- `opening_balance` is the balance **immediately before `from`**, i.e.
  `SUM(signed amount) WHERE account_type='receivable' AND scoped AND
  transaction_date < from`.
- `closing_balance = opening_balance + SUM(signed amount in [from, to])`.
  Equivalently `closing_balance = SUM(signed amount) WHERE transaction_date
  <= to` (scoped). The two formulations must agree (test `T-STMT-ARITH-01`).
- `net_movement = charge_total - collection_total` (the in-range signed sum);
  `closing_balance` must equal `opening_balance + net_movement`
  (test `T-STMT-ARITH-02`).

#### 8.3.3 settled_total vs net_movement (do not conflate; independent lists)
- `settled_total` is the sum of `settled_payments[].amount` in range
  (`payments.status='completed'`) — sourced from the **payments list only**.
  `net_movement` is the signed sum of `movements[]` (charges minus
  collections) — sourced from the **ledger list only**. These measure
  **different things** and are computed from **independent** source sets: a
  charge increases the receivable (and `net_movement`) but is not a payment; a
  completed payment appears in `settled_total` and its collection appears in
  `collection_total`/`net_movement` **only if** the ledger posting falls in
  range. The two lists are **never cross-populated** and totals are never
  substituted for one another. Movements and settled payments reconcile
  independently (test `T-STMT-INDEP-RECON-01`).
- **pending declarations** are never included in `opening_balance`,
  `closing_balance`, `net_movement`, `charge_total`, `collection_total`, or
  `settled_total`. They appear only in the separate non-accounting section
  (decision D4).

#### 8.3.4 Customer-facing balance truth and internal reconciliation (R2, binding)
- **Exactly one authoritative customer-facing balance.** The printable
  statement shows **one** opening and **one** closing balance — both
  **receivable-ledger-derived** (`movements[]` arithmetic, §8.3.2). This is the
  only balance the customer/supplier reads on the document.
- **`binding.outstanding_balance` is an internal credit-exposure diagnostic,
  not a customer balance.** It is **never rendered** on the printable document
  (not as a balance, not as a second comparable figure, not in a
  "reconciliation" block). `StatementPrintView` contains no
  `outstanding_balance`, no `anchor`, no `matched` field
  (test `T-STMT-CACHE-ABSENT-01`). The customer sees the ledger truth only.
- **Internal reconciliation (server-side, not serialized).** Because
  `binding.outstanding_balance` tracks **credit exposure only** (credit sales
  +, credit collections −; cash/transfer ignored) while the ledger receivable
  tracks **all confirmed orders net of all collections**, the two **diverge for
  mixed relationships** and **no reconciliation exists today** (audited). The
  statement route computes a server-side internal check but **does not expose
  it to the customer**:
  1. Compute `ledger_opening`, `ledger_closing`, `ledger_current` (all-dates
     scoped receivable sum).
  2. Assert `ledger_closing == ledger_opening + net_movement` (internal
     consistency); else 409 `STATEMENT_INTERNAL_INCONSISTENT`.
  3. **Credit-only relationships:** if there are **no cash/transfer ledger
     collections** for the relationship (classification per §8.3.5) and
     `ledger_current != binding.outstanding_balance` (beyond 0.01 tolerance),
     the statement **refuses to render**: 409 `STATEMENT_RECONCILIATION_FAILED`
     with no document emitted (test `T-STMT-MISMATCH-01`).
  4. **Mixed relationships:** the statement **prints the single ledger-derived
     balance and nothing else.** It does **not** claim the ledger balance and
     the credit-exposure cache "are expected to be equal" — they are different
     measures. No comparison, no note, no second number is shown to the
     customer. (The divergence is an internal operator concern, surfaced via
     separate ops tooling, not the customer statement.)
- The MVP does **not** mutate the binding cache from the statement path
  (read-only, §3.1).

#### 8.3.5 Credit/mixed classification (R2, binding)
- **Payment method is determined from canonical `payments`, never from
  `ledger_entries`.** `ledger_entries` carries no method (`models/ledger.py`).
  A relationship is **credit-only** iff **every** completed payment for it has
  `payments.method = 'credit'`; it is **mixed** iff **any** completed payment
  has `method IN ('cash','transfer')`. The classification query is:
  `SELECT COUNT(*) FROM payments p JOIN orders o ON o.id = p.order_id WHERE
  o.wholesaler_id = :w AND o.retailer_id = :r AND p.is_deleted IS FALSE AND
  p.status = 'completed' AND p.method IN ('cash','transfer')` — `> 0` ⇒ mixed.
  This drives the §8.3.4 reconciliation decision (credit-only is fail-closed
  on mismatch; mixed is not reconciled against the cache).

### 8.4 Required permission
- Retailer: **`client:finance:read`**. Supplier: **`finance:read`**. Reuse
  (decision D5-R1). **No "or" wording** — each route has exactly one
  permission. Declaration/receipt routes remain `client:payments:read` /
  `payments:read` (§6.3, §7.4).

### 8.5 Ownership predicate / ledger scoping (R2 — historical scope, binding)
- Retailer: `wholesaler_id` (token) + `retailer_id` (binding). Supplier:
  `wholesaler_id` (token) + `retailer_id` (validated against active binding).
  Mismatch → neutral 404 / empty.
- **Ledger scoping query (binding):** because `ledger_entries` has no
  `wholesaler_id`/`retailer_id`/`order_id` column, relationship scoping is:
  resolve the order-id set `O` for the relationship, then read the receivable
  ledger for those orders. **R2 historical-scope rule:** the order-id
  resolution does **NOT** filter `orders.is_deleted`:
  resolve the set `O = { orders.id | orders.wholesaler_id = :w AND
  orders.retailer_id = :r }` — **no `is_deleted` predicate** — then read
  `ledger_entries WHERE account_type = 'receivable' AND reference_type IN
  ('order','refund') AND reference_id IN (O)`. The join shape mirrors
  `api/v1/finance.py:103-109`; note `ReceivablesService`
  (`receivables_service.py:113-129`) **does** filter `is_deleted` and
  aggregates from `payments`, so it is **not** reused for the ledger path.
- **Historical retention rule (R2, binding):** soft-deleting an order **must
  never** remove its immutable ledger movements from the statement. Because
  the scope omits the `is_deleted` filter, a soft-deleted order's charges and
  collections remain in `movements[]` and in `opening`/`closing`/`net_movement`
  exactly as before deletion (tests `T-STMT-SOFTDELETE-RETAIN-01`,
  `T-STMT-ACTIVE-DELETED-EQUAL-01`). (Audit note: no production code path sets
  `orders.is_deleted = true` today — cancel/void is status-only — but this rule
  is binding regardless, so a future soft-delete cannot silently drop history.)
- **Orphan-ledger fail-closed (R2, binding):** if a `ledger_entries` row has
  `reference_type IN ('order','refund')` but its `reference_id` does **not**
  resolve to a row in `orders` (physical order missing/deleted-hard), the
  statement **refuses to render**: 409 `STATEMENT_LEDGER_SCOPE_INCOMPLETE` with
  **zero partial document** emitted (test `T-STMT-ORPHAN-01`). The movement is
  **never silently omitted** — an unresolvable reference is an integrity
  breach, not a display gap. The error does not leak the orphan id or any
  cross-tenant detail.

### 8.6 Status terminology
- `movements[]` lines carry `kind` (`charge`/`collection`) and a signed amount,
  **no method, no receipt_number** (§8.1.1). `settled_payments[]` lines carry
  `method` + `receipt_number`. No pending/rejected terms in the accounting
  section.

### 8.7 Currency / timezone
- KES, 2 dp (display); ledger arithmetic is `Numeric(20,4)` then rounded to
  `Numeric(12,2)` for display. All line dates shown as **authoritative UTC +
  fixed `Africa/Nairobi` (EAT) display** (truth correction D-tz). Date range
  `from`/`to` are interpreted against the **fixed `Africa/Nairobi`** zone for
  the day boundary, with the UTC boundary also shown for audit.

### 8.8 Pagination / range
- `from`/`to` required (controlled range, max span 365 days for MVP to bound
  query cost). Line results paginated server-side; the printable view requests
  a single page sized for the range (cap applied; overflow → controlled
  "narrow your range" notice rather than silent truncation).

### 8.9–8.13
- HTML/print CSS: dedicated route + `@media print` (D1).
- Accessibility: semantic `<table>`, `<th scope>`, column headers, `lang`,
  contrast, mobile. Totals row clearly labelled.
- Filename/title: `Statement {supplier_name} ↔ {retailer_name} {from}-{to}`;
  print filename `statement-{retailer_short}-{from}-{to}.pdf`.
- Empty/error: empty range → "No receivable movements in this range" (still
  shows opening = closing, both ledger-derived). Malformed date → 400
  `INVALID_DATE_RANGE`. **Fail-closed:** (a) §8.3.4 credit-only reconciliation
  mismatch → 409 `STATEMENT_RECONCILIATION_FAILED`, no document;
  (b) §8.5 orphan ledger reference → 409 `STATEMENT_LEDGER_SCOPE_INCOMPLETE`,
  **zero partial document**.
- Redaction: no UUIDs in the rendered statement (internal ids redacted to
  short forms); no payment row ids; no `tenant_user_id`.
- Cross-tenant: relationship scoped to `(wholesaler_id, retailer_id)`; a
  retailer token can only see their own relationship; a supplier token can
  only see their own retailers. → neutral empty/404.

### 8.14 No frontend financial recomputation
- The statement view **renders server-computed balances verbatim**. It does not
  sum lines client-side to "verify" the total — any such client-side sum is
  display-only and labelled "for your reference", never authoritative. This
  matches the existing `FinanceBalancePage` convention ("This value is from
  your supplier relationship and is not recalculated on this device",
  `FinanceBalancePage.tsx:66`).

---

## 9. Notification-Event Contracts (future, design only)

**These are contracts only.** I2C-D does **not** implement SMS, WhatsApp,
email, webhooks, queues, an outbox table, message templates, or any provider
integration (decision D7, D8). The contracts define the *shape* of versioned
events so a future, separately-gated delivery layer can be built against them.

### 9.1 Event types (four)
1. `payment_declaration_submitted` — a retailer submitted a declaration.
2. `payment_declaration_confirmed` — a cashier confirmed a declaration (a
   canonical payment + receipt now exist).
3. `payment_declaration_rejected` — a cashier rejected a declaration.
4. `payment_receipt_issued` — a receipt was issued (co-occurs with confirmation;
   modelled as a distinct event because the recipient/relevance may differ).

### 9.2 Versioned event envelope (all four share this shape)
Every event is a JSON document with exactly these fields:

| Field | Type | Rule |
|---|---|---|
| `event_id` | UUID (v4) | unique per emission; generated by the emitter after commit |
| `event_type` | one of the four above | |
| `schema_version` | semver string, e.g. `"1.0.0"` | bumps on any payload change; consumers must gate on it |
| `occurred_at` | ISO-8601 UTC timestamp | the timestamp of the **committed** state change, not the emit time |
| `tenant_id` | UUID | `= wholesaler_id` (the supplier tenant); derived from context, never payload-trusted by consumers |
| `relationship_identity` | `{ wholesaler_id, retailer_id }` | dual-key; both server-derived |
| `binding_identity` | `{ binding_id, binding_status_at_event }` | snapshot of binding liveness at `occurred_at` |
| `actor` | `{ actor_id, actor_type }` | `actor_type ∈ {retailer_operator, admin, system}`; `actor_id` = the committing user |
| `aggregate` | `{ aggregate_type, aggregate_id }` | `aggregate_type ∈ {payment_declaration, canonical_payment, receipt}` |
| `correlation` | `{ correlation_id, idempotency_key }` | `correlation_id` links the four events of one declaration lifecycle; `idempotency_key` = the declaration's idempotency key |
| `payload` | redacted, type-specific (§9.3) | minimal; no credentials, no JWT, no raw rows, no other-supplier identity |
| `committed_state_requirement` | `true` (constant) | the event MAY NOT be emitted unless the state change is committed |
| `transition` | `{ transition_ts, transition_version }` | the **persisted** transition timestamp/version; see §9.2.1 for which column feeds each event type |
| `replay_dedup` | `{ dedup_key, dedup_strategy }` | `dedup_key` = `(tenant_id, event_type, aggregate_type, aggregate_id, transition_ts, transition_version)`; `dedup_strategy = "drop_duplicates"` |

#### 9.2.1 Deterministic transition timestamp per event type (binding, R1)
The dedup key is **deterministic** — it is built only from **persisted**
columns (not from emit-time `now()`), so a replay can never generate a fresh
logical transition timestamp and therefore never a fresh dedup key:
- **`payment_declaration_submitted`** → `transition_ts =
  payment_declarations.submitted_at` (NOT NULL, set at create); `transition_version = 1` (single transition into `pending`).
- **`payment_declaration_confirmed`** → `transition_ts =
  payment_declarations.confirmed_at` (the persisted timestamp set by
  `mark_confirmed`, `payment_declaration_repository.py:252`); `transition_version = 1`. On replay, `confirm_declaration`'s replay path
  (`payment_declaration_service.py:189,323`) performs **zero new writes**, so
  `confirmed_at` is unchanged → identical dedup key.
- **`payment_receipt_issued`** → `transition_ts =
  payment_declarations.confirmed_at` (same persisted column as confirmed; the
  receipt is allocated in the same committed transaction, so they share the
  transition anchor); `transition_version = 1`. No receipt event if §7.1 fails.
- **`payment_declaration_rejected`** → `transition_ts =
  payment_declarations.rejected_at` (persisted, set by `mark_rejected`,
  `payment_declaration_repository.py:282`); `transition_version = 1`.

Because each declaration transition is **terminal and write-once** (CHECK
`status IN ('pending','confirmed','rejected')`, immutability of the
lifecycle), a given `(aggregate_id, transition_ts)` pair is stable for the life
of the row. A replay that does not write cannot change `transition_ts`, so the
dedup key is stable and a replayed transition is **always** deduplicated.
Required test: `T-EVT-DEDUP-01`.

### 9.3 Per-type redacted payload
- **`payment_declaration_submitted`**: `{ declaration_id, order_id,
  declared_amount, method, transfer_reference_present (bool, not the value) }`.
- **`payment_declaration_confirmed`**: `{ declaration_id, canonical_payment_id,
  confirmed_amount, method, receipt_number }`.
- **`payment_declaration_rejected`**: `{ declaration_id,
  rejection_reason_length, rejection_reason_present (bool) }` — the reason
  text is **not** carried in the event payload (it may contain sensitive
  notes); consumers fetch it via an authorised read if needed.
- **`payment_receipt_issued`**: `{ declaration_id, receipt_number,
  confirmed_amount, method, confirmed_at }`. **Requires a valid canonical
  receipt** (§7.1); if the receipt predicate fails, this event is **not
  emitted** even if a confirmation event was.

### 9.4 Mandatory semantics (binding)
1. **Committed-state only.** An event may represent **only committed** state.
   The emitter hooks the post-commit phase of the existing service methods
   (`PaymentDeclarationService.submit_declaration` / `confirm_declaration` /
   `reject_declaration`), never the pre-commit phase.
2. **Rollback emits nothing.** If the transaction rolls back (e.g. confirm
   fails the canonical-payment prechecks, or `mark_confirmed` rowcount != 1),
   **zero events** are emitted. Required test (`T-EVT-ROLLBACK-01`).
3. **Replay must not duplicate logical notifications.** Because
   `payment_declarations` confirmation is idempotent (replay returns the same
   canonical payment, **zero new writes**), a replayed confirm must **not**
   emit a second `payment_declaration_confirmed` / `payment_receipt_issued`.
   Dedup is **deterministic** on the persisted transition columns
   (`§9.2.1`): `dedup_key = (tenant_id, event_type, aggregate_type,
   aggregate_id, transition_ts, transition_version)`. A replay that does not
   write cannot change the persisted `confirmed_at`/`rejected_at`/`submitted_at`,
   so it cannot generate a fresh logical transition timestamp and therefore
   cannot generate a fresh dedup key. Required test (`T-EVT-DEDUP-01`).
4. **Receipt-issued requires a valid canonical receipt** (§7.1). No receipt
   event for a pending/rejected/missing-receipt state.
5. **Payload must not expose** another supplier's identity, credentials, JWTs,
   raw table rows, internal user ids beyond the actor, or `tenant_user_id`.
6. **No provider-specific delivery logic** in I2C-D — no phone number lookup,
   no email, no SMS gateway, no WhatsApp template, no webhook POST.
7. **No message templates, webhooks, queues, outbox table, or migration** in
   this design task. A future transactional outbox is explicitly flagged as a
   **separately gated prerequisite** (decision D6) — it is NOT part of I2C-D
   and NOT part of I2C implementation.
8. **I2C implementation remains print-only.** Event **emission** (actually
   writing/transmitting these events) is **out of scope** for I2C
   implementation and waits for the separately gated transactional-outbox
   workstream. I2C delivers only the four **printable records** (Contracts
   A–D). These event contracts are shape-only so the future outbox layer can be
   built against a stable, deterministic schema.
9. **Printing does not emit a financial event.** A print request (Contracts
   A–D) emits nothing (§3.1, §7.6).

### 9.5 Audit and retention boundary
- Events are audit records. Their retention boundary is the same as the
  underlying financial records (they describe financial state changes). The
  contract does not define a deletion path for emitted events — they are
  append-only. A future retention policy is a separate governance concern.
- Cross-tenant event leakage is rejected: a consumer scoped to tenant A must
  never receive an event whose `tenant_id` != A. Required test
  (`T-EVT-XTENANT-01`).

---

## 10. Read-Only and Isolation Rules (binding summary)

Restating §3 in the exact form required by the task, for explicit traceability:

1. **Print operations are read-only.** No mutation of `payments`, `orders`,
   `payment_declarations`, ledger, receivables, settlement, declaration,
   receipt, or `receipt_sequences`. (Test `PRINT-ZM-01`.)
2. **No payment/order/ledger/receivable/settlement/declaration/receipt mutation
   from printing.** (Same test.)
3. **No client-supplied `wholesaler_id` or `retailer_id` as authority.** Both
   are context-derived (JWT + binding). (Tests `PRINT-XSUP-01`,
   `PRINT-XRET-01`.)
4. **Contextual JWT + active binding + tenant schema remain authoritative.**
   (Enforced by existing `resolve_client_identity`, `RequirePermission`,
   JWT-derived `search_path`.)
5. **Supplier A cannot print supplier B's data.** (`wholesaler_id = token.
   tenant_id` + `search_path`.) (Test `PRINT-XSUP-01`.)
6. **Retailer A cannot print another retailer's records.** (`retailer_id` from
   binding.) (Test `PRINT-XRET-01`.)
7. **Generic wholesaler/platform routes remain unavailable to retailer
   tokens**, and vice versa. (Route guards + `RequirePermission`.)
8. **No SQL, schema name, internal exception, or unrelated supplier identity
   leaks.** (Redaction rules §3.6; tests `PRINT-LEAK-01`, `PRINT-INJ-01`.)
9. **R2 — No false receipt association.** A ledger movement and a payment
   receipt are never correlated by amount, timestamp, or `order_id` alone. No
   `method`/`receipt_number` is attached to a movement unless a real persisted
   key proves the association — and none exists today (`post_payment_received`
   writes `reference_id=order_id` only). The statement renders two independent
   lists (`movements[]`, `settled_payments[]`). (Test
   `T-STMT-NOCROSSASSOC-01`.)
10. **R2 — Historical retention.** Soft-deleting an order never removes its
    immutable ledger movements from the statement; accounting scope does not
    filter `orders.is_deleted`. An unresolvable (orphan) ledger reference
    fails closed (409 `STATEMENT_LEDGER_SCOPE_INCOMPLETE`), never silently
    omitted. (Tests `T-STMT-SOFTDELETE-RETAIN-01`,
    `T-STMT-ACTIVE-DELETED-EQUAL-01`, `T-STMT-ORPHAN-01`.)

---

## 11. MVP Boundary (explicit non-expansions)

I2C **does not**:
- implement SMS, WhatsApp, email, or any external-provider delivery (D7, D8);
- generalize wholesalers/retailers into a Party graph or Commerce Relationship
  Kernel (D9);
- implement upstream-supplier or downstream-consumer layers;
- create cross-supplier comparison or shared accounting;
- add PDF generation infrastructure (D1 — browser print only);
- add a migration, an outbox table, or a queue (D6 — future gated
  prerequisite);
- add new permissions (D5 — reuse existing read permissions for print);
- add new financial write paths — all print/statement data is read from the
  existing authoritative backbone.

The post-MVP Commerce Relationship Kernel remains **strategic memory only**.
Current implementation planning stops at **printable records + event
contracts** for the accepted wholesaler-to-retailer MVP.

---

## 12. Quality and Self-Review (executed before commit)

- `git diff --check` — clean (no whitespace errors).
- Scoped `detect-secrets` — 0 secrets in the three deliverables.
- Mojibake scan — clean (no replacement characters / encoding artefacts).
- **Exactly three documentation files changed** (this report, the CSV matrix,
  the decision register). No product code, no frontend, no tests, no migration,
  no config.
- No implementation claim, no invented runtime evidence.
- Report / CSV / decision register are **mutually consistent** (cross-checked
  finding IDs and test IDs; accounting gap zero — see CSV §accounting).
- GitNexus: `context` queries confirmed all cited symbols;
  `analyze`/`detect_changes` run after commit on the current worktree.

---

## 13. Verdict

**PASS_FOR_CTO_DC12R1_S3_S2B_I2C_IMPLEMENTATION_PLANNING_R2**

- Base proof gate PASS (exact base, I2B ancestor, clean isolated worktree).
- Source truth audit complete; every cited `file:line` verified.
- Four printable-document contracts defined with all 13 decision points each.
- **R1:** Contract D balance trajectory sourced from the immutable receivable
  ledger (`ledger_entries`), not from `payments`/`binding.outstanding_balance`;
  fail-closed reconciliation; deterministic dedup; fixed-EAT timezone; exact
  permissions.
- **R2:** Contract D historical scope ignores `orders.is_deleted`;
  `movements[]` (ledger) and `settled_payments[]` (canonical payments) are two
  independent lists with no amount/timestamp/order-only correlation (no
  persisted ledger↔payment key exists); one customer-facing ledger-derived
  balance (binding cache is internal-only, never on the document); orphan
  ledger reference fail-closed 409 `STATEMENT_LEDGER_SCOPE_INCOMPLETE`.
- Four notification-event contracts defined with versioned envelope, redacted
  payloads, committed-state semantics, and **deterministic dedup** on persisted
  transition columns.
- Read-only, dual-key, binding-liveness, redaction, and cross-tenant rules
  binding.
- Capability/test matrix (CSV) maps every finding to status, evidence, proposed
  contract, implementation slice, and required test IDs — accounting gap zero.
- Decision register records all binding decisions including the explicit
  non-expansions.
- No unresolved decision could produce a false receipt, false receipt
  association, duplicate-payment ambiguity, incorrect balance, historical
  deletion, orphan-ledger omission, cross-tenant leak, unstable dedup,
  unsupported timezone claim, ambiguous permission, or pre-commit notification.

No merge, no protected-branch push, no I2C implementation started. Awaiting CTO
directive to proceed to I2C implementation against this contract.
