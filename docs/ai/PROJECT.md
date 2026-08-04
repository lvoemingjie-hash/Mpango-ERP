# Mpango ERP Project Status

**Last updated:** 2026-08-04
**Status owner:** CTO
**Canonical product branch:** `origin/product-dev-recovered`
**Accepted product merge:** `753048f029c4eede86fb11857677db57b865900e`
**Current database head:** `037_payment_declarations_schema`
**Delivery state:** Pre-pilot MVP hardening; not yet approved for customer delivery

This file is the continuously maintained source of truth for product status,
accepted capabilities, delivery blockers, and ordered work. Detailed execution
evidence belongs in `ai-ledger/`. Durable product philosophy belongs in
`docs/ai/PROJECT_MEMORY.md` and `decision-register/`.

## 1. Executive Summary

Mpango is beyond prototype stage. The wholesaler ERP, tenant isolation,
financial invariants, credential lifecycle, deterministic test gate, retailer
identity, supplier-scoped retailer login, catalog/order workspace, read-only
retailer finance visibility, and the payment-declaration maker-checker loop are
materially implemented.

The current product is still pre-pilot because printable business documents,
final workspace polish, the real-mailbox browser journey, customer HTTPS
deployment, the formal DB-OPS package, tenant branding, and current user
manuals are not all closed.

Current engineering truth:

- The wholesaler remains the primary customer and value owner.
- A retailer operates inside one selected wholesaler relationship at a time.
- Mpango does not expose a cross-supplier comparison workspace.
- Retailer catalog, negotiated price, orders, payments, and balances are scoped
  by the contextual JWT, active binding, and tenant schema.
- Retailer finance reads remain server-authoritative and relationship-scoped.
  A retailer may submit a non-authoritative payment declaration, but no client
  route can settle it, mutate a ledger, or alter receivables; only cashier
  confirmation may enter the canonical payment transaction.
- A merged SHA is not a deployed SHA. Runtime delivery requires exact-SHA
  deployment evidence.

## 2. Product Position

### Primary value owner

The wholesaler is the primary customer and future payer. Mpango helps a
wholesaler operate orders, inventory, payments, receivables, reporting, staff
permissions, and a private downstream retailer channel.

### Retailer role

The retailer is an invited operational participant. Retailer UX reduces order
friction and improves wholesaler throughput and retention; it must not turn
Mpango into a retailer-facing price-comparison marketplace.

A retailer may have independent relationships with multiple wholesalers, but:

- each relationship has a private catalog, negotiated price, order, payment,
  receivable, and operational context;
- one wholesaler cannot read another wholesaler's data;
- retailer login selects one supplier portal and receives one contextual JWT;
- the product does not generate a cross-supplier comparison view;
- Mpango cannot prevent a human from manually sharing information they already
  know, but it must not aggregate or disclose that information for them.

The positioning decision is recorded in
`decision-register/2026-07-23_wholesaler-private-channel-positioning.md`.

### Platform operator role

Platform operators maintain service health, tenant lifecycle, support,
backups, restores, incidents, and controlled operations. They are not ordinary
tenant users. Early pilot customers may be manually onboarded and supported;
subscription billing is outside the current MVP.

## 3. Branch and Environment Map

| Item | Current truth |
|---|---|
| Product code baseline | `origin/product-dev-recovered@753048f0` includes the accepted I2B runtime merge |
| Main | `origin/main@134ea59e`, not promoted |
| Platform historical branch | `origin/platform-dev@12c5ee55`, not the active product baseline |
| Alembic head | `037_payment_declarations_schema` |
| Windows default workspace | Dirty; read-only for controlled work |
| Controlled work | Clean isolated worktrees only |
| Tencent mainland VPS | Development, validation, or disaster-recovery role |
| Customer MVP hosting | Non-mainland HTTPS environment remains to be selected and closed |

Every runtime task must verify the deployed SHA independently. Do not infer
deployment state from a merged branch.

## 4. Capability Status

