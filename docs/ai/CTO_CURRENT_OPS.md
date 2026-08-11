# CTO Current Ops

**Last updated:** 2026-08-11
**Owner:** Codex acting as CTO
**Canonical product branch:** `origin/product-dev-recovered`
**Accepted product code merge:** `adcc7f281c661897ad050a8278686375b611edb5`
**Current migration head:** `037_payment_declarations_schema`
**Delivery state:** Pre-pilot MVP hardening; not approved for customer delivery

This is the short operating picture for Mpango agents. Read
`docs/ai/PROJECT.md` for the full status and roadmap. Detailed evidence belongs
in `ai-ledger/`.

## Current Truth

- `origin/product-dev-recovered@adcc7f28` includes accepted I2B and read-only
  backend/browser-printable Contracts A-D.
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
- I2C-I2B Contract D is merged at `adcc7f28`: retailer and supplier
  relationship statements use immutable receivable ledger movements, keep
  movement/payment lists independent, and remain read-only.

## Latest Accepted Evidence

I2C-I2B Contract D controlled merge and independent verification:

`origin/product-dev-recovered` includes `adcc7f28`

- Approved source: `133ca46b`; merge tree equals the reviewed source tree.
- Kilo final source/test-authenticity review: `a56078c6`.
- Lubuntu independent runtime report: `b652b683`.
- Two independent full-backend runs each reported `3285 passed`, `48 skipped`,
  `15 xfailed`, zero failures, and zero errors.
- Full frontend suite: `270 passed`; production build succeeded.
- Post-merge compile, generator/CSV, frontend, build, pre-commit,
  detect-secrets, diff, and GitNexus gates passed.

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

- Final responsive/brand retailer workspace polish remains.
- Transactional outbox/event emission and SMS/WhatsApp delivery are deferred
  outside the current MVP and remain unimplemented.
- Real-mailbox and real-browser end-to-end proof on the latest deployed SHA
  remains.
- Non-mainland customer HTTPS hosting, formal DB-OPS, platform operator runtime,
  tenant branding, and user manuals remain.

## Active Phase

**Active product gate:**
`DC-12R1-S3-S3-D Responsive Branded Workspace Planning`

I2B and printable Contracts A-D are merged and independently verified. S3-S3-D
must audit the existing retailer workspace and produce a bounded implementation
plan. It must not duplicate existing print or finance paths, change financial
semantics, or introduce an external messaging provider.

Required planning boundary:

1. Inventory and reuse the existing retailer shell, guards, navigation,
   catalog, order, finance, declaration, and Contracts A-D print views.
2. Define desktop, tablet, and mobile behavior without introducing a parallel
   retailer application or duplicating routes.
3. Use only existing authoritative relationship context; tenant-configurable
   branding remains outside this slice unless separately approved.
4. Preserve string-safe financial rendering and server-authoritative values;
   no client-side financial recomputation is allowed.
5. Cover navigation, empty/error/loading states, logout recovery, keyboard
   access, focus management, labels, and responsive tests.
6. Keep supplier and retailer route ownership isolated and fail closed.
7. This design task is documentation/audit only: no product implementation,
   migration, permission, dependency, provider, deployment, or financial write.

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
5. **S3-S2B-I2C-I2B (completed):** read-only backend and browser-print Contract D
   relationship statement using immutable-ledger arithmetic and two independent
   movement/payment lists.
6. **S3-S3-D (active):** audit and plan the responsive branded retailer
   workspace closure without changing product code.
7. **S3-S2B-I2C-I3 (deferred post-MVP):** transactional outbox, event emission,
   and provider delivery require separate CTO authorization.
8. **S4 (pending):** run fresh-database, HTTPS, real-mailbox, real-browser end-to-end gate.
9. **DB-OPS:** access, backups, restore, monitoring, retention, and incident
   package.
10. **Tenant branding and manuals:** legal profile, logo, dual branding, and
   current user/operator documentation.

## Agent Assignment

- **Primary planning agent (Zcode):** audit and plan S3-S3-D in a clean
  worktree from `origin/product-dev-recovered@adcc7f28`.
- **Independent reviewer:** Kilo performs adversarial UX/source and
  test-authenticity review after the S3-S3-D plan is frozen.
- **Codex CTO:** own scope, financial blast radius, and merge decision.
- **Lubuntu Codex:** independently validate runtime only after a separately
  approved S3-S3 implementation candidate is frozen.
- **OPS:** handle deployment/runtime work only after product merge approval.
- **Human owner:** approve production, credentials, domains, and business/legal
  decisions.

## Stop Conditions

Stop and report to the CTO if:

- fetched `origin/product-dev-recovered` does not equal or descend from accepted
  Contract D merge `adcc7f281c661897ad050a8278686375b611edb5`;
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
- S3-S3-D edits product code instead of remaining a design/audit gate;
- the task changes deployment or protected refs;
- evidence relies on skip, xfail, deselection, or assertion weakening.

## Update Protocol

Update this file after every meaningful merge, blocker, deployment, or phase
transition. Keep it current and concise. Move durable strategy to
`PROJECT_MEMORY.md`, full status to `PROJECT.md`, and detailed evidence to
`ai-ledger/`.
