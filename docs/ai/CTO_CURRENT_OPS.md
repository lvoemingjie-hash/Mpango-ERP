# CTO Current Ops

**Last updated:** 2026-08-02
**Owner:** Codex acting as CTO
**Canonical product branch:** `origin/product-dev-recovered`
**Accepted product merge:** `45899145e07c1c21424f2f32904965b49b689e1f`
**Current migration head:** `037_payment_declarations_schema`
**Delivery state:** Pre-pilot MVP hardening; not approved for customer delivery

This is the short operating picture for Mpango agents. Read
`docs/ai/PROJECT.md` for the full status and roadmap. Detailed evidence belongs
in `ai-ledger/`.

## Current Truth

- `origin/product-dev-recovered@45899145` is the active product baseline.
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
- I2A canonical payment transaction service extraction is validated and
  awaiting CTO merge decision.

## Latest Accepted Evidence

H4 post-merge forensics and repair:

`origin/product-dev-recovered@45899145`

- Backend Run A: `3116 passed`, `48 skipped`, `15 xfailed`, zero red, zero errors.
- Backend Run B: `3116 passed`, `48 skipped`, `15 xfailed`, zero red, zero errors.
- Alembic sole head: `037_payment_declarations_schema`.
- H4-R1 regression suite (`test_dc12r1_h4_event_loop_pool_isolation.py`): `7 passed`.
- S1-R5 migration preflight: `41 passed`.
- I1 real-Alembic upgrade: `29 passed`.
- All prior S3-S2 validation evidence remains valid.

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

- Canonical payment transaction service extraction is not yet complete.
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
`DC-12R1-S3-S2B-I2A Canonical Payment Transaction Service Extraction`

The design gate and schema foundation are complete. I2A extracts the canonical
payment transaction core without changing direct-payment behavior or exposing
declaration routes.

The I2A candidate has been reconciled against baseline `45899145` and passed
exact full-suite validation on two independent fresh stacks: `3127 passed`,
`48 skipped`, `15 xfailed`, zero red. Awaiting CTO merge decision.

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

1. **S3-S2B-I2A (active):** extract `CanonicalPaymentService` from `pay_order`
   with behavior-preserving parity and independent financial validation.
2. **S3-S2B-I2B/I2C (pending):** declaration confirmation workflow, receipt,
   retailer declaration visibility, and maker-checker runtime closure.
3. **S3-S3 (pending):** complete responsive branded retailer workspace and print UX.
4. **S4 (pending):** run fresh-database, HTTPS, real-mailbox, real-browser end-to-end gate.
5. **DB-OPS:** access, backups, restore, monitoring, retention, and incident
   package.
6. **Tenant branding and manuals:** legal profile, logo, dual branding, and
   current user/operator documentation.

## Agent Assignment

- **Zcode:** execute the bounded S3-S2B-D docs-only design gate.
- **Codex CTO:** review the contract, financial blast radius, and merge decision.
- **Lubuntu Codex:** independently validate later implementation on fresh
  PostgreSQL 16 and Redis 7.
- **OPS:** handle deployment/runtime work only after product merge approval.
- **Human owner:** approve production, credentials, domains, and business/legal
  decisions.

## Stop Conditions

Stop and report to the CTO if:

- fetched `origin/product-dev-recovered` is not
  `45899145e07c1c21424f2f32904965b49b689e1f`;
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