| Area | Status | Current truth |
|---|---|---|
| Tenant isolation | Strong foundation | Schema-per-tenant, validated identifiers, contextual JWTs, and binding guards |
| Wholesaler authentication | Implemented | Login, tenant selection, setup/reset, and terminal-token handling |
| Credential email links | Source complete; runtime pending | Absolute fragment links and query rejection are merged |
| Users and RBAC | Implemented | Tenant roles exist; retailer permissions are isolated as `client:*` |
| Orders | Implemented and hardened | State, financial, ownership, and cross-retailer boundaries are regression-covered |
| Payments | Financially hardened | Canonical methods, idempotency, replay, partial payment, and ledger invariants |
| Receivables | Financially hardened | Non-negative exposure and collection semantics protected by migration `035` |
| Inventory and catalog | Core capability present | Retailer catalog and order workspace are supplier-scoped |
| Reporting and exports | Implemented | Supported provisioning and sanitized worker/runtime boundaries |
| Retailer identity S1 | Merged | Invitation, setup/reset, verified email, authoritative mapping, migration `036` |
| Retailer private login S2 | Merged | One supplier portal, one contextual JWT, no `available_tenants` |
| Retailer workspace S3-S1 | Merged | Catalog/order ownership hardening and exact route/RBAC contracts |
| Retailer finance S3-S2 | Merged | Read-only payment history and server-authoritative relationship balance |
| Retailer payment declaration schema foundation | Merged | Migration `037` provides declarations, receipt sequences, and receipt numbers |
| Canonical payment transaction extraction I2A | Merged | `CanonicalPaymentService` owns the reusable mutation core; direct pay behavior is preserved and invalid amounts fail before DB access |
| Payment declaration and cashier confirmation I2B | Merged | Retailer declaration remains non-authoritative; cashier confirm/reject is supplier-scoped; confirmation uses the canonical atomic payment path and allocates a receipt |
| Printable business records | Incomplete | Payment declaration, confirmed receipt, order, and statement print contracts remain |
| Retailer workspace closure | In progress | Printable records and final responsive/brand UX remain |
| Retailer end-to-end S4 | Not closed | Real mailbox and browser journey on deployed latest SHA remains |
| Platform operator schema | Foundation merged | Migration `034` tables exist |
| Platform operator runtime | Incomplete | Dedicated login/JWT/guard/frontend lifecycle remains |
| DB operations | Partial | Evidence exists, but one approved access/backup/restore/monitoring package remains |
| Tenant branding | Not implemented | Legal profile, logo, dual branding, and controlled configuration remain |
| User manuals | Incomplete | Wholesaler, retailer, and operator guidance must match deployed behavior |
| AI-native operations | Planned | Requires trustworthy data, permissions, approvals, audit, and rollback first |

## 5. Accepted Engineering Milestones

### DC-10 and DC-11 foundation

- Export worker tenant-context restoration and sanitized errors.
- Canonical payment-method integrity.
- Finance and receivable scope protection.
- Payment replay, concurrency, idempotency, partial-payment, and ledger safety.
- Receivable collection integrity in migration `035`.
- Reporting/bootstrap test-contract repair.
- Deterministic backend gate on fresh PostgreSQL and Redis.
- Platform operator schema foundation in migration `034`.

### DC-12 customer-entry and retailer workspace

- Wholesaler-private-channel product positioning.
- Absolute fragment-based credential links and query-token rejection.
- Retailer identity, invitation, credentials, role, and mapping foundation in
  migration `036`.
- Supplier-scoped retailer login and private portal context.
- Structured public error contract and rate-limit 429 boundary.
- Catalog/order dual-key hardening and exact client route allowlist.
- Read-only retailer payment history and authoritative relationship balance.
- Non-authoritative retailer payment declarations with idempotent replay.
- Supplier-scoped cashier confirmation/rejection through the canonical payment
  transaction, including atomic receipt allocation and retailer-visible status.

### DC-12R1-H4 post-merge test-contract forensics and repair

Forensic investigation identified two latent test-contract defects masked by
event-loop state leakage from a prior session:

- H4-R1: four `asyncio.run` calls in the I1 real-Alembic upgrade test bypassed
  the session-scoped event loop and corrupted pool isolation. Replaced with
  `run_coroutine` and added a dedicated regression suite.
- H4-R2: three `run_alembic_upgrade(config, "head")` calls in the S1-R5
  migration preflight test over-upgraded past the contract pin revision `036`,
  masking rollback semantics. Replaced with `REV_036` and removed two stale
  sole-head assertions.
- H4-R2-R1: evidence-ledger correction adding CTO GitNexus cross-environment
  confirmation.

Full suite after H4 repair: `3116 passed`, `48 skipped`, `15 xfailed`,
zero red, zero errors (two identical runs on independent stacks).

## 6. Latest Validation Snapshot

I2B-R5-R1 validation ran twice on independent fresh PostgreSQL 16 and Redis 7
stacks after the final test-evidence integrity correction:

| Metric | Run A | Run B |
|---|---:|---:|
| Passed | 3180 | 3180 |
| Skipped | 48 | 48 |
| XFailed | 15 | 15 |
| Failed | 0 | 0 |
| Errors | 0 | 0 |

