# CTO Current Ops

**Last updated:** 2026-08-10
**Owner:** Codex acting as CTO
**Canonical product branch:** `origin/product-dev-recovered`
**Accepted product code merge:** `0dc245114ec7442ebb1dea16e9332d95ddb3a6fe`
**Current migration head:** `037_payment_declarations_schema`
**Delivery state:** Pre-pilot MVP hardening; not approved for customer delivery

This is the short operating picture for Mpango agents. Read
`docs/ai/PROJECT.md` for the full status and roadmap. Detailed evidence belongs
in `ai-ledger/`.

## Current Truth

- `origin/product-dev-recovered` includes accepted I2B, I2C-I1, and I2C-I2
  merges at `0dc24511`.
- `origin/main@134ea59e` and `origin/platform-dev@12c5ee55` remain unchanged.
- All controlled work begins from a fetched, clean, isolated worktree.
- The wholesaler is the primary customer and value owner.
- Retailers operate inside one selected supplier relationship at a time.
- Mpango is not a cross-supplier price-comparison marketplace.
- Retailer finance reads are relationship-scoped. Retailers may submit
  non-authoritative declarations, but only supplier cashier confirmation can
  invoke the canonical financial write path.
- Merged code is not considered deployed without exact-SHA runtime proof.

## What Is Closed

- Tenant isolation and contextual JWT-derived supplier scope.
- Wholesaler credential setup/reset and terminal-token boundaries.
- Retailer identity, invitation, verified email, credentials, mapping, and
  `retailer_operator` foundation through migration `036`.
- Supplier-scoped retailer login with no `available_tenants`.
- Structured HTTP error and rate-limit 429 boundaries.
- Retailer catalog/order ownership hardening and exact client route contracts.
- Read-only retailer payment history:
  `GET /api/v1/client/payments`.
- Server-authoritative relationship balance:
  `GET /api/v1/client/finance/balance`.
- Retailer payment and finance reads use both authoritative supplier and
  retailer identities.
- No retailer route currently settles payments, writes ledger entries, or
  changes receivables.
- I1 financial schema foundation is merged at `9528cb6d`.
- H4 post-merge test-contract forensics closed at `45899145`: event-loop pool
  isolation regression suite added, migration-preflight contract pinned to
  `036`, evidence ledger corrected.
- I2A canonical payment transaction service extraction is merged at
  `b03a3b5c`, including the fail-closed positive finite amount boundary.
- I2B payment declaration and cashier confirmation runtime is merged at
  `753048f0`, including idempotent declaration submission, confirmation/
  rejection, atomic canonical payment, receipt allocation, and relationship-
  scoped status visibility.
- I2C-I1 Contracts A-C are merged at `e923fd85`: six read-only order,
  declaration, and receipt print-data routes. Receipt eligibility is
  fail-closed; no print request mutates financial state.
- I2C-I2 browser-printable Contracts A-C are merged at `0dc24511`: retailer
  and supplier order, declaration, and eligible receipt views are available;
  money display is string-safe and print actions remain read-only.

## Latest Accepted Evidence

I2C-I2 controlled merge and independent verification:

`origin/product-dev-recovered` includes `0dc24511`

- Approved source: `10c9158d`; merge tree equals the reviewed source tree.
- Kilo final source/test-authenticity closure: `d1e5f518`.
- Lubuntu independent runtime report: `12460e0c`.
- Focused printable-workspace suite: `63 passed` across repeated runs.
- Full frontend suite: `223 passed`; production build succeeded.
- Eight adversarial mutations went RED and were restored byte-identically.
- Post-merge scoped pre-commit, detect-secrets, diff, mojibake, build, and
  GitNexus gates passed.

I2C-I1 controlled merge and independent verification:

`origin/product-dev-recovered` includes `e923fd85`

- Approved implementation tree: `4c322c2a`; merge tree equals the reviewed
  source tree.
- Lubuntu full-clone backend Run A: `3216 passed`, `48 skipped`, `15 xfailed`,
  zero failures and zero errors.
- Lubuntu full-clone backend Run B: identical totals.
- I2C-I1 printable-record suite: `36 passed`; reversed focused order:
  `44 passed`.
- The validation environment used disposable PostgreSQL 16 and Redis 7. It is
  runtime evidence for the merged source, not a customer deployment claim.

I2B-R5-R1 controlled merge:

`origin/product-dev-recovered` includes `753048f0`

- Approved source: `c65c87cb`; merge tree equals source tree.
- Independent backend Run A: `3180 passed`, `48 skipped`, `15 xfailed`, zero
  failures and zero errors.
- Independent backend Run B: identical totals.
- I2A/I2B/H5 bundle: `64 passed` in both orders.
- Post-merge lifecycle regressions: `30 passed`.
- Frontend: `160 passed`; production build succeeded.
- Alembic sole head: `037_payment_declarations_schema`.
- Lubuntu independent runtime report: `34220d0f`.
- OpenCode independent source review: five INFO findings, zero blockers,
  accounting gap zero, report `df25e67b`.

Earlier accepted evidence:

S3-S2 source candidate:

`kilo/dc12r1-s3-s2-read-only-retailer-finance-2026-07-30@b56ae841`

Source validation:

- Backend Run A: `3030 passed`, `48 skipped`, `15 xfailed`, zero red.
- Backend Run B: `3030 passed`, `48 skipped`, `15 xfailed`, zero red.
- Frontend: 16 files and 148 tests passed; production build passed.

Controlled merge:

`0f9d259b4a6c20584721c53b59ba94c510d1970d`

S2B-I1 source candidate:

`codex/dc12r1-s3-s2b-i1-financial-schema-foundation-2026-08-01@9528cb6d`

Controlled merge:

`9528cb6de5f668ed09feb7a1eaa9aafaa537987d`

Post-merge validation:

- Fresh PostgreSQL 16 and Redis 7.
- Alembic sole head `036_retailer_mvp_identity`.
- S3-S1/S3-S2 backend bundle: `50 passed`.
- Focused frontend bundle: `6 passed`.
- Production frontend build, scoped pre-commit, and secret detection passed.

## What Is Not Closed

- Contract D relationship statements are not implemented.
- Future notification-event contracts are not closed; SMS/WhatsApp delivery is
  not implemented.
- Final responsive/brand retailer workspace polish remains.
- Real-mailbox and real-browser end-to-end proof on the latest deployed SHA
  remains.
- Non-mainland customer HTTPS hosting, formal DB-OPS, platform operator runtime,
  tenant branding, and user manuals remain.

## Active Phase

**Active product gate:**
`DC-12R1-S3-S2B-I2C-I2B Contract D Relationship Statement`

I2B, I2C-I1, and I2C-I2 are merged and independently verified. I2C-I2B now
closes the read-only printable relationship statement using the accepted
Contract D ledger boundary. It must not change financial semantics or integrate
an external messaging provider.

Required business boundary:

1. Statement authority must be derived from contextual supplier and retailer
   identity; request-supplied relationship authority is forbidden.
2. The one customer-facing opening and closing balance must be computed from
   immutable receivable `ledger_entries` over an inclusive date range.
3. `movements[]` and `settled_payments[]` are independent lists. Never infer a
   receipt-to-ledger relationship from amount, time, or order id.
4. Soft-deleted orders remain in historical accounting scope. An orphan ledger
   reference fails closed with `STATEMENT_LEDGER_SCOPE_INCOMPLETE`.
5. Internal arithmetic inconsistency or required credit-only reconciliation
   failure returns a controlled 409 and no partial document.
6. Pending declarations never enter balance or settled-payment totals.
7. Retailer access uses `client:finance:read`; supplier access uses
   `finance:read`; cross-relationship access is neutral and fail-closed.
8. The browser renders server decimal strings without `Number`, `parseFloat`,
   rounding, or financial recomputation.
9. Statement reads and printing are zero-write operations.
10. No migration, permission, event/outbox, SMS/WhatsApp, provider credential,
    PDF dependency, financial mutation, or deployment change is allowed.

## Ordered Delivery Plan

1. **S3-S2B-I2A (completed):** reusable canonical payment mutation service,
   behavior-preserving parity, amount-integrity guard, and independent review.
2. **S3-S2B-I2B (completed):** declaration submission, cashier confirmation/
   rejection, atomic canonical payment, receipt allocation, and relationship-
   scoped status visibility.
3. **S3-S2B-I2C-I1 (completed):** read-only backend Contracts A-C for order,
   declaration, and receipt print data.
4. **S3-S2B-I2C-I2 (completed):** browser-printable frontend for Contracts A-C;
   no Contract D, events, outbox, provider delivery, or financial writes.
5. **S3-S2B-I2C-I2B (active):** read-only backend and browser-print Contract D
   relationship statement using immutable-ledger arithmetic and two independent
   movement/payment lists.
6. **S3-S2B-I2C-I3 (pending):** separately gated committed-state event/outbox
   design and implementation, without SMS/WhatsApp delivery unless approved.
7. **S3-S3 (pending):** complete responsive branded retailer workspace.
8. **S4 (pending):** run fresh-database, HTTPS, real-mailbox, real-browser end-to-end gate.
9. **DB-OPS:** access, backups, restore, monitoring, retention, and incident
   package.
10. **Tenant branding and manuals:** legal profile, logo, dual branding, and
   current user/operator documentation.

## Agent Assignment

- **Primary coding agent (Zcode):** implement I2C-I2B in a clean worktree from
  `origin/product-dev-recovered@0dc24511`.
- **Independent reviewer:** Kilo performs adversarial financial/source and
  test-authenticity review after the I2C-I2B candidate is frozen.
- **Codex CTO:** own scope, financial blast radius, and merge decision.
- **Lubuntu Codex:** independently validate implementation on fresh
  PostgreSQL 16 and Redis 7.
- **OPS:** handle deployment/runtime work only after product merge approval.
- **Human owner:** approve production, credentials, domains, and business/legal
  decisions.

## Stop Conditions

Stop and report to the CTO if:

- fetched `origin/product-dev-recovered` does not equal or descend from accepted
  I2C-I2 merge `0dc245114ec7442ebb1dea16e9332d95ddb3a6fe`;
- statement data is accepted from client-calculated financial fields;
- supplier or retailer authority comes from request-supplied IDs;
- ledger movements and settled payments are correlated without a persisted key;
- a soft-deleted order loses historical movements, an orphan ledger reference
  is silently omitted, or inconsistent arithmetic renders a document;
- printing or event generation can mutate a payment, ledger, order, receivable,
  settlement, declaration, or receipt;
- an event may be emitted before the related transaction is committed;
- the slice adds external SMS/WhatsApp delivery, provider credentials, an
  event/outbox, a new migration, permission, dependency, or financial write;
- the task changes deployment or protected refs;
- evidence relies on skip, xfail, deselection, or assertion weakening.

## Update Protocol

Update this file after every meaningful merge, blocker, deployment, or phase
transition. Keep it current and concise. Move durable strategy to
`PROJECT_MEMORY.md`, full status to `PROJECT.md`, and detailed evidence to
`ai-ledger/`.
