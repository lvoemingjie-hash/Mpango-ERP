# CTO Current Ops

**Last updated:** 2026-08-09
**Owner:** Codex acting as CTO
**Canonical product branch:** `origin/product-dev-recovered`
**Accepted product code merge:** `e923fd8567637ecc87b40d775caa8860b10821a0`
**Current migration head:** `037_payment_declarations_schema`
**Delivery state:** Pre-pilot MVP hardening; not approved for customer delivery

This is the short operating picture for Mpango agents. Read
`docs/ai/PROJECT.md` for the full status and roadmap. Detailed evidence belongs
in `ai-ledger/`.

## Current Truth

- `origin/product-dev-recovered` includes accepted I2B and I2C-I1 merges at
  `e923fd85`.
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

## Latest Accepted Evidence

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

- I2C-I2 browser-printable workspace is not closed. It must consume the
  existing read-only Contracts A-C without recomputing or mutating finance.
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
`DC-12R1-S3-S2B-I2C-I2 Retailer Printable Workspace`

I2B and I2C-I1 are merged and independently verified. I2C-I2 now adds only the
browser-printable frontend for the existing authoritative order, declaration,
and receipt data contracts. It must not change financial semantics or integrate
an external messaging provider.

Required business boundary:

1. Print data must be server-authoritative and scoped by supplier plus retailer.
2. An order printout must preserve authoritative item, price, total, and status.
3. An unconfirmed declaration must be labelled pending, never paid or received.
4. Only a confirmed canonical payment with a valid allocated receipt may
   produce a receipt document.
5. A rejected declaration must show controlled status and reason without
   exposing internal errors or unrelated supplier data.
6. I2C-I2 must not implement Contract D relationship statements or frontend
   financial recomputation.
7. Print actions must be read-only and must not mutate financial state.
8. Future notification events must be emitted only from committed state and
   must define idempotency, replay, tenant scope, redaction, and audit rules.
9. I2C must not deliver SMS/WhatsApp or add provider credentials/configuration.
10. No new migration or payment mutation is allowed without a separate CTO gate.

## Ordered Delivery Plan

1. **S3-S2B-I2A (completed):** reusable canonical payment mutation service,
   behavior-preserving parity, amount-integrity guard, and independent review.
2. **S3-S2B-I2B (completed):** declaration submission, cashier confirmation/
   rejection, atomic canonical payment, receipt allocation, and relationship-
   scoped status visibility.
3. **S3-S2B-I2C-I1 (completed):** read-only backend Contracts A-C for order,
   declaration, and receipt print data.
4. **S3-S2B-I2C-I2 (active):** browser-printable frontend for Contracts A-C;
   no Contract D, events, outbox, provider delivery, or financial writes.
5. **S3-S2B-I2C-I3 (pending):** separately gated committed-state event/outbox
   design and implementation, without SMS/WhatsApp delivery unless approved.
6. **S3-S3 (pending):** complete responsive branded retailer workspace.
7. **S4 (pending):** run fresh-database, HTTPS, real-mailbox, real-browser end-to-end gate.
8. **DB-OPS:** access, backups, restore, monitoring, retention, and incident
   package.
9. **Tenant branding and manuals:** legal profile, logo, dual branding, and
   current user/operator documentation.

## Agent Assignment

- **Primary coding agent (Zcode):** implement I2C-I2 in a clean worktree from
  this merged baseline, limited to frontend consumption of Contracts A-C.
- **Independent reviewer:** perform adversarial source review after the I2C-I2
  candidate is frozen.
- **Codex CTO:** own scope, financial blast radius, and merge decision.
- **Lubuntu Codex:** independently validate implementation on fresh
  PostgreSQL 16 and Redis 7.
- **OPS:** handle deployment/runtime work only after product merge approval.
- **Human owner:** approve production, credentials, domains, and business/legal
  decisions.

## Stop Conditions

Stop and report to the CTO if:

- fetched `origin/product-dev-recovered` does not descend from accepted I2C-I1
  merge `e923fd8567637ecc87b40d775caa8860b10821a0`;
- print data is accepted from client-calculated financial fields;
- supplier or retailer authority comes from request-supplied IDs;
- an unconfirmed or receipt-ineligible declaration can be labelled received or
  printed as a receipt;
- printing or event generation can mutate a payment, ledger, order, receivable,
  settlement, declaration, or receipt;
- an event may be emitted before the related transaction is committed;
- the slice adds Contract D statements, external SMS/WhatsApp delivery,
  provider credentials, a new migration, or a financial write without separate
  authorization;
- the I2C-I2 task changes backend product code, migrations, permissions, config,
  deployment, or protected refs;
- evidence relies on skip, xfail, deselection, or assertion weakening.

## Update Protocol

Update this file after every meaningful merge, blocker, deployment, or phase
transition. Keep it current and concise. Move durable strategy to
`PROJECT_MEMORY.md`, full status to `PROJECT.md`, and detailed evidence to
`ai-ledger/`.