The final source `c65c87cb` was independently runtime-verified by Lubuntu and
independently source-reviewed by OpenCode, then merged with `--no-ff` into
`origin/product-dev-recovered` as:

`753048f029c4eede86fb11857677db57b865900e`

Alembic sole head remains `037_payment_declarations_schema`. The merge tree is
byte-identical to the reviewed source. Focused post-merge evidence includes the
I2A/I2B/H5 bundle at `64 passed` in both orders, lifecycle regressions at
`30 passed`, frontend Vitest at `160 passed`, and a successful production
frontend build. The independent source review recorded five INFO findings,
zero blocking findings, and an accounting gap of zero.

The accepted runtime now proves that declaration submission has zero financial
effect before confirmation; supplier-scoped cashier confirmation/rejection is
available; confirmation enters the existing canonical transaction atomically;
and confirmed payments receive replay-safe receipt numbers.

This proves the merged source tree. It does not prove customer deployment or a
real browser/mailbox journey.

## 7. Current Delivery Blockers

### P1 product journey blockers

1. Printable order, declaration, confirmed receipt, and account-statement
   contracts and UX are not yet closed.
2. The complete retailer workspace is not yet closed on mobile and desktop.
3. The latest SHA has not passed the full invitation/setup/reset/login/order/
   payment/finance journey through a real mailbox and browser.

### P1 operational blockers

1. The intended non-mainland customer HTTPS environment is not yet canonical.
2. DB access, backup, restore, monitoring, retention, incident response, and
   safe AI-agent actions are not one approved DB-OPS package.
3. Dedicated platform operator runtime authentication is incomplete.
4. User manuals and operator runbooks do not yet match final deployed behavior.

### Important but later

- Subscription and billing automation.
- Multi-warehouse expansion.
- Retailer staff sub-roles such as buyer, inventory clerk, and finance
  reconciler.
- Automated KYC and self-service tenant branding.
- SMS or WhatsApp transaction notification delivery.
- AI-native conversational mutations.

## 8. Ordered Work Plan

### Stage 1: Complete the retailer MVP loop

#### DC-12R1-S3-S1 - catalog and order hardening (completed)

Merged in the product history leading to `44ec07ff`. Catalog/order reads and
writes are supplier-scoped, use authoritative identities, and preserve the
retailer permission boundary.

#### DC-12R1-S3-S2 - read-only retailer finance (completed)

Merged as `0f9d259b4a6c20584721c53b59ba94c510d1970d`.

Delivered:

- read-only `GET /api/v1/client/payments`;
- read-only `GET /api/v1/client/finance/balance`;
- dual-key supplier/retailer predicates;
- server-authoritative Decimal balance;
- status-aware cash labels;
- no payment write, ledger, settlement, or receivable mutation.

#### DC-12R1-S3-S2B-D - payment declaration contract (completed)

This is a design/audit gate before implementation because it introduces a new
financial workflow.

The contract must define:

- a retailer declaration as non-authoritative evidence, not a canonical
  payment;
- cashier confirm/reject as the only transition that may invoke the canonical
  payment write path;
- exact idempotency, concurrency, overpayment, replay, and maker-checker rules;
- immutable status history and rejection reason boundaries;
- retailer-visible pending/confirmed/rejected states;
- confirmed receipt versus unconfirmed declaration terminology;
- printable order, declaration, receipt, and account-statement requirements;
- event hooks for future SMS/WhatsApp without implementing delivery;
- an explicit decision to remove, retain, or replace the currently unused
  `client:payments:create` permission;
- migration requirements, rollback/forward-fix strategy, and an
  implementation/test matrix.

The design gate is complete and approved as the contract input for implementation work.

#### DC-12R1-S3-S2B-I1 - schema foundation (completed)

Merged as `9528cb6de5f668ed09feb7a1eaa9aafaa537987d`.

Delivered:

- migration `037_payment_declarations_schema`;
- declaration, receipt-sequence, and receipt-number schema foundation;
- no frontend/runtime activation.

#### DC-12R1-S3-S2B-I2A - canonical payment transaction extraction (completed)

The existing direct pay-order financial mutation path is now extracted into a
reusable `CanonicalPaymentService` without changing current wholesaler payment
behavior. This stage prepares the declaration-confirmation transaction core
but does not expose declaration routes.

Merged as `b03a3b5c078a3824d333b541ccacf19b668c9f9c`. The final I2A-R3
source passed exact full-suite validation on two independent fresh stacks:
`3134 passed`, `48 skipped`, `15 xfailed`, zero red, zero errors (identical
totals both runs). The canonical service rejects non-positive and non-finite
amounts before any financial read or mutation.

#### DC-12R1-S3-S2B-I2B - declaration runtime and confirmation closure (completed)

