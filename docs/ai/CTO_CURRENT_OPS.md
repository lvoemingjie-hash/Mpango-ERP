# CTO Current Ops

**Last updated:** 2026-08-03
**Owner:** Codex acting as CTO
**Canonical product branch:** `origin/product-dev-recovered`
**Accepted product merge:** `b03a3b5c078a3824d333b541ccacf19b668c9f9c`
**Current migration head:** `037_payment_declarations_schema`
**Delivery state:** Pre-pilot MVP hardening; not approved for customer delivery

This is the short operating picture for Mpango agents. Read
`docs/ai/PROJECT.md` for the full status and roadmap. Detailed evidence belongs
in `ai-ledger/`.

## Current Truth

- `origin/product-dev-recovered` includes accepted I2A merge `b03a3b5c`.
- `origin/main@134ea59e` and `origin/platform-dev@12c5ee55` remain unchanged.
- All controlled work begins from a fetched, clean, isolated worktree.
- The wholesaler is the primary customer and value owner.
- Retailers operate inside one selected supplier relationship at a time.
- Mpango is not a cross-supplier price-comparison marketplace.
- Retailer finance is read-only at the current baseline.
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

## Latest Accepted Evidence

I2A-R3 controlled merge:

`origin/product-dev-recovered` includes `b03a3b5c`

- Approved source: `f7bd75c1`; merge tree equals source tree.
- Backend Run A: `3134 passed`, `48 skipped`, `15 xfailed`, zero red, zero errors.
- Backend Run B: identical totals.
- I2A service and amount-boundary suite: `18 passed`.
- Payment/order/receivable/ledger bundle: `101 passed`.
- H4 regression suite: `7 passed`.
- Alembic sole head: `037_payment_declarations_schema`.
- S1-R5 migration preflight: `41 passed`.
- I1 real-Alembic upgrade: `29 passed`.
- Zcode independent final review: 43 PASS, 2 INFO, 0 FAIL.

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

- Wholesaler cashier confirmation/rejection is not implemented as a dedicated
  maker-checker workflow.
- Retailer-visible confirmed receipt and rejection result are not closed.
- Print contracts for orders, declarations, receipts, and statements are not
  closed.
- Final responsive/brand retailer workspace polish remains.
- Real-mailbox and real-browser end-to-end proof on the latest deployed SHA
  remains.
- Non-mainland customer HTTPS hosting, formal DB-OPS, platform operator runtime,
  tenant branding, and user manuals remain.

## Active Phase

**Active product gate:**
`DC-12R1-S3-S2B-I2B Payment Declaration and Cashier Confirmation Runtime`

The design gate, schema foundation, and canonical payment transaction service
are complete. I2B may now implement declaration submission and maker-checker
confirmation/rejection without duplicating the financial mutation path.

Required business boundary:

1. A retailer may submit a payment declaration.
2. Submission is not a canonical payment and has zero accounting effect.
3. A wholesaler cashier may confirm or reject the declaration.
4. Confirmation may invoke only the approved canonical payment write path.
5. Confirmation must atomically preserve payment, order, ledger, and receivable
   invariants.
6. The retailer sees pending, confirmed, or rejected status in the selected
   supplier relationship.
7. Only a confirmed payment may be called received and rendered as a receipt.
8. Printable business documents must clearly show status and never imply an
   unconfirmed declaration was settled.
9. Future SMS/WhatsApp integration is event-contract-only in this phase.
10. The design must explicitly remove, retain, or replace the currently unused
    `client:payments:create` permission; it must not become active by accident.

## Ordered Delivery Plan

1. **S3-S2B-I2A (completed):** reusable canonical payment mutation service,
   behavior-preserving parity, amount-integrity guard, and independent review.
2. **S3-S2B-I2B (active):** declaration submission, cashier confirmation/
   rejection, atomic canonical payment, receipt allocation, and relationship-
   scoped status visibility.
3. **S3-S2B-I2C (pending):** printable records and future notification-event
   contracts without external messaging delivery.
4. **S3-S3 (pending):** complete responsive branded retailer workspace and print UX.
5. **S4 (pending):** run fresh-database, HTTPS, real-mailbox, real-browser end-to-end gate.
6. **DB-OPS:** access, backups, restore, monitoring, retention, and incident
   package.
7. **Tenant branding and manuals:** legal profile, logo, dual branding, and
   current user/operator documentation.

## Agent Assignment

- **Primary coding agent:** implement bounded I2B slices from the accepted
  contract in a clean worktree.
- **Zcode:** perform independent source review after implementation is frozen.
- **Codex CTO:** own scope, financial blast radius, and merge decision.
- **Lubuntu Codex:** independently validate implementation on fresh
  PostgreSQL 16 and Redis 7.
- **OPS:** handle deployment/runtime work only after product merge approval.
- **Human owner:** approve production, credentials, domains, and business/legal
  decisions.

## Stop Conditions

Stop and report to the CTO if:

- fetched `origin/product-dev-recovered` does not descend from accepted I2A
  merge `b03a3b5c078a3824d333b541ccacf19b668c9f9c`;
- the design permits a declaration to mutate a payment, ledger, order status, or
  receivable before cashier confirmation;
- the design reuses generic wholesaler routes for retailer writes;
- supplier or retailer authority comes from request-supplied IDs;
- an unconfirmed declaration can be labelled received or printed as a receipt;
- overpayment, concurrency, replay, idempotency, rejection, audit, or rollback
  semantics remain unresolved;
- the task changes product code, migrations, permissions, config, deployment,
  or protected refs;
- evidence relies on skip, xfail, deselection, or assertion weakening.

## Update Protocol

Update this file after every meaningful merge, blocker, deployment, or phase
transition. Keep it current and concise. Move durable strategy to
`PROJECT_MEMORY.md`, full status to `PROJECT.md`, and detailed evidence to
`ai-ledger/`.