Merged as `753048f029c4eede86fb11857677db57b865900e`.

Delivered:

- relationship-scoped retailer declaration submission with stable idempotency;
- zero financial effect before cashier action;
- supplier-scoped cashier confirmation/rejection;
- canonical atomic payment, order, ledger, receivable, and settlement effects;
- rollback-safe, replay-safe confirmed receipt allocation;
- retailer-visible pending, confirmed, and rejected states;
- two identical independent full backend gates at `3180 passed`, `48 skipped`,
  `15 xfailed`, zero failures, and zero errors.

#### DC-12R1-S3-S2B-I2C - print and notification-event closure (active)

Define the authoritative printable contracts for orders, unconfirmed payment
declarations, confirmed receipts, and relationship account statements. Every
document must be server-authoritative, dual-key scoped, status-explicit, and
must never label an unconfirmed declaration as received or settled.

Define durable event contracts for future SMS/WhatsApp delivery, including
event identity, tenant/relationship scope, committed-state timing, redaction,
replay, and audit semantics. Do not integrate an external messaging provider
or introduce a new financial mutation path in this slice.

#### DC-12R1-S3-S3 - workspace and print closure

Deliver responsive retailer navigation, branded relationship context, clear
financial state language, printable documents, empty/error states, logout
recovery, and focused accessibility tests.

#### DC-12R1-S4 - end-to-end delivery closure

Deliver fresh migration, real invitation and credential email, browser login,
catalog, order, declaration, cashier confirmation, retailer receipt visibility,
printing, two-wholesaler isolation, and sanitized runtime evidence.

### Stage 2: Establish human-plus-AI DB operations

- Named human and AI-agent responsibility matrix.
- Least-privilege production access and break-glass process.
- Encrypted backup policy, retention, and restore drill.
- Migration preflight, maintenance mode, and rollback decision tree.
- Database health, storage, backup-age, and error monitoring.
- Incident ledger and prohibition on direct business-data edits outside
  approved replayable artifacts.

### Stage 3: Tenant identity, branding, and onboarding UX

- Legal/business profile and controlled operator review.
- Logo validation and safe asset storage.
- Mpango plus tenant dual-brand entry experience.
- Controlled asset replacement and configuration UX.
- Current wholesaler, retailer, and operator manuals.

Manual operator review is acceptable for the first one or two pilot
wholesalers. Automated billing and automated KYC are not pilot prerequisites.

### Stage 4: Non-mainland pilot deployment

- Region selected for Kenyan latency, reliability, support, and legal fit.
- Customer domain, DNS, TLS, backups, monitoring, and alert ownership.
- Exact-SHA deployment and rollback proof.
- One or two controlled wholesaler pilots with named support contacts.

### Stage 5: AI-native operating layer

Start only after reliable operational data and action boundaries exist.
Initial capabilities should be read-only assistance, guided data entry,
anomaly summaries, and approval-required typed actions. No unrestricted SQL,
shell, payment mutation, or tenant impersonation.

## 9. Role and Ownership Model

| Role | Responsibility |
|---|---|
| CTO/Codex | Architecture, scope, risk, contracts, merge, release verdict, project truth |
| Product coding agent | Bounded implementation/design slices on isolated branches |
| Independent Lubuntu validator | Fresh DB, full-suite, cross-environment, and browser evidence |
| OPS agent | Deployment, DNS/TLS, backup/restore, monitoring, and runtime evidence |
| Human owner | Credentials, mailbox, domain, legal data, and production authorization |
| Wholesaler pilot owner | Business workflow acceptance and operational feedback |

No agent's self-reported PASS is sufficient by itself.

## 10. Non-Negotiables

- No cross-tenant or cross-supplier disclosure.
- No client-supplied wholesaler or retailer authority.
- No payment declaration represented as received or settled.
- No canonical financial mutation outside the approved atomic payment path.
- No negative receivable exposure represented as valid customer debt.
- No query-string credential tokens.
- No silent schema repair inside a read-only validation gate.
- No dirty-worktree merge or deployment.
- No hidden skip, xfail, deselection, or assertion weakening.
- No secrets, credentials, raw exceptions, or private row contents in reports.
- No protected push without explicit human approval.
- No claim that merged code is deployed without exact runtime SHA proof.

## 11. Document Maintenance

Update `docs/ai/CTO_CURRENT_OPS.md` after every meaningful active-task change.
Update this file when the product baseline, migration head, accepted feature
stage, delivery blocker, deployment role, roadmap, or product trust decision
changes.

Do not append raw transcripts. Replace stale status with current facts.
Historical command output belongs in `ai-ledger/`.
